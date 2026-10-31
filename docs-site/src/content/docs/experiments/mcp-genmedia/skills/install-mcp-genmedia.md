---
title: "Install MCP GenMedia"
name: install-mcp-genmedia
description: Installs Google's GenMedia MCP servers (Lyria, NanoBanana, Veo, Chirp, AVTool) via curl from pre-compiled release binaries and registers them in mcp_config.json. Use when the required media synthesis tools are missing or inactive.
license: Apache-2.0
---

# Install GenMedia MCP Servers (Pre-compiled Binaries)

This skill provides direct, clone-free instructions to download, install, and register the Google GenMedia Model Context Protocol (MCP) servers using official release binaries.

## When to Invoke this Skill
*   Required media synthesis tools (`lyria_generate_music`, `nanobanana_image_generation`, or `ffmpeg_*`) are not present in your active tool list.
*   You want a fast, pre-compiled setup without installing the Go runtime or cloning the source repository.

---

## Installation Procedure

### 1. Run the Online Installer
This command fetches the official install script, which automatically detects your OS and architecture, downloads the latest pre-compiled binaries from the GitHub Releases page, and extracts them into your `~/.local/bin/` folder.

```bash
curl -sL https://raw.githubusercontent.com/GoogleCloudPlatform/genmedia-creative-studio/main/experiments/mcp-genmedia/mcp-genmedia-go/install-online.sh | bash
```

*Note: Ensure that `~/.local/bin` is in your system's executable search `PATH`.*

---

## Configuration & Registration

### 1. Update your MCP Configuration
Add the installed binaries to your platform's global MCP configuration file (typically `~/.gemini/antigravity-cli/mcp_config.json` or your IDE's settings).

Configure the environment to include your Google Cloud Project ID and Region:

```json
{
  "mcpServers": {
    "lyria": {
      "command": "/Users/YOUR_USER/.local/bin/mcp-lyria-go",
      "env": {
        "PROJECT_ID": "YOUR_GCP_PROJECT",
        "LOCATION": "us-central1"
      }
    },
    "nanobanana": {
      "command": "/Users/YOUR_USER/.local/bin/mcp-nanobanana-go",
      "env": {
        "PROJECT_ID": "YOUR_GCP_PROJECT",
        "LOCATION": "us-central1"
      }
    },
    "avtool": {
      "command": "/Users/YOUR_USER/.local/bin/mcp-avtool-go"
    }
  }
}
```

### 2. Antigravity CLI (agy) Plugin Sync
If you are running the **Antigravity CLI (agy)** client and want to sync all the expert skills (such as `genmedia-producer`, `genmedia-audio-engineer`, etc.) and their integrated MCP servers that are configured under your main Gemini config, you must import the plugins into Antigravity:

```bash
antigravity plugin import gemini
```

This will automatically scan, register, and stage all your active Gemini plugins and MCP servers under your Antigravity configuration folder (`~/.gemini/config/`).

### 3. Reload and Verify the Session
To register and activate the new tool definitions in your active agent's context, you must reload your active session:
*   In **Gemini CLI**, run: `/skills reload`
*   In **Antigravity (agy)**, exit your current chat session and restart the client (e.g., using `antigravity --continue` or starting a new turn) so the tool schemas are re-negotiated and locked.
