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
# GKE deploy-root variables.
#
# The MODEL / LOCATION / SIZING inputs below intentionally MIRROR the Cloud Run
# root's variables (deploy/terraform/cloudrun/variables.tf) name-for-name and
# default-for-default, so the container's environment-variable config contract is
# IDENTICAL across the two compute platforms (assembled in main.tf into
# local.creative_studio_env_vars, the GKE analogue of the Cloud Run root's map).
# The GKE-specific inputs (cluster shape, ingress/TLS, IAP OAuth) follow.
# ---------------------------------------------------------------------------

variable "project_id" {
  description = "GCP project ID. The GKE root READS the existing data stores + runtime SA in this project and creates the GKE cluster + workload."
  type        = string
}

variable "region" {
  description = "Region for the regional Autopilot cluster and the deployment location label."
  type        = string
  default     = "us-central1"
}

# --- Environment-variable parity inputs (1:1 with the Cloud Run root) ---------

variable "api_base_url" {
  description = "Base URL for the application. If empty, it is inferred from the GKE ingress domain (https://<domain>)."
  type        = string
  default     = ""
}

variable "model_id" {
  description = "Primary Gemini model ID to use for text and multimodal reasoning tasks"
  type        = string
  default     = "gemini-3.5-flash"
}

variable "gemini_location" {
  description = "Endpoint used for Gemini text/multimodal calls. Gemini 3.x models are not served from single regions such as us-central1 — keep this at 'global' (or a us/eu multi-region) even when region is regional."
  type        = string
  default     = "global"
}

variable "gemini_audio_analysis_model_id" {
  description = "Gemini model ID to use for audio analysis features"
  type        = string
  default     = "gemini-3.1-flash-lite"
}

variable "veo_model_id" {
  description = "Veo model ID to use for video generation"
  type        = string
  default     = "veo-3.1-fast-generate-001"
}

variable "veo_location" {
  description = "Location for Veo model API calls. Defaults to the deployment region when unset."
  type        = string
  default     = null
}

variable "veo_exp_model_id" {
  description = "Experimental Veo model ID to use for video generation"
  type        = string
  default     = "veo-3.1-generate-001"
}

variable "lyria_model_id" {
  description = "Lyria model ID to use for audio generation"
  type        = string
  default     = "lyria-002"
}

variable "edit_images_enabled" {
  description = "Feature flag for Edit Images feature"
  type        = bool
  default     = true
}

variable "gemini_critique_model_id" {
  description = "Gemini model ID to use for Imagen critiques"
  type        = string
  default     = "gemini-3-flash-preview"
}

variable "gemini_critique_location" {
  description = "Location for the Gemini critique model"
  type        = string
  default     = "global"
}

variable "character_consistency_gemini_location" {
  description = "Location for the Gemini character consistency model"
  type        = string
  default     = "global"
}

variable "gemini_tts_location" {
  description = "Location for the Gemini TTS model"
  type        = string
  default     = "global"
}

# --- Cost-allocation labels (1:1 with the Cloud Run root) ---------------------

variable "environment" {
  description = "Deployment environment label used for cost allocation and filtering (e.g. dev, staging, prod)."
  type        = string
  default     = "prod"
}

variable "team" {
  description = "Owning team label used for cost allocation."
  type        = string
  default     = "creative-studio"
}

variable "owner" {
  description = "Owner label used for cost allocation. Must be a valid GCP label value (lowercase letters, numbers, dashes, underscores)."
  type        = string
  default     = "creative-studio"
}

variable "cost_center" {
  description = "Cost center label used for cost allocation and billing reports."
  type        = string
  default     = "creative-studio"
}

variable "sleep_time" {
  description = "Amount of time to wait post service API enablement to allow for eventual consistency to trickle through GCP."
  type        = number
  default     = 45
}

variable "initial_user" {
  description = "Email address of the initial user granted roles/iap.httpsResourceAccessor on the GKE ingress backend service (IAP access). Null skips the binding until known."
  type        = string
  nullable    = true
  default     = null
}

# --- Container image (same image contract as the Cloud Run path) --------------

variable "image" {
  description = "Container image to run on GKE (same image contract as the Cloud Run path). Defaults to a placeholder; the deploy pipeline rolls the real image and the Deployment ignores in-place changes to this field."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/placeholder"
}

# --- Secret-backed env (Phase 4 parity, DORMANT by default) -------------------

variable "secret_env" {
  description = "Map of ENV_VAR_NAME => value for secret-backed environment variables (parity with the Cloud Run secret_env). DORMANT by default ({} => no Kubernetes Secret rendered). When non-empty, values are supplied OUT-OF-BAND from Secret Manager (NEVER authored in committed Terraform); enabling any entry also flips the container.googleapis.com sibling flag's secretmanager peer on."
  type        = map(string)
  default     = {}
  sensitive   = true
}

# --- GKE cluster shape (gke-cluster module) -----------------------------------

variable "cluster_name" {
  description = "Name of the GKE Autopilot cluster."
  type        = string
  default     = "creative-studio"
}

variable "network" {
  description = "Name (or self_link) of the VPC network for the cluster. Defaults to the project's default network."
  type        = string
  default     = "default"
}

variable "subnetwork" {
  description = "Name (or self_link) of the subnetwork for the cluster. Defaults to the project's default subnet."
  type        = string
  default     = "default"
}

