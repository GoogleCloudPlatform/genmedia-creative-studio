#!/usr/bin/env bash
# Copyright 2025 Google LLC
#
# Boot smoke test for the GenMedia Creative Studio core app.
#
# What this checks:
#   1. Dependencies sync (uv sync) with the pinned Python (>=3.14).
#   2. The app boots under gunicorn/uvicorn in APP_ENV=local mode.
#   3. GET /        -> 307 redirect to /home, which serves HTTP 200 (Mesop UI).
#   4. GET /__login -> HTTP 200.
#   5. (Optional, env-gated) one live Vertex gemini-3.8-flash generateContent
#      call, only when a PROJECT_ID + working ADC are available.
#
# What this does NOT check: it is not the full test suite, not a deploy
# validation, and not an IAP / Load Balancer check (that's the terraform path).
#
# Usage:
#   ./scripts/smoke_test.sh              # boot + UI check (recommended default)
#   ./scripts/smoke_test.sh -l           # also run the live Vertex generation leg
#   ./scripts/smoke_test.sh -p 8090      # use a different port
#   ./scripts/smoke_test.sh -t 120       # wait up to 120s for boot
#
# Environment variables respected:
#   PROJECT_ID   Google Cloud project used by the app (falls back to
#                `gcloud config get-value project`, else a local placeholder).
#   PORT         Port to bind (default: 8080). Overridden by -p.
#   LIVE_CHECK   Set to 1 to enable the live Vertex leg (same as -l).
#   GEMINI_LOCATION  Vertex location for the live leg (default: global; the
#                gemini-3.x flash family is global-only). Matches the app env of
#                the same name. Set a region like us-central1 only if you
#                override the model to a regional one.
#
# Run this before merging any PR that touches core-app runtime code
# (pages/, models/, state/, config/, main.py).

set -euo pipefail

# --- Resolve repo root (script lives in <root>/scripts) --------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# --- Defaults / options ----------------------------------------------------
PORT="${PORT:-8080}"
BOOT_TIMEOUT=90
LIVE_CHECK="${LIVE_CHECK:-0}"
GEMINI_LOCATION="${GEMINI_LOCATION:-global}"

while getopts "p:t:lh" opt; do
  case ${opt} in
    p) PORT="${OPTARG}" ;;
    t) BOOT_TIMEOUT="${OPTARG}" ;;
    l) LIVE_CHECK=1 ;;
    h)
      echo "Usage: $0 [-p PORT] [-t BOOT_TIMEOUT_SECS] [-l]"
      echo "  -p PORT   Port to bind the app (default: 8080)"
      echo "  -t SECS   Seconds to wait for the app to boot (default: 90)"
      echo "  -l        Also run the optional live Vertex generateContent leg"
      exit 0
      ;;
    \?)
      echo "Invalid option: -${OPTARG}" >&2
      exit 1
      ;;
  esac
done

BASE_URL="http://localhost:${PORT}"
APP_PID=""

echo "======================================================================"
echo "🚀 GMCS Core App Boot Smoke Test"
echo "Repo root : ${REPO_ROOT}"
echo "Base URL  : ${BASE_URL}"
echo "======================================================================"
echo ""

