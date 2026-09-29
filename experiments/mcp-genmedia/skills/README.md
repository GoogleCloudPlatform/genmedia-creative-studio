# GenMedia Agent Skills

This directory contains a set of expert **Agent Skills** designed to provide AI agents (like [Gemini CLI](https://github.com/google-gemini/gemini-cli) or [Antigravity](https://antigravity.google/docs/)) with deep domain knowledge on how to use the GenMedia MCP tools for complex, multi-step workflows.

## Available Skills

- **`install-mcp-genmedia`**: Installs the mcp-genmedia MCP servers from pre-compiled release binaries and registers them in `mcp_config.json`. Use this for the clone-free setup path when you don't need to build from source.
- **`build-mcp-genmedia`**: Builds the mcp-genmedia Go MCP servers from source and configures them. Use this to compile missing or broken MCP tools in restricted environments.
- **`genmedia-producer`**: The high-level orchestrator. Use this for storyboarding, podcast creation, and managing complex production pipelines.
- **`genmedia-video-editor`**: Specialized in post-production. Use this for FFmpeg composition, image-on-video overlays, and creating high-quality GIFs.
- **`genmedia-audio-engineer`**: Specialized in sound design. Use this for high-fidelity speech synthesis, music generation, and multi-track audio mixing.
- **`genmedia-voice-director`**: Expert in casting, directing, and generating expressive text-to-speech. Use this for virtual voice actor personas and "take 3 on the bounce" variations.
- **`genmedia-image-artist`**: Specialized in visual arts. Use this for high-fidelity image generation, prompt optimization, and iterative collaborative refinement.
- **`story-generator`**: Expert in generating full multi-scene multimedia storybooks (image, video, voice, and music) using direct, native MCP tool calls and parallel subagent orchestration, and packaging them into premium Material 3 interactive making-of reports.

## Installation & Usage

### For Gemini CLI (Remote)

You can install these skills directly from GitHub without cloning the repository:

```bash
# Install all skills in this directory
gemini skills install https://github.com/GoogleCloudPlatform/genmedia-creative-studio.git --path experiments/mcp-genmedia/skills

# Install a specific skill (e.g., Producer)
gemini skills install https://github.com/GoogleCloudPlatform/genmedia-creative-studio.git --path experiments/mcp-genmedia/skills/genmedia-producer
```

### For Gemini CLI (Local)

If you have already cloned the repository, Gemini CLI can link to these skills from your workspace. Run the following command within your interactive session:

```bash
/skills link ./skills --scope workspace
```

### For Antigravity

Antigravity discovers skills within the `.agents/skills` directory of your workspace. To install these skills, copy them into your project:

```bash
mkdir -p .agents/skills
cp -r /path/to/this/repo/experiments/mcp-genmedia/skills/* .agents/skills/
```

For global installation across all Antigravity projects:

```bash
mkdir -p ~/.gemini/antigravity/skills
cp -r /path/to/this/repo/experiments/mcp-genmedia/skills/* ~/.gemini/antigravity/skills/
```

## Creating New Skills

These skills follow the [Agent Skills Open Standard](https://agentskills.io). Each skill is a directory containing a `SKILL.md` file with YAML frontmatter.

To contribute a new skill:
1. Create a new directory named after your skill.
2. Add a `SKILL.md` file following the standard format.
3. Provide clear, procedural instructions that help an AI agent navigate the specific tools and edge cases of the workflow.
