#!/bin/bash
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


# This script provides a convenient way to install or upgrade the Go MCP servers
# in this project. It performs the following actions:
#
# 1. Discovers all available MCP servers (directories matching 'mcp-*-go').
# 2. Checks if Go is installed and provides instructions if it is not.
# 3. Checks if the user's PATH includes the Go binary directory and provides
#    instructions on how to add it if it is missing.
# 4. Presents an interactive menu to install a specific server or all of them.
# 5. Compiles and installs the selected server(s) using 'go install'.

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

#
# Function to find all MCP servers.
#
# This function searches for all directories in the current directory that match
# the pattern 'mcp-*-go' and prints them to standard output.
find_mcp_servers() {
  # Imagen deprecation as of June 30, 2026
  find . -mindepth 1 -maxdepth 1 -type d -name 'mcp-*-go' ! -name 'mcp-imagen-go' | sed 's|./||'
}

#
# Function to check if Go is installed.
#
# This function checks if the 'go' command is available in the system's PATH.
# If it is not found, it prints an error message and exits the script.
check_go_installation() {
  if ! command -v go &> /dev/null; then
    echo -e "${RED}Go is not installed.${NC}"
    echo "Please install it from the official website: https://go.dev/dl/"
    echo "After installation, make sure that the Go binary is in your PATH, then run this script again."
    exit 1
  fi
}

#
# Function to check and configure the PATH.
#
# This function checks if the user's PATH includes the Go binary directory
# ($HOME/go/bin). If it does not, it prints a warning and instructions on how
# to add it to the user's shell configuration file.
check_path() {
  if [[ ! ":$PATH:" == *":$HOME/go/bin:"* ]]; then
    echo -e "${YELLOW}WARNING: Your PATH does not include the Go binary directory ($HOME/go/bin).${NC}"
    echo "The MCP server binaries will be installed there."
    echo "To run them from your command line, please add the following line to your shell configuration file (e.g., ~/.bashrc, ~/.zshrc):"
    echo ""
    echo -e "  ${BLUE}export PATH=\"\$PATH:$HOME/go/bin\"${NC}"
    echo ""
    echo "You will need to restart your shell or run 'source <your_config_file>' for the change to take effect."
    read -p "Press Enter to continue, or Ctrl+C to exit and configure your PATH."
  fi
}

#
# Function to ad-hoc codesign a locally built binary on macOS.
#
# 'go install' produces binaries with a signature that macOS Gatekeeper can
# reject at exec time, silently killing the process (SIGKILL / exit 137)
# with no output. Re-signing with an ad-hoc signature resolves this. This is
# a no-op on non-macOS platforms.
#
codesign_go_binary() {
  local server_dir="$1"
  if [[ "$(uname -s)" != "Darwin" ]]; then
    return
  fi
  if ! command -v codesign &> /dev/null; then
    return
  fi
  local binary_path="$HOME/go/bin/$server_dir"
  if [ -f "$binary_path" ]; then
    if ! codesign --force --sign - "$binary_path" 2>/dev/null; then
      echo -e "${YELLOW}WARNING: Failed to ad-hoc sign $binary_path. It may be blocked by macOS Gatekeeper.${NC}"
      echo -e "  Run manually: ${BLUE}codesign --force --sign - \"$binary_path\"${NC}"
    fi
  fi
}

