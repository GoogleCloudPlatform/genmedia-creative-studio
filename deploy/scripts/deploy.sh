#!/usr/bin/env bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# ---------------------------------------------------------------------------
# GenMedia Creative Studio — lightweight, non-Terraform deploy + pre/post-flight
# check script for the canonical Cloud Run path.
#
# WHAT THIS IS: a fast operator loop that (1) verifies prerequisites of an
# ALREADY-provisioned environment, (2) drives the existing Cloud Build +
# `gcloud run deploy` flow (wrapping cloudbuild.yaml), and (3) runs post-deploy
# health + auth-wiring smoke checks.
#
# WHAT THIS IS NOT: an infrastructure provisioner. It creates NOTHING except the
# single idempotent auto-remediation of the Artifact Registry repository
# (pre-check #16). Provisioning is Terraform's job. It never reads or writes
# secret values and it does not manage the container-image contract beyond
# invoking the existing build. See the "What this script does NOT do" section of
# deploy.md.
# ---------------------------------------------------------------------------

set -euo pipefail

# --------------------------------------------------------------------------- #
# Constants (repo-known resource names — see Terraform modules).
# --------------------------------------------------------------------------- #
SCRIPT_NAME="$(basename "$0")"; readonly SCRIPT_NAME
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
# Repo root is two levels up from deploy/scripts/ (this script lives at
# deploy/scripts/deploy.sh). Build files (Dockerfile, cloudbuild.yaml) stay there.
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"; readonly REPO_ROOT
readonly SERVICE_NAME_DEFAULT="creative-studio"       # cloud-run-service module
readonly FIRESTORE_DB="create-studio-asset-metadata"  # data-stores module
readonly TASKS_QUEUE="thumbnail-extraction"           # data-stores module
readonly AR_REPO="creative-studio"                     # artifact-registry module
readonly IMAGE_PATH="creative-studio/creative-studio"  # cloudbuild.yaml _IMAGE_NAME
readonly EXPECTED_INDEX_COUNT=4                         # data-stores firestore_indexes (genmedia collection)
readonly APIS_FILE="${SCRIPT_DIR}/apis.txt"
readonly TF_APIS_VARFILE="${SCRIPT_DIR}/../terraform/modules/project-services/variables.tf"
readonly CLOUDBUILD_CONFIG="${REPO_ROOT}/cloudbuild.yaml"
readonly HEALTH_TIMEOUT_DEFAULT=300   # seconds for post-deploy health poll
readonly HEALTH_INTERVAL=10           # seconds between polls

# --------------------------------------------------------------------------- #
# Exit codes (documented in deploy.md).
#   0  success (all HARD-BLOCK pre-checks + all post-checks passed)
#   1  usage / internal error
#   2  a HARD-BLOCK pre-check failed (deploy refused)
#   3  the build or deploy step failed
#   4  a post-deploy check failed
# --------------------------------------------------------------------------- #
readonly EXIT_OK=0
readonly EXIT_USAGE=1
readonly EXIT_PRECHECK=2
readonly EXIT_DEPLOY=3
readonly EXIT_POSTCHECK=4

# --------------------------------------------------------------------------- #
# Runtime state.
# --------------------------------------------------------------------------- #
MODE="check"          # check | deploy | list-versions
TARGET="cloudrun"     # --target: cloudrun (default, unchanged behavior) | gke
STRICT=0              # --strict: promote every WARN to a HARD-BLOCK
DO_BUILD=1            # --no-build: deploy an existing image, do not build
PROJECT=""
REGION_ENV="${REGION:-}"  # inherited REGION env var (documented); captured before REGION becomes the internal resolution var
REGION=""
SERVICE_NAME="${SERVICE_NAME_DEFAULT}"
NAMESPACE="${NAMESPACE:-default}"  # k8s namespace for the --target gke rollout check
IMAGE_TAG="latest"
IMAGE_DIGEST=""       # --image: deploy an exact digest (@sha256:…); implies --no-build
VERSION_TAG=""        # computed immutable per-build tag v<UTC-ts>-<shortSHA> (set at build time)
SERVICE_ACCOUNT_EMAIL=""
GCS_ASSETS_BUCKET=""
BUILD_SA_EMAIL=""
GCLOUD_OK=0           # set to 1 once check #1 passes
ENABLED_APIS_CACHE="" # newline list of enabled APIs (fetched once)

BLOCK_COUNT=0
WARN_COUNT=0
PASS_COUNT=0

# --------------------------------------------------------------------------- #
# Output helpers (colour only on a TTY and when NO_COLOR is unset).
# --------------------------------------------------------------------------- #
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_RED=$'\033[0;31m'; C_GRN=$'\033[0;32m'; C_YEL=$'\033[0;33m'
  C_BLU=$'\033[0;34m'; C_DIM=$'\033[2m'; C_NC=$'\033[0m'
else
  C_RED=""; C_GRN=""; C_YEL=""; C_BLU=""; C_DIM=""; C_NC=""
fi

log()  { printf '%s\n' "$*"; }
info() { printf '%s%s%s\n' "${C_BLU}" "$*" "${C_NC}"; }
hr()   { printf '%s\n' "-------------------------------------------------------------------"; }

# pass/warn/block/skip take: "<#id>" "<title>" "<detail>"
pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf '%s[ PASS ]%s %-5s %s — %s\n' "${C_GRN}" "${C_NC}" "$1" "$2" "$3"
}
skip() {
  printf '%s[ SKIP ]%s %-5s %s — %s\n' "${C_DIM}" "${C_NC}" "$1" "$2" "$3"
}
# warn(): a WARN, unless --strict promotes it to a HARD-BLOCK.
warn() {
  if [[ "${STRICT}" -eq 1 ]]; then
    BLOCK_COUNT=$((BLOCK_COUNT + 1))
    printf '%s[ BLOCK]%s %-5s %s — %s %s(WARN promoted by --strict)%s\n' \
      "${C_RED}" "${C_NC}" "$1" "$2" "$3" "${C_DIM}" "${C_NC}"
  else
    WARN_COUNT=$((WARN_COUNT + 1))
    printf '%s[ WARN ]%s %-5s %s — %s\n' "${C_YEL}" "${C_NC}" "$1" "$2" "$3"
  fi
}
block() {
  BLOCK_COUNT=$((BLOCK_COUNT + 1))
  printf '%s[ BLOCK]%s %-5s %s — %s\n' "${C_RED}" "${C_NC}" "$1" "$2" "$3"
}

