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

variable "project_id" {
  description = "GCP project ID in which to enable the APIs."
  type        = string
}

variable "sleep_time" {
  description = "Amount of time to wait post service API enablement to allow for eventual consistency to trickle through GCP."
  type        = number
  default     = 45
}

variable "enable_secret_manager_api" {
  description = "When true, adds secretmanager.googleapis.com to the activated APIs (P4 Secret Manager adoption). Defaults false so the mechanism is dormant: with no secrets configured the API set is unchanged and a default apply enables no additional API."
  type        = bool
  default     = false
}

variable "enable_container_api" {
  description = "When true, adds container.googleapis.com to the activated APIs (P9 GKE target). Defaults false so the mechanism is dormant: the Cloud Run root never sets it, so the Cloud Run API set is unchanged and a default apply enables no additional API. The GKE root sets it true."
  type        = bool
  default     = false
}

variable "activate_apis" {
  description = "List of GCP APIs to enable for the project. Defaults to the API set required by Creative Studio (see deploy/scripts/apis.txt; keep the two in sync)."
  type        = list(string)
  default = [
    "iap.googleapis.com",
    "compute.googleapis.com",
    "certificatemanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "containerscanning.googleapis.com",
    "storage.googleapis.com",
    "aiplatform.googleapis.com",
    "firestore.googleapis.com",
    "cloudtasks.googleapis.com",
    "serviceusage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "texttospeech.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
  ]
}