#
# Function to check and optionally enable required Google Cloud APIs.
#
check_gcp_services() {
  local non_interactive="$1"
  local required_apis=(
    "aiplatform.googleapis.com"
    "texttospeech.googleapis.com"
    "storage.googleapis.com"
  )

  if ! command -v gcloud &> /dev/null; then
    echo -e "${YELLOW}WARNING: gcloud CLI not found; skipping Google Cloud API enablement check.${NC}"
    echo "Ensure these APIs are enabled in project ${GOOGLE_CLOUD_PROJECT}: ${required_apis[*]}"
    return
  fi

  echo -e "${BLUE}Checking required Google Cloud APIs in project ${GOOGLE_CLOUD_PROJECT}...${NC}"
  local enabled_apis
  if ! enabled_apis=$(gcloud services list --enabled --project="${GOOGLE_CLOUD_PROJECT}" --format="value(config.name)" 2>/dev/null); then
    echo -e "${YELLOW}WARNING: Could not query enabled Google Cloud APIs for project ${GOOGLE_CLOUD_PROJECT}.${NC}"
    echo -e "To enable required services manually, run:"
    echo -e "  ${BLUE}gcloud services enable ${required_apis[*]} --project=${GOOGLE_CLOUD_PROJECT}${NC}"
    return
  fi

  local missing_apis=()
  for api in "${required_apis[@]}"; do
    if ! printf '%s\n' "$enabled_apis" | grep -Fxq "$api"; then
      missing_apis+=("$api")
    fi
  done

  if [ "${#missing_apis[@]}" -eq 0 ]; then
    echo -e "${GREEN}All required Google Cloud APIs are enabled (${required_apis[*]}).${NC}"
    return
  fi

  echo -e "${YELLOW}The following required Google Cloud APIs are not enabled in project ${GOOGLE_CLOUD_PROJECT}:${NC}"
  for api in "${missing_apis[@]}"; do
    echo "  - $api"
  done

  if [[ "$non_interactive" -eq 1 ]]; then
    echo -e "${YELLOW}Enable them by running:${NC}"
    echo -e "  ${BLUE}gcloud services enable ${missing_apis[*]} --project=${GOOGLE_CLOUD_PROJECT}${NC}"
    return
  fi

  read -p "Would you like to enable these Google Cloud APIs now? (y/N): " enable_reply
  case "$enable_reply" in
    [yY]|[yY][eE][sS])
      if gcloud services enable "${missing_apis[@]}" --project="${GOOGLE_CLOUD_PROJECT}"; then
        echo -e "${GREEN}Successfully enabled required Google Cloud APIs.${NC}"
      else
        echo -e "${YELLOW}WARNING: Failed to enable one or more APIs. You can enable them manually with:${NC}"
        echo -e "  ${BLUE}gcloud services enable ${missing_apis[*]} --project=${GOOGLE_CLOUD_PROJECT}${NC}"
      fi
      ;;
    *)
      echo -e "${YELLOW}Skipping API enablement. You can enable them later with:${NC}"
      echo -e "  ${BLUE}gcloud services enable ${missing_apis[*]} --project=${GOOGLE_CLOUD_PROJECT}${NC}"
      ;;
  esac
}

