---
title: "Build MCP GenMedia"
name: build-mcp-genmedia
description: Builds the mcp-genmedia Go MCP servers (nanobanana, veo, lyria, gemini-multimodal, chirp3-hd, avtool) from source and wires them into settings.json. Use this skill whenever the MCP tools are missing or broken — typically at the start of a new session, after a container restart, or when /tmp has been wiped.
license: Apache-2.0
---

# Build mcp-genmedia from Source

## When to invoke this skill

- MCP tools (nanobanana, veo, lyria, etc.) are not responding or missing from tool list
- `/tmp` has been wiped (container restart, new session)
- `settings.json` still points to `/workspace/.local/bin/` binaries (which are not executable)
- Any `exec format error` or `permission denied` when Claude Code tries to start an MCP server

## How it works

The prebuilt binaries shipped in `/workspace/.local/bin/` lack the executable bit and live on a noexec
filesystem mount — they can never be run directly. The source code for all six servers lives in the
upstream repo. This skill clones that repo, downloads Go if needed, compiles the servers into `/tmp/bin/`
(which is exec-allowed), and updates `settings.json` to point there.

## Step-by-step procedure

### 1. Run the build script

```bash
bash /workspace/.claude/skills/build-mcp-genmedia/scripts/build.sh
```
