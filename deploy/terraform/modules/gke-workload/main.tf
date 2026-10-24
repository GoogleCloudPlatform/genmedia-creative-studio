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

# gke-workload module: the GKE analogue of the Cloud Run service + networking-lb
# path. It runs the SAME container image on port 8080 with requests == limits
# (parity with the Cloud Run cpu/memory limits), fronted by a GCE external HTTPS
# load balancer (Ingress + ManagedCertificate) with IAP enabled on the backend
# service (BackendConfig), and binds the pod's Kubernetes ServiceAccount to the
# EXISTING runtime Google service account via Workload Identity (no key material).
#
# It reuses, never creates, the runtime Google SA and data stores (those come
# from the shared iam/data-stores modules). Secrets/config mirror the Cloud Run
# Phase 4 contract and are dormant by default (secret_env = {} => no Secret).
#
# Provider note (offline-gate implication): the GCE CRDs BackendConfig and
# ManagedCertificate are rendered through the gavinbunney/kubectl provider
# (kubectl_manifest). That provider parses the manifest bodies locally and does
# NOT perform a server-side dry-run at plan, so `terraform validate` passes
# offline; a real `terraform plan`/`apply` still needs cluster access (that step
# is gated). The native kubernetes_manifest resource was avoided precisely
# because it requires a live API server even to plan.

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.49"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.0"
    }
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = "~> 1.14"
    }
  }
}

locals {
  labels = {
    "app" = var.name
  }
  # Workload Identity member: binds the KSA to the runtime Google SA.
  wi_member = "serviceAccount:${var.project_id}.svc.id.goog[${var.namespace}/${var.ksa_name}]"

  backend_config_name    = "${var.name}-backendconfig"
  managed_cert_name      = "${var.name}-cert"
  create_iap_oauth       = var.enable_iap && var.create_iap_oauth_secret
  render_iap_iam_binding = var.enable_iap && var.initial_user != null && var.iap_backend_service_name != null

  # secret_env is sensitive (its VALUES are secret), so it cannot drive count /
  # for_each directly. The env var NAMES are not secret: unmark just the key set
  # for control-flow. Values are only ever referenced inside the Secret's `data`
  # and via secretKeyRef (by name), never expanded into config here.
  secret_env_keys = nonsensitive(toset(keys(var.secret_env)))

  # Vuln #4 (the fail-safe GKE rollout mechanism) — versioned/immutable ConfigMap
  # name. The name embeds a content hash of the env data map so that ANY change to
  # env_vars yields a NEW ConfigMap NAME (never an in-place mutation of a fixed
  # name). A new name flows into the Deployment pod template
  # (env_from.config_map_ref.name below), which rolls a NEW ReplicaSet — so the env
  # change and the (out-of-band) image roll are carried by a single pod-template
  # update. Both ConfigMaps are REASONED to coexist while the roll is in flight
  # (`create_before_destroy`; the destroy EDGE is statically measured, but
  # destroy-after-rollout-COMPLETION is the composite through the unmeasured wait —
  # reasoned, NOT measured), so an old-RS pod that RESTARTS would still resolve the
  # OLD immutable ConfigMap (`envFrom` resolves at pod start, so a restart re-reads
  # it). Stall-path safety does NOT rest on that: already-running old pods are
  # unaffected by removal of the retired CM (documented Kubernetes semantics, not
  # measured in our cluster -- see the bound on kubernetes_config_map_v1.env below).
  # The retired CM is NOT retained as a rollback target; see the note on
  # kubernetes_config_map_v1.env below. The hash input is deterministic (jsonencode
  # sorts map keys; no timestamps/random), so a re-render of the same env produces
  # the same name => a `terraform apply` reconcile is a no-op.
  env_config_map_name = "${var.name}-env-${substr(sha256(jsonencode(var.env_vars)), 0, 10)}"
}

# --- Workload Identity: KSA annotated to the existing runtime Google SA -------

resource "kubernetes_service_account_v1" "workload" {
  metadata {
    name      = var.ksa_name
    namespace = var.namespace
    annotations = {
      "iam.gke.io/gcp-service-account" = var.runtime_sa_email
    }
  }
}

# roles/iam.workloadIdentityUser binding of the KSA to the EXISTING Google SA.
# The runtime SA itself is an input (created by the shared iam module).
resource "google_service_account_iam_member" "workload_identity" {
  service_account_id = var.runtime_sa_id
  role               = "roles/iam.workloadIdentityUser"
  member             = local.wi_member
}

