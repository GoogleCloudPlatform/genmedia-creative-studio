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

output "load_balancer_ip" {
  description = "External IP address of the load balancer (for the DNS A record)."
  value       = module.lb-http.external_ip
}

# Server-assigned NUMERIC id (generated_id) of the LB backend service. This is the
# id the IAP JWT audience needs for the LB topology
# (/projects/<number>/global/backendServices/<NUMERIC_ID>) — NOT .id (a resource
# path built from the NAME) and NOT .name. Only the numeric id is exposed here:
# module.lb-http.backend_services is marked sensitive (it carries iap_config), so
# the single non-secret field is unwrapped with nonsensitive() rather than
# surfacing the whole object. Consumed by the cloudrun root for verification /
# runbook cross-check of IAP_JWT_AUDIENCE.
output "backend_service_generated_id" {
  description = "Numeric server-assigned generated_id of the LB backend service (for the IAP JWT audience). Numeric id only; the sensitive backend_services object is never exposed."
  value       = nonsensitive(module.lb-http.backend_services["default"].generated_id)
}
