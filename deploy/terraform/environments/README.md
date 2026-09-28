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
environment** (the design default — see `design.md` §3.6.1). This works because:

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
unchanged **by the multi-environment mechanism itself**. That statement is about
this directory's per-environment variable selection only — it is not a claim that
prod is unaffected by every change that uses it. For the prod identity change in
the current phase, see the Vuln #4 section below.

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
`creative-studio/staging` matches the proven staging stand-up
(`staging-standup-report.md`).

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

## Vuln #4: verified-identity env contract & apply ordering

**Both** environments set the same three verified-identity env vars on the Cloud
Run service (`APP_ENV`, `REQUIRE_AUTHENTICATED_USER`, `IAP_JWT_AUDIENCE`), and in
both `APP_ENV` resolves to a non-local value so the app derives `AUTH_MODE='iap'`.
They differ only in the **form of the audience**, because they differ in topology.
They remain separate applies against separate state, so each environment is rolled
independently and on its own schedule:

| Path | Audience form | Fail-closed guard | Rolled in |
| :-- | :-- | :-- | :-- |
| nonprod (`use_lb = false`), native Cloud Run | `/projects/<number>/locations/<region>/services/creative-studio` | `terraform_data.nonprod_app_env_guard` | the nonprod/staging phase |
| prod (`use_lb = true`), behind the LB | `/projects/<number>/global/backendServices/<generated_id>` | `terraform_data.prod_app_env_guard` | **this phase** — see below |

### Contract rules (both paths)

- **Atomic co-deploy (REQUIRED).** In `iap` mode the app FATALs at boot if
  `IAP_JWT_AUDIENCE` is unset, and once `REQUIRE_AUTHENTICATED_USER=true` the
  service rejects any request without a verified identity. These env vars MUST
  therefore land in the **same Cloud Run revision as the app image that reads
  them** — i.e. a single `terraform apply` where `var.initial_container_image`
  points at the merged verified-identity build, so image + env render into one
  `google_cloud_run_v2_service` spec / one revision. Never apply these env vars
  before that image exists, and never split image and env across two updates.
- **Fail-closed guard.** A `terraform_data.<path>_app_env_guard` precondition
  fails the plan/apply if `APP_ENV` resolves to a local-mode value (`""`, `dev`,
  `development`, `local`, `test`), preventing a silent fail-open (mock identity)
  misconfiguration. Each guard is count-gated to its own path, so the nonprod
  guard is inert on prod and vice versa.
- **Post-apply fail-closed smoke (owner-run, do NOT run from CI/agents).** After
  the atomic apply, confirm the service fails **closed**: (1) a request to the
  service's entry point (the Cloud Run URL on nonprod, the LB domain on prod)
  lacking a valid `X-Goog-IAP-JWT-Assertion` is rejected (not served an
  authenticated page); (2) the running revision resolves `APP_ENV` to the
  non-local value (so `AUTH_MODE='iap'`) and has a non-empty `IAP_JWT_AUDIENCE`.

### nonprod (`use_lb = false`) — native Cloud Run audience

The nonprod path sets the three env vars with `APP_ENV` resolving to the `staging`
label, and `IAP_JWT_AUDIENCE` as the native Cloud Run audience built from the
project **number**, region, and the static service name `creative-studio` (never a
hardcoded literal). The guard on this path is
`terraform_data.nonprod_app_env_guard`.

### prod (`use_lb = true`) — LB backend-service audience: **this phase changes prod**

An earlier phase of this rollout described the prod IAP audience as "a separate
two-stage change held for a later phase", and prod's rendered env map as unchanged.
**That later phase is this change.** The prod path now merges the same three
identity env vars into the prod Cloud Run service, using the LB backend-service
audience form.

**Blast radius: applying this to prod rolls a NEW prod revision.** The prod service
spec is *not* byte-for-byte unchanged. What to expect and watch:

- **In the plan:** an **in-place update** of the `google_cloud_run_v2_service`
  adding the three env vars — not a replacement — and **no** change to the LB, the
  serverless NEG or the backend service. Anything else, stop and re-check the
  tfvars and backend prefix.
- **`IAP_JWT_AUDIENCE` must render non-empty** in the plan, as
  `/projects/<number>/global/backendServices/<numeric id>`. An empty or
  partially-rendered audience means the data source below did not resolve — stop,
  do not apply.
- **At apply:** a new revision is created and traffic migrates to it. Once it
  serves, `REQUIRE_AUTHENTICATED_USER=true` is live in prod and any request the app
  cannot attach a verified IAP identity to is rejected. Verify real user access
  through the LB domain promptly after traffic shifts.
- **Rollback is forward, not in-place.** There is no undo of a revision through
  this configuration: reverting means `terraform apply` of the previous config,
  which rolls a *further* new revision. A manual Cloud Run traffic split back to
  the prior revision will be reverted by the next apply, so treat it as an
  emergency stop-gap only and reconcile the config afterwards.

#### PRECONDITION — green-field / DR: check BEFORE the prod plan

The prod audience is derived by reading the **already-existing** prod backend
service `creativestudio-backend-default` through a `google_compute_backend_service`
data source, resolved at **plan** time. This path is therefore an **in-place
rollout only**; it does not bootstrap a prod that does not yet exist.

- *What to check:* the backend service exists in the target prod project before you
  plan —
  ```bash
  gcloud compute backend-services describe creativestudio-backend-default \
    --global --project <PROD_PROJECT_ID>
  ```
  This should return the resource; its `id` is the numeric id that goes into the
  audience.
- *If it is not met* — a fresh prod project, or a disaster-recovery rebuild —
  `terraform plan` **fails with a 404 on that data source**. That is expected
  behaviour, not a bug in the configuration.
- *What to do:* do **not** work around it by hardcoding a number or id into the
  audience; a wrong audience means every request 401s, with no plan-time failure to
  warn you. Green-field bootstrap is a separate two-phase concern: stand up the LB,
  the serverless NEG and the backend service first, then re-run this apply so the
  data source resolves against the real backend service. If you hit this during a
  DR restore, raise it rather than improvising the audience.

The same limitation is recorded in an inline comment on the data source in
`cloudrun/main.tf`; this section is the operator-facing statement of it.

## Notes

- **Backend config is never stored in these tfvars files.** The state bucket and
  prefix are supplied at `init` (see `backend.tf`), keeping project-specific state
  locations out of version control.
- **No secrets live here.** The configuration currently has none; the Phase 4
  Secret Manager inputs (`secret_ids`, `secret_env`) stay empty/dormant.
- For the full end-to-end deploy story (Cloud Build image build via `build.sh`,
  DNS A record for the LB, IAP user grants), see `deploy.md`. This directory only
  adds the per-environment variable selection on top of that existing flow.
- A future layered state split / GKE fan-out (design.md §3.5, §3.6.2, Phase 8+)
  would extend the prefix to `creative-studio/<env>/<layer>`; today there is a
  single root, so the prefix is `creative-studio/<env>`.