# --- Config & secrets (parity with Cloud Run; secret path dormant by default) -

# Vuln #4 (the fail-safe GKE rollout mechanism): versioned/immutable ConfigMap.
# The NAME is content-hashed (local.env_config_map_name) and the object is
# `immutable = true`, so it can NEVER be mutated in place — an env change
# produces a brand-new ConfigMap under a new name instead. The new ConfigMap
# exists BEFORE the pod template switches to it (ordering basis stated below),
# so the Deployment can always resolve its config_map_ref during the roll.
#
# Content-hashed immutable name: a changed env set produces a new ConfigMap.
# Creation ordering is enforced by a real resource reference (Deployment
# env_from -> kubernetes_config_map_v1.env.metadata[0].name) plus depends_on, so
# the new CM exists before the Deployment is rolled. wait_for_rollout is set
# true explicitly (effective default also true, observed across 2.31.0-2.38.0);
# with it true, Terraform is documented to block the apply until the new
# ReplicaSet is healthy -- that blocking is provider-documented, not measured in
# our cluster, and is the same wait scoped below (to be observed at first
# apply). Stall-path safety does NOT depend on ConfigMap retention: envFrom is
# resolved at pod START and injected into the container env, so already-running
# old pods are unaffected by deletion of the retired CM, and a successful
# maxUnavailable=0/maxSurge=1 roll does not recreate old-RS pods. Ordering of
# the retired-CM destroy relative to the Deployment update: the apply graph
# sequences the deposed-CM destroy after the Deployment update, and this EDGE is
# statically measured on two harnesses over the SAME REAL MODULE, differing in
# how prior state was produced (hand-authored vs provider-schema-generated
# attribute skeletons) -- independent in execution and in control design, not in
# the module under test. The two COMPOSE rather than agree: one rules the HPA
# hop out as the carrier, the other (a two-by-two control matrix) identifies the
# ConfigMap->Deployment dependency as the actual carrier and finds it
# redundantly held (config reference plus depends_on). A bare 'a direct edge
# appears' is NOT diagnostic of why -- both controls can produce that shape from
# different causes. Bound: what is measured is the graph edge (a reachability
# rendering; the path runs through the HPA, which Terraform transitively
# reduces), NOT the executor's runtime order. The inference from edge to strict
# execution order relies on Terraform's walker honouring reachability -- a
# single link that is reasoned and merely held twice by both methods, not
# independently confirmed; this comment does not claim the execution-order
# inference is measured. Separately, that the destroy lands after the roll is
# healthy (not merely after the update step is scheduled) is wait_for_rollout
# runtime behavior, still to be observed at the first ordinary terraform-driven
# env-change apply (NOT this Phase-5 co-deploy, which bypasses the TF destroy
# path via state-rm/import + manual GC). Rollback: the retired ConfigMap is not
# retained as a rollback target (the module has no keep-previous logic, by
# design); roll back by re-applying the previous config inputs (regenerates the
# byte-identical previous ConfigMap) and, separately, moving the image with
# kubectl to the previous digest -- TWO rolls, not one, and their order is
# load-bearing. The governing rule is the same fail-safe invariant that governs
# the forward co-deploy -- "never an old image with the gate on" -- discharged
# differently in each direction. FORWARD it is discharged by ATOMICITY: config
# is Terraform-owned but the image is out-of-band under ignore_changes, and the
# deploy pipeline carries both into a SINGLE Deployment rollout, so the three
# elements land together and no ordering is required or possible. ROLLBACK
# through Terraform has no single carrier for both -- Terraform owns the config
# but ignore_changes bars it from moving the image -- so config and image move
# in separate rolls, and the invariant is discharged by ORDER instead: clear the
# gate (re-apply the previous config) FIRST, then move the image. Image-first
# would stand up the old image with the gate still on -- the forbidden state --
# so the two rolls must not be reversed and must not be read as the forward
# atomic co-deploy run backwards. NOT kubectl rollout undo -- in this
# Terraform-owns-config model rollout undo is out-of-band drift the next
# reconcile reverts, so it is not a durable recovery even if it appears to work.
# (Post-success rollout undo is moreover expected to fail outright -- the
# retired CM the prior ReplicaSet references is gone; likely symptom
# CreateContainerConfigError -- expected, not measured, cluster-bound like the
# wait above.) The stall-path property that old pods keep serving rests on
# documented Kubernetes semantics (envFrom resolved at pod start plus
# maxUnavailable=0) but is likewise not measured in our cluster, to be observed
# at first apply.
resource "kubernetes_config_map_v1" "env" {
  metadata {
    name      = local.env_config_map_name
    namespace = var.namespace
    labels    = local.labels
  }
  data      = var.env_vars
  immutable = true

  lifecycle {
    create_before_destroy = true
  }
}

