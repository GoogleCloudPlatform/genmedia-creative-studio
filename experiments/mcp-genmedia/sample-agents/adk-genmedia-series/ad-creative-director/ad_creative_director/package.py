# Copyright 2025 Google LLC
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

"""Headless dogfood entrypoint — the `storyboard` profile's package/manifest CLI.

This is the "we built this to write about itself" tool: it runs the storyboard
profile of the engine HEADLESSLY (no adk web), lets the generation sub-agents
write real media into a package directory, and then a THIN, DETERMINISTIC,
NON-LLM packaging function reads the schema-validated plan out of session state,
re-verifies every expected artifact BY EXISTENCE, and writes a versioned
`manifest.json` + `plan.json`. The archivist (or any downstream tool) consumes
ONLY `manifest.json` — a stable, versioned data contract, never the agent's
Python internals.

    uv run python -m ad_creative_director.package \\
        --profile storyboard \\
        --brief "<brief text | @path/to/brief.txt>" \\
        --out packages/<slug>/         # default packages/<slug>-<UTC-timestamp>/

Exit code: 0 on full success; NON-ZERO if any expected artifact is unverified
(and the manifest records `artifacts_verified: false`). No stubs, ever — a
missing file is a hard failure, not a placeholder.

--------------------------------------------------------------------------------
The ADK 2.8.0 headless-runner API used below is source-verified against the
installed 2.8.0 (== tag v2.8.0 of github.com/google/adk-python). There is no
pre-existing `driver.py` in the merged series to copy, so this entrypoint is
authored from scratch against these APIs:

  * InMemoryRunner  — runners.py:2716 (class), :2729 (__init__): a Runner with
    in-memory session/artifact/memory services; takes `agent=` and `app_name=`.
  * Runner.run_async — runners.py:1240: async generator; takes `user_id`,
    `session_id`, `new_message`, optional `state_delta`; yields Events until the
    invocation completes.
  * session_service.create_session — base_session_service.py:70: takes
    `app_name`, `user_id`, optional `state` (seed dict) and `session_id`. We seed
    the package/shots/audio dirs here so the sub-agents write predictable names.
  * session_service.get_session — base_session_service.py:92: read the final
    session back to pull `state[<plan key>]` (the planner's output_schema plan).
  * Runner.close — runners.py:2684: closes plugin/MCP resources on exit.

The plan lands in state as a DICT (not the Pydantic object): for a
`type[BaseModel]` output_schema ADK stores
`schema.model_validate_json(text).model_dump(exclude_none=True)`
(utils/_schema_utils.py:141-142; write at llm_agent.py:1044-1045). So the
deterministic packager below treats `state[plan_key]` as a dict.
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants sourced deterministically (NOT LLM-authored). See --help / the
# validation recipe.
# ---------------------------------------------------------------------------
MANIFEST_VERSION = "1"

# The genmedia suite version recorded in the manifest. Sourced deterministically,
# never from the LLM: the credentialed runner sets GENMEDIA_SUITE_VERSION to the
# installed suite's version (the single source of truth is the suite's VERSION
# file, mcp-genmedia-go/VERSION); if unset we fall back to the series-pinned floor
# the whole series targets (>= v3.18.1 for muxable Lyria audio). The recipe
# documents setting the env var so the manifest reflects the ACTUAL suite used.
SUITE_VERSION_DEFAULT = "3.18.1"


def _suite_version() -> str:
    return os.getenv("GENMEDIA_SUITE_VERSION", SUITE_VERSION_DEFAULT).strip() or (
        SUITE_VERSION_DEFAULT
    )


def _utc_now_iso() -> str:
    """UTC timestamp, seconds precision, Z-suffixed (e.g. 2026-09-07T12:00:00Z)."""
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _slugify(text: str, max_words: int = 6) -> str:
    """A filesystem-safe slug from the first few words of the brief."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    slug = "-".join(words[:max_words]) if words else "storyboard"
    return slug or "storyboard"