#
# Function to setup Agent Skills.
#
setup_agent_skills() {
  SKILLS_DIR="$(cd "$(dirname "$0")/../skills" && pwd)"
  if [ -d "$SKILLS_DIR" ]; then
    echo -e "\n${BLUE}Expert Agent Skills found at:${NC} $SKILLS_DIR"
    
    # Check if gemini CLI is installed for remote installation tip
    if command -v gemini &> /dev/null; then
      echo -e "${YELLOW}Tip: You can also install these skills remotely via Gemini CLI:${NC}"
      echo -e "  ${BLUE}gemini skills install https://github.com/GoogleCloudPlatform/genmedia-creative-studio.git --path experiments/mcp-genmedia/skills${NC}\n"
    fi

    # Gemini CLI
    if [ -d "$HOME/.gemini" ]; then
      read -p "Would you like to link these skills to Gemini CLI locally? (y/N): " link_gemini
      case "$link_gemini" in
        [yY]|[yY][eE][sS])
          mkdir -p "$HOME/.gemini/skills"
          # Link all skill directories
          for skill in "$SKILLS_DIR"/*/; do
            if [ -d "$skill" ] && [ -f "${skill}SKILL.md" ]; then
              skill_name=$(basename "$skill")
              ln -sfn "$skill" "$HOME/.gemini/skills/$skill_name"
              echo -e "${GREEN}Linked $skill_name to Gemini CLI${NC}"
            fi
          done
          ;;
      esac
    fi

    # Antigravity
    if [ -d "$HOME/.gemini/antigravity" ]; then
      read -p "Would you like to install these skills for Antigravity? (y/N): " install_agy
      case "$install_agy" in
        [yY]|[yY][eE][sS])
          mkdir -p "$HOME/.gemini/antigravity/skills"
          cp -R "$SKILLS_DIR"/* "$HOME/.gemini/antigravity/skills/"
          echo -e "${GREEN}Skills installed to Antigravity global directory${NC}"
          ;;
      esac
    fi
  fi
}

#
# Function to print usage information.
#
usage() {
  cat <<EOF
Usage: ./install.sh [OPTION]

Interactively install or upgrade the Go MCP servers in this project.

Options:
  -a, --all    Install all MCP servers non-interactively (no menu).
  -h, --help   Show this help message and exit.

With no option, an interactive menu is shown. At the menu prompt you can
enter a server's number, or enter '0', 'a', or 'all' to install everything.
EOF
}

#
# Function to install all discovered MCP servers.
#
install_all() {
  echo -e "${BLUE}Installing all MCP servers...${NC}"
  for d in $(find_mcp_servers); do
    echo "Installing $d..."
    # Run go mod tidy to prevent checksum mismatch errors
    if ! (cd "$d" && go mod tidy && go install); then
      echo -e "${RED}ERROR: Failed to install $d. Please check the output above for details.${NC}"
      exit 1
    fi
    codesign_go_binary "$d"
  done
  echo -e "${GREEN}All MCP servers have been installed successfully.${NC}"
  echo -e "\n${YELLOW}Reminder: Ensure ${BLUE}\$HOME/go/bin${YELLOW} is in your PATH to run the installed servers.${NC}"
  setup_agent_skills
}

#
# Function to install a single MCP server.
#
install_one() {
  local server="$1"
  echo -e "${BLUE}Installing $server...${NC}"
  # Run go mod tidy to prevent checksum mismatch errors
  if (cd "$server" && go mod tidy && go install); then
    codesign_go_binary "$server"
    echo -e "${GREEN}$server has been installed successfully.${NC}"
    echo -e "\n${YELLOW}Reminder: Ensure ${BLUE}\$HOME/go/bin${YELLOW} is in your PATH to run the installed server.${NC}"
    setup_agent_skills
  else
    echo -e "${RED}ERROR: Failed to install $server. Please check the output above for details.${NC}"
    exit 1
  fi
}

#
# Main function.
#
# This is the main entry point of the script. It calls the other functions to
# perform the installation process.
main() {

  # Parse command-line options.
  local install_all_flag=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -a|--all)
        install_all_flag=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo -e "${RED}Unknown option: $1${NC}"
        usage
        exit 1
        ;;
    esac
  done

  # Fallback to PROJECT_ID if GOOGLE_CLOUD_PROJECT is not set
  if [[ -z "${GOOGLE_CLOUD_PROJECT}" ]] && [[ -n "${PROJECT_ID}" ]]; then
    export GOOGLE_CLOUD_PROJECT="${PROJECT_ID}"
  fi

  if [[ -z "${GOOGLE_CLOUD_PROJECT}" ]]; then
    echo -e "${YELLOW}GOOGLE_CLOUD_PROJECT not set, attempting to retrieve from gcloud config...${NC}"
    GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project 2>/dev/null)
    if [[ -z "${GOOGLE_CLOUD_PROJECT}" ]]; then
      echo -e "${RED}ERROR: Could not retrieve GOOGLE_CLOUD_PROJECT from gcloud. Please set it manually.${NC}"
      echo "For example: export GOOGLE_CLOUD_PROJECT=your-gcp-project-id"
      exit 1
    else
      echo -e "${GREEN}Successfully retrieved GOOGLE_CLOUD_PROJECT: ${GOOGLE_CLOUD_PROJECT}${NC}"
      export GOOGLE_CLOUD_PROJECT
    fi
  fi

  check_go_installation
  check_path
  check_gcp_services "$install_all_flag"

  # Non-interactive path: --all installs everything and exits.
  if [[ "$install_all_flag" -eq 1 ]]; then
    install_all
    return
  fi

  echo -e "${BLUE}Please choose an MCP server to install:${NC}"
  echo -e "${YELLOW}(enter '0', 'a', or 'all' to install everything)${NC}"
  select server in $(find_mcp_servers) "Install All" "Exit"; do
    # Accept '0', 'a', or 'all' (case-insensitive) as aliases for "Install All",
    # regardless of the number 'select' assigns to that menu item. REPLY holds
    # the raw text the user typed. tr keeps this portable to bash 3.2 (macOS).
    local reply_lc
    reply_lc=$(printf '%s' "$REPLY" | tr '[:upper:]' '[:lower:]')
    case "$reply_lc" in
      0|a|all)
        install_all
        break
        ;;
    esac
    case $server in
      "Install All")
        install_all
        break
        ;;
      "Exit")
        echo "Exiting."
        exit 0
        ;;
      *)
        if [ -n "$server" ]; then
          install_one "$server"
        else
          echo -e "${RED}Invalid selection.${NC}"
        fi
        break
        ;;
    esac
  done
}

main "$@"
