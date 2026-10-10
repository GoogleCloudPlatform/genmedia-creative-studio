/**
* Copyright 2024 Google LLC
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*     http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*/

terraform {
  required_providers {
    google = {
      version = "~> 6.49"
    }
    google-beta = {
      version = "~> 6.49"
    }
  }
}
locals {
  # Applied to every resource that supports labels (via provider default_labels)
  # for cost allocation, filtering, and billing reports.
  common_labels = {
    app         = "genmedia-studio"
    environment = var.environment
    team        = var.team
    owner       = var.owner
    cost_center = var.cost_center
  }
}

provider "google" {
  project        = var.project_id
  region         = var.region
  default_labels = local.common_labels
}

provider "google-beta" {
  project        = var.project_id
  region         = var.region
  default_labels = local.common_labels
}

data "google_project" "project" {
  project_id = var.project_id
}

module "apis" {
  source     = "../modules/project-services"
  project_id = var.project_id
  sleep_time = var.sleep_time
  # Enable the Secret Manager API only when secrets are actually configured, so
  # the P4 mechanism is dormant by default (API set unchanged only when BOTH
  # secret_ids and secret_env are empty; either being non-empty enables it).
  enable_secret_manager_api = length(var.secret_ids) > 0 || length(var.secret_env) > 0
}

/********************************************
*  Network Infra Resources Section
*********************************************/

module "networking-lb" {
  count               = var.use_lb ? 1 : 0
  source              = "../modules/networking-lb"
  project_id          = var.project_id
  region              = var.region
  domain              = var.domain
  reserved_ip_address = var.reserved_ip_address
  service_name        = module.cloud-run-service.service_name
  enable_iap          = true
  initial_user        = var.initial_user

  depends_on = [module.apis]
}

/********************************************
*  Runtime Resources Section
*********************************************/

module "data" {
  source                   = "../modules/data-stores"
  project_id               = var.project_id
  region                   = var.region
  bucket_name              = local.asset_bucket_name
  cors_domains             = local.cors_domains
  enable_data_deletion     = var.enable_data_deletion
  asset_lifecycle_age_days = var.asset_lifecycle_age_days

  depends_on = [module.apis]
}

module "iam" {
  source             = "../modules/iam"
  project_id         = var.project_id
  firestore_db_id    = module.data.firestore_db_id
  assets_bucket_name = module.data.assets_bucket_name
  initial_user       = var.initial_user
  deployer_members   = var.deployer_members
}

# Secret Manager adoption (Phase 4), DORMANT by default. Creates one secret
# *container* per entry in var.secret_ids (default []) plus a per-secret
# accessor binding for the runtime SA. No secret values/versions are created by
# Terraform. With defaults (secret_ids = []) this module creates nothing.
module "secret-manager" {
  source            = "../modules/secret-manager"
  project_id        = var.project_id
  secret_ids        = var.secret_ids
  accessor_sa_email = module.iam.runtime_sa_email

  depends_on = [module.apis]
}

