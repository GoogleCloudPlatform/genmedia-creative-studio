#!/usr/bin/env bash
# build-mcp-genmedia/scripts/build.sh
# Builds all mcp-genmedia Go MCP servers from source into /tmp/bin/
# and updates /workspace/.claude/settings.json to use them.
# Safe to re-run: skips steps that are already done.

set -euo pipefail

LOG="[build-mcp-genmedia]"
GO_VERSION="1.26.2"
GO_URL="https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz"
GO_BIN="/tmp/go/bin/go"
GOPATH="/tmp/gopath"
GOCACHE="/tmp/gocache"
REPO_URL="https://github.com/GoogleCloudPlatform/genmedia-creative-studio"
REPO_DIR="/tmp/genmedia-creative-studio"
SRC_DIR="${REPO_DIR}/experiments/mcp-genmedia/mcp-genmedia-go"
OUT_DIR="/tmp/bin"
SETTINGS="/workspace/.claude/settings.json"

SERVERS=(
  "mcp-nanobanana-go"
  "mcp-veo-go"
  "mcp-omni-go"
  "mcp-lyria-go"
  "mcp-gemini-go"
  "mcp-chirp3-go"
  "mcp-avtool-go"
)

mkdir -p "${OUT_DIR}"

# ── Step 1: Go toolchain ────────────────────────────────────────────────────
if "${GO_BIN}" version &>/dev/null; then
  echo "${LOG} Go $("${GO_BIN}" version | awk '{print $3}') already present at ${GO_BIN}"
else
  echo "${LOG} Downloading Go ${GO_VERSION}..."
  curl -fsSL "${GO_URL}" -o /tmp/go.tar.gz
  rm -rf /tmp/go
  tar -xf /tmp/go.tar.gz -C /tmp
  rm /tmp/go.tar.gz
  echo "${LOG} Go installed: $("${GO_BIN}" version)"
fi

# ── Step 2: Source repo ─────────────────────────────────────────────────────
if [[ -d "${SRC_DIR}" ]]; then
  echo "${LOG} Repo already present, pulling latest..."
  git -C "${REPO_DIR}" pull --ff-only --quiet 2>/dev/null || echo "${LOG} (pull skipped — detached or dirty)"
else
  echo "${LOG} Cloning source repo..."
  git clone --depth=1 "${REPO_URL}" "${REPO_DIR}"
fi

# ── Step 3: Build each server ───────────────────────────────────────────────
cd "${SRC_DIR}"
export GOPATH GOCACHE

for server in "${SERVERS[@]}"; do
  bin="${OUT_DIR}/${server}"
  printf "${LOG} Building %-22s" "${server}..."
  "${GO_BIN}" build -o "${bin}" "./${server}/"
  size=$(du -sh "${bin}" | cut -f1)
  echo " OK (${size})"
done

# ── Step 4: Patch settings.json ─────────────────────────────────────────────
echo "${LOG} Patching settings.json..."

declare -A KEY_MAP=(
  [mcp-nanobanana-go]="nanobanana"
  [mcp-veo-go]="veo"
  [mcp-omni-go]="omni"
  [mcp-lyria-go]="lyria"
  [mcp-gemini-go]="gemini-multimodal"
  [mcp-chirp3-go]="chirp3-hd"
  [mcp-avtool-go]="avtool"
)

# Use Python for reliable JSON editing (jq may not be installed)
python3 - "${SETTINGS}" "${OUT_DIR}" <<'PYEOF'
import sys, json

settings_path = sys.argv[1]
out_dir = sys.argv[2]

bin_map = {
    "nanobanana":        f"{out_dir}/mcp-nanobanana-go",
    "veo":               f"{out_dir}/mcp-veo-go",
    "omni":              f"{out_dir}/mcp-omni-go",
    "lyria":             f"{out_dir}/mcp-lyria-go",
    "gemini-multimodal": f"{out_dir}/mcp-gemini-go",
    "chirp3-hd":         f"{out_dir}/mcp-chirp3-go",
    "avtool":            f"{out_dir}/mcp-avtool-go",
}

with open(settings_path) as f:
    cfg = json.load(f)

for key, binary in bin_map.items():
    if key in cfg.get("mcpServers", {}):
        cfg["mcpServers"][key]["command"] = binary

with open(settings_path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")

print(f"  Updated {len(bin_map)} server entries → {out_dir}/")
PYEOF

echo ""
echo "${LOG} ✓ All done."
echo "${LOG}   Binaries: ${OUT_DIR}/"
echo "${LOG}   Settings: ${SETTINGS}"
echo ""
echo "${LOG} Restart Claude Code (reload the session) to activate the new MCP servers."