# Secret-backed env. DORMANT by default: secret_env = {} => count 0 => no Secret.
# Values are supplied out-of-band by the root from Secret Manager, never authored
# in committed Terraform.
resource "kubernetes_secret_v1" "env" {
  count = length(local.secret_env_keys) > 0 ? 1 : 0
  metadata {
    name      = var.secret_name
    namespace = var.namespace
    labels    = local.labels
  }
  data = var.secret_env
  type = "Opaque"
}

# --- Deployment --------------------------------------------------------------

resource "kubernetes_deployment_v1" "workload" {
  metadata {
    name      = var.name
    namespace = var.namespace
    labels    = local.labels
  }
  spec {
    replicas = var.replicas_min

    # Vuln #4 (the fail-safe GKE rollout mechanism): explicit RollingUpdate with
    # maxUnavailable=0/maxSurge=1 (the strategy VALUES are configured fact); under
    # those values Kubernetes is documented to keep the OLD ReplicaSet serving
    # until the new pods are Ready (documented semantics, not measured in our
    # cluster -- see the stall-path note in the env ConfigMap comment).
    # maxUnavailable=0 means no old pod is torn down before a new pod passes its
    # readiness probe; maxSurge=1 brings up one new pod at a time. When a new pod
    # CrashLoops on the app's startup FATAL (e.g. iap-mode with an unset audience,
    # or a local-mode-on-managed-platform backstop), if it never becomes Ready, the
    # rollout STALLS and the old ReplicaSet keeps serving = fail-safe DOWN -- this
    # fail-safe-down CONSEQUENCE rests on documented Kubernetes semantics
    # (maxUnavailable=0) and is NOT measured in our cluster; to be observed at
    # first apply, same tier as the wait (see the env ConfigMap comment). NOT
    # Recreate (which would tear down the old pods first and open an outage /
    # bad-state window).
    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_unavailable = "0"
        max_surge       = "1"
      }
    }

    selector {
      match_labels = local.labels
    }
    template {
      metadata {
        labels = local.labels
      }
      spec {
        service_account_name = kubernetes_service_account_v1.workload.metadata[0].name
        container {
          name  = var.name
          image = var.image

          port {
            container_port = var.container_port
          }

          # requests == limits => parity with the Cloud Run cpu/memory limits.
          resources {
            requests = {
              cpu    = var.cpu
              memory = var.memory
            }
            limits = {
              cpu    = var.cpu
              memory = var.memory
            }
          }

          # Plaintext env from the ConfigMap (1:1 with Cloud Run plaintext env).
          env_from {
            config_map_ref {
              name = kubernetes_config_map_v1.env.metadata[0].name
            }
          }

          # Secret-backed env via valueFrom.secretKeyRef, one per secret_env key.
          # Renders nothing when secret_env is empty (dormant).
          dynamic "env" {
            for_each = local.secret_env_keys
            content {
              name = env.value
              value_from {
                secret_key_ref {
                  name = var.secret_name
                  key  = env.value
                }
              }
            }
          }

          # REQUIRED probes, mirroring the Cloud Run probe targets on port 8080.
          readiness_probe {
            http_get {
              path = "/readyz"
              port = var.container_port
            }
            period_seconds    = 10
            timeout_seconds   = 3
            failure_threshold = 3
          }
          liveness_probe {
            http_get {
              path = "/healthz"
              port = var.container_port
            }
            period_seconds    = 30
            timeout_seconds   = 5
            failure_threshold = 3
          }
        }
      }
    }
  }

  wait_for_rollout = true # provider-documented to block the apply until the new ReplicaSet is healthy; not measured in our cluster (see env ConfigMap comment bound)

  # Preserve the out-of-band image/deploy contract: the image is rolled by the
  # deploy pipeline, so Terraform ignores in-place changes to it (parity with the
  # Cloud Run service's ignore_changes on the image field).
  lifecycle {
    ignore_changes = [spec[0].template[0].spec[0].container[0].image]
  }

  depends_on = [kubernetes_config_map_v1.env]
}