variable "release_channel" {
  description = "GKE release channel (RAPID, REGULAR, STABLE, or UNSPECIFIED)."
  type        = string
  default     = "REGULAR"
}

variable "deletion_protection" {
  description = "deletion_protection on the CLUSTER resource only. Default false so a non-prod cluster can be torn down cleanly. Never applied to a data-bearing resource (this root does not create any)."
  type        = bool
  default     = false
}

# --- Workload shape (gke-workload module) -------------------------------------

variable "namespace" {
  description = "Kubernetes namespace the workload runs in (assumed to already exist; the default namespace always exists)."
  type        = string
  default     = "default"
}

variable "ksa_name" {
  description = "Name of the Kubernetes ServiceAccount the pods run as, annotated to the EXISTING runtime Google service account for Workload Identity."
  type        = string
  default     = "creative-studio"
}

variable "cpu" {
  description = "CPU for the container, set as BOTH requests and limits (parity with the Cloud Run cpu limit)."
  type        = string
  default     = "2000m"
}

variable "memory" {
  description = "Memory for the container, set as BOTH requests and limits (parity with the Cloud Run memory limit)."
  type        = string
  default     = "4Gi"
}

variable "replicas_min" {
  description = "Minimum replica count for the HPA (no scale-to-zero on GKE; documented difference from Cloud Run)."
  type        = number
  default     = 1
}

variable "replicas_max" {
  description = "Maximum replica count for the HPA (kept small for the minimal/testing profile)."
  type        = number
  default     = 3
}

variable "cpu_target_utilization" {
  description = "Target average CPU utilization percentage that drives HPA scaling."
  type        = number
  default     = 60
}

# --- Ingress / TLS ------------------------------------------------------------

variable "domain" {
  description = "Domain that fronts the external HTTPS ingress (used for the ManagedCertificate and, when api_base_url is empty, the API_BASE_URL env var). Placeholder in tfvars until a real non-prod domain is provided at the gated apply."
  type        = string
  default     = ""
}

variable "static_ip_name" {
  description = "Name of the reserved global static IP for the ingress. When create_static_ip is true this root reserves it under this name; otherwise it must already exist."
  type        = string
  default     = "creative-studio-gke-ip"
}

variable "create_static_ip" {
  description = "When true, reserve the global static IP (google_compute_global_address) under static_ip_name. Set false to reference a pre-existing address."
  type        = bool
  default     = true
}

# --- IAP (auth parity with the Cloud Run IAP path) ----------------------------

variable "enable_iap" {
  description = "When true, enable IAP on the ingress backend service via BackendConfig.spec.iap (auth parity with the Cloud Run IAP path)."
  type        = bool
  default     = true
}

variable "iap_oauth_secret_name" {
  description = "Name of the Kubernetes Secret holding the IAP OAuth client credentials (keys client_id / client_secret), referenced by BackendConfig.spec.iap.oauthclientCredentials.secretName. See p9-report.md for the out-of-band provisioning contract."
  type        = string
  default     = "creative-studio-iap-oauth"
}

variable "create_iap_oauth_secret" {
  description = "When true, create the IAP OAuth Kubernetes Secret from iap_oauth_client_id / iap_oauth_client_secret. Set false (default) when the secret is provisioned OUT-OF-BAND (recommended). NEVER commit real client credentials."
  type        = bool
  default     = false
}

variable "iap_oauth_client_id" {
  description = "IAP OAuth 2.0 client ID. Supplied out-of-band; NEVER committed. Only used when create_iap_oauth_secret is true."
  type        = string
  default     = ""
  sensitive   = true
}

variable "iap_oauth_client_secret" {
  description = "IAP OAuth 2.0 client secret. Supplied out-of-band; NEVER committed. Only used when create_iap_oauth_secret is true."
  type        = string
  default     = ""
  sensitive   = true
}

variable "iap_backend_service_name" {
  description = "Name of the GCLB backend service GKE creates for the ingress, used for the roles/iap.httpsResourceAccessor binding. GKE derives this at apply from the Service/BackendConfig; supply the resolved name on a follow-up apply (or leave null to skip the IAM binding until known)."
  type        = string
  default     = null
}

variable "iap_backend_service_id" {
  description = "NUMERIC id (not the name) of the GCLB backend service GKE auto-creates for the ingress, used to compose IAP_JWT_AUDIENCE (/projects/<PROJECT_NUMBER>/global/backendServices/<NUMERIC_ID>). The GKE Ingress/NEG controller creates the backend service asynchronously AFTER the first apply, so this id does not exist at initial plan/apply — supply it OUT-OF-BAND on a SECOND apply (mirroring iap_backend_service_name), discovered via e.g. `gcloud compute backend-services describe <name> --global --format='value(id)'`. This is the STAGE-2 switch: setting it (non-null) renders the full Vuln #4 identity contract together in one revision — APP_ENV (=var.environment, non-local), REQUIRE_AUTHENTICATED_USER=true, and IAP_JWT_AUDIENCE. Leave null (default) for Stage-1 infra bring-up, where NONE of those three is set and iap mode is unreachable (fail-safe DOWN). See gke/IAP_JWT_AUDIENCE.md. Typed string (not number) intentionally: the id is interpolated into the aud string and string form avoids any large-integer precision concerns."
  type        = string
  nullable    = true
  default     = null
}
