# environments/prod.tfvars — CURRENT effective production configuration (Phase 5).
#
# Purpose: make the production config legible and reproducible. Historically prod
# has been deployed by writing a root `terraform.tfvars` by hand (see deploy.md,
# "Deploying with Custom Domain") and otherwise relying on variable defaults.
# This file captures that same effective configuration explicitly so it can be
# selected with `-var-file=environments/prod.tfvars`.
#
# Multi-environment model: DEFAULT = separate GCP project per
# environment. `project_id` is already a variable, so prod and non-prod live in
# different projects; every project-scoped resource name (Cloud Run service,
# Firestore DB, Artifact Registry repo, service accounts) and both GCS buckets
# (which are derived from `project_id`) are unique per project and cannot collide.
# Nothing here changes prod's runtime behavior — these values equal today's
# defaults / documented deploy flow; adding this file does not affect a default
# `terraform apply` (env tfvars are only used with an explicit `-var-file`).
#
# Backend state for this environment (supplied at init, NOT in this file):
#   terraform init -reconfigure \
#     -backend-config="bucket=<PROD_TF_STATE_BUCKET>" \
#     -backend-config="prefix=creative-studio/prod"
# ("creative-studio/prod" is the prefix already committed in backend.tf.)

# --- Deployment-specific inputs the operator MUST supply (no safe default) ---
# Replace the placeholders below with the real production values before applying.
project_id   = "REPLACE_WITH_PROD_PROJECT_ID"        # required (no default)
initial_user = "REPLACE_WITH_PROD_ADMIN@example.com" # effectively required: interpolated as user:${initial_user}
domain       = "REPLACE_WITH_PROD_DOMAIN"            # required when use_lb = true (managed cert + API_BASE_URL)

# Deployer principal that runs `gcloud builds submit` during a deploy. MUST be
# member-formatted (serviceAccount:...@....iam.gserviceaccount.com or user:...),
# NOT a bare email. This single list drives TWO additive bindings:
#   - roles/cloudbuild.builds.editor (project) via the iam module — submit builds.
#   - roles/artifactregistry.reader (repo) via the artifact-registry module (FU-3)
#     — run `deploy.sh list-versions` and deploy by tag/digest.
# Codifies previously-manual staging grants (IAM drift). With one principal the
# owner's next apply shows +2 to add (1 per binding; +N for N principals). Leave
# as [] to skip both bindings.
deployer_members = ["REPLACE_WITH_DEPLOYER_PRINCIPAL"]

# --- Behavior-defining settings (stated explicitly for legibility) ---
region               = "us-central1" # matches variables.tf default and deploy.md
environment          = "prod"        # cost-allocation label (variables.tf default)
use_lb               = true          # prod topology: external HTTPS LB + managed cert + IAP backend (default)
enable_data_deletion = false         # buckets keep force_destroy=false in prod (default; safe)

# All other inputs intentionally inherit their repo defaults from variables.tf
# (model IDs, model locations, cloud_run_cpu/memory/timeout/concurrency,
# max_instance_count = 10 (P3), asset_lifecycle_age_days = 90, team/owner/
# cost_center labels, secret_ids = [] and secret_env = {} — P4 dormant).
# Restating them here is unnecessary and would risk drift from the source of truth.