# ===========================================================================
# The DETERMINISTIC packager (non-LLM). This is the real integration contract.
# It is deliberately free of any ADK/LLM import so it is unit-testable with a
# tiny local fixture (see the validation recipe / project log).
# ===========================================================================
def build_manifest(
    plan: dict[str, Any],
    package_dir: Path,
    *,
    profile: str,
    brief: str,
    model: str,
    created: str | None = None,
    suite_version: str | None = None,
) -> dict[str, Any]:
    """Build the versioned manifest dict by VERIFYING each expected file exists.

    Deterministic, non-LLM. Reads the schema-validated plan (a dict), derives the
    expected artifact paths from the shot indices (shots/shot-0N.png), the fixed
    audio names, and the assembled animatic, and records `verified: <bool>` for
    each from an actual `os.path.exists` check against `package_dir` — never a
    resource_link. `artifacts_verified` is True ONLY if EVERY listed path exists.

    Args:
      plan: the planner's output (dict) — expects a "shots" list of
        {beat, prompt, ...} and optional "subject"/"music_mood".
      package_dir: the package root; all manifest paths are relative to it.
      profile: the profile name ("storyboard").
      brief: the original brief text.
      model: the Gemini model constant used (recorded for provenance).
      created: UTC timestamp; defaults to now.
      suite_version: the genmedia suite version; defaults to `_suite_version()`.

    Returns:
      The manifest dict (manifest_version "1"; see module docstring). The caller
      writes it to manifest.json.
    """
    created = created or _utc_now_iso()
    suite_version = suite_version or _suite_version()
    package_dir = Path(package_dir)

    def _exists(rel: str) -> bool:
        return (package_dir / rel).is_file()

    shots_out: list[dict[str, Any]] = []
    all_verified = True
    raw_shots = plan.get("shots") or []
    for i, shot in enumerate(raw_shots, start=1):
        rel = f"shots/shot-{i:02d}.png"
        verified = _exists(rel)
        all_verified = all_verified and verified
        shots_out.append(
            {
                "index": i,
                "beat": shot.get("beat", ""),
                "prompt": shot.get("prompt", ""),
                "image": rel,
                "verified": verified,
            }
        )

    # An empty plan must NEVER verify true (defense in depth; the StoryboardPlan
    # schema already enforces min_length=1, but the packager does not trust that).
    if not shots_out:
        all_verified = False

    narration_rel = "audio/narration.wav"
    music_rel = "audio/music.mp3"
    assembled_rel = "animatic.mp4"
    narration_ok = _exists(narration_rel)
    music_ok = _exists(music_rel)
    assembled_ok = _exists(assembled_rel)
    all_verified = all_verified and narration_ok and music_ok and assembled_ok

    return {
        "manifest_version": MANIFEST_VERSION,
        "profile": profile,
        "brief": brief,
        "created": created,
        "model": model,
        "suite_version": suite_version,
        "subject": plan.get("subject", ""),
        "music_mood": plan.get("music_mood", ""),
        "shots": shots_out,
        "audio": {"narration": narration_rel, "music": music_rel},
        "assembled": assembled_rel,
        "artifacts_verified": all_verified,
    }


