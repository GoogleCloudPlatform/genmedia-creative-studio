# gemini_audio_tts live eval

Opt-in, live (billed) evaluation of the `mcp-gemini-go` TTS tools. It covers Gemini 3.8 and the earlier 3.1 / 2.5 models. It is not run in CI.

There are two layers:
1. **Tool contract (scripted):** `run_eval.py` drives the server over MCP stdio (real `initialize` handshake) and runs every case in `cases.json`. For each case it checks:
   - error vs success
   - the expected **prompt advisories**
   - saved file type, a single valid WAV header, and duration
2. **What was actually heard (LLM listener):** for cases with `"judge": true`, the WAV is sent to `gemini-3.5-flash`. The listener returns a verbatim transcript, any direction or tag words that were spoken aloud, and the speaker count. These checks are **soft** (WARN) because a listener model is noisy. `--hard-judge` makes them fail the run.

A `control` case sends a known-bad prompt (`Take 1 …` markers on 3.8) and passes only if the listener *catches* the spoken markers. This proves the not-spoken check is not vacuous.

The server is started with `LOCATION=us-central1` on purpose, to prove 3.8 requests are pinned to `global`.

## Run

```bash
cd experiments/mcp-genmedia/mcp-genmedia-go/mcp-gemini-go && go build -o /tmp/mcp-gemini-go .
cd ../../evals/gemini-tts
gcloud auth application-default login     # server (ADC)
gcloud auth login                          # judge (gcloud token)
python3 run_eval.py --server /tmp/mcp-gemini-go --project $GOOGLE_CLOUD_PROJECT
python3 run_eval.py --server /tmp/mcp-gemini-go --project $P --groups 38-lint,31 --no-judge   # fast, cheap
```

Output goes to `out/<timestamp>/`:
- `report.md`: table with what the listener heard
- `results.json`
- `audio/*.wav`: listen to these
- `server.log`

Groups: `38`, `38-lint`, `38-validate`, `take3`, `31`, `voices`, `control`.

A full run is 25 cases and ~1 minute, with about 20 short TTS calls plus 11 judge calls.

## Try it in an agent (skill-level check)

The script tests the tool. To test the **skills** (does an agent follow the 3.8 guidance?), register the branch build and give an agent real requests.

**Gemini CLI**, in `~/.gemini/settings.json`:
```json
{
  "mcpServers": {
    "gemini-multimodal": {
      "command": "/tmp/mcp-gemini-go",
      "args": ["-t", "stdio"],
      "env": { "GOOGLE_CLOUD_PROJECT": "your-project", "MCP_OUTPUT_ROOT": "/tmp/genmedia-out" }
    }
  }
}
```
Then link the skills from the repo root with `/skills link ./experiments/mcp-genmedia/skills --scope workspace`.

**opencode**, in `opencode.json`:
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "gemini-multimodal": {
      "type": "local",
      "command": ["/tmp/mcp-gemini-go", "-t", "stdio"],
      "environment": { "GOOGLE_CLOUD_PROJECT": "your-project", "MCP_OUTPUT_ROOT": "/tmp/genmedia-out" }
    }
  },
  "skills": { "paths": ["./experiments/mcp-genmedia/skills"] }
}
```
Restart the agent after editing config.

Prompts to try, with what a correct agent should do:

| Prompt | Expect |
|---|---|
| "Give me a take 3 on the bounce of: *Welcome to the future of cloud computing.*" | Three `gemini_audio_tts` calls with the same voice and the same words, a different short `prompt` each, files `…_take1/2/3`, and no "Take 1" in `text` |
| "Make Jaz R. the Brixton radio DJ say: *massive vibes in the studio*" | 3.8: a voice (Voice-design description or `Puck`) plus a short style; it does *not* paste the Audio Profile into `prompt` |
| "Same line, but use gemini-3.1-flash-tts-preview" | The Audio Profile goes in `prompt`, with `[square]` tags in `text` |
| "A short two-person podcast intro, Joe and Jane" | One call with `turns` + `speakers` (two), backchannels in `|pipes|`, and no `Joe:` in the text |
| "Read this whispered: *don't move*" | Style `whispering`, not an inline `<whispering>` tag |
| "Find me an Australian narrator voice" | `list_gemini_voices` with `accent: "Sydney"` (not `search: "australian"`, which returns nothing) |
| "Make it an MP3" (3.8) | Generates WAV, then converts with avtool; it does not request `MP3` from 3.8 |

If the tool output contains **Prompt advisories** and the agent ignores them, the skill guidance needs strengthening.
