---
title: "Deploying to GKE (Self-Service)"
---

## Deploying GenMedia Creative Studio to GKE

:::caution[Self-service / community-supported path]
The supported, documented deployment target is **Cloud Run** (see the [Deployment Guide](../deploy/)). The GKE path described here is offered for teams who want to run on GKE **now**, before first-class GKE support lands. It is **community-supported**: the Terraform exists in the repository, but the current GKE root does **not** wire the app's verified-identity settings for you (see [Current state: identity wiring is manual](#current-state-identity-wiring-is-manual-on-gke)). You must complete that step yourself.

First-class GKE support is in progress. The parked change that wires the GKE IAP audience is [PR #1926](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1926). It is not merged. This page lets you proceed without waiting for it.

We welcome you to try this path. Please share your experience, caveats, and fixes through [GitHub issues](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues) or pull requests.
:::

This page describes what is actually in the repository today, under `deploy/terraform/gke` and `deploy/terraform/modules/gke-*`. Where something has not been verified against a real deployment, the page says so explicitly.

## Architecture of the GKE path

The GKE Terraform root lives in `deploy/terraform/gke`. It is a thin composition of three modules plus read-only lookups.

### What it creates

| Component | Module / resource | Notes |
|---|---|---|
| APIs | `modules/project-services` with `enable_container_api = true` | Adds `container.googleapis.com` to the shared API set. Secret Manager is enabled only when `secret_env` is non-empty. |
| Cluster | `modules/gke-cluster` (`google_container_cluster`) | A **new regional Autopilot** cluster with Workload Identity (`<project_id>.svc.id.goog`). Defaults: name `creative-studio`, `default` network and subnetwork, `REGULAR` release channel, `deletion_protection = false`. No node pools (Autopilot manages nodes). |
| Kubernetes ServiceAccount | `kubernetes_service_account_v1` | Default name `creative-studio`, annotated `iam.gke.io/gcp-service-account` to the existing runtime Google service account. |
| Workload Identity binding | `google_service_account_iam_member` | Grants `roles/iam.workloadIdentityUser` on the runtime SA to `serviceAccount:<project_id>.svc.id.goog[<namespace>/<ksa_name>]`. No key material. |
| ConfigMap | `kubernetes_config_map_v1` `<name>-env` | Holds the plaintext environment variables. Injected into the container with `envFrom`. |
| Secret (dormant) | `kubernetes_secret_v1` | Only created when `secret_env` is non-empty. |
| Deployment | `kubernetes_deployment_v1` | One container on port `8080`, CPU/memory requests equal to limits (default `2000m` / `4Gi`). Readiness probe `GET /readyz`, liveness probe `GET /healthz`. |
| Service | `kubernetes_service_v1` (ClusterIP, port 80 → 8080) | Annotated for container-native load balancing (`cloud.google.com/neg`) and attached to the BackendConfig. |
| BackendConfig | `kubectl_manifest` (`cloud.google.com/v1`) | Turns on IAP (`spec.iap.enabled = var.enable_iap`, default `true`) using the OAuth client Secret named by `iap_oauth_secret_name`. Health check: HTTP `/readyz` on 8080. |
| ManagedCertificate | `kubectl_manifest` (`networking.gke.io/v1`) | One certificate for `var.domain`. |
| Static IP | `google_compute_global_address` | Reserved under `static_ip_name` (default `creative-studio-gke-ip`) when `create_static_ip = true` (default). |
| Ingress | `kubernetes_ingress_v1` | Class `gce` (external HTTPS load balancer). Uses the static IP and managed certificate. |
| HPA | `kubernetes_horizontal_pod_autoscaler_v2` | Scales on CPU (default target 60%) between `replicas_min` (1) and `replicas_max` (3). **No scale-to-zero.** |
| IAP access grant | `google_iap_web_backend_service_iam_member` | Grants `roles/iap.httpsResourceAccessor` to `initial_user`. **Only created when both `initial_user` and `iap_backend_service_name` are set.** |

The Deployment, Service, Ingress and HPA are all named after `cluster_name` (default `creative-studio`), and so is the container.

### What it only reads (does not create)

The GKE root **creates no data-bearing resources**. It reads these existing ones:

- The assets bucket `creative-studio-<project_id>-assets` (a `google_storage_bucket` data source, so the apply fails if the bucket is missing).
- The runtime service account `service-creative-studio@<project_id>.iam.gserviceaccount.com` (a `google_service_account` data source).
- The Firestore database `create-studio-asset-metadata` and the Cloud Tasks queue `thumbnail-extraction`. These are referenced **by name only** and are not checked at apply time.

In this repository, those resources are created by the shared `iam` and `data-stores` modules, and the **only root that calls those modules is the Cloud Run root** (`deploy/terraform/cloudrun`). In practice, that means **you must apply the Cloud Run root in the same project before applying the GKE root.** Applying the Cloud Run root also creates the Artifact Registry repository and the Cloud Build service account used to build the image.

:::note[TODO: not verified]
There is no data-only Terraform root in the repository. Applying the Cloud Run root also deploys a Cloud Run service. Whether you can safely skip or tear down the Cloud Run compute layer while keeping the shared data layer has not been verified.
:::

### Environment variables

The root builds `local.creative_studio_env_vars` in `deploy/terraform/gke/main.tf`. It carries the same model, location, bucket, Firestore and queue settings as the Cloud Run root, and it sets `API_BASE_URL` to `https://<domain>` unless `api_base_url` is set. That map becomes the ConfigMap.

**It does not include `APP_ENV`, `REQUIRE_AUTHENTICATED_USER`, or `IAP_JWT_AUDIENCE`.** See the next section.

### Terraform state

`deploy/terraform/gke/backend.tf` uses a GCS backend with **its own prefix**, separate from the Cloud Run root. The committed default is `creative-studio/prod/gke`, and `environments/nonprod.tfvars` documents `creative-studio/staging/gke`. Supply the bucket at init time:

```bash
cd deploy/terraform/gke
terraform init -reconfigure \
  -backend-config="bucket=<YOUR_TF_STATE_BUCKET>" \
  -backend-config="prefix=creative-studio/staging/gke"
```

Only `environments/nonprod.tfvars` exists under `deploy/terraform/gke/environments/`. The comments in `backend.tf` mention an `environments/prod.tfvars`, but that file is **not** in the GKE root. Create your own variable file for any other environment. Comments in the GKE Terraform also refer to a `p9-report.md`, which is **not** in the repository either.

## How identity and auth work

The app does **not** trust plaintext identity headers. Identity comes only from the signed IAP assertion header `X-Goog-IAP-JWT-Assertion`, verified in `common/verified_identity.py`:

- **`APP_ENV` decides the auth mode.** If `APP_ENV` is one of `""` (unset), `dev`, `development`, `local`, or `test`, the app runs in `local` mode with a mock identity. Any other value puts it in `iap` mode (`resolve_auth_mode`). There is no separate `AUTH_MODE` switch.
- **In `iap` mode**, the app verifies the assertion's signature, expiry and issuer (`https://cloud.google.com/iap`), and checks that its audience equals `IAP_JWT_AUDIENCE`. If the assertion is missing or invalid, the request has no identity.
- **`REQUIRE_AUTHENTICATED_USER`** controls whether a request with no identity gets `401 Authentication required` on non-public paths. If unset, it defaults to **on** for any non-local `APP_ENV` (`common/identity.py`). The public paths are `/healthz`, `/readyz` and `/favicon.ico` (`main.py`).

The app also checks its own configuration **at boot**:

1. `validate_identity_config()` (run when `config/default.py` is imported): in `iap` mode, an empty `IAP_JWT_AUDIENCE` raises `IdentityConfigError` (*"AUTH_MODE=iap requires IAP_JWT_AUDIENCE to be set … Refusing to serve."*).
2. `validate_serving_environment()` (run when `main.py` is imported): in `local` mode, if `K_SERVICE` or `KUBERNETES_SERVICE_HOST` is set, it raises `IdentityConfigError` (*"AUTH_MODE resolved to 'local' but a managed-platform marker is set … Refusing to serve with a mock identity in a deployed environment."*).

On GKE, IAP runs on the load balancer's backend service through the BackendConfig. The app then verifies the assertion that IAP adds to each request.

## Current state: identity wiring is manual on GKE

**The Cloud Run root wires the identity contract for you. The GKE root does not.**

- **Cloud Run** (`deploy/terraform/cloudrun/main.tf`) merges `nonprod_identity_env_vars` or `prod_identity_env_vars` into `cloud_run_env_vars`. Each sets `APP_ENV = var.environment`, `REQUIRE_AUTHENTICATED_USER = "true"`, and an `IAP_JWT_AUDIENCE` computed from the project number. It also adds `terraform_data` `*_app_env_guard` preconditions that fail the plan if `APP_ENV` would resolve to a local value.
- **GKE** (`deploy/terraform/gke`) sets **none** of those three variables and has no equivalent guard. The GKE root also has **no input variable for adding extra environment variables**.

### What happens if you do not wire them

**The app fails closed.** A pod refuses to serve rather than accepting a spoofed identity:

- With `APP_ENV` unset (the GKE root's current behavior), the app resolves to `local` mode. Kubernetes sets `KUBERNETES_SERVICE_HOST` in pods, so `validate_serving_environment()` raises `IdentityConfigError` while the server is loading the app (`main:app`). The app never serves, readiness never passes, and the Deployment does not become available.
- With `APP_ENV` set to a non-local value but `IAP_JWT_AUDIENCE` empty, `validate_identity_config()` raises `IdentityConfigError` while the app is loading, with the same result.
- With `IAP_JWT_AUDIENCE` set to the **wrong** value, the pod starts, but every IAP assertion fails audience verification. Protected paths then return `401` (because `REQUIRE_AUTHENTICATED_USER` is on), while `/healthz` and `/readyz` still return `200`.

### What to set

Set these three variables on the container:

| Variable | Value | Why |
|---|---|---|
| `APP_ENV` | Any value **not** in `{"", dev, development, local, test}`, for example `staging` or `prod`. Matching the Cloud Run root, use `var.environment` (defaults to `prod`; `nonprod.tfvars` sets `staging`). | Selects `iap` mode. |
| `REQUIRE_AUTHENTICATED_USER` | `"true"` | Rejects requests without a verified identity. This is already the default for a non-local `APP_ENV`; setting it explicitly matches Cloud Run. **Do not set it to `false`.** |
| `IAP_JWT_AUDIENCE` | `/projects/<PROJECT_NUMBER>/global/backendServices/<BACKEND_SERVICE_ID>` | The **load-balancer backend-service form**. `<PROJECT_NUMBER>` is the numeric project number (not the project ID). `<BACKEND_SERVICE_ID>` is the **numeric ID** of the backend service that the GKE Ingress controller creates. Do not hardcode or guess it; look it up after the Ingress exists (step 6 below). |

:::caution[Do not reuse the Cloud Run audience]
The Cloud Run nonprod audience form, `/projects/<number>/locations/<region>/services/creative-studio`, applies only to native Cloud Run IAP. It is **not** valid behind the GKE load balancer.
:::

Because the GKE root has no input for extra variables, the most direct way to set them is to add the three entries to `local.creative_studio_env_vars` in **your own copy** of `deploy/terraform/gke/main.tf`:

```hcl
  creative_studio_env_vars = {
    # ... existing entries unchanged ...

    # Verified-identity contract (manual on GKE; see docs)
    APP_ENV                    = var.environment
    REQUIRE_AUTHENTICATED_USER = "true"
    IAP_JWT_AUDIENCE           = "/projects/<PROJECT_NUMBER>/global/backendServices/<BACKEND_SERVICE_ID>"
  }
```

Do not commit real project numbers or IDs upstream. [PR #1926](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1926) shows a variable-based approach: a `google_project` data source plus a nullable `iap_backend_service_id` variable.

:::note
Changes made with `kubectl edit` or `kubectl set env` drift from Terraform state. The next `terraform apply` reverts them (only the container `image` is in `ignore_changes`). Keep the values in Terraform.
:::

## Prerequisites

- Terraform, the Google Cloud SDK (`gcloud`), and `kubectl`.
- A Google Cloud project where the **Cloud Run root has already been applied** (see [What it only reads](#what-it-only-reads-does-not-create)). This provides the runtime SA `service-creative-studio`, the assets bucket, Firestore, the tasks queue, the Artifact Registry repository `creative-studio`, and the build SA.
- A GCS bucket for Terraform state.
- A domain you control, so you can create a DNS A record for it (needed for the ManagedCertificate).
- An **OAuth client** for IAP. You create it outside Terraform, and its credentials are stored in a Kubernetes Secret (step 3).

:::note[TODO: not documented in the repo]
The repository does not document how to create the IAP OAuth client for the GKE path. The Terraform comments point to a `p9-report.md` that is not in the repository. Follow Google Cloud's IAP-for-GKE documentation for this step.
:::

## Step outline

These steps follow what the repository's Terraform and comments describe. **They have not been verified end-to-end against a real apply.** Read each step before you run it.

Run all Terraform commands from `deploy/terraform/gke`.

### 1. Prepare a variable file

Copy `environments/nonprod.tfvars` and replace its placeholders: `project_id`, `initial_user`, and `domain`. **Set `image`** to the image you will run (step 2), because the Deployment ignores later changes to `image` (see [Updating the image](#updating-the-image)). Leave `iap_backend_service_name` unset for now.

### 2. Build the container image

`build.sh` at the repo root builds with Cloud Build and then runs `gcloud run deploy` (Cloud Run). For GKE you only need its **build** step, the `gcloud builds submit …` line. That step pushes `$REGION-docker.pkg.dev/$PROJECT_ID/creative-studio/creative-studio:latest` plus an immutable `v<timestamp>-<sha>` tag (see `cloudbuild.yaml`). Use that image reference, preferably the version tag, as `image`.

### 3. Provide the IAP OAuth Secret

`create_iap_oauth_secret` defaults to `false`, so Terraform expects a Kubernetes Secret named `iap_oauth_secret_name` (default `creative-studio-iap-oauth`) in the workload namespace, with keys **`client_id`** and **`client_secret`**. Create it once the cluster exists (after step 4), for example:

```bash
kubectl create secret generic creative-studio-iap-oauth -n default \
  --from-literal=client_id=<CLIENT_ID> \
  --from-literal=client_secret=<CLIENT_SECRET>
```

Alternatively, set `create_iap_oauth_secret = true` and pass `iap_oauth_client_id` / `iap_oauth_client_secret` as sensitive inputs. **Never commit them.**

### 4. Two-stage apply

The kubernetes and kubectl providers are configured from the cluster's endpoint and CA, which do not exist until the cluster has been created. `deploy/terraform/gke/main.tf` resolves this with a **two-stage apply**: apply the APIs and the cluster first with `-target`, then run a full apply.

```bash
# Stage A: APIs + cluster
terraform apply -var-file=<your>.tfvars -target=module.apis -target=module.gke_cluster

# Fetch cluster credentials for kubectl (then create the step-3 Secret)
gcloud container clusters get-credentials creative-studio --region <REGION>

# Stage B: everything else
terraform apply -var-file=<your>.tfvars
```

**Expected at this point:** the pods **do not become ready**. `APP_ENV` is not set yet, so the app fails closed at boot (see above). This is expected.

### 5. Point DNS at the ingress

Create a DNS A record for `domain` pointing at the `ingress_static_ip` Terraform output. The ManagedCertificate cannot provision until DNS resolves.

### 6. Find the backend service name and numeric ID

The GKE Ingress controller creates the load-balancer backend service **after** apply, with a name GKE generates. You need two things from it:

- its **name**, for `iap_backend_service_name` (enables the `initial_user` IAP grant)
- its **numeric ID**, for `IAP_JWT_AUDIENCE`

For example (standard `gcloud`/`kubectl` usage, not scripted by this repository):

```bash
# Backends attached to the ingress (annotation set by the GKE ingress controller)
kubectl get ingress creative-studio -n default -o yaml | grep -i backends

# Numeric id of the backend service
gcloud compute backend-services describe <BACKEND_SERVICE_NAME> --global --format='value(id)'

# Project number
gcloud projects describe <PROJECT_ID> --format='value(projectNumber)'
```

:::note[TODO: not verified]
The repository assumes the Ingress controller creates the backend service even while the pods are failing readiness. That has not been checked against a real apply. If no backend service appears, check the Ingress events with `kubectl describe ingress`.
:::

### 7. Wire identity and apply again

1. Add `APP_ENV`, `REQUIRE_AUTHENTICATED_USER` and `IAP_JWT_AUDIENCE` to your copy of `main.tf` (see [What to set](#what-to-set)).
2. Set `iap_backend_service_name = "<BACKEND_SERVICE_NAME>"` in your tfvars so the `roles/iap.httpsResourceAccessor` grant for `initial_user` is created.
3. Run `terraform apply -var-file=<your>.tfvars`.
4. Containers read ConfigMap values through `envFrom` only when they start, so restart the pods: `kubectl rollout restart deployment/creative-studio -n default`.

## Verification / smoke test

1. **Rollout:** `kubectl rollout status deploy/creative-studio -n default` should complete.
2. **No identity errors:** `kubectl logs deploy/creative-studio -n default` should contain no `IdentityConfigError`. If it does, the message tells you which variable is missing (see [What happens if you do not wire them](#what-happens-if-you-do-not-wire-them)).
3. **Certificate and ingress:** `kubectl get ingress creative-studio -n default` should show an address, and the ManagedCertificate should eventually reach `Active` (`kubectl describe managedcertificate creative-studio-cert -n default`).
4. **Unauthenticated request is blocked:** `curl -s -o /dev/null -w '%{http_code}' https://<domain>/home` should return a redirect (`302`/`303`/`307`, from IAP) or `401` (from the app). It must **not** return `200`.
5. **Authenticated request works:** open `https://<domain>/` in a browser and sign in as `initial_user`. The app should load. If IAP signs you in but the app returns `401`, `IAP_JWT_AUDIENCE` probably does not match the backend service; the pod logs will show `IAP assertion verification failed`.

`deploy/scripts/deploy.sh` has a `--target gke` mode. It runs the pre-checks (adding `container.googleapis.com` to the required APIs) and, in `deploy` mode, **skips build and deploy** and runs only the post-deploy checks: `/healthz` and `/readyz` polls, the `/home` auth smoke test, `kubectl rollout status`, and an ingress-address check. Point it at your domain with `LB_HOST`:

```bash
LB_HOST=<domain> APP_ENV=<same APP_ENV you set> \
  deploy/scripts/deploy.sh deploy --target gke --project <PROJECT_ID> --region <REGION>
```

`APP_ENV` in your shell only drives the script's local pre-check `#22`. It does not change the cluster.

:::note[TODO: not verified]
The script's health poll expects `200` from `https://$LB_HOST/healthz`. With IAP on the backend service, unauthenticated requests through the load balancer may be redirected by IAP before they reach the app, so that poll may report a failure even though the pods are healthy. This has not been verified. Use steps 1–5 above as the primary signal.
:::

## Updating the image

The Deployment has `lifecycle.ignore_changes` on the container image, so **changing `image` after the first apply has no effect**. The variable description says a deploy pipeline rolls the image, but the repository has **no** GKE image rollout (`deploy.sh --target gke` does not deploy). Roll a new image yourself:

```bash
kubectl set image deployment/creative-studio creative-studio=<IMAGE_REF> -n default
```

## Known differences from Cloud Run

- No scale-to-zero: the HPA keeps at least `replicas_min` (default 1) pods running.
- The GKE path always sits behind an ingress, a managed certificate, and a custom domain. There is no equivalent of the `*.run.app` URL option.
- The identity env vars and the `APP_ENV` guard are not wired (see above).
- The IAP access grant for `initial_user` requires a second apply once the backend service name is known.