# Centralizing environment variables here and passing them explicitly to the
# cloud-run-service module (no module reads a global locals). Assembled from the
# data-stores + iam module outputs plus input variables.
locals {
  asset_bucket_name = "creative-studio-${var.project_id}-assets"
  creative_studio_env_vars = {
    PROJECT_ID                            = var.project_id
    LOCATION                              = var.region
    GEMINI_LOCATION                       = var.gemini_location
    GEMINI_TTS_LOCATION                   = var.gemini_tts_location
    MODEL_ID                              = var.model_id
    GEMINI_AUDIO_ANALYSIS_MODEL_ID        = var.gemini_audio_analysis_model_id
    GEMINI_CRITIQUE_MODEL_ID              = var.gemini_critique_model_id
    GEMINI_CRITIQUE_LOCATION              = var.gemini_critique_location
    CHARACTER_CONSISTENCY_GEMINI_LOCATION = var.character_consistency_gemini_location
    VEO_MODEL_ID                          = var.veo_model_id
    VEO_LOCATION                          = coalesce(var.veo_location, var.region)
    VEO_EXP_MODEL_ID                      = var.veo_exp_model_id
    LYRIA_MODEL_VERSION                   = var.lyria_model_id
    LYRIA_PROJECT_ID                      = var.project_id
    GENMEDIA_BUCKET                       = local.asset_bucket_name
    VIDEO_BUCKET                          = local.asset_bucket_name
    MEDIA_BUCKET                          = local.asset_bucket_name
    IMAGE_BUCKET                          = local.asset_bucket_name
    GCS_ASSETS_BUCKET                     = local.asset_bucket_name
    GENMEDIA_FIREBASE_DB                  = module.data.firestore_db_name
    SERVICE_ACCOUNT_EMAIL                 = module.iam.runtime_sa_email
    EDIT_IMAGES_ENABLED                   = var.edit_images_enabled
    THUMBNAIL_QUEUE_ID                    = module.data.tasks_queue_name
    API_BASE_URL                          = var.api_base_url != "" ? var.api_base_url : (var.use_lb ? "https://${var.domain}" : "")
  }

  # Vuln #4 S1 (audience) + S3 (gate-on) identity contract — NONPROD NATIVE
  # CLOUD RUN ONLY (use_lb = false). These three env vars establish verified-
  # identity enforcement for the native Cloud Run + native IAP topology:
  #   - APP_ENV: a NON-local value so the app derives AUTH_MODE='iap' (the app's
  #     local set is {"", dev, development, local, test}). We reuse the existing
  #     deployed non-prod env label (var.environment, "staging" in nonprod.tfvars)
  #     so the app env matches the deployed environment. AUTH_MODE itself is NOT
  #     operator-set — it is derived by the app from APP_ENV.
  #   - REQUIRE_AUTHENTICATED_USER: gate on "no verified identity" (fail closed).
  #   - IAP_JWT_AUDIENCE: the native Cloud Run deterministic audience, built from
  #     the project NUMBER (never a hardcoded literal), region, and the static
  #     Cloud Run service name "creative-studio". The app FATALs at boot in iap
  #     mode if this is unset, which is why this must be applied atomically with
  #     the S2 image (see deploy docs).
  # Local set that yields the app's local (mock-identity) AUTH_MODE. Kept here so
  # the LOW-3 precondition and the intent above share one source of truth.
  local_app_envs = ["", "dev", "development", "local", "test"]
  nonprod_identity_env_vars = {
    APP_ENV                    = var.environment
    REQUIRE_AUTHENTICATED_USER = "true"
    IAP_JWT_AUDIENCE           = "/projects/${data.google_project.project.number}/locations/${var.region}/services/creative-studio"
  }
  # Prod (use_lb = true) uses the load balancer; its IAP audience is the LB
  # backend-service form (a separate, two-stage change held for Phase 5), so the
  # native-Cloud-Run identity vars are merged for the nonprod path ONLY. Prod's
  # rendered env map is therefore byte-for-byte unchanged by this PR.
  cloud_run_env_vars = var.use_lb ? local.creative_studio_env_vars : merge(local.creative_studio_env_vars, local.nonprod_identity_env_vars)

  deployed_domain = var.use_lb ? ["https://${var.domain}"] : module.cloud-run-service.service_urls
  cors_domains    = concat(local.deployed_domain, var.allow_local_domain_cors_requests ? ["http://localhost:8080", "http://0.0.0.0:8080"] : [])
}

module "cloud-run-service" {
  source             = "../modules/cloud-run-service"
  project_id         = var.project_id
  region             = var.region
  image              = var.initial_container_image
  env_vars           = local.cloud_run_env_vars
  secret_env         = var.secret_env
  runtime_sa_email   = module.iam.runtime_sa_email
  runtime_sa_name    = module.iam.runtime_sa_name
  build_sa_member    = module.iam.build_sa_member
  cpu                = var.cloud_run_cpu
  memory             = var.cloud_run_memory
  timeout            = var.cloud_run_timeout
  concurrency        = var.cloud_run_max_concurrency
  max_instance_count = var.max_instance_count

  # use_lb decomposed into explicit ingress + auth fields (exact prior values).
  ingress_mode         = var.use_lb ? "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" : "INGRESS_TRAFFIC_ALL"
  default_uri_disabled = var.use_lb
  iap_enabled          = !var.use_lb
  invoker_iam_disabled = !var.use_lb
  launch_stage         = var.use_lb ? "GA" : "BETA"

  depends_on = [module.apis]
}

# Vuln #4 LOW-3: fail-closed APP_ENV misconfig guard for the DEPLOYED nonprod
# native Cloud Run path. This root is only ever run for a deployed environment
# (local/dev/test do not run this Terraform root), so on the nonprod path
# (use_lb = false) APP_ENV MUST resolve to a NON-local value — otherwise the app
# would derive AUTH_MODE='local' and serve a mock identity (fail OPEN). The
# precondition FAILS the plan/apply in that case. Prod (use_lb = true) creates
# zero instances of this resource, so prod is entirely unaffected.
resource "terraform_data" "nonprod_app_env_guard" {
  count = var.use_lb ? 0 : 1

  lifecycle {
    precondition {
      condition     = !contains(local.local_app_envs, local.nonprod_identity_env_vars.APP_ENV)
      error_message = "Vuln #4 LOW-3 misconfig: nonprod native Cloud Run (use_lb=false) resolved APP_ENV='${local.nonprod_identity_env_vars.APP_ENV}', which is in the app's LOCAL set {\"\", dev, development, local, test} and would derive AUTH_MODE='local' (mock identity, fail-open). Set var.environment to a non-local value (e.g. \"staging\") so AUTH_MODE derives to 'iap'."
    }
  }
}

/********************************************
*  Build time Resources Section
*********************************************/

module "registry" {
  source               = "../modules/artifact-registry"
  project_id           = var.project_id
  region               = var.region
  initial_user         = var.initial_user
  enable_data_deletion = var.enable_data_deletion
  build_sa_member      = module.iam.build_sa_member
  # FU-3: same deployer principal(s) as the iam module, granted AR reader on the
  # repo for list-versions / deploy-by-digest. Default [] ⇒ no binding.
  deployer_members = var.deployer_members

  depends_on = [module.apis]
}
