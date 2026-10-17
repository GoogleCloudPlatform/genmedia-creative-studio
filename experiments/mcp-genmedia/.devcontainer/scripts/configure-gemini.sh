#!/usr/bin/env bash
set -euo pipefail

template_path="/usr/local/share/mcp-genmedia-devcontainer/templates/gemini-extension.json"
extension_dir="${HOME}/.gemini/extensions/google-genmedia-devcontainer"

# Project: GOOGLE_CLOUD_PROJECT is preferred; PROJECT_ID is the legacy fallback
# (see ENV_VARS.md). Fall back to the active gcloud config if neither is set.
project_id="${GOOGLE_CLOUD_PROJECT:-${PROJECT_ID:-}}"
if [[ -z "${project_id}" ]] && command -v gcloud >/dev/null 2>&1; then
  project_id="$(gcloud config get-value project 2>/dev/null || true)"
fi

# Location: GOOGLE_CLOUD_LOCATION is preferred; LOCATION is the fallback.
location="${GOOGLE_CLOUD_LOCATION:-${LOCATION:-us-central1}}"

# The Gemini server defaults to the global endpoint (see #1591); GEMINI_LOCATION
# overrides it per-server. Default to "global" here, allowing host override.
gemini_location="${GEMINI_LOCATION:-global}"

genmedia_bucket="${GENMEDIA_BUCKET:-}"
if [[ -z "${genmedia_bucket}" && -n "${project_id}" ]]; then
  genmedia_bucket="gs://${project_id}-mcp-genmedia"
fi

# Export the settings the v3.x extension declares (GOOGLE_CLOUD_PROJECT,
# GENMEDIA_BUCKET) plus location vars, so the MCP servers — which read the
# process environment directly — pick them up at runtime.
export GOOGLE_CLOUD_PROJECT="${project_id}"
export GENMEDIA_BUCKET="${genmedia_bucket}"
export GOOGLE_CLOUD_LOCATION="${location}"
export GEMINI_LOCATION="${gemini_location}"

mkdir -p "${extension_dir}"
# The settings-based v3.x extension carries project/bucket via the top-level
# `settings` block (resolved from the environment), so only GEMINI_LOCATION is
# templated into the extension.
envsubst '${GEMINI_LOCATION}' \
  < "${template_path}" \
  > "${extension_dir}/gemini-extension.json"

echo "Configured Gemini CLI extension at ${extension_dir}/gemini-extension.json"
echo "GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT:-unset}"
echo "GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION}"
echo "GEMINI_LOCATION=${GEMINI_LOCATION}"
echo "GENMEDIA_BUCKET=${GENMEDIA_BUCKET:-unset}"
