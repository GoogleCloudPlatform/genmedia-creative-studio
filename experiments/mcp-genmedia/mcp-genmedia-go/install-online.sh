#!/usr/bin/env bash
set -e

# GenMedia MCP Servers Online Installation Script
# This script downloads and installs the pre-compiled binaries for your OS and Architecture.
#
# Usage:
#   curl -sL https://raw.githubusercontent.com/GoogleCloudPlatform/genmedia-creative-studio/main/experiments/mcp-genmedia/mcp-genmedia-go/install-online.sh | bash

REPO="GoogleCloudPlatform/genmedia-creative-studio"
INSTALL_DIR="$HOME/.local/bin"
ARCHIVE_PREFIX="genmedia-mcp-servers"

echo_info() { printf "\033[1;34m==>\033[0m %s\n" "$1"; }
echo_success() { printf "\033[1;32m==>\033[0m %s\n" "$1"; }
echo_err() { printf "\033[1;31mError:\033[0m %s\n" "$1" >&2; }

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

case "$ARCH" in
    x86_64) ARCH="amd64" ;;
    arm64|aarch64) ARCH="arm64" ;;
    *) echo_err "Unsupported architecture: $ARCH"; exit 1 ;;
esac

OS_TITLE="$(tr '[:lower:]' '[:upper:]' <<< ${OS:0:1})${OS:1}"

LATEST_URL="https://api.github.com/repos/${REPO}/releases"
echo_info "Checking GitHub for the latest MCP release..."

if command -v curl >/dev/null 2>&1; then
    RELEASE_DATA=$(curl -sL "$LATEST_URL")
else
    RELEASE_DATA=$(wget -qO- "$LATEST_URL")
fi

TAG=$(echo "$RELEASE_DATA" | grep '"tag_name": "mcp-v' | head -n 1 | awk -F'"' '{print $4}')

if [ -z "$TAG" ]; then
    echo_err "Could not find a valid mcp-v* release tag on GitHub."
    echo_err "Make sure an automated release has been published for the MCP servers."
    exit 1
fi
echo_info "Found version: ${TAG}"

TARBALL="${ARCHIVE_PREFIX}_${OS}_${ARCH}.tar.gz"
# GoReleaser uses the stripped semantic version for the actual release assets if we stripped it in CI
CLEAN_TAG=${TAG#mcp-}
DOWNLOAD_URL="https://github.com/${REPO}/releases/download/v${CLEAN_TAG#v}/${TARBALL}"

echo_info "Downloading ${TARBALL}..."
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

if command -v curl >/dev/null 2>&1; then
    curl -sL -f "$DOWNLOAD_URL" -o "$TMP_DIR/$TARBALL" || { echo_err "Failed to download $DOWNLOAD_URL. The binaries for your architecture might not be available yet."; exit 1; }
else
    wget -qO "$TMP_DIR/$TARBALL" "$DOWNLOAD_URL" || { echo_err "Failed to download $DOWNLOAD_URL."; exit 1; }
fi

echo_info "Extracting binaries..."
tar -xzf "$TMP_DIR/$TARBALL" -C "$TMP_DIR"

mkdir -p "$INSTALL_DIR"

# Install Agent Skills if present in the tarball
if [ -d "$TMP_DIR/skills" ]; then
    echo ""
    echo_info "Found expert Agent Skills (Producer, Audio Engineer, Video Editor, Image Artist)."
    
    # Check for Gemini CLI
    if [ -d "$HOME/.gemini" ]; then
        read -p "Install these skills for Gemini CLI? (y/N): " install_gemini_skills
        case "$install_gemini_skills" in
            [yY]|[yY][eE][sS])
                GEMINI_SKILLS_DIR="$HOME/.gemini/skills"
                mkdir -p "$GEMINI_SKILLS_DIR"
                cp -R "$TMP_DIR/skills/"* "$GEMINI_SKILLS_DIR/"
                echo_success "Skills installed to $GEMINI_SKILLS_DIR"
                ;;
        esac
    fi

    # Check for Antigravity
    if [ -d "$HOME/.gemini/antigravity" ]; then
        read -p "Install these skills for Antigravity? (y/N): " install_agy_skills
        case "$install_agy_skills" in
            [yY]|[yY][eE][sS])
                AGY_SKILLS_DIR="$HOME/.gemini/antigravity/skills"
                mkdir -p "$AGY_SKILLS_DIR"
                cp -R "$TMP_DIR/skills/"* "$AGY_SKILLS_DIR/"
                echo_success "Skills installed to $AGY_SKILLS_DIR"
                ;;
        esac
    fi
fi

# Install Gemini Extensions if present in the tarball
if [ -d "$TMP_DIR/gemini-extensions" ]; then
    echo ""
    read -p "Are you using Gemini CLI? Would you like to install the Google GenMedia extensions for it? (y/N): " install_ext
    case "$install_ext" in
        [yY]|[yY][eE][sS])
            echo_info "Installing Gemini CLI Extensions..."
            GEMINI_EXT_DIR="$HOME/.gemini/extensions"
            mkdir -p "$GEMINI_EXT_DIR"
            cp -R "$TMP_DIR/gemini-extensions/"* "$GEMINI_EXT_DIR/"
            echo_success "Extensions installed to $GEMINI_EXT_DIR"
            echo_info "Restart Gemini CLI and run '/extensions list' to configure them!"
            ;;
        *)
            echo_info "Skipping Gemini CLI extensions installation."
            ;;
    esac