usage() {
  cat <<EOF
${SCRIPT_NAME} — GenMedia Creative Studio deploy + pre/post-flight checks (Cloud Run).

USAGE:
  ${SCRIPT_NAME} check         [options]  Run ALL pre-checks and exit (no deploy). Alias: --check-only, --dry-run
  ${SCRIPT_NAME} deploy        [options]  Pre-checks -> build+deploy -> post-checks
  ${SCRIPT_NAME} list-versions [options]  List AR image versions (tags + digest + create time), newest first (read-only)
  ${SCRIPT_NAME} --help

On \`deploy\`, the build pushes an IMMUTABLE version tag \`v<UTC-timestamp>-<gitShortSHA>\`
(e.g. v20260920t153012z-3eb17bf; a dirty tree keeps the SHA as \`...-<gitShortSHA>-dirty\`,
and a non-git checkout falls back to \`v<UTC-timestamp>-nogit\`) AND updates the moving
\`:latest\`, both pointing at the same digest. The
default UX still deploys \`:latest\` unless \`--version\`/\`--image\` selects a specific image.

OPTIONS:
  --target <t>          Deploy target: cloudrun (default) or gke. cloudrun is the
                        canonical path and is unchanged. gke reuses the same
                        pre-checks (pre-check #2 additionally requires
                        container.googleapis.com) and health/auth post-checks
                        (point them at the ingress with LB_HOST=<gke ingress host>),
                        and swaps the revision/traffic post-check for a
                        \`kubectl rollout status\` + ingress-address readiness check.
                        GKE provisioning/image roll-out is Terraform's job
                        (deploy/terraform/gke); this path runs checks + smoke only.
  --strict              Promote every WARN pre-check to a HARD-BLOCK (for CI).
  --no-build            Deploy an already-built image (skip Cloud Build). Makes
                        pre-check #17 (image exists) a HARD-BLOCK and skips the
                        build-SA (#10) and caller-can-submit-builds (#10a) checks.
  --project <id>        GCP project id (else \$PROJECT_ID / gcloud config).
  --region <region>     GCP region (else \$REGION / \$GOOGLE_CLOUD_REGION /
                        gcloud config / us-central1, in that order).
  --service <name>      Cloud Run service name (default: ${SERVICE_NAME_DEFAULT}).
  --tag <tag>           Image tag to build/deploy (default: latest).
  --version <tag>       Deploy an EXISTING version tag (e.g. v20260920t153012z-3eb17bf)
                        without rebuilding. Implies --no-build; the tag's existence is
                        gated by pre-check #17 (HARD-BLOCK if absent). This is also the
                        rollback path: pick a prior tag from \`list-versions\`.
  --image <digest>      Deploy an EXACT image by digest (a bare sha256:… , or a full
                        <region>-docker.pkg.dev/<project>/creative-studio/creative-studio@sha256:…
                        ref). Digest is tag-independent ground truth. Implies --no-build;
                        existence is gated by #17. Mutually exclusive with --version.
  -h, --help            Show this help.

ENVIRONMENT (optional overrides; sensible defaults are derived):
  PROJECT_ID, REGION, GOOGLE_CLOUD_REGION (region fallback, ranked after REGION),
  SERVICE_ACCOUNT_EMAIL, GCS_ASSETS_BUCKET, BUILD_SA_EMAIL,
  HEALTH_TIMEOUT, LB_HOST (poll health through this host instead of the run.app
  URL), IAP_ID_TOKEN (OIDC token for the positive auth smoke), APP_ENV
  (drives pre-check #22), TF_STATE_BUCKET (enables pre-check #18), SECRET_ENV
  (comma-separated secret ids -> enables pre-check #19).

EXIT CODES:
  0 ok   1 usage/internal   2 HARD-BLOCK pre-check   3 build/deploy   4 post-check
EOF
}

# --------------------------------------------------------------------------- #
# Argument parsing.
# --------------------------------------------------------------------------- #
parse_args() {
  local version_selected=0
  if [[ $# -eq 0 ]]; then MODE="check"; return; fi
  case "$1" in
    check|--check-only|--dry-run) MODE="check"; shift ;;
    deploy) MODE="deploy"; shift ;;
    list-versions) MODE="list-versions"; shift ;;
    -h|--help) usage; exit "${EXIT_OK}" ;;
    --*) MODE="check" ;;  # bare flags default to check mode
    *) log "Unknown command: $1"; usage; exit "${EXIT_USAGE}" ;;
  esac
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --target)
        TARGET="${2:-}"; shift 2
        case "${TARGET}" in
          cloudrun|gke) ;;
          *) log "Unknown --target: ${TARGET} (expected cloudrun|gke)"; usage; exit "${EXIT_USAGE}" ;;
        esac
        ;;
      --strict) STRICT=1; shift ;;
      --no-build) DO_BUILD=0; shift ;;
      --project) PROJECT="${2:-}"; shift 2 ;;
      --region) REGION="${2:-}"; shift 2 ;;
      --service) SERVICE_NAME="${2:-}"; shift 2 ;;
      --tag) IMAGE_TAG="${2:-}"; shift 2 ;;
      # --version / --image select an EXISTING image and each imply --no-build
      # (deploy without rebuilding). Existence is gated by pre-check #17.
      --version) IMAGE_TAG="${2:-}"; DO_BUILD=0; version_selected=1; shift 2 ;;
      --image) IMAGE_DIGEST="${2:-}"; DO_BUILD=0; shift 2 ;;
      -h|--help) usage; exit "${EXIT_OK}" ;;
      *) log "Unknown option: $1"; usage; exit "${EXIT_USAGE}" ;;
    esac
  done
  # --version and --image are mutually exclusive: one selects by tag, the other by
  # digest; specifying both is ambiguous about which ref to deploy.
  if [[ "${version_selected}" -eq 1 && -n "${IMAGE_DIGEST}" ]]; then
    log "Cannot combine --version and --image (choose a tag OR a digest)."
    usage; exit "${EXIT_USAGE}"
  fi
}

# --------------------------------------------------------------------------- #
# Config resolution (no GCP calls except reading gcloud config).
# --------------------------------------------------------------------------- #
resolve_config() {
  [[ -z "${PROJECT}" ]] && PROJECT="${PROJECT_ID:-}"
  if [[ -z "${PROJECT}" ]] && command -v gcloud >/dev/null 2>&1; then
    PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
    [[ "${PROJECT}" == "(unset)" ]] && PROJECT=""
  fi
  # Region precedence: --region flag > REGION env > GOOGLE_CLOUD_REGION > gcloud
  # config > us-central1. --region populates REGION during arg parsing; the
  # inherited REGION env value was captured as REGION_ENV before it was blanked.
  [[ -z "${REGION}" ]] && REGION="${REGION_ENV}"
  [[ -z "${REGION}" ]] && REGION="${GOOGLE_CLOUD_REGION:-}"
  if [[ -z "${REGION}" ]] && command -v gcloud >/dev/null 2>&1; then
    REGION="$(gcloud config get-value run/region 2>/dev/null || true)"
    [[ "${REGION}" == "(unset)" ]] && REGION=""
  fi
  [[ -z "${REGION}" ]] && REGION="us-central1"

  # Derive load-bearing values (env override wins), matching the Terraform
  # locals: asset bucket "creative-studio-<project>-assets", runtime SA
  # "service-creative-studio@<project>", build SA "builds-creative-studio@<project>".
  SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_EMAIL:-}"
  [[ -z "${SERVICE_ACCOUNT_EMAIL}" && -n "${PROJECT}" ]] &&
    SERVICE_ACCOUNT_EMAIL="service-creative-studio@${PROJECT}.iam.gserviceaccount.com"
  GCS_ASSETS_BUCKET="${GCS_ASSETS_BUCKET:-}"
  [[ -z "${GCS_ASSETS_BUCKET}" && -n "${PROJECT}" ]] &&
    GCS_ASSETS_BUCKET="creative-studio-${PROJECT}-assets"
  BUILD_SA_EMAIL="${BUILD_SA_EMAIL:-}"
  [[ -z "${BUILD_SA_EMAIL}" && -n "${PROJECT}" ]] &&
    BUILD_SA_EMAIL="builds-creative-studio@${PROJECT}.iam.gserviceaccount.com"
  return 0
}

# image_ref: the fully-qualified image reference to deploy. Defaults to the
# tag-based ref (<region>-docker.pkg.dev/<project>/<path>:<tag>). When --image
# supplies a digest, deploy that exact digest instead (tag-independent ground
# truth). --image accepts a full ref, a bare "sha256:…" digest, or a bare digest.
image_ref() {
  local base="${REGION}-docker.pkg.dev/${PROJECT}/${IMAGE_PATH}"
  if [[ -n "${IMAGE_DIGEST}" ]]; then
    case "${IMAGE_DIGEST}" in
      *docker.pkg.dev/*) printf '%s' "${IMAGE_DIGEST}" ;;          # full ref given
      sha256:*)          printf '%s@%s' "${base}" "${IMAGE_DIGEST}" ;;
      *)                 printf '%s@sha256:%s' "${base}" "${IMAGE_DIGEST}" ;;
    esac
    return
  fi
  printf '%s:%s' "${base}" "${IMAGE_TAG}"
}

# compute_version_tag: an immutable, human-sortable per-build version tag.
# Three cases, so the commit SHA is preserved for provenance whenever one exists:
#   - clean git checkout:  v<UTC-timestamp>-<gitShortSHA>       (e.g. v20260920t153012z-3eb17bf)
#   - dirty working tree:  v<UTC-timestamp>-<gitShortSHA>-dirty (keeps the SHA, marks it dirty)
#   - true non-git:        v<UTC-timestamp>-nogit               (no repo / no resolvable HEAD)
# A version tag is ALWAYS produced and never collides with a clean build (FU-3 Q1).
compute_version_tag() {
  local ts sha
  ts="$(date -u +%Y%m%dt%H%M%Sz)"
  if command -v git >/dev/null 2>&1 &&
     git -C "${REPO_ROOT}" rev-parse --git-dir >/dev/null 2>&1 &&
     sha="$(git -C "${REPO_ROOT}" rev-parse --short=7 HEAD 2>/dev/null)" &&
     [[ -n "${sha}" ]]; then
    # In a git checkout with a resolvable HEAD: keep the SHA, appending -dirty
    # when the working tree has uncommitted changes.
    if [[ -n "$(git -C "${REPO_ROOT}" status --porcelain 2>/dev/null)" ]]; then
      printf 'v%s-%s-dirty' "${ts}" "${sha}"
    else
      printf 'v%s-%s' "${ts}" "${sha}"
    fi
  else
    printf 'v%s-nogit' "${ts}"
  fi
}

# Read the canonical required-API list from the single source (apis.txt).
read_required_apis() {
  [[ -f "${APIS_FILE}" ]] || return 1
  grep -vE '^\s*(#|$)' "${APIS_FILE}" | sed 's/[[:space:]]//g' | grep -E '.'
}

# Extract the API set Terraform declares (variable "activate_apis" default) for
# the drift check. Returns a sorted, one-per-line list. Scoped to the
# activate_apis block only, so an API literal elsewhere in the file (e.g. another
# variable's description) cannot false-positive the #2a parity check.
read_tf_apis() {
  [[ -f "${TF_APIS_VARFILE}" ]] || return 1
  awk '
    /variable[[:space:]]+"activate_apis"/ { in_block=1 }
    in_block                              { print }
    in_block && /^}/                      { exit }
  ' "${TF_APIS_VARFILE}" |
    grep -oE '"[a-z][a-z0-9.-]+\.googleapis\.com"' |
    tr -d '"' | sort -u
}

# Accurate IAM binding lookups via gcloud server-side filters (avoids fragile
# text parsing: the role/members ordering in the policy JSON is not reliable).
#
# _has_binding <role> <member> <get-iam-policy command...>
#   Returns 0 iff <member> holds <role> in the policy the command prints.
_has_binding() {
  local role="$1" member="$2"; shift 2
  local out
  out="$("$@" --flatten="bindings[].members" \
    --filter="bindings.role=${role} AND bindings.members=${member}" \
    --format="value(bindings.role)" 2>/dev/null || true)"
  [[ -n "${out}" ]]
}

# _role_present <role> <get-iam-policy command...> : role bound to ANY member.
_role_present() {
  local role="$1"; shift
  local out
  out="$("$@" --flatten="bindings[].members" \
    --filter="bindings.role=${role}" --format="value(bindings.role)" 2>/dev/null || true)"
  [[ -n "${out}" ]]
}

has_project_role() {
  _has_binding "$2" "serviceAccount:$1" gcloud projects get-iam-policy "${PROJECT}"
}

# _caller_iam_permission <project> <permission>
#   Positive capability probe for the ACTIVE principal via Cloud Resource Manager
#   testIamPermissions (REST). testIamPermissions returns only the SUBSET of the
#   queried permissions the caller actually holds — including grants inherited via
#   Google groups or custom roles — so a returned hit is authoritative.
#   Prints exactly one of:
#     has     - the caller holds <permission>
#     absent  - a clean answer: the caller does NOT hold it (empty {} or a
#               permissions list without it)
#     error   - the probe itself could not return a decision (no curl / no token,
#               network failure, API disabled, HTTP != 200, or non-JSON body).
#               Callers should treat 'error' (and ONLY 'error') as grounds to fall
#               back to coarser role-name matching.
_caller_iam_permission() {
  local project="$1" perm="$2"
  command -v curl >/dev/null 2>&1 || { printf 'error\n'; return; }
  local token
  token="$(gcloud auth print-access-token 2>/dev/null || true)"
  [[ -n "${token}" ]] || { printf 'error\n'; return; }

  local url="https://cloudresourcemanager.googleapis.com/v1/projects/${project}:testIamPermissions"
  local raw http body
  # Append the HTTP status on its own trailing line so we can split it off.
  raw="$(curl -sS -X POST \
      -H "Authorization: Bearer ${token}" \
      -H "Content-Type: application/json" \
      -d "{\"permissions\":[\"${perm}\"]}" \
      -w $'\n%{http_code}' \
      "${url}" 2>/dev/null || true)"
  [[ -n "${raw}" ]] || { printf 'error\n'; return; }
  http="${raw##*$'\n'}"
  body="${raw%$'\n'*}"
  [[ "${http}" == "200" ]] || { printf 'error\n'; return; }

  # Parse the body robustly. Prefer a real JSON parser; fall back to a careful
  # grep only when neither python3 nor jq is available.
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "${body}" | python3 -c '
import sys, json
perm = sys.argv[1]
try:
    d = json.load(sys.stdin)
except Exception:
    print("error"); sys.exit(0)
if not isinstance(d, dict) or "error" in d:
    print("error"); sys.exit(0)
print("has" if perm in d.get("permissions", []) else "absent")
' "${perm}" 2>/dev/null || printf 'error\n'
    return
  fi
  if command -v jq >/dev/null 2>&1; then
    if ! printf '%s' "${body}" | jq -e . >/dev/null 2>&1; then printf 'error\n'; return; fi
    if printf '%s' "${body}" | jq -e 'has("error")' >/dev/null 2>&1; then printf 'error\n'; return; fi
    if printf '%s' "${body}" | jq -e --arg p "${perm}" '((.permissions // []) | index($p)) != null' >/dev/null 2>&1; then
      printf 'has\n'
    else
      printf 'absent\n'
    fi
    return
  fi
  # Careful grep fallback (no JSON parser present). Only a clearly-structured,
  # error-free object is trusted; anything else is reported as an error so the
  # caller falls back rather than mis-reading the response.
  if printf '%s' "${body}" | grep -q '"error"'; then printf 'error\n'; return; fi
  local esc="${perm//./\\.}"
  if printf '%s' "${body}" | grep -Eq "\"${esc}\""; then
    printf 'has\n'
  elif printf '%s' "${body}" | grep -q '{'; then
    printf 'absent\n'
  else
    printf 'error\n'
  fi
}

# --------------------------------------------------------------------------- #
# PRE-CHECKS — implement the DECIDED pre-check table (all 22). Classification is
# authoritative and must not be re-litigated here.
# --------------------------------------------------------------------------- #

# #1 gcloud present, authenticated, project resolvable (HARD-BLOCK)
precheck_1_gcloud() {
  if ! command -v gcloud >/dev/null 2>&1; then
    block "#1" "gcloud CLI present" "gcloud not found on PATH"
    return
  fi
  local active
  active="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null || true)"
  if [[ -z "${active}" ]]; then
    block "#1" "gcloud authenticated" "no ACTIVE credentialed account (run: gcloud auth login)"
    return
  fi
  if [[ -z "${PROJECT}" ]]; then
    block "#1" "project resolvable" "PROJECT_ID unset and gcloud config has no project"
    return
  fi
  GCLOUD_OK=1
  pass "#1" "gcloud ready" "account=${active} project=${PROJECT} region=${REGION}"
}

# #2 Required APIs enabled (HARD-BLOCK) + #2a single-source drift (WARN)
precheck_2_apis() {
  local required
  if ! required="$(read_required_apis)"; then
    block "#2" "required APIs" "cannot read single-source API list (${APIS_FILE})"
    return
  fi
  # #2a drift guard: apis.txt must match the Terraform-declared set.
  local tf_apis src_apis
  tf_apis="$(read_tf_apis 2>/dev/null || true)"
  src_apis="$(printf '%s\n' "${required}" | sort -u)"
  if [[ -n "${tf_apis}" ]]; then
    if [[ "${tf_apis}" == "${src_apis}" ]]; then
      pass "#2a" "API single-source" "apis.txt matches Terraform activate_apis default ($(printf '%s\n' "${src_apis}" | grep -c .) APIs)"
    else
      warn "#2a" "API single-source drift" "apis.txt differs from Terraform activate_apis default — reconcile the single source"
    fi
  else
    skip "#2a" "API single-source" "Terraform variables.tf not found; skipping drift comparison"
  fi

  # Conditional additions (#2): +secretmanager if secrets used.
  if [[ -n "${SECRET_ENV:-}" ]]; then
    required="${required}"$'\n'"secretmanager.googleapis.com"
  fi
  # +container for a GKE target (the GKE root enables container.googleapis.com;
  # apis.txt documents this as a target-conditional API). No-op for cloudrun.
  if [[ "${TARGET}" == "gke" ]]; then
    required="${required}"$'\n'"container.googleapis.com"
  fi

  if [[ "${GCLOUD_OK}" -eq 0 ]]; then
    skip "#2" "required APIs enabled" "unauthenticated — would verify $(printf '%s\n' "${required}" | grep -c .) APIs"
    return
  fi
  if [[ -z "${ENABLED_APIS_CACHE}" ]]; then
    ENABLED_APIS_CACHE="$(gcloud services list --enabled --project="${PROJECT}" \
      --format='value(config.name)' 2>/dev/null || true)"
  fi
  local api missing=""
  while IFS= read -r api; do
    [[ -z "${api}" ]] && continue
    if ! printf '%s\n' "${ENABLED_APIS_CACHE}" | grep -qx "${api}"; then
      missing="${missing} ${api}"
    fi
  done <<< "${required}"
  if [[ -n "${missing}" ]]; then
    block "#2" "required APIs enabled" "disabled:${missing}"
  else
    pass "#2" "required APIs enabled" "all $(printf '%s\n' "${required}" | grep -c .) required APIs enabled"
  fi
}

# #3 Hard-required env vars resolvable (HARD-BLOCK)
precheck_3_env() {
  local missing=""
  [[ -z "${PROJECT}" ]] && missing="${missing} PROJECT_ID"
  [[ -z "${GCS_ASSETS_BUCKET}" ]] && missing="${missing} GCS_ASSETS_BUCKET"
  [[ -z "${SERVICE_ACCOUNT_EMAIL}" ]] && missing="${missing} SERVICE_ACCOUNT_EMAIL"
  if [[ -n "${missing}" ]]; then
    block "#3" "hard-required env vars" "unresolved:${missing}"
  else
    pass "#3" "hard-required env vars" "PROJECT_ID/GCS_ASSETS_BUCKET/SERVICE_ACCOUNT_EMAIL all resolved"
  fi
}

# #4 Runtime SA exists (HARD-BLOCK)
precheck_4_runtime_sa() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then
    skip "#4" "runtime SA exists" "unauthenticated — would describe ${SERVICE_ACCOUNT_EMAIL}"; return
  fi
  if gcloud iam service-accounts describe "${SERVICE_ACCOUNT_EMAIL}" \
      --project="${PROJECT}" >/dev/null 2>&1; then
    pass "#4" "runtime SA exists" "${SERVICE_ACCOUNT_EMAIL}"
  else
    block "#4" "runtime SA exists" "not found: ${SERVICE_ACCOUNT_EMAIL}"
  fi
}

# #5 Runtime SA has serviceAccountTokenCreator on itself (HARD-BLOCK)
precheck_5_self_token_creator() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then
    skip "#5" "SA token-creator on self" "unauthenticated — would inspect SA IAM policy"; return
  fi
  # TF grants token-creator to the runtime SA at project scope (iam module),
  # which lets it self-impersonate; also accept a binding on the SA resource.
  if has_project_role "${SERVICE_ACCOUNT_EMAIL}" "roles/iam.serviceAccountTokenCreator" ||
     _has_binding "roles/iam.serviceAccountTokenCreator" "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
       gcloud iam service-accounts get-iam-policy "${SERVICE_ACCOUNT_EMAIL}" --project="${PROJECT}"; then
    pass "#5" "SA token-creator on self" "self-impersonation binding present (signed URLs)"
  else
    block "#5" "SA token-creator on self" "missing roles/iam.serviceAccountTokenCreator for the runtime SA"
  fi
}

# #6 Runtime SA has datastore.user (HARD-BLOCK)
precheck_6_datastore() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#6" "runtime SA datastore.user" "unauthenticated"; return; fi
  if has_project_role "${SERVICE_ACCOUNT_EMAIL}" "roles/datastore.user"; then
    pass "#6" "runtime SA datastore.user" "Firestore access present"
  else
    block "#6" "runtime SA datastore.user" "missing roles/datastore.user"
  fi
}

# #7 Runtime SA has aiplatform.user (HARD-BLOCK)
precheck_7_aiplatform() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#7" "runtime SA aiplatform.user" "unauthenticated"; return; fi
  if has_project_role "${SERVICE_ACCOUNT_EMAIL}" "roles/aiplatform.user"; then
    pass "#7" "runtime SA aiplatform.user" "Vertex generation access present"
  else
    block "#7" "runtime SA aiplatform.user" "missing roles/aiplatform.user"
  fi
}

# #8 Runtime SA has bucket object roles (HARD-BLOCK)
precheck_8_bucket_roles() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#8" "runtime SA bucket roles" "unauthenticated"; return; fi
  # `gcloud storage buckets get-iam-policy` does not accept --filter, so flatten
  # and filter client-side for the runtime SA's roles.
  local roles
  roles="$(gcloud storage buckets get-iam-policy "gs://${GCS_ASSETS_BUCKET}" \
    --flatten="bindings[].members" \
    --format="value[separator=' '](bindings.role,bindings.members)" 2>/dev/null |
    grep "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" || true)"
  if printf '%s' "${roles}" | grep -qE 'roles/storage.(objectViewer|objectCreator|objectUser|bucketViewer|objectAdmin)'; then
    pass "#8" "runtime SA bucket roles" "object role(s) present on gs://${GCS_ASSETS_BUCKET}"
  elif has_project_role "${SERVICE_ACCOUNT_EMAIL}" "roles/storage.objectViewer" ||
       has_project_role "${SERVICE_ACCOUNT_EMAIL}" "roles/storage.objectAdmin"; then
    pass "#8" "runtime SA bucket roles" "project-level storage object role present"
  else
    block "#8" "runtime SA bucket roles" "no object role for SA on gs://${GCS_ASSETS_BUCKET}"
  fi
}

# #9 Runtime SA has cloudtasks.enqueuer (WARN)
precheck_9_tasks_enqueuer() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#9" "runtime SA cloudtasks.enqueuer" "unauthenticated"; return; fi
  if has_project_role "${SERVICE_ACCOUNT_EMAIL}" "roles/cloudtasks.enqueuer"; then
    pass "#9" "runtime SA cloudtasks.enqueuer" "async thumbnail enqueue enabled"
  else
    warn "#9" "runtime SA cloudtasks.enqueuer" "missing — async thumbnail extraction will degrade"
  fi
}

# #10 Build SA exists + roles (HARD-BLOCK when building)
precheck_10_build_sa() {
  if [[ "${DO_BUILD}" -eq 0 ]]; then
    skip "#10" "build SA" "N/A — --no-build (deploying a pre-built image out-of-band)"; return
  fi
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then
    skip "#10" "build SA" "unauthenticated — would verify ${BUILD_SA_EMAIL} + roles"; return
  fi
  if ! gcloud iam service-accounts describe "${BUILD_SA_EMAIL}" --project="${PROJECT}" >/dev/null 2>&1; then
    block "#10" "build SA exists" "not found: ${BUILD_SA_EMAIL}"
    return
  fi
  # The build-SA bindings live at several scopes (Terraform iam +
  # cloud-run-service + artifact-registry modules): logging.logWriter at project,
  # serviceAccountUser on the runtime SA resource, run.developer on the service,
  # AR reader/writer on the repo. Check each at its real scope.
  local missing="" bsa_member="serviceAccount:${BUILD_SA_EMAIL}"
  has_project_role "${BUILD_SA_EMAIL}" "roles/logging.logWriter" ||
    missing="${missing} logging.logWriter(project)"
  _has_binding "roles/iam.serviceAccountUser" "${bsa_member}" \
    gcloud iam service-accounts get-iam-policy "${SERVICE_ACCOUNT_EMAIL}" --project="${PROJECT}" ||
    missing="${missing} serviceAccountUser(runtime-SA)"
  _has_binding "roles/run.developer" "${bsa_member}" \
    gcloud run services get-iam-policy "${SERVICE_NAME}" --project="${PROJECT}" --region="${REGION}" ||
    missing="${missing} run.developer(service)"
  { _has_binding "roles/artifactregistry.writer" "${bsa_member}" \
      gcloud artifacts repositories get-iam-policy "${AR_REPO}" --project="${PROJECT}" --location="${REGION}" ||
    _has_binding "roles/artifactregistry.reader" "${bsa_member}" \
      gcloud artifacts repositories get-iam-policy "${AR_REPO}" --project="${PROJECT}" --location="${REGION}"; } ||
    missing="${missing} artifactregistry.reader/writer(repo)"
  if [[ -n "${missing}" ]]; then
    block "#10" "build SA roles" "missing:${missing}"
  else
    pass "#10" "build SA roles" "logging.logWriter + act-as runtime SA + run.developer + AR access present"
  fi
}

# #10a classification helper: HARD-BLOCK in deploy mode (the build WILL fail),
# advisory WARN in check-only mode. --strict still promotes the WARN via warn().
_report_10a_missing() {
  local member="$1" grant="$2"
  local detail="${member} lacks cloudbuild.builds.create — 'gcloud builds submit' will PERMISSION_DENIED; grant with: ${grant}"
  if [[ "${MODE}" == "check" ]]; then
    warn "#10a" "caller can submit builds" "${detail}"
  else
    block "#10a" "caller can submit builds" "${detail}"
  fi
}

# #10a Invoking principal can submit Cloud Build builds (HARD-BLOCK when building
# in deploy mode / WARN in check-only). Distinct from #10: #10 validates the
# *build service account's* roles, whereas this verifies the *active principal*
# running deploy.sh can actually SUBMIT a build. A caller lacking
# cloudbuild.builds.create passes #10 but `gcloud builds submit` still returns
# PERMISSION_DENIED (observed on staging with a warm-up service account). Same
# conditionality as #10: build mode only (skipped under --no-build).
#
# The capability is confirmed with a REAL positive probe: Cloud Resource Manager
# testIamPermissions (REST) reports the subset of queried permissions the caller
# holds, INCLUDING grants inherited via Google groups or custom roles. Role-name
# matching is used ONLY as a fallback when the probe itself cannot return a
# decision (no curl/token, network, API disabled, non-JSON) — never on a clean
# "permission absent" answer, which is authoritative.
precheck_10a_caller_build() {
  if [[ "${DO_BUILD}" -eq 0 ]]; then
    skip "#10a" "caller can submit builds" "N/A — --no-build (no Cloud Build submission)"; return
  fi
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then
    skip "#10a" "caller can submit builds" "unauthenticated — would verify the active principal holds cloudbuild.builds.create"; return
  fi
  # Determine the active principal robustly (user or service account).
  local caller
  caller="$(gcloud config get-value account 2>/dev/null || true)"
  if [[ -z "${caller}" || "${caller}" == "(unset)" ]]; then
    caller="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n1 || true)"
  fi
  if [[ -z "${caller}" ]]; then
    block "#10a" "caller can submit builds" "cannot determine the active gcloud principal (run: gcloud auth login)"; return
  fi
  local member
  if [[ "${caller}" == *.gserviceaccount.com ]]; then
    member="serviceAccount:${caller}"
  else
    member="user:${caller}"
  fi
  local grant="gcloud projects add-iam-policy-binding ${PROJECT} --member=${member} --role=roles/cloudbuild.builds.editor"

  # Preferred: positive capability probe via Cloud Resource Manager
  # testIamPermissions (REST). It returns only the subset of the queried
  # permissions the CALLER actually holds — capturing inherited/group and
  # custom-role grants too, which role-name matching on a direct project binding
  # would miss. A clean "absent" answer is authoritative (BLOCK/WARN, no
  # fallback); only a probe ERROR falls through to role-name matching.
  local probe
  probe="$(_caller_iam_permission "${PROJECT}" cloudbuild.builds.create)"
  case "${probe}" in
    has)
      pass "#10a" "caller can submit builds" "${member} holds cloudbuild.builds.create (testIamPermissions probe)"
      return
      ;;
    absent)
      _report_10a_missing "${member}" "${grant}"
      return
      ;;
    *)
      : # probe could not decide (no curl/token, network, API disabled, non-JSON)
      ;;
  esac

  # Fallback (probe errored — offline / no curl / resourcemanager path blocked):
  # match membership in a project-scope role that grants cloudbuild.builds.create.
  # Coarser than the probe — it cannot see group/custom-role grants — so it runs
  # only when the probe itself failed to return a decision.
  local role
  for role in roles/cloudbuild.builds.editor roles/cloudbuild.builds.builder roles/owner roles/editor; do
    if _has_binding "${role}" "${member}" gcloud projects get-iam-policy "${PROJECT}"; then
      pass "#10a" "caller can submit builds" "${member} has ${role} (grants cloudbuild.builds.create)"
      return
    fi
  done
  _report_10a_missing "${member}" "${grant}"
}

# #11 Firestore Native DB exists (HARD-BLOCK)
precheck_11_firestore_db() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#11" "Firestore DB exists" "unauthenticated"; return; fi
  if gcloud firestore databases describe --database="${FIRESTORE_DB}" \
      --project="${PROJECT}" >/dev/null 2>&1; then
    pass "#11" "Firestore DB exists" "${FIRESTORE_DB}"
  else
    block "#11" "Firestore DB exists" "not found: ${FIRESTORE_DB}"
  fi
}

# #12 Firestore composite genmedia indexes present (WARN)
precheck_12_indexes() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#12" "Firestore composite indexes" "unauthenticated"; return; fi
  local count
  count="$(gcloud firestore indexes composite list --database="${FIRESTORE_DB}" \
    --project="${PROJECT}" --format='value(name)' 2>/dev/null | grep -c . || true)"
  count="${count:-0}"
  if [[ "${count}" -ge "${EXPECTED_INDEX_COUNT}" ]]; then
    pass "#12" "Firestore composite indexes" "${count} composite index(es) present (>= ${EXPECTED_INDEX_COUNT})"
  else
    warn "#12" "Firestore composite indexes" "only ${count}/${EXPECTED_INDEX_COUNT} present — some queries may FAILED_PRECONDITION"
  fi
}

# #13 GCS assets bucket exists (HARD-BLOCK)
precheck_13_bucket() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#13" "assets bucket exists" "unauthenticated"; return; fi
  if gcloud storage buckets describe "gs://${GCS_ASSETS_BUCKET}" >/dev/null 2>&1; then
    pass "#13" "assets bucket exists" "gs://${GCS_ASSETS_BUCKET}"
  else
    block "#13" "assets bucket exists" "not found: gs://${GCS_ASSETS_BUCKET}"
  fi
}

# #14 Assets bucket PAP=enforced + uniform BLA (WARN)
precheck_14_bucket_posture() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#14" "assets bucket posture" "unauthenticated"; return; fi
  local desc pap ubla
  desc="$(gcloud storage buckets describe "gs://${GCS_ASSETS_BUCKET}" \
    --format='value(public_access_prevention,uniform_bucket_level_access)' 2>/dev/null || true)"
  pap="$(printf '%s' "${desc}" | awk '{print $1}')"
  ubla="$(printf '%s' "${desc}" | awk '{print $2}')"
  if [[ "${pap}" == "enforced" && "${ubla}" == "True" ]]; then
    pass "#14" "assets bucket posture" "public_access_prevention=enforced, uniform BLA on"
  else
    warn "#14" "assets bucket posture" "pap=${pap:-unknown} uniform_bla=${ubla:-unknown} (recommend enforced + uniform)"
  fi
}

# #15 Cloud Tasks queue exists (WARN)
precheck_15_tasks_queue() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#15" "tasks queue exists" "unauthenticated"; return; fi
  if gcloud tasks queues describe "${TASKS_QUEUE}" --location="${REGION}" \
      --project="${PROJECT}" >/dev/null 2>&1; then
    pass "#15" "tasks queue exists" "${TASKS_QUEUE} (${REGION})"
  else
    warn "#15" "tasks queue exists" "not found: ${TASKS_QUEUE} — async thumbnails degrade"
  fi
}

# #16 Artifact Registry repo (AUTO-REMEDIATE)
precheck_16_ar_repo() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#16" "Artifact Registry repo" "unauthenticated"; return; fi
  if gcloud artifacts repositories describe "${AR_REPO}" --location="${REGION}" \
      --project="${PROJECT}" >/dev/null 2>&1; then
    pass "#16" "Artifact Registry repo" "${AR_REPO} (${REGION})"
    return
  fi
  if [[ "${MODE}" == "check" ]]; then
    warn "#16" "Artifact Registry repo" "absent — would AUTO-REMEDIATE (create) on deploy"
    return
  fi
  info "#16 auto-remediating: creating Artifact Registry repo '${AR_REPO}' in ${REGION}..."
  if gcloud artifacts repositories create "${AR_REPO}" --repository-format=docker \
      --location="${REGION}" --project="${PROJECT}" \
      --description="GenMedia Creative Studio images (auto-created by deploy.sh)" >/dev/null 2>&1; then
    pass "#16" "Artifact Registry repo" "created ${AR_REPO} (${REGION})"
  else
    block "#16" "Artifact Registry repo" "auto-remediate create FAILED for ${AR_REPO}"
  fi
}

# #17 AR image exists for target tag (WARN when building / HARD-BLOCK deploy-only)
precheck_17_image() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#17" "target image exists" "unauthenticated"; return; fi
  local img_base="${REGION}-docker.pkg.dev/${PROJECT}/${IMAGE_PATH}"
  # --image (digest) path: gate on digest existence using the same list-based
  # probe (metadata-only, no container-analysis perm). Only runs when --image is
  # given; the tag path below is unchanged. --image always implies --no-build, so
  # a missing digest is a HARD-BLOCK (nothing to deploy).
  if [[ -n "${IMAGE_DIGEST}" ]]; then
    local want="${IMAGE_DIGEST##*@}"                 # strip any full-ref prefix
    [[ "${want}" == sha256:* ]] || want="sha256:${want}"
    local digs
    digs="$(gcloud artifacts docker images list "${img_base}" \
      --include-tags --format='value(version)' 2>/dev/null || true)"
    if grep -Fxq -- "${want}" <<<"${digs}"; then
      pass "#17" "target image exists" "${img_base}@${want}"
    else
      block "#17" "target image exists" "digest absent and --no-build: nothing to deploy (${img_base}@${want})"
    fi
    return
  fi
  # Probe existence with `artifacts docker images list --include-tags`, which needs
  # only artifact-registry list/read permission. The former `... images describe`
  # additionally requires containeranalysis.occurrences.list and FALSE-BLOCKED
  # --no-build on staging when the caller lacked that permission even though the
  # image provably existed. Match the requested tag against the listed tags
  # client-side (exact equality, avoiding substring false-positives a server-side
  # filter's `has` operator would allow).
  # Normalize the listed tags into one-per-line in a variable FIRST, then match
  # with a here-string. Piping directly into `grep -Fxq` is unsound under
  # `set -o pipefail`: grep exits on first match and SIGPIPEs the upstream
  # tr/sed, flipping the pipeline's status non-zero and FALSE-BLOCKING a present
  # image. A here-string gives grep no upstream pipe to break.
  local tags_out norm
  tags_out="$(gcloud artifacts docker images list "${img_base}" \
    --include-tags --format='value(tags)' 2>/dev/null || true)"
  norm="$(printf '%s\n' "${tags_out}" | tr ',;' '\n' | sed 's/[[:space:]]//g')"
  # Guard against an empty --tag: grep -Fx "" would match a blank tag line and
  # falsely PASS. A real image tag is never empty.
  if [[ -n "${IMAGE_TAG}" ]] && grep -Fxq -- "${IMAGE_TAG}" <<<"${norm}"; then
    pass "#17" "target image exists" "${img_base}:${IMAGE_TAG}"
  elif [[ "${DO_BUILD}" -eq 1 ]]; then
    warn "#17" "target image exists" "absent — expected; this run will build ${IMAGE_TAG}"
  else
    block "#17" "target image exists" "absent and --no-build: nothing to deploy (${img_base}:${IMAGE_TAG})"
  fi
}

# #18 TF state backend bucket (HARD-BLOCK existence / WARN versioning) — only when fronting TF
precheck_18_tf_state() {
  if [[ -z "${TF_STATE_BUCKET:-}" ]]; then
    skip "#18" "TF state backend" "N/A — script does not front a terraform apply (set TF_STATE_BUCKET to enable)"
    return
  fi
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#18" "TF state backend" "unauthenticated"; return; fi
  local ver
  if ! gcloud storage buckets describe "gs://${TF_STATE_BUCKET}" >/dev/null 2>&1; then
    block "#18" "TF state backend exists" "not found: gs://${TF_STATE_BUCKET} (terraform init would fail)"
    return
  fi
  ver="$(gcloud storage buckets describe "gs://${TF_STATE_BUCKET}" \
    --format='value(versioning.enabled)' 2>/dev/null || true)"
  if [[ "${ver}" == "True" ]]; then
    pass "#18" "TF state backend" "gs://${TF_STATE_BUCKET} exists, versioning enabled"
  else
    warn "#18" "TF state versioning" "gs://${TF_STATE_BUCKET} exists but versioning disabled (recoverability risk)"
  fi
}

# #19 Referenced Secret Manager secrets exist + accessor (HARD-BLOCK) — only for migrated vars
precheck_19_secrets() {
  if [[ -z "${SECRET_ENV:-}" ]]; then
    pass "#19" "secret references" "no-op — no vars migrated to Secret Manager"
    return
  fi
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#19" "secret references" "unauthenticated"; return; fi
  local s missing=""
  IFS=',' read -ra _secrets <<< "${SECRET_ENV}"
  for s in "${_secrets[@]}"; do
    s="$(printf '%s' "${s}" | sed 's/[[:space:]]//g')"
    [[ -z "${s}" ]] && continue
    gcloud secrets describe "${s}" --project="${PROJECT}" >/dev/null 2>&1 || missing="${missing} ${s}"
  done
  if [[ -n "${missing}" ]]; then
    block "#19" "secret references" "missing secret(s):${missing} (revision would fail to start)"
  else
    pass "#19" "secret references" "all referenced secrets exist"
  fi
}

# #20 Vertex AI service agent present (WARN)
precheck_20_vertex_agent() {
  if [[ "${GCLOUD_OK}" -eq 0 ]]; then skip "#20" "Vertex AI service agent" "unauthenticated"; return; fi
  if _role_present "roles/aiplatform.serviceAgent" gcloud projects get-iam-policy "${PROJECT}"; then
    pass "#20" "Vertex AI service agent" "roles/aiplatform.serviceAgent present"
  else
    warn "#20" "Vertex AI service agent" "not found — normally TF/auto-provisioned; some Vertex features may fail"
  fi
}

# #21 Quota headroom (WARN — cannot be reliably pre-checked)
precheck_21_quota() {
  warn "#21" "quota headroom" "not reliably pre-checkable (cpu=2000m,mem=4Gi) — a real shortfall surfaces at deploy"
}

# #22 REQUIRE_AUTHENTICATED_USER resolves enforced for a prod target (WARN)
precheck_22_auth_resolution() {
  local app_env="${APP_ENV:-}" enforced target_is_prod="no" configured="${REQUIRE_AUTHENTICATED_USER:-}"
  if [[ -n "${configured}" ]]; then
    case "$(printf '%s' "${configured}" | tr '[:upper:]' '[:lower:]')" in
      1|true|yes|on) enforced="yes" ;; *) enforced="no" ;;
    esac
  else
    case "${app_env}" in
      ""|dev|development|local|test) enforced="no" ;; *) enforced="yes" ;;
    esac
  fi
  case "$(printf '%s' "${app_env}" | tr '[:upper:]' '[:lower:]')" in
    prod|production|staging) target_is_prod="yes" ;;
  esac
  if [[ "${target_is_prod}" == "yes" && "${enforced}" == "no" ]]; then
    warn "#22" "auth enforcement" "APP_ENV='${app_env}' looks prod-like but auth resolves DISABLED (security smell)"
  else
    pass "#22" "auth enforcement" "APP_ENV='${app_env:-<unset>}' -> REQUIRE_AUTHENTICATED_USER enforced=${enforced}"
  fi
}

run_prechecks() {
  info "== Pre-flight checks (§4.2) — mode=${MODE} strict=${STRICT} build=${DO_BUILD} =="
  hr
  precheck_1_gcloud
  precheck_2_apis
  precheck_3_env
  precheck_4_runtime_sa
  precheck_5_self_token_creator
  precheck_6_datastore
  precheck_7_aiplatform
  precheck_8_bucket_roles
  precheck_9_tasks_enqueuer
  precheck_10_build_sa
  precheck_10a_caller_build
  precheck_11_firestore_db
  precheck_12_indexes
  precheck_13_bucket
  precheck_14_bucket_posture
  precheck_15_tasks_queue
  precheck_16_ar_repo
  precheck_17_image
  precheck_18_tf_state
  precheck_19_secrets
  precheck_20_vertex_agent
  precheck_21_quota
  precheck_22_auth_resolution
  hr
  info "Pre-check summary: ${PASS_COUNT} pass, ${WARN_COUNT} warn, ${BLOCK_COUNT} block"
}

# --------------------------------------------------------------------------- #
# BUILD + DEPLOY (wraps the existing cloudbuild.yaml / gcloud run deploy flow).
# --------------------------------------------------------------------------- #
do_build() {
  info "== Build (Cloud Build, cloudbuild.yaml) =="
  if [[ ! -f "${CLOUDBUILD_CONFIG}" ]]; then
    log "ERROR: ${CLOUDBUILD_CONFIG} not found"; return 1
  fi
  # Compute the immutable version tag once and pass it (plus the moving tag via
  # _IMAGE_NAME) to cloudbuild.yaml, which builds once and pushes BOTH refs to the
  # same digest. The moving tag (default :latest) preserves the existing default UX.
  VERSION_TAG="$(compute_version_tag)"
  info "Build tags: ${IMAGE_PATH}:${IMAGE_TAG} (moving) + ${IMAGE_PATH}:${VERSION_TAG} (immutable)"
  gcloud builds submit "${REPO_ROOT}" \
    --project="${PROJECT}" \
    --region="${REGION}" \
    --config="${CLOUDBUILD_CONFIG}" \
    --substitutions="_IMAGE_NAME=${IMAGE_PATH}:${IMAGE_TAG},_VERSION_TAG=${VERSION_TAG}"
}

# list-versions: read-only listing of the repo's image versions (tags + digest +
# create time), newest first. Backed by `artifacts docker images list
# --include-tags` (metadata-only; needs roles/artifactregistry.reader on the
# repo — see deploy.md). Used to pick a prior version/digest for a rollback.
do_list_versions() {
  if ! command -v gcloud >/dev/null 2>&1; then
    log "ERROR: gcloud not found on PATH"; return "${EXIT_USAGE}"
  fi
  if [[ -z "${PROJECT}" ]]; then
    log "ERROR: project not resolvable (set --project, \$PROJECT_ID, or gcloud config)"; return "${EXIT_USAGE}"
  fi
  local repo_path="${REGION}-docker.pkg.dev/${PROJECT}/${IMAGE_PATH}"
  info "== Artifact Registry image versions (newest first) — ${repo_path} =="
  if ! gcloud artifacts docker images list "${repo_path}" \
      --include-tags \
      --sort-by="~CREATE_TIME" \
      --format="table(version.basename():label=DIGEST, tags.list():label=TAGS, createTime.date('%Y-%m-%dT%H:%M:%SZ'):label=CREATE_TIME)"; then
    log "ERROR: failed to list image versions for ${repo_path}"
    log "       (does the active principal hold roles/artifactregistry.reader on the repo?)"
    return "${EXIT_USAGE}"
  fi
  return "${EXIT_OK}"
}

do_deploy() {
  info "== Deploy (gcloud run deploy — MCP idempotent shape, private by default) =="
  gcloud run deploy "${SERVICE_NAME}" \
    --project="${PROJECT}" \
    --region="${REGION}" \
    --image="$(image_ref)" \
    --port=8080 \
    --no-allow-unauthenticated \
    --timeout=3600 \
    --quiet
}

# --------------------------------------------------------------------------- #
# POST-CHECKS. Non-zero exit on any failure.
# --------------------------------------------------------------------------- #
POST_FAIL=0

resolve_service_url() {
  gcloud run services describe "${SERVICE_NAME}" --project="${PROJECT}" \
    --region="${REGION}" --format='value(status.url)' 2>/dev/null || true
}

http_code() { curl -s -o /dev/null -m 15 -w '%{http_code}' "$@" 2>/dev/null || echo "000"; }

# 1. Health poll of /healthz and /readyz (auth-exempt) until ok or timeout.
postcheck_health() {
  local base="$1" timeout="${HEALTH_TIMEOUT:-${HEALTH_TIMEOUT_DEFAULT}}"
  local host_base="${base}"
  [[ -n "${LB_HOST:-}" ]] && host_base="https://${LB_HOST}"
  info "-- health poll (${host_base}) timeout=${timeout}s --"
  local path code deadline now ok
  for path in /healthz /readyz; do
    ok=0
    deadline=$(( $(date +%s) + timeout ))
    while :; do
      code="$(http_code "${host_base}${path}")"
      if [[ "${code}" == "200" ]]; then
        pass "post" "health ${path}" "200 OK at ${host_base}${path}"; ok=1; break
      fi
      now=$(date +%s)
      [[ "${now}" -ge "${deadline}" ]] && break
      sleep "${HEALTH_INTERVAL}"
    done
    if [[ "${ok}" -eq 0 ]]; then
      block "post" "health ${path}" "did not return 200 within ${timeout}s (last=${code})"
      POST_FAIL=1
    fi
  done
}

# 2. Auth-wiring smoke: protected path 401 without identity (always-available
#    negative signal); 200 with an IAP OIDC token where one can be minted.
postcheck_auth() {
  local base="$1"
  local host_base="${base}"
  [[ -n "${LB_HOST:-}" ]] && host_base="https://${LB_HOST}"
  info "-- auth-wiring smoke (${host_base}/home) --"
  local code
  code="$(http_code "${host_base}/home")"
  case "${code}" in
    401)
      pass "post" "auth negative" "/home -> 401 without identity (app auth enforced)" ;;
    302|303|307)
      pass "post" "auth negative" "/home -> ${code} redirect (IAP/LB auth enforced upstream)" ;;
    200)
      block "post" "auth negative" "/home -> 200 WITHOUT identity — endpoint appears OPEN"; POST_FAIL=1 ;;
    *)
      warn "post" "auth negative" "/home -> ${code} (unexpected; verify manually)" ;;
  esac
  if [[ -n "${IAP_ID_TOKEN:-}" ]]; then
    code="$(http_code -H "Authorization: Bearer ${IAP_ID_TOKEN}" "${host_base}/home")"
    if [[ "${code}" == "200" ]]; then
      pass "post" "auth positive" "/home -> 200 with IAP OIDC token"
    else
      warn "post" "auth positive" "/home -> ${code} with provided token (verify token/audience)"
    fi
  else
    skip "post" "auth positive" "no IAP_ID_TOKEN provided — positive smoke skipped (negative signal is authoritative)"
  fi
}

