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

# gke-cluster module: a fresh Autopilot, regional GKE cluster with Workload
# Identity enabled. This is the GKE analogue of the compute substrate the
# cloud-run-service module provides for the Cloud Run path; it owns exactly one
# resource (the cluster) and provisions no data-bearing state.
#
# Autopilot manages nodes, so there is intentionally NO google_container_node_pool
# here: the Autopilot decision is locked, and it overrides the Standard-path
# node-pool model. deletion_protection is on the CLUSTER only (default false so
# a non-prod cluster can be torn down cleanly) and is never applied to any data
# resource. The cluster depends on container.googleapis.com being enabled; the
# root wires that ordering by passing the project-services `apis_ready` handle
# through var.apis_ready_dependency (same pattern the Cloud Run root uses).

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.49"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.49"
    }
  }
}

resource "google_container_cluster" "creative_studio" {
  provider = google-beta
  project  = var.project_id
  name     = var.cluster_name
  location = var.region

  enable_autopilot = true

  # deletion_protection guards the CLUSTER resource only. Default false so a
  # non-prod cluster can be destroyed cleanly; never set on data resources.
  deletion_protection = var.deletion_protection

  network    = var.network
  subnetwork = var.subnetwork

  # Autopilot requires VPC-native (alias IP) networking. An empty
  # ip_allocation_policy lets GKE auto-provision the pod/service secondary
  # ranges on the target subnet, keeping the minimal/testing cluster simple.
  ip_allocation_policy {}

  # Workload Identity is implicit under Autopilot; declared explicitly so the
  # workload pool (<project_id>.svc.id.goog) is visible in config and outputs.
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  release_channel {
    channel = var.release_channel
  }

  # Ordering handle: the cluster is created only after the project-services
  # module reports its APIs (incl. container.googleapis.com) are enabled. The
  # root passes module.apis.apis_ready through this variable.
  depends_on = [var.apis_ready_dependency]
}