fi

# Install Antigravity Skills if present
if [ -d "$TMP_DIR/gemini-extensions/antigravity" ]; then
    echo ""
    read -p "Are you using Antigravity? Would you like to install the Google GenMedia Agent Skills globally? (y/N): " install_agy
    case "$install_agy" in
        [yY]|[yY][eE][sS])
            echo_info "Installing Antigravity Skills..."
            AGY_SKILL_DIR="$HOME/.gemini/antigravity/skills"
            mkdir -p "$AGY_SKILL_DIR"
            cp -R "$TMP_DIR/gemini-extensions/antigravity/.agents/skills/"* "$AGY_SKILL_DIR/"
            echo_success "Agent Skills installed to $AGY_SKILL_DIR"
            echo_info "You will still need to manually configure the mcp_config.json via the Antigravity UI."
            ;;
        *)
            echo_info "Skipping Antigravity Skills installation."
            ;;
    esac
fi



echo_info "Installing binaries to ${INSTALL_DIR}..."
mv "$TMP_DIR"/mcp-*-go "$INSTALL_DIR/" 2>/dev/null || true
if ls "$INSTALL_DIR"/mcp-*-go 1> /dev/null 2>&1; then
    chmod +x "$INSTALL_DIR"/mcp-*-go
else
    echo_err "No binaries found in the archive."
    exit 1
fi

# macOS Gatekeeper will silently SIGKILL (exit 137) downloaded binaries that
# aren't signed with a trusted/valid signature, since they inherit a
# quarantine attribute from being fetched over the network. Our release
# binaries are unsigned, so clear the quarantine flag and apply an ad-hoc
# signature to let them run.
if [[ "$OS" == "darwin" ]]; then
    if command -v xattr >/dev/null 2>&1; then
        xattr -dr com.apple.quarantine "$INSTALL_DIR"/mcp-*-go 2>/dev/null || true
    fi
    if command -v codesign >/dev/null 2>&1; then
        echo_info "Ad-hoc signing binaries for macOS Gatekeeper..."
        for bin in "$INSTALL_DIR"/mcp-*-go; do
            codesign --force --sign - "$bin" 2>/dev/null || echo_err "Failed to sign $bin; it may be blocked by Gatekeeper. Run: codesign --force --sign - \"$bin\""
        done
    fi
fi

echo_success "Installation successful!"
echo_info "The following servers were installed:"
ls -1 "$INSTALL_DIR"/mcp-*-go | xargs -n 1 basename | sed 's/^/  - /'

if [[ ! ":$PATH:" == *":$INSTALL_DIR:"* ]]; then
    echo ""
    echo -e "\033[1;33mWARNING: Your PATH does not include $INSTALL_DIR\033[0m"
    echo "To run these servers, please add the following to your shell configuration file (~/.bashrc, ~/.zshrc, etc.):"
    echo "  export PATH=\"\$PATH:$INSTALL_DIR\""
fi

# Check and optionally enable required Google Cloud APIs
REQUIRED_APIS=("aiplatform.googleapis.com" "texttospeech.googleapis.com" "storage.googleapis.com")
GCP_PROJECT="${GOOGLE_CLOUD_PROJECT:-${PROJECT_ID:-}}"
if [[ -z "$GCP_PROJECT" ]] && command -v gcloud >/dev/null 2>&1; then
    GCP_PROJECT=$(gcloud config get-value project 2>/dev/null || true)
fi

if [[ -n "$GCP_PROJECT" ]] && command -v gcloud >/dev/null 2>&1; then
    echo ""
    echo_info "Checking required Google Cloud APIs in project ${GCP_PROJECT}..."
    if ENABLED_APIS=$(gcloud services list --enabled --project="$GCP_PROJECT" --format="value(config.name)" 2>/dev/null); then
        MISSING_APIS=()
        for api in "${REQUIRED_APIS[@]}"; do
            if ! printf '%s\n' "$ENABLED_APIS" | grep -Fxq "$api"; then
                MISSING_APIS+=("$api")
            fi
        done
        if [[ "${#MISSING_APIS[@]}" -eq 0 ]]; then
            echo_success "All required Google Cloud APIs are enabled (${REQUIRED_APIS[*]})."
        else
            echo -e "\033[1;33mWARNING: The following required Google Cloud APIs are not enabled in ${GCP_PROJECT}:\033[0m"
            for api in "${MISSING_APIS[@]}"; do
                echo "  - $api"
            done
            if [[ -t 0 ]]; then
                read -p "Would you like to enable these Google Cloud APIs now? (y/N): " enable_apis
                case "$enable_apis" in
                    [yY]|[yY][eE][sS])
                        gcloud services enable "${MISSING_APIS[@]}" --project="$GCP_PROJECT" && echo_success "Enabled required Google Cloud APIs."
                        ;;
                    *)
                        echo_info "Run manually: gcloud services enable ${MISSING_APIS[*]} --project=${GCP_PROJECT}"
                        ;;
                esac
            else
                echo_info "Run manually: gcloud services enable ${MISSING_APIS[*]} --project=${GCP_PROJECT}"
            fi
        fi
    else
        echo_info "Ensure required Google Cloud APIs are enabled: gcloud services enable ${REQUIRED_APIS[*]} --project=${GCP_PROJECT}"
    fi
else
    echo ""
    echo_info "Ensure required Google Cloud APIs are enabled in your GCP project:"
    echo "  gcloud services enable ${REQUIRED_APIS[*]}"
fi