# 3b. GKE rollout check (--target gke): Deployment rolled out + ingress address
#     ready. The GKE analogue of the Cloud Run revision/traffic check.
postcheck_rollout_gke() {
  info "-- GKE rollout / ingress check (deploy/${SERVICE_NAME}, ns=${NAMESPACE}) --"
  if ! command -v kubectl >/dev/null 2>&1; then
    warn "post" "GKE rollout" "kubectl not found — cannot verify rollout (run: gcloud container clusters get-credentials)"
    return
  fi
  local timeout="${HEALTH_TIMEOUT:-${HEALTH_TIMEOUT_DEFAULT}}"
  if kubectl rollout status "deploy/${SERVICE_NAME}" -n "${NAMESPACE}" \
      --timeout="${timeout}s" >/dev/null 2>&1; then
    pass "post" "GKE rollout" "deploy/${SERVICE_NAME} rolled out (ns=${NAMESPACE})"
  else
    block "post" "GKE rollout" "deploy/${SERVICE_NAME} did not complete rollout within ${timeout}s"
    POST_FAIL=1
  fi
  # Ingress address readiness (the GCLB IP GKE assigns once the LB is programmed).
  local ing_addr
  ing_addr="$(kubectl get ingress "${SERVICE_NAME}" -n "${NAMESPACE}" \
    -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
  if [[ -n "${ing_addr}" ]]; then
    pass "post" "GKE ingress address" "ingress ${SERVICE_NAME} has address ${ing_addr}"
  else
    warn "post" "GKE ingress address" "ingress ${SERVICE_NAME} has no address yet (LB still programming / cert provisioning)"
  fi
}