def write_package(
    plan: dict[str, Any],
    package_dir: Path,
    *,
    profile: str,
    brief: str,
    model: str,
) -> dict[str, Any]:
    """Write manifest.json + plan.json into the package dir; return the manifest.

    `plan.json` is the schema-validated planner output (provenance). `manifest.json`
    is the versioned contract the archivist reads. Both are written even when
    `artifacts_verified` is False, so a failed run leaves an inspectable record of
    WHICH files were missing (the caller then exits non-zero).
    """
    package_dir = Path(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(
        plan, package_dir, profile=profile, brief=brief, model=model
    )
    (package_dir / "plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (package_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


# ===========================================================================
# The headless run (imports ADK + the engine lazily, so the deterministic
# packager above stays import-light and unit-testable without ADK installed).
# ===========================================================================
def _read_brief(brief_arg: str) -> str:
    """Resolve --brief: literal text, or @path to read the brief from a file."""
    if brief_arg.startswith("@"):
        path = Path(brief_arg[1:]).expanduser()
        if not path.is_file():
            raise SystemExit(f"ERROR: --brief file not found: {path}")
        return path.read_text(encoding="utf-8").strip()
    return brief_arg.strip()


async def _run_storyboard(profile, brief: str, package_dir: Path) -> dict[str, Any]:
    """Run the storyboard root_agent headlessly and return the plan dict."""
    # Lazy imports: ADK + the engine are only needed for the live run.
    from google.genai import types
    from google.adk.runners import InMemoryRunner

    from .agent import build_root_agent

    shots_dir = package_dir / "shots"
    audio_dir = package_dir / "audio"
    for d in (package_dir, shots_dir, audio_dir):
        d.mkdir(parents=True, exist_ok=True)

    root_agent = build_root_agent(profile)
    app_name = "creative_studio"
    user_id = "cli"
    session_id = uuid.uuid4().hex

    runner = InMemoryRunner(agent=root_agent, app_name=app_name)
    try:
        # Seed the destination dirs into session state so the sub-agents write
        # predictable, packager-findable names into <out>/shots and <out>/audio.
        await runner.session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            state={
                "package_dir": str(package_dir.resolve()),
                "shots_dir": str(shots_dir.resolve()),
                "audio_dir": str(audio_dir.resolve()),
            },
        )
        message = types.Content(role="user", parts=[types.Part(text=brief)])
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            # Surface a light trace so the operator can follow the run.
            author = getattr(event, "author", None)
            if author:
                print(f"[{author}] event", file=sys.stderr)

        session = await runner.session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
    finally:
        await runner.close()

    if session is None:
        raise SystemExit("ERROR: session vanished after the run; cannot package.")
    plan = session.state.get(profile.plan_state_key)
    if not isinstance(plan, dict):
        raise SystemExit(
            "ERROR: the planner did not write a schema-validated plan to "
            f"state['{profile.plan_state_key}'] (got {type(plan).__name__}). "
            "Cannot build a manifest from a missing plan."
        )
    return plan


def _resolve_profile(name: str):
    """Map the --profile string to a Profile object (lazy import of the engine)."""
    from .profiles import AD_PROFILE, STORYBOARD_PROFILE

    profiles = {"ad": AD_PROFILE, "storyboard": STORYBOARD_PROFILE}
    if name not in profiles:
        raise SystemExit(f"ERROR: unknown --profile '{name}'.")
    return profiles[name]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ad_creative_director.package",
        description=(
            "Headless dogfood entrypoint: run the storyboard profile and emit a "
            "package dir + versioned manifest.json (verified by existence)."
        ),
    )
    parser.add_argument(
        "--profile",
        default="storyboard",
        choices=["ad", "storyboard"],
        help=(
            "Which profile to run. The package/manifest contract is the "
            "storyboard profile's dogfood tool; 'ad' is accepted for symmetry "
            "but the ad capstone's home is `adk web`."
        ),
    )
    parser.add_argument(
        "--brief",
        required=True,
        help="The brief text, or @path to read it from a file.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "Output package directory. Defaults to "
            "packages/<slug>-<UTC-timestamp>/."
        ),
    )
    args = parser.parse_args(argv)

    if args.profile != "storyboard":
        raise SystemExit(
            "ERROR: only --profile storyboard emits a package/manifest. The 'ad' "
            "profile's surface is `adk web` (root_agent = AD_PROFILE)."
        )

    brief = _read_brief(args.brief)
    if not brief:
        raise SystemExit("ERROR: --brief is empty.")

    profile = _resolve_profile(args.profile)

    if args.out:
        package_dir = Path(args.out)
    else:
        slug = _slugify(brief)
        ts = _utc_now_iso().replace(":", "").replace("-", "")
        package_dir = Path("packages") / f"{slug}-{ts}"

    # Reuse the engine's single MODEL constant for provenance (lazy import).
    from .agent import MODEL

    plan = asyncio.run(_run_storyboard(profile, brief, package_dir))
    manifest = write_package(
        plan, package_dir, profile=profile.name, brief=brief, model=MODEL
    )

    print(f"\nPackage written to: {package_dir}")
    print(f"  manifest.json  artifacts_verified={manifest['artifacts_verified']}")
    for shot in manifest["shots"]:
        mark = "OK " if shot["verified"] else "MISSING"
        print(f"  [{mark}] {shot['image']}")
    for label, rel in (
        ("narration", manifest["audio"]["narration"]),
        ("music", manifest["audio"]["music"]),
        ("animatic", manifest["assembled"]),
    ):
        exists = (package_dir / rel).is_file()
        print(f"  [{'OK ' if exists else 'MISSING'}] {rel} ({label})")

    if not manifest["artifacts_verified"]:
        print(
            "\nFAILED: one or more expected artifacts are missing; "
            "artifacts_verified=false. Exiting non-zero.",
            file=sys.stderr,
        )
        return 1
    print("\nSUCCESS: every expected artifact verified by existence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
