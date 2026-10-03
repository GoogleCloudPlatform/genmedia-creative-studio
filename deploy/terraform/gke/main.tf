/**
* Copyright 2025 Google LLC
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

# ---------------------------------------------------------------------------
# GKE deploy root — the GKE analogue of deploy/terraform/cloudrun.
#
# A thin composition that:
#   1. Enables the required APIs (reusing the shared project-services module with
#      enable_container_api = true — the ONLY place that flag is set; it is
#      dormant on the Cloud Run path).
#   2. READS the existing data stores + runtime SA read-only (GCS bucket, runtime
#      Google SA via data sources; Firestore DB + Cloud Tasks queue via their
#      DETERMINISTIC names — those two have no first-class provider data source,
#      verified at the offline validate gate). It creates/manages NO data-bearing
#      resource; GKE and the data layer live in separate state.
#   3. Assembles the SAME environment-variable contract the Cloud Run root builds
#      (local.creative_studio_env_vars) so the container config is identical
#      across platforms.
#   4. Creates a fresh Autopilot regional cluster (gke-cluster) and the workload
#      Deployment/Service/Ingress/BackendConfig/HPA (gke-workload).
#
# PROVIDER BOOTSTRAP ORDERING (real-world nuance — see p9-report.md P9c sequence):
# the kubernetes/kubectl providers are configured from gke-cluster outputs
# (endpoint + CA) plus a google_client_config token. On a from-scratch apply those
# outputs are unknown until the cluster exists, which is the classic
# provider-config-depends-on-resource bootstrap problem. This is resolved with a
# TWO-STAGE apply (documented in the P9c sequence): apply the cluster (and APIs)
# first with -target, then a full apply once the provider inputs are known. A
# single `terraform validate` is fully offline (no cluster needed); only the real
# apply needs the two stages.
# ---------------------------------------------------------------------------

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.49"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.49"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.31"
    }
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = "~> 1.14"
    }
  }
}

locals {
  # Applied to every resource that supports labels (via provider default_labels)
  # for cost allocation, filtering, and billing reports. Mirrors the Cloud Run
  # root's common_labels.
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

# Cluster-scoped provider auth for the kubernetes/kubectl providers, sourced from
# the gke-cluster outputs + a short-lived google_client_config token. On a
# from-scratch apply these are unknown until the cluster exists — see the
# two-stage P9c apply sequence in p9-report.md.
data "google_client_config" "default" {}

provider "kubernetes" {
  host                   = "https://${module.gke_cluster.endpoint}"
  cluster_ca_certificate = base64decode(module.gke_cluster.ca_certificate)
  token                  = data.google_client_config.default.access_token
}

provider "kubectl" {
  host                   = "https://${module.gke_cluster.endpoint}"
  cluster_ca_certificate = base64decode(module.gke_cluster.ca_certificate)
  token                  = data.google_client_config.default.access_token
  load_config_file       = false
}

# ---------------------------------------------------------------------------
# Read-only references to existing data stores + identity.
# ---------------------------------------------------------------------------

# Assets GCS bucket — REAL read-only data source (asserts the bucket exists at
# apply). Deterministic name, identical to the data-stores module + the Cloud Run
# root's local.asset_bucket_name.
data "google_storage_bucket" "assets" {
  name = local.asset_bucket_name
}

# Existing runtime Google service account (created by the shared iam module on the
# Cloud Run / platform-agnostic apply). READ-ONLY: the GKE root binds the KSA to
# it via Workload Identity but never creates or mutates it.
data "google_service_account" "runtime" {
  account_id = "service-creative-studio"
  project    = var.project_id
}

locals {
  asset_bucket_name = "creative-studio-${var.project_id}-assets"

  # Firestore DB + Cloud Tasks queue have NO first-class google-provider data
  # source (verified at the offline validate gate: the google_firestore_database
  # and google_cloud_tasks_queue DATA sources do not exist in hashicorp/google
  # ~>6.49). Per plan §4.4, the root reconstructs their DETERMINISTIC names from
  # the same convention the data-stores module hardcodes — a read-only string
  # reference, never a resource. The GKE apply therefore never creates, modifies,
  # or destroys Firestore or the queue.
  firestore_db_name = "create-studio-asset-metadata" # data-stores module literal
  tasks_queue_name  = "thumbnail-extraction"         # data-stores module literal

  # SAME env-var contract as the Cloud Run root (cloudrun/main.tf
  # local.creative_studio_env_vars), so the container config is identical across
  # platforms. Values are sourced from the read-only data sources + the
  # deterministic names above. edit_images_enabled is tostring()'d because a
  # ConfigMap's data is map(string).
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
    GENMEDIA_BUCKET                       = data.google_storage_bucket.assets.name
    VIDEO_BUCKET                          = data.google_storage_bucket.assets.name
    MEDIA_BUCKET                          = data.google_storage_bucket.assets.name
    IMAGE_BUCKET                          = data.google_storage_bucket.assets.name
    GCS_ASSETS_BUCKET                     = data.google_storage_bucket.assets.name
    GENMEDIA_FIREBASE_DB                  = local.firestore_db_name
    SERVICE_ACCOUNT_EMAIL                 = data.google_service_account.runtime.email
    EDIT_IMAGES_ENABLED                   = tostring(var.edit_images_enabled)
    THUMBNAIL_QUEUE_ID                    = local.tasks_queue_name
    # GKE is always LB/ingress-fronted (managed cert on var.domain), so the base
    # URL follows the ingress domain — parity with the Cloud Run use_lb path.
    API_BASE_URL = var.api_base_url != "" ? var.api_base_url : (var.domain != "" ? "https://${var.domain}" : "")
    # Vuln #4 INTERIM mitigation (deployed-envs only; env-config, no app code change).
    # Parity with the Cloud Run root: restrict trusted identity headers to ONLY the
    # IAP-set, priority-#1 header, removing the non-Goog plaintext passthrough
    # impersonation vector (X-Email, X-Authenticated-User, X-Auth-Request-Email,
    # X-Forwarded-Email). The app already honors AUTH_EMAIL_HEADERS
    # (common/identity.py). Fixed Google header NAME, not a secret. Retired by the
    # Vuln #4 app fix (design Phase 3). See vuln4-design.md §5/§6.
    AUTH_EMAIL_HEADERS = "X-Goog-Authenticated-User-Email"
  }
}

# ---------------------------------------------------------------------------
# APIs — shared module, with the GKE (container) API enabled. This is the ONLY
# root that sets enable_container_api = true; on the Cloud Run root the flag takes
# its false default (dormant), so the Cloud Run API set is unchanged.
# ---------------------------------------------------------------------------

module "apis" {
  source                    = "../modules/project-services"
  project_id                = var.project_id
  sleep_time                = var.sleep_time
  enable_container_api      = true
  enable_secret_manager_api = length(var.secret_env) > 0
}

# ---------------------------------------------------------------------------
# GKE cluster — fresh Autopilot regional cluster + Workload Identity.
# ---------------------------------------------------------------------------

module "gke_cluster" {
  source                = "../modules/gke-cluster"
  project_id            = var.project_id
  region                = var.region
  cluster_name          = var.cluster_name
  network               = var.network
  subnetwork            = var.subnetwork
  release_channel       = var.release_channel
  deletion_protection   = var.deletion_protection
  apis_ready_dependency = module.apis.apis_ready
}

# ---------------------------------------------------------------------------
# GKE workload — Deployment/Service/Ingress/BackendConfig/HPA + WI binding.
# Runs the same image on 8080 with requests == limits (Cloud Run parity), fronted
# by a GCE external HTTPS LB with IAP. Binds the KSA to the EXISTING runtime SA.
# ---------------------------------------------------------------------------

module "gke_workload" {
  source     = "../modules/gke-workload"
  project_id = var.project_id
  name       = var.cluster_name
  namespace  = var.namespace
  image      = var.image

  # Workload Identity: KSA annotated to the EXISTING runtime Google SA (read via
  # the data source above; never created here).
  ksa_name         = var.ksa_name
  runtime_sa_email = data.google_service_account.runtime.email
  runtime_sa_id    = data.google_service_account.runtime.name

  # Resources (requests == limits) + config/secret parity with Cloud Run.
  cpu        = var.cpu
  memory     = var.memory
  env_vars   = local.creative_studio_env_vars
  secret_env = var.secret_env

  # Autoscaling.
  replicas_min           = var.replicas_min
  replicas_max           = var.replicas_max
  cpu_target_utilization = var.cpu_target_utilization

  # Ingress / TLS.
  domain           = var.domain
  static_ip_name   = var.static_ip_name
  create_static_ip = var.create_static_ip

  # IAP (auth parity). OAuth credentials are provisioned OUT-OF-BAND by default
  # (create_iap_oauth_secret = false) — see the p9-report.md IAP OAuth contract.
  enable_iap               = var.enable_iap
  iap_oauth_secret_name    = var.iap_oauth_secret_name
  create_iap_oauth_secret  = var.create_iap_oauth_secret
  iap_oauth_client_id      = var.iap_oauth_client_id
  iap_oauth_client_secret  = var.iap_oauth_client_secret
  iap_backend_service_name = var.iap_backend_service_name
  initial_user             = var.initial_user

  depends_on = [module.gke_cluster]
}