# 3. Revision/traffic check: new revision serving 100% of traffic.
postcheck_revision() {
  # --target gke swaps this Cloud-Run-specific check for the GKE rollout check.
  if [[ "${TARGET}" == "gke" ]]; then
    postcheck_rollout_gke
    return
  fi
  info "-- revision / traffic check --"
  local latest serving pct
  latest="$(gcloud run services describe "${SERVICE_NAME}" --project="${PROJECT}" \
    --region="${REGION}" --format='value(status.latestReadyRevisionName)' 2>/dev/null || true)"
  serving="$(gcloud run services describe "${SERVICE_NAME}" --project="${PROJECT}" \
    --region="${REGION}" --format='value(status.traffic[0].revisionName)' 2>/dev/null || true)"
  pct="$(gcloud run services describe "${SERVICE_NAME}" --project="${PROJECT}" \
    --region="${REGION}" --format='value(status.traffic[0].percent)' 2>/dev/null || true)"
  if [[ -n "${latest}" && "${pct}" == "100" ]]; then
    pass "post" "revision/traffic" "latest=${latest} serving=${serving} (100%)"
  else
    block "post" "revision/traffic" "latest=${latest:-?} serving=${serving:-?} pct=${pct:-?} (expected latest at 100%)"
    POST_FAIL=1
  fi
}

