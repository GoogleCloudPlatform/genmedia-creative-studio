#!/usr/bin/env bash
# Copyright 2025 Google LLC
#
# Smoke test analyzer for GenMedia Creative Studio telemetry logs.
# Parses local JSON logs captured during UI generation flows.
#
# Usage:
#   # 1. Start app with log tee in Terminal A:
#   #    uv run main.py 2>&1 | tee /tmp/gmcs.log
#   # 2. Exercise UI flows at http://localhost:8080/
#   # 3. Run this script in Terminal B:
#   ./scripts/smoke_telemetry.sh
#   ./scripts/smoke_telemetry.sh -f /path/to/custom.log

set -euo pipefail

LOG_FILE="/tmp/gmcs.log"

while getopts "f:h" opt; do
  case ${opt} in
    f) LOG_FILE="${OPTARG}" ;;
    h)
      echo "Usage: $0 [-f LOG_FILE]"
      echo "  -f LOG_FILE  Path to captured application log (default: /tmp/gmcs.log)"
      exit 0
      ;;
    \?)
      echo "Invalid option: -${OPTARG}" >&2
      exit 1
      ;;
  esac
done

if [ ! -f "${LOG_FILE}" ]; then
  echo "❌ Log file not found: ${LOG_FILE}"
  echo ""
  echo "To capture local logs, launch the app with 'tee':"
  echo "  uv run main.py 2>&1 | tee /tmp/gmcs.log"
  echo ""
  echo "Or run the offline sample generator first:"
  echo "  python3 scripts/emit_sample_telemetry.py 2>/tmp/gmcs.log"
  exit 1
fi

echo "======================================================================"
echo "📊 GMCS Telemetry & Observability Smoke Analyzer"
echo "Log source: ${LOG_FILE}"
echo "======================================================================"
echo ""

python3 - "${LOG_FILE}" << 'EOF'
import json
import sys

log_file = sys.argv[1]

model_calls = []
with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        line = line.strip()
        if '"event_type"' in line and '"model_call"' in line:
            try:
                # Find JSON payload in line
                start_idx = line.find('{')
                if start_idx != -1:
                    payload = json.loads(line[start_idx:])
                    if payload.get("event_type") == "model_call":
                        model_calls.append(payload)
            except Exception:
                pass

if not model_calls:
    print("❌ No 'model_call' events found in log file.")
    print("   Exercise a page in the UI (e.g. /nano-banana or /gemini-tts) and re-run.")
    sys.exit(1)

successes = [c for c in model_calls if c.get("status") == "success"]
failures = [c for c in model_calls if c.get("status") == "failure"]
with_units = [c for c in model_calls if c.get("billing_units")]
with_tokens = [c for c in model_calls if c.get("billing_units", {}).get("prompt_tokens") is not None]
with_classified_errors = [c for c in model_calls if c.get("error", {}).get("category")]

print(f"Total Model Calls Observed : {len(model_calls)}")
print(f"  ├─ Successes             : {len(successes)}")
print(f"  ├─ Failures              : {len(failures)}")
print(f"  ├─ With Billing Units    : {len(with_units)}")
print(f"  ├─ With Token Capture    : {len(with_tokens)}")
print(f"  └─ With Classified Error : {len(with_classified_errors)}")
print("")

print("----------------------------------------------------------------------")
print("Detailed Model Invocations:")
print("----------------------------------------------------------------------")
hdr = f"{'MODEL NAME':<32} | {'STATUS':<7} | {'MS':<7} | {'BILLING UNITS / DETAILS'}"
print(hdr)
print("-" * len(hdr))

for c in model_calls:
    m_name = str(c.get("model_name", "unknown"))[:32]
    status = str(c.get("status", "unknown")).upper()
    duration = f"{c.get('duration_ms', 0):.0f}ms"
    units = c.get("billing_units") or {}
    err = c.get("error") or {}

    unit_str_parts = []
    if units:
        unit_str_parts.append("units=" + json.dumps(units))
    if err:
        unit_str_parts.append(f"err_cat={err.get('category')}(code={err.get('code')},retry={err.get('retryable')})")
    if not unit_str_parts:
        unit_str_parts.append("no_billing_units")

    units_summary = " ".join(unit_str_parts)
    print(f"{m_name:<32} | {status:<7} | {duration:<7} | {units_summary}")

print("")
print("----------------------------------------------------------------------")
print("Model Coverage Checklist:")
print("----------------------------------------------------------------------")

EXPECTED_MODELS = {
    "lyria": "Lyria Music Generation (/lyria)",
    "tts": "Gemini TTS (/gemini-tts)",
    "chirp": "Chirp 3 HD (/chirp-3hd)",
    "vto": "Virtual Try-On (/vto)",
    "imagen": "Imagen Image Generation (/imagen)",
    "banana": "Gemini Image / Nano Banana (/nano-banana)",
    "veo": "Veo Video Generation (/veo)",
    "omni": "Gemini Omni 1.1 Flash (/gemini-omni)",
}

observed_names = [str(c.get("model_name", "")).lower() for c in model_calls]

for key, label in EXPECTED_MODELS.items():
    matched = any(key in name for name in observed_names)
    icon = "✅" if matched else "⚪"
    status_msg = "OBSERVED" if matched else "NOT SEEN YET"
    print(f"  {icon} {label:<45} : {status_msg}")

print("")
if with_units:
    print("✨ SUCCESS: Structured billing units and telemetry verified!")
else:
    print("⚠️ WARNING: Model calls found but none contained billing_units. Check model instrumentation.")

sys.exit(0)
EOF
