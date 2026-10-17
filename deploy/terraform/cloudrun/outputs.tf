/**
* Copyright 2024 Google LLC
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

output "load-balancer-ip" {
  value       = var.use_lb ? module.networking-lb[0].load_balancer_ip : ""
  description = "IP Address that should be used for DNS A record for the domain provided."
}

output "backend-service-generated-id" {
  value       = var.use_lb ? module.networking-lb[0].backend_service_generated_id : null
  description = "Numeric generated_id of the prod LB backend service (null unless use_lb). Exposed for verification/runbook cross-check of IAP_JWT_AUDIENCE; the service env derives the same id cycle-free via a data source."
}

output "assets-bucket" {
  value       = module.data.assets_bucket_name
  description = "Name of the GCS bucket where assets are stored."
}

output "cloud-run-app-url" {
  value       = !var.use_lb ? "https://${module.cloud-run-service.service_name}-${data.google_project.project.number}.${module.cloud-run-service.service_location}.run.app" : ""
  description = "The Cloud Run URL where the website can be reached."
}

output "builds-service-account" {
  value       = module.iam.build_sa_email
  description = "Service Account used for Cloud Build"
}

output "application-service-account" {
  value       = module.iam.runtime_sa_email
  description = "Service Account used by the Creative Studio web application"
}