run_postchecks() {
  info "== Post-deploy checks (§4.3) =="
  hr
  local url
  # For --target gke there is no Cloud Run service to describe; the ingress host
  # is supplied via LB_HOST (health/auth post-checks already key off it).
  if [[ "${TARGET}" == "gke" ]]; then
    url=""
  else
    url="$(resolve_service_url)"
  fi
  if [[ -z "${url}" && -z "${LB_HOST:-}" ]]; then
    block "post" "service url" "could not resolve status.url for ${SERVICE_NAME}"
    POST_FAIL=1
  else
    postcheck_health "${url}"
    postcheck_auth "${url}"
  fi
  postcheck_revision
  hr
}

# --------------------------------------------------------------------------- #
# Main.
# --------------------------------------------------------------------------- #
main() {
  parse_args "$@"
  resolve_config

  # list-versions is a read-only query, not a deploy: skip the pre-check gate and
  # just list the repo's image versions.
  if [[ "${MODE}" == "list-versions" ]]; then
    do_list_versions
    exit "$?"
  fi

  run_prechecks

  if [[ "${BLOCK_COUNT}" -gt 0 ]]; then
    log ""
    log "${C_RED}RESULT: ${BLOCK_COUNT} HARD-BLOCK pre-check(s) failed — refusing to deploy.${C_NC}"
    exit "${EXIT_PRECHECK}"
  fi

  if [[ "${MODE}" == "check" ]]; then
    log ""
    log "${C_GRN}RESULT: pre-checks passed (check-only). No deploy performed.${C_NC}"
    exit "${EXIT_OK}"
  fi

  # deploy mode.
  # GKE provisioning + image roll-out is Terraform's job (deploy/terraform/gke);
  # the --target gke deploy path runs the post-deploy smoke only, against the
  # already-applied ingress (LB_HOST). The Cloud Run build+deploy block below is
  # unchanged and only runs for the (default) cloudrun target.
  if [[ "${TARGET}" == "gke" ]]; then
    info "Target gke: skipping Cloud Run build/deploy (provisioning is Terraform's job); running post-deploy smoke."
  else
    if [[ "${DO_BUILD}" -eq 1 ]]; then
      if ! do_build; then
        log "${C_RED}RESULT: build failed.${C_NC}"; exit "${EXIT_DEPLOY}"
      fi
    else
      info "Skipping build (--no-build); deploying existing image $(image_ref)"
    fi
    if ! do_deploy; then
      log "${C_RED}RESULT: deploy failed.${C_NC}"; exit "${EXIT_DEPLOY}"
    fi
  fi

  run_postchecks
  if [[ "${POST_FAIL}" -ne 0 ]]; then
    log "${C_RED}RESULT: deploy completed but post-checks FAILED.${C_NC}"
    exit "${EXIT_POSTCHECK}"
  fi
  log "${C_GRN}RESULT: deploy + post-checks succeeded.${C_NC}"
  exit "${EXIT_OK}"
}

# Run main only when executed, not when sourced (lets the pure helpers — e.g.
# compute_version_tag — be unit-tested without side effects). When executed,
# BASH_SOURCE[0] == $0, so behavior is unchanged.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
