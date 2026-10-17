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
    # Vuln #4 INTERIM mitigation (deployed-envs only; env-config, no app code change).
    # Restrict the identity headers the app trusts to ONLY the IAP-set, priority-#1
    # header, removing the non-Goog plaintext passthrough impersonation vector
    # (X-Email, X-Authenticated-User, X-Auth-Request-Email, X-Forwarded-Email). The
    # app already honors AUTH_EMAIL_HEADERS (common/identity.py). This is a fixed
    # Google header NAME, not a secret. Retired by the Vuln #4 app fix (design
    # Phase 3), which removes the plaintext path entirely. See vuln4-design.md §5/§6.
    AUTH_EMAIL_HEADERS = "X-Goog-Authenticated-User-Email"
  }

  deployed_domain = var.use_lb ? ["https://${var.domain}"] : module.cloud-run-service.service_urls
  cors_domains    = concat(local.deployed_domain, var.allow_local_domain_cors_requests ? ["http://localhost:8080", "http://0.0.0.0:8080"] : [])
}

module "cloud-run-service" {
  source             = "../modules/cloud-run-service"
  project_id         = var.project_id
  region             = var.region
  image              = var.initial_container_image
  env_vars           = local.creative_studio_env_vars
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
