# deploy/terraform/gke/environments/nonprod.tfvars — non-production (staging)
# configuration for the GKE deploy root. NON-PROD FIRST: apply and validate this
# environment before prod.
#
# This is the GKE-specific env overlay. It is SEPARATE from the Cloud Run root's
# ../../environments/*.tfvars because the GKE root has a different compute/ingress
# variable set (it is always ingress/LB-fronted with a managed cert, so it needs a
# `domain`, and it has no `use_lb`/`cloud_run_*` inputs). The platform-agnostic
# model/location/label inputs mirror the Cloud Run env model 1:1, so the
# container's env-var contract is identical across platforms.
#
# There are NO secrets in this file (secret_env stays dormant). project_id /
# initial_user / domain below are PLACEHOLDERS; set them to your own non-prod
# project, owner, and domain before the gated apply. NEVER commit real values.
#
# Backend state for this environment (supplied at init, NOT in this file):
#   terraform init -reconfigure \
#     -backend-config="bucket=<NONPROD_TF_STATE_BUCKET>" \
#     -backend-config="prefix=creative-studio/staging/gke"
# The "/gke" suffix isolates GKE state from the Cloud Run root's
# creative-studio/staging object (separate blast radius).

# --- Deployment-specific inputs (placeholders) ---
project_id   = "REPLACE_WITH_NONPROD_PROJECT_ID"       # separate non-prod project
initial_user = "REPLACE_WITH_NONPROD_USER@example.com" # non-prod project owner (IAP access grant)
domain       = "REPLACE_WITH_NONPROD_GKE_DOMAIN"       # fronts the ingress managed certificate

# --- Behavior-defining settings for non-prod ---
region              = "us-central1"
environment         = "staging" # cost-allocation label
deletion_protection = false     # cluster-only: allow clean non-prod teardown

# IAP OAuth: provisioned OUT-OF-BAND as a Kubernetes Secret named by
# iap_oauth_secret_name (default "creative-studio-iap-oauth"). create_iap_oauth_secret
# stays false (default) so no client credentials are ever authored in Terraform.
# The Secret must already exist in the workload namespace before an apply with
# enable_iap = true.

# All other inputs inherit their repo defaults from variables.tf (models, sizing
# cpu=2000m/mem=4Gi, replicas 1..3, labels team/owner/cost_center, secret_env
# dormant, Autopilot REGULAR channel).
