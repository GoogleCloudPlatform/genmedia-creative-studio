# GMCS Telemetry & Observability Smoke Tools

This directory contains diagnostic tools to validate and smoke-test model telemetry, billing unit capture, and error classification across the GenMedia Creative Studio platform.

---

## 🛠️ Included Tools

### 1. `scripts/smoke_telemetry.sh`
Analyzes local JSON application logs captured during UI generation flows.

```bash
# 1. Start application with log tee in Terminal A:
uv run main.py 2>&1 | tee /tmp/gmcs.log

# 2. Exercise UI flows at http://localhost:8080/

# 3. Analyze captured telemetry in Terminal B:
./scripts/smoke_telemetry.sh
```

**Features:**
- Summarizes total model calls, successes, failures, and unit capture counts.
- Displays a detailed per-call breakdown of model name, duration, billing units, and error taxonomy.
- Includes a coverage checklist across all 8 instrumented model subsystems (`Lyria`, `Gemini TTS`, `Chirp 3 HD`, `VTO`, `Imagen`, `Nano Banana`, `Veo`, `Gemini Omni`).

---

### 2. `scripts/emit_sample_telemetry.py`
Emits mock `model_call` JSON log events for all instrumented models without invoking real Google Cloud APIs or incurring usage costs.

```bash
# Emit sample telemetry directly into a log file for offline testing:
python3 scripts/emit_sample_telemetry.py 2>/tmp/gmcs.log

# Run smoke analyzer against offline sample log:
./scripts/smoke_telemetry.sh -f /tmp/gmcs.log
```

---

## 📊 Telemetry Schema Specification

Every generative model call emits a JSON log event to `genmedia.analytics` containing:

| Field | Type | Description |
| :--- | :--- | :--- |
| `event_type` | `string` | Always `"model_call"` |
| `model_name` | `string` | Canonical model identifier (e.g. `veo-3.1-fast-generate-001`, `lyria-3-clip-preview`, `gemini-3.1-flash-image`) |
| `status` | `string` | `"success"` or `"failure"` |
| `duration_ms` | `float` | Wall-clock execution time in milliseconds |
| `billing_units` | `object` | Raw billable dimensions (`prompt_tokens`, `candidates_tokens`, `video_seconds_generated`, `characters_synthesized`, `sample_count`, `aspect_ratio`, `resolution`, `audio_bytes`) |
| `error` | `object` | Structured failure classification (`category`, `code`, `message`, `retryable`) |
| `pipeline_id` | `string` | Optional workflow correlation ID |

---

## 🧪 Error Categories (`common/error_handling.py`)

- `CAPACITY_EXHAUSTED` (Quota / 429 / High Load)
- `SAFETY_FILTER` (RAI / Recitation / Harm Block)
- `CLIENT_TIMEOUT` (HTTP 504 / Gateway Timeout)
- `INVALID_ARGUMENT` (HTTP 400 / Invalid Prompt or Resolution)
- `AUTH_ERROR` (Permission / IAM / HTTP 403)
- `UPSTREAM_FAILURE` (Backend 500 / 503)
- `UNKNOWN`
