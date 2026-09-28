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

# Remote state backend (GCS) for the GKE deploy root.
#
# The state bucket is intentionally NOT hardcoded here so this configuration
# stays reusable across projects and no project-specific value is committed to
# version control. Supply the bucket at init time, e.g.:
#
#   terraform init -backend-config="bucket=YOUR_TF_STATE_BUCKET"
#
# IMPORTANT — the GKE root uses its OWN state, isolated from the Cloud Run root:
# the prefix carries a "/gke" layer suffix so the GKE state can never collide with
# the Cloud Run root's "creative-studio/<env>" object. GKE and Cloud Run are
# mutually-exclusive compute layers with separate blast radii; keeping their state
# separate means a `terraform destroy` of the GKE root leaves the Cloud Run
# deployment (and the data stores, which this root only READS) untouched.
#
# Select the state per environment by overriding the prefix at init and pairing it
# with a per-env variable file (non-prod first):
#
#   # non-prod (staging) — apply this FIRST, before prod (the P9c sequence)
#   terraform init -reconfigure -backend-config="bucket=..." \
#       -backend-config="prefix=creative-studio/staging/gke"
#   terraform apply -var-file=environments/nonprod.tfvars
#
#   # prod (only after non-prod passes)
#   terraform init -reconfigure -backend-config="bucket=..." \
#       -backend-config="prefix=creative-studio/prod/gke"
#   terraform apply -var-file=environments/prod.tfvars
#
# Run these from this directory (deploy/terraform/gke). The default prefix below is
# the prod environment (mirroring the Cloud Run root's committed default); override
# it with -reconfigure for non-prod.
terraform {
  backend "gcs" {
    # bucket = "YOUR_TF_STATE_BUCKET"  # provide via -backend-config
    prefix = "creative-studio/prod/gke"
  }
}