# --- Service (NEG-backed, wired to the BackendConfig) ------------------------

resource "kubernetes_service_v1" "workload" {
  metadata {
    name      = var.name
    namespace = var.namespace
    labels    = local.labels
    annotations = {
      # Standalone/ingress-managed NEG of type GCE_VM_IP_PORT.
      "cloud.google.com/neg" = jsonencode({ ingress = true })
      # Attach the BackendConfig (IAP + health check) to this Service.
      "cloud.google.com/backend-config" = jsonencode({ default = local.backend_config_name })
    }
  }
  spec {
    type     = "ClusterIP"
    selector = local.labels
    port {
      port        = 80
      target_port = var.container_port
    }
  }
}

# --- BackendConfig CRD: IAP + health check (offline-safe via kubectl) --------

resource "kubectl_manifest" "backend_config" {
  yaml_body = yamlencode({
    apiVersion = "cloud.google.com/v1"
    kind       = "BackendConfig"
    metadata = {
      name      = local.backend_config_name
      namespace = var.namespace
    }
    spec = {
      iap = {
        enabled = var.enable_iap
        oauthclientCredentials = {
          secretName = var.iap_oauth_secret_name
        }
      }
      healthCheck = {
        type        = "HTTP"
        requestPath = "/readyz"
        port        = var.container_port
      }
    }
  })
}

# Optional IAP OAuth client Secret. Only created when create_iap_oauth_secret is
# true; values come from sensitive inputs supplied out-of-band. NEVER committed.
resource "kubernetes_secret_v1" "iap_oauth" {
  count = local.create_iap_oauth ? 1 : 0
  metadata {
    name      = var.iap_oauth_secret_name
    namespace = var.namespace
    labels    = local.labels
  }
  data = {
    client_id     = var.iap_oauth_client_id
    client_secret = var.iap_oauth_client_secret
  }
  type = "Opaque"
}

# --- Managed certificate CRD + reserved static IP + Ingress ------------------

resource "kubectl_manifest" "managed_certificate" {
  yaml_body = yamlencode({
    apiVersion = "networking.gke.io/v1"
    kind       = "ManagedCertificate"
    metadata = {
      name      = local.managed_cert_name
      namespace = var.namespace
    }
    spec = {
      domains = [var.domain]
    }
  })
}

# Reserved global static IP for the ingress (parity with networking-lb's
# reserved IP). Skipped when create_static_ip is false (address pre-exists).
resource "google_compute_global_address" "ingress_ip" {
  count      = var.create_static_ip ? 1 : 0
  project    = var.project_id
  name       = var.static_ip_name
  ip_version = "IPV4"
}

resource "kubernetes_ingress_v1" "workload" {
  metadata {
    name      = var.name
    namespace = var.namespace
    labels    = local.labels
    annotations = {
      "kubernetes.io/ingress.class"                 = "gce"
      "kubernetes.io/ingress.global-static-ip-name" = var.static_ip_name
      "networking.gke.io/managed-certificates"      = local.managed_cert_name
    }
  }
  spec {
    default_backend {
      service {
        name = kubernetes_service_v1.workload.metadata[0].name
        port {
          number = 80
        }
      }
    }
  }

  depends_on = [
    kubectl_manifest.backend_config,
    kubectl_manifest.managed_certificate,
    google_compute_global_address.ingress_ip,
  ]
}

# --- Horizontal Pod Autoscaler (no scale-to-zero) ----------------------------

resource "kubernetes_horizontal_pod_autoscaler_v2" "workload" {
  metadata {
    name      = var.name
    namespace = var.namespace
    labels    = local.labels
  }
  spec {
    min_replicas = var.replicas_min
    max_replicas = var.replicas_max
    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = kubernetes_deployment_v1.workload.metadata[0].name
    }
    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = var.cpu_target_utilization
        }
      }
    }
  }
}

# --- IAP access IAM: roles/iap.httpsResourceAccessor on the ingress backend ---
# Analogue of the Cloud Run google_iap_web_iam_member. The GKE backend service
# name is derived by GKE from the Service/BackendConfig; the binding is rendered
# only once that name (and an initial_user) are known.
resource "google_iap_web_backend_service_iam_member" "initial_user" {
  count               = local.render_iap_iam_binding ? 1 : 0
  project             = var.project_id
  web_backend_service = var.iap_backend_service_name
  role                = "roles/iap.httpsResourceAccessor"
  member              = "user:${var.initial_user}"
}
