# Multi-environment configuration (`environments/`)

This directory holds one `*.tfvars` file per deployment environment plus this
guide. It supports running the **same** root Terraform configuration against
**more than one environment** (non-prod and prod) without duplicating the config
and without Terraform workspaces.

It does **not** change how a default `terraform apply` behaves: these files are
inert unless you pass one explicitly with `-var-file`. The existing hand-written
`terraform.tfvars` flow documented in `deploy.md` still works unchanged.

## Model: separate GCP project per environment

Environment isolation is achieved by **using a separate GCP project per
environment** (the design default). This works because:

- `project_id` is already an input variable, so each environment simply targets
  a different project.
- Every project-scoped resource name (the Cloud Run service `creative-studio`,
  the Firestore database `create-studio-asset-metadata`, the Artifact Registry
  repo `creative-studio`, the runtime/build service accounts) is unique **within**
  its project and therefore cannot collide across projects.
- Both GCS buckets are derived from `project_id`
  (`creative-studio-<project_id>-assets` and
  `run-resources-<project_id>-<region>`), so even though GCS bucket names are a
  **global** namespace, two environments in two projects get distinct, non-
  colliding bucket names automatically. **No resource name is env-suffixed.**

Because names do not change between environments, moving to multi-env introduces
**no resource-address changes and no `moved {}` blocks**, and prod behavior is
unchanged.

## Per-environment workflow

Each environment has **isolated Terraform state**: a distinct backend `prefix`
(and normally a distinct state bucket, since each project has its own). Run these
from the Cloud Run root directory `deploy/terraform/cloudrun` (the tfvars files in
this directory are referenced as `../environments/<env>.tfvars`). Select an
environment at `init` time (backend prefix) and at `plan`/`apply` time (tfvars):

```bash
# Run from deploy/terraform/cloudrun (this file lives at ../environments/).
cd deploy/terraform/cloudrun

# 1. Point Terraform at this environment's state (backend is not in *.tfvars).
#    -reconfigure is REQUIRED when switching environments so Terraform adopts the
#    new backend settings instead of reusing the previously-initialized backend.
terraform init -reconfigure \
  -backend-config="bucket=<STATE_BUCKET_FOR_ENV>" \
  -backend-config="prefix=creative-studio/<env>"

# 2. Plan / apply with this environment's variable file.
terraform plan  -var-file=../environments/<env>.tfvars
terraform apply -var-file=../environments/<env>.tfvars
```

Where `<env>` is `prod` or `nonprod` (staging). Examples:

| Environment | tfvars (from `cloudrun/`) | Backend prefix | State bucket (example) |
| :-- | :-- | :-- | :-- |
| prod | `../environments/prod.tfvars` | `creative-studio/prod` | `<PROD_TF_STATE_BUCKET>` |
| non-prod | `../environments/nonprod.tfvars` | `creative-studio/staging` | `gs://<NONPROD_TF_STATE_BUCKET>` |

The `creative-studio/prod` prefix matches the value committed in `backend.tf`;
`creative-studio/staging` matches the proven staging stand-up (the worked,
validated non-prod configuration in `nonprod.tfvars`).

## The isolated-state boundary (why `-reconfigure`)

Each `(environment)` pair maps to exactly one state object:
`gs://<state-bucket>/<prefix>/default.tfstate`. That object is the blast-radius
boundary — an apply against one environment can never read or mutate another
environment's resources, because it is a different state in a different project.

Terraform caches the backend it was last initialized with in `.terraform/`. When
you switch from one environment to another you **must** re-run
`terraform init -reconfigure` with the new `-backend-config` so it does not keep
operating against the previous environment's state object. Skipping
`-reconfigure` is the classic "applied to the wrong environment" foot-gun; the
explicit prefix + `-var-file` per environment (instead of Terraform workspaces)
keeps "which environment am I about to touch" visible on every command.

## Notes

- **Backend config is never stored in these tfvars files.** The state bucket and
  prefix are supplied at `init` (see `backend.tf`), keeping project-specific state
  locations out of version control.
- **No secrets live here.** The configuration currently has none; the Phase 4
  Secret Manager inputs (`secret_ids`, `secret_env`) stay empty/dormant.
- For the full end-to-end deploy story (Cloud Build image build via `build.sh`,
  DNS A record for the LB, IAP user grants), see `deploy.md`. This directory only
  adds the per-environment variable selection on top of that existing flow.
- A future layered state split / GKE fan-out (Phase 8+)
  would extend the prefix to `creative-studio/<env>/<layer>`; today there is a
  single root, so the prefix is `creative-studio/<env>`.
