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

resource "kubernetes_config_map_v1" "env" {
  metadata {
    name      = "${var.name}-env"
    namespace = var.namespace
    labels    = local.labels
  }
  data = var.env_vars
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