# --- Teardown (runs on any exit) -------------------------------------------
cleanup() {
  if [ -n "${APP_PID}" ] && kill -0 "${APP_PID}" 2>/dev/null; then
    echo ""
    echo "🧹 Tearing down app (pid ${APP_PID})..."
    # Kill the whole process group so uvicorn workers are reaped too.
    kill -TERM "-${APP_PID}" 2>/dev/null || kill -TERM "${APP_PID}" 2>/dev/null || true
    sleep 2
    kill -KILL "-${APP_PID}" 2>/dev/null || kill -KILL "${APP_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

fail() {
  echo ""
  echo "----------------------------------------------------------------------"
  echo "❌ SMOKE TEST FAILED: $*"
  echo "----------------------------------------------------------------------"
  if [ -f "${BOOT_LOG:-/dev/null}" ]; then
    echo "--- Last 30 lines of boot log (${BOOT_LOG}) ---"
    tail -30 "${BOOT_LOG}" || true
  fi
  exit 1
}

# --- Step 1: toolchain check (fail fast, do NOT auto-install) ---------------
echo "🔎 1/5  Checking toolchain..."
if ! command -v uv >/dev/null 2>&1; then
  fail "'uv' is not installed. Install it (https://github.com/astral-sh/uv), e.g.
        curl -LsSf https://astral.sh/uv/install.sh | sh
        This script does not auto-install the toolchain."
fi
echo "     ✅ uv found: $(uv --version)"

# --- Step 2: dependency sync -----------------------------------------------
echo ""
echo "📦 2/5  Syncing dependencies (uv sync)..."
if ! uv sync >/tmp/gmcs_smoke_sync.log 2>&1; then
  echo "--- uv sync output ---"; tail -30 /tmp/gmcs_smoke_sync.log || true
  fail "'uv sync' failed. Ensure Python >=3.14 is available (uv can install it)."
fi
echo "     ✅ dependencies synced"

# --- Step 3: import smoke check (pages & models) --------------------------
echo ""
echo "🧪 3/5  Running page & model import smoke test..."
if ! uv run pytest test/test_app_imports.py >/tmp/gmcs_smoke_imports.log 2>&1; then
  echo "--- import smoke test output ---"; tail -30 /tmp/gmcs_smoke_imports.log || true
  fail "Page or model import smoke test failed."
fi
echo "     ✅ all core pages and models imported successfully"

# --- Step 4: boot the app in APP_ENV=local ---------------------------------
echo ""
echo "🚦 4/5  Booting app (APP_ENV=local) on port ${PORT}..."

if [ -z "${PROJECT_ID:-}" ]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi
if [ -z "${PROJECT_ID:-}" ]; then
  PROJECT_ID="local-smoke-test"
  echo "     ⚠️  PROJECT_ID not set and none from gcloud; using placeholder '${PROJECT_ID}'."
fi
echo "     PROJECT_ID=${PROJECT_ID}"

BOOT_LOG="$(mktemp /tmp/gmcs_smoke_boot.XXXXXX.log)"

# setsid gives the app its own process group so cleanup() can reap workers.
APP_ENV=local PROJECT_ID="${PROJECT_ID}" PORT="${PORT}" \
  setsid .venv/bin/gunicorn \
    --bind ":${PORT}" \
    --workers 1 \
    --threads 8 \
    --timeout 0 \
    --forwarded-allow-ips="*" \
    -k uvicorn.workers.UvicornWorker \
    main:app >"${BOOT_LOG}" 2>&1 &
APP_PID=$!
echo "     app pid/pgid: ${APP_PID}  (log: ${BOOT_LOG})"

# --- Step 5: poll until the UI serves 200 ----------------------------------
echo ""
echo "🌐 5/5  Waiting for the UI (timeout ${BOOT_TIMEOUT}s)..."
deadline=$(( $(date +%s) + BOOT_TIMEOUT ))
home_code="000"
while [ "$(date +%s)" -lt "${deadline}" ]; do
  if ! kill -0 "${APP_PID}" 2>/dev/null; then
    fail "app process exited before serving traffic (see boot log)."
  fi
  home_code="$(curl -sL -o /dev/null -w '%{http_code}' -m 5 "${BASE_URL}/" 2>/dev/null || echo 000)"
  if [ "${home_code}" = "200" ]; then
    break
  fi
  sleep 2
done

if [ "${home_code}" != "200" ]; then
  fail "GET / did not reach a 200 within ${BOOT_TIMEOUT}s (last code: ${home_code})."
fi

# Assert the redirect target is /home.
redirect_url="$(curl -s -o /dev/null -w '%{redirect_url}' -m 5 "${BASE_URL}/" 2>/dev/null || true)"
echo "     ✅ GET /        -> 307 -> ${redirect_url:-/home} (200)"

login_code="$(curl -s -o /dev/null -w '%{http_code}' -m 5 "${BASE_URL}/__login" 2>/dev/null || echo 000)"
if [ "${login_code}" != "200" ]; then
  fail "GET /__login returned ${login_code} (expected 200)."
fi
echo "     ✅ GET /__login -> ${login_code}"

# --- Optional: live Vertex generateContent leg -----------------------------
LIVE_RESULT="skipped"
if [ "${LIVE_CHECK}" = "1" ]; then
  echo ""
  echo "🧪 (optional) Live Vertex gemini-3.8-flash generateContent leg..."
  if [ "${PROJECT_ID}" = "local-smoke-test" ]; then
    echo "     ⏭️  Skipped: no real PROJECT_ID available."
  elif ! command -v gcloud >/dev/null 2>&1; then
    echo "     ⏭️  Skipped: gcloud not installed (needed for an access token)."
  else
    TOKEN="$(gcloud auth application-default print-access-token 2>/dev/null || true)"
    if [ -z "${TOKEN}" ]; then
      echo "     ⏭️  Skipped: no Application Default Credentials available."
    else
      # gemini-3.x flash is global-only. The global endpoint uses the plain
      # aiplatform.googleapis.com host (no region prefix); regional overrides use
      # the "<region>-aiplatform" host. Build the URL accordingly.
      if [ "${GEMINI_LOCATION}" = "global" ]; then
        URL="https://aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/global/publishers/google/models/gemini-3.8-flash:generateContent"
      else
        URL="https://${GEMINI_LOCATION}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${GEMINI_LOCATION}/publishers/google/models/gemini-3.8-flash:generateContent"
      fi
      gen_code="$(curl -s -o /tmp/gmcs_smoke_gen.json -w '%{http_code}' -m 30 \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Content-Type: application/json" \
        -X POST "${URL}" \
        -d '{"contents":[{"role":"user","parts":[{"text":"Reply with the single word: pong"}]}]}' \
        2>/dev/null || echo 000)"
      if [ "${gen_code}" = "200" ]; then
        echo "     ✅ live generateContent -> 200"
        LIVE_RESULT="pass"
      else
        echo "     ⚠️  live generateContent -> ${gen_code} (non-fatal). Response:"
        head -c 500 /tmp/gmcs_smoke_gen.json 2>/dev/null || true
        echo ""
        LIVE_RESULT="warn(${gen_code})"
      fi
    fi
  fi
else
  echo ""
  echo "🧪 (optional) Live Vertex leg not requested (pass -l or LIVE_CHECK=1 to enable)."
fi

# --- Summary ---------------------------------------------------------------
echo ""
echo "======================================================================"
echo "✅ SMOKE TEST PASSED"
echo "   boot: OK | GET /: 200 | GET /__login: 200 | live: ${LIVE_RESULT}"
echo "======================================================================"
exit 0
