# GKE `IAP_JWT_AUDIENCE` + Vuln #4 identity co-deploy (two-stage)

This note documents how the GKE deploy root sets the Vuln #4 verified-identity
contract — `APP_ENV`, `REQUIRE_AUTHENTICATED_USER`, and `IAP_JWT_AUDIENCE` — for the
app-layer IAP-JWT verification, and how it avoids the app's **FATAL-on-unset** boot
path on a real deploy.

**This root is self-contained:** every knob the two-stage runbook below references
(`iap_backend_service_id`, and the `APP_ENV`/`REQUIRE_AUTHENTICATED_USER` values it
gates) exists in this GKE root, so the Stage-2 atomic co-deploy is executable end to
end from here — no separate PR is required to complete it. (This mirrors the
per-env S1+S3 wiring the Cloud Run root received in PR #1925 for native Cloud Run.)

## The audience value

The app cryptographically verifies the IAP-signed `X-Goog-IAP-JWT-Assertion` and
checks its `aud` claim against `IAP_JWT_AUDIENCE`. For the **GKE
Ingress/BackendConfig** topology the audience uses the Compute/GKE load-balancer
form (confirmed from the IAP *signed-headers-howto* doc):

```
/projects/<PROJECT_NUMBER>/global/backendServices/<NUMERIC_BACKEND_SERVICE_ID>
```

- `<PROJECT_NUMBER>` is derived from `data.google_project.project.number`
  (added to this root; the Cloud Run root already had it). **Never hardcoded.**
- `<NUMERIC_BACKEND_SERVICE_ID>` is the **server-assigned numeric id** of the
  backend service — **not** its name. The existing `var.iap_backend_service_name`
  (which feeds the IAP IAM binding) is the *name*, fine for IAM but **wrong for the
  aud**. The aud needs the numeric id of the same backend service.

## Why it is not knowable at apply

On GKE the backend service is **not** created by Terraform. The GKE Ingress/NEG
controller creates it **asynchronously, after apply**, from the
`Service` + `Ingress` + `BackendConfig`. Its numeric id therefore does not exist
at initial plan/apply time — a single-pass apply cannot know it. This mirrors how
the repo already treats the backend-service **name** as out-of-band
(`var.iap_backend_service_name`, supplied on a follow-up apply).

## The identity contract is gated as one Stage-2 unit

All three identity env vars are gated on the **same** Stage-2 condition
(`var.iap_backend_service_id != null`) and rendered together
(`local.stage2_identity_env_vars` in `main.tf`), then merged into the workload env
map (`local.gke_env_vars`):

```hcl
stage2_identity_env_vars = var.iap_backend_service_id != null ? {
  APP_ENV                    = var.environment  # non-local (default "prod") => AUTH_MODE=iap
  REQUIRE_AUTHENTICATED_USER = "true"           # fail closed on no verified identity
  IAP_JWT_AUDIENCE           = "/projects/${data.google_project.project.number}/global/backendServices/${var.iap_backend_service_id}"
} : {}

gke_env_vars = merge(local.creative_studio_env_vars, local.stage2_identity_env_vars)
```

- **Stage 1 (`iap_backend_service_id = null`):** the map is empty — **none** of
  `APP_ENV` / `REQUIRE_AUTHENTICATED_USER` / `IAP_JWT_AUDIENCE` is set. iap mode is
  **unreachable** from this root (infra bring-up only). Never a hardcoded id and
  never an empty aud placeholder.
- **Stage 2 (`iap_backend_service_id` supplied):** all three land together in one
  Deployment rollout.

**Alternative considered** for the id: a `data "google_compute_backend_service"`
lookup by name reading `.generated_id` in the second apply. Equivalent once the
backend service exists, but it adds a live read/permission dependency and returns
nothing useful on the first apply. The out-of-band input variable was chosen for
parity with `iap_backend_service_name` and to keep the offline gates clean. Either
is acceptable to the owner.

## LOW-3 plan guard

`terraform_data.gke_app_env_guard` (in `main.tf`) is active **only in Stage 2**
(`count = var.iap_backend_service_id != null ? 1 : 0`). Its `precondition` fails
the plan/apply if the resolved `APP_ENV` (= `var.environment`) is in the app's
local set `{"", dev, development, local, test}` — defense-in-depth against a mis-set
`APP_ENV` that would derive `AUTH_MODE=local` and fail **open** on a managed
platform. It is inert in Stage 1 (count 0), where iap mode is unreachable anyway.

## Owner's two-stage apply sequence

1. **Stage 1 — infra bring-up (no identity vars, app NOT in iap mode).** Apply the
   GKE root with `iap_backend_service_id = null`. This creates the cluster,
   workload, Service, Ingress and BackendConfig. The GKE Ingress/NEG controller
   then reconciles and **auto-creates the backend service** (and its numeric id),
   independent of pod health, so the id is discoverable for Stage 2.
   - The app never enters iap mode here (no `APP_ENV`). If the Stage-1 pods run the
     Vuln #4 (S2) image, the managed-platform backstop (`KUBERNETES_SERVICE_HOST`)
     makes local-mode **refuse to serve** — expected and safe (fail-safe DOWN); the
     backend service is still materialized from the Ingress spec regardless.
2. **Discover the numeric id** once the Ingress has reconciled:
   ```
   # name is what BackendConfig/Ingress produced (also what feeds iap_backend_service_name):
   gcloud compute backend-services list  --global --format='value(name)'
   gcloud compute backend-services describe <name> --global --format='value(id)'
   ```
3. **Stage 2 — atomic co-deploy (S1+S3+S2 in ONE rollout).** Set
   `iap_backend_service_id = <numeric id>`. This renders `IAP_JWT_AUDIENCE`,
   `APP_ENV` (= `var.environment`, non-local) and `REQUIRE_AUTHENTICATED_USER=true`
   into the ConfigMap **together**, and the S2 image is rolled in the **same**
   Deployment revision. The app now boots in iap mode **with a resolved audience**.
   The LOW-3 guard asserts `APP_ENV` is non-local or the apply fails.

## How the FATAL-on-unset path is never hit on a live boot

The merged app (commit `69e8af20`) enforces two boot-time checks in
`common/verified_identity.py`:

- `validate_identity_config()` — in **iap mode** (`APP_ENV` non-local), an
  unset/empty `IAP_JWT_AUDIENCE` raises `IdentityConfigError` (FATAL, refuse to
  serve).
- managed-platform backstop (`validate_serving_environment()`) — if `AUTH_MODE`
  resolves to **local** while a managed-platform marker is present
  (`KUBERNETES_SERVICE_HOST` on GKE), it also raises `IdentityConfigError` (refuse
  to serve, no easy override).

Because `APP_ENV` and `IAP_JWT_AUDIENCE` are gated on the **same** condition, the
app is placed into iap mode **only in Stage 2**, and Stage 2 always sets a resolved
`IAP_JWT_AUDIENCE` in the same revision. Every GKE boot state is fail-safe:

| Stage | `APP_ENV` | `IAP_JWT_AUDIENCE` | Image | Boot outcome |
|-------|-----------|--------------------|-------|--------------|
| 1 | unset (not rendered) | unset (not rendered) | pre-S2 | Serves (no app verification yet; perimeter IAP only — no worse than pre-fix). Backend service still auto-created. |
| 1 (if S2 image used) | unset (not rendered) | unset (not rendered) | S2 | **Refuses to serve** via the managed-platform backstop (local mode on a platform → fail-safe DOWN). Backend service still auto-created from the Ingress spec regardless of pod health. |
| 2 | non-local (iap) | **resolved** | S2 | Serves, verifying the assertion against the aud. |

There is **no reachable state** where the app boots in iap mode with an empty
audience: iap mode is only entered in Stage 2, where the aud is already resolved
and delivered in the same revision as `APP_ENV`. Because all three identity vars and
the image land in one Deployment rollout, there is no intra-deploy window either.

> This is argued from the config/sequence and the merged app checks — it was
> **not** proven by running `terraform apply` (apply is the owner's venue; only the
> offline gates were run here).

## Scope

GKE-only. Cloud Run non-prod/prod roots and the native path are untouched. No
app-code change. No `.terraform/` or lock file committed. No project
ids/numbers/SA/bucket literals.
