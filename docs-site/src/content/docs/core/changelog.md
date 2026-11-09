---
title: "Changelog & Notices"
---

All notable changes to GenMedia Creative Studio are documented on this page.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Common Changelog](https://common-changelog.org/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> For Model Context Protocol (MCP) server releases (`mcp-v3.x`), see [`experiments/mcp-genmedia/mcp-genmedia-go/CHANGELOG.md`](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/blob/main/experiments/mcp-genmedia/mcp-genmedia-go/CHANGELOG.md).

> Entries before 1.14.0 are consolidated: intermediate patch releases (for example 1.3.x, 1.5.x, 1.7.3–1.7.5, and 1.8.1–1.8.5) are folded into the nearest documented version, so an entry may include changes merged after its listed date.

## [Unreleased]

## [1.24.0] - 2026-11-09

### Changed
- **Storyboarder Narrative Writer Models:** Make the Storyboarder Narrative Writer selector config-driven (`GEMINI_STORYBOARDER_NARRATIVE_MODELS` and `GEMINI_STORYBOARDER_NARRATIVE_MODEL_ID`), defaulting to `gemini-3.8-flash` alongside `gemini-4-argon` and `gemini-3.5-flash-lite`, and remove the retired `gemini-3.0-pro` option (`gmcs-71i`, [#2168]).

### Security
- **GitHub Actions Gemini Workflows:** Remove shell execution tools (`run_shell_command`) from untrusted issue triage, invoke, and review workflows (`gemini-triage.yml`, `gemini-scheduled-triage.yml`, `gemini-invoke.yml`, `gemini-review.yml`) so prompt inputs are passed inline without shell expansion (`gmcs-vdg`, [#2163], [#2166]). These workflow-only changes did not bump the Core version and shipped between 1.23.0 and 1.24.0.

## [1.23.0] - 2026-11-09

### Changed
- **Workflow Video Defaults:** Default `INTERIOR_DESIGN_VIDEO_MODEL` and `OBJECT_ROTATION_VIDEO_MODEL` to `gemini-omni-1.2-flash` via a unified `models/workflow_video.py` router that supports both `gemini-omni-*` (image-to-video and reference-to-video) and `veo-*` models (`gmcs-eyp`, [#2162]).

## [1.22.1] - 2026-11-09

### Fixed
- **Object Rotation Library Chooser:** Wire all five Object Rotation upload slots (main + 4 views) to the shared `library_chooser_button` with unique keys, remove the legacy bare-list state field that triggered Mesop deserialization errors, filter failed/URI-less items from chooser pages, and pre-sign display URLs in parallel (`warm_display_urls`) (`gmcs-0l1`, [#2159]).

## [1.22.0] - 2026-11-09

### Added
- **Veo Page Omni Banner:** Add a `components/omni_hint/omni_hint.py` banner on the Veo page linking users to `/gemini-omni` (`gmcs-eyp`, [#2158]).

### Changed
- **Action Button Ordering:** Render the **Omni** send-to button before **Veo** across Virtual Try-On, Imagen, Interior Design, and Library image-detail action rows (`gmcs-eyp`, [#2158]).

## [1.21.0] - 2026-11-06

### Changed
- **Writers Workshop Model Picker:** Populate the Gemini Writers Workshop model selector from `GEMINI_WRITERS_WORKSHOP_MODELS` (defaulting to `gemini-4-argon,gemini-3.8-flash` with `GEMINI_WRITERS_WORKSHOP_MODEL_ID=gemini-4-argon` preselected) and reset stale session selections on load (`gmcs-2b7`, [#2157]).
- **Workflow Image Defaults:** Default `INTERIOR_DESIGN_IMAGE_MODEL` and `OBJECT_ROTATION_IMAGE_MODEL` to `gemini-nano-banana-2.1` (`gmcs-2b7`, [#2157]).

## [1.20.2] - 2026-11-06

### Fixed
- **Action Row Layout:** Stack the **Omni** and **Veo** send-to buttons vertically on the Nano Banana and Gemini Image Generation pages so the Actions row fits inside the left panel without horizontal overflow (`gmcs-6l5`, [#2156]).

## [1.20.1] - 2026-11-06

### Security
- **HTTP Security Middleware:** Add `common/http_security.py` enforcing `403 Forbidden` responses on authorization denials, `Strict-Transport-Security` (HSTS) headers, request correlation IDs, and sanitized error responses without internal stack or exception leakage (`gmcs-0lo`, [#2155]).

## [1.20.0] - 2026-11-06

### Added
- **Cached V4 Signed Display URLs:** Serve Library v2 media via 50-minute cached V4 signed URLs (`common/utils.py`) with parallel batch warming (`warm_display_urls`) when the media proxy is disabled, and guard empty/error tiles in `media_tile.js` (`gmcs-oi4`, [#2154]).

## [1.19.1] - 2026-11-06

### Security
- **Signed URL Endpoint Hardening:** Restrict `/api/get_signed_url` to authenticated callers and the application's configured GCS buckets (`_is_proxy_bucket_allowed`) (`gmcs-oi4.3`, [#2153]).

## [1.19.0] - 2026-11-06

### Added
- **Library v2 Media Viewer Omni Action:** Add a **Send to Omni** button next to **Veo** in the Library v2 media detail viewer (`gmcs-4x6`, [#2152]).

## [1.18.0] - 2026-11-06

### Added
- **Cross-App Send-to-Omni Buttons:** Add the **Omni** send-to button alongside **Veo** across Imagen, Gemini Image Generation, Interior Design, Virtual Try-On, and Library image details (`gmcs-w7x`, [#2151]).

## [1.17.0] - 2026-11-06

### Added
- **Nano Banana Send-to-Omni Button:** Add reusable `components/omni_button/omni_button.py` and wire a **Send to Omni** action on the Nano Banana Studio page (`gmcs-vs6`, [#2150]).

## [1.16.1] - 2026-11-05

### Fixed
- **Gemini Omni Reference-to-Video & Follow-Ups:** Send an explicit `task="reference_to_video"` field on initial ref2v requests and omit the task field on multi-turn chat follow-ups (`gmcs-csx`, [#2144]).

## [1.16.0] - 2026-11-05

### Added
- **Gemini Omni First/Last Frame Mode:** Add `first_last_frame` video interpolation mode to the Gemini Omni studio with start and end frame uploaders (`gmcs-qw3`, [#2143]).

## [1.15.0] - 2026-11-05

### Changed
- **Storyboarder Default Video Model:** Default Storyboarder scene video generation to `gemini-omni-1.2-flash` via `models/storyboard_video.py` while preserving Veo compatibility (`gmcs-04u`, [#2141]).

## [1.14.0] - 2026-11-05

_Major feature, infrastructure, and security consolidation spanning the repository rebrand to `genmedia-creative-studio`, modular Terraform + GKE deployment, IAP JWT verification, Nano Banana 2.1, and Gemini Omni 1.2 Flash._

### Added
- **Gemini Omni 1.2 Flash Default & Extend/Upscale Modes:** Add `gemini-omni-1.2-flash` as the default Omni model with `extend` and `upscale` video generation modes (`gmcs-f3b`, `gmcs-7cy`, [#2130], [#2140]).
- **Virtual Try-On Placement Critique:** Add Gemini-as-judge garment placement and fit critique workflow (`models/vto_critique.py`, `pages/vto.py`) (`gmcs-0px`, [#2097]).
- **Reviewable Failed Image Generations:** Persist failed Gemini image generation exceptions as reviewable `MediaItem` entries in Firestore (`gmcs-qnb`, [#2096]).
- **Nano Banana 2.1 Default Image Model:** Add `gemini-nano-banana-2.1` as the default image model across Nano Banana Studio and Gemini Image Generation ([#1986]).
- **Veo Deterministic Seed Control:** Expose `seed` parameter in the Veo UI and backend generation pipeline ([#1780]).
- **Foundation Models & Creative Workflows Documentation:** Add 17 dedicated Starlight documentation pages with light/dark Luminous Graphviz architecture diagrams covering all Foundation Models and Creative Workflows, plus a self-service GKE Autopilot deployment guide (`gmcs-ice`, `gmcs-h26`, [#2084], [#2086], [#2138]).
- **Modular `deploy/` Infrastructure & GKE Autopilot Support:** Decompose Terraform into reusable modules (`artifact-registry`, `cloud-run-service`, `data-stores`, `iam`, `networking-lb`, `project-services`, `secret-manager`, `gke-cluster`, `gke-workload`) under `deploy/`, add `deploy/scripts/deploy.sh` (`--target cloudrun|gke`), and support immutable versioned container tags in Artifact Registry ([#1883], [#1884], [#1895]–[#1900], [#1902]–[#1905]).

### Changed
- **Breaking (Repository Rename):** Rename canonical repository, Go module paths, Starlight base URL (`/genmedia-creative-studio/`), and package metadata from `vertex-ai-creative-studio` to `GoogleCloudPlatform/genmedia-creative-studio` (`gmcs-85f`, [#1908]).
- **Durable Text Model Migration:** Migrate core text generation and workflow notebooks from `gemini-2.x` to `gemini-3.5-flash` ([#1945]).
- **Virtual Model Prompt Helper:** Route virtual try-on prompt generation helpers to Nano Banana ([#1855]).
- **Gemini Omni Structured Output:** Send Omni `aspect_ratio` and `duration` via Interactions API `response_format` (`gmcs-aw4`, [#2137]).

### Removed
- **Legacy `gemini-2.5-flash-image` Model:** Remove `gemini-2.5-flash-image` as a selectable image generation model in favor of `gemini-nano-banana-2.1` and the Gemini 3.x image series ([#1992], [#1993]).
- **Decommissioned Arena Experiment:** Decommission and remove `archive/arena` ([#1970], [#2072]).

### Fixed
- **Gemini Omni Input Validation & Error Reporting:** Require per-mode input media before generating ([#1937]) and surface plural `errors[]` payloads from failed Interactions API calls (`gmcs-7vz`, [#2136]).
- **Web Components Static Mount:** Remove redundant `/__web-components-module__` `StaticFiles` mount from `main.py` ([#2073]).

### Security
- **Verified IAP JWT Identity & ASGI→WSGI Bridge:** Verify IAP JWT assertions (`common/verified_identity.py`) as the sole identity source in `iap` mode, retire raw plaintext email headers, wire `IAP_JWT_AUDIENCE` and fail-closed `APP_ENV` guards in Cloud Run Terraform, and bridge verified identity across the ASGI→WSGI boundary ([#1923], [#2079], [#2083]).
- **Server-Side Ownership Authorization & Bucket Allowlists:** Enforce server-side ownership checks (`common/authz.py`, `common/task_auth.py`) across Firestore mutations, workflow media reads, `get_media_item_by_id`, `get_media_for_chooser`, and Veo task/status routes, and enforce GCS bucket allowlists on `/api/get_media` ([#1920], [#1930], [#1971], [#1980], [#1982], [#1983]).

## [1.13.1] - 2026-09-14

### Added
- **Gemini Omni 1.1 Flash & Resolution Selector:** Upgrade default Omni model to `gemini-omni-1.1-flash-preview` and expose output resolution controls (`360p`, `720p`, `1080p`, `4k`) ([#1753]).
- **Starlight Catppuccin Theme:** Adopt `@catppuccin/starlight` (Latte/Mocha) across the documentation hub ([#1756]).

### Fixed
- **Configuration & Route Guards:** Define `EDIT_IMAGES_ENABLED` to gate the Object Rotation route ([#1872]), source Shop the Look Veo dropdown options from `VEO_MODELS` ([#1871]), fix Veo `negative_prompt` state propagation ([#1870]), and unwrap `WebEvent` payloads in Omni GCS uploader handlers ([#1844]).

## [1.13.0] - 2026-08-11

_Notice: In August 2026, repository history on `main` was scrubbed with `git-filter-repo` to remove historical compiled binaries, reducing clone size by ~60% (from ~400 MB to ~160 MB)._

<details>
<summary>Historical Notice: Git History Reset Instructions for Pre-August 2026 Clones</summary>

If you have a local clone created prior to August 9, 2026 that fails to pull due to rewritten commit history:

**Option 1: Fast Reset (No uncommitted local changes)**
```bash
git fetch origin
git checkout main
git reset --hard origin/main
git clean -fd
```

**Option 2: Fresh Clone (Recommended)**
```bash
git clone git@github.com:GoogleCloudPlatform/genmedia-creative-studio.git
```

**Option 3: Rebase an In-Flight Feature Branch**
```bash
git fetch origin
git rebase --onto origin/main <old-base-commit> <your-feature-branch>
```
</details>

### Added
- **Telemetry & Billing Instrumentation:** Add structured logging, canonical error taxonomy, and per-model billing unit capture across Chirp 3 HD, Gemini, Gemini TTS, and GCS storage ([#1638], [#1639]).
- **Image-Aware Veo Prompt Rewriter:** Inspect reference images in image-to-video, first/last frame, and reference-to-video Veo prompt rewriting ([#1642], [#1647]).
- **Automated Boot Smoke Testing:** Add `scripts/smoke_test.sh` and Python 3.14 pytest CI workflow ([#1645], [#1648], [#1661]).

### Changed
- **GA Veo 3.1 & Nano Banana Migration:** Standardize video generation on GA Veo 3.1 (`veo-3.1-fast`, `veo-3.1`, `veo-3.1-lite`), migrate Character Consistency image editing to Nano Banana (`gemini-3.1-flash-image`), and lock Omni turn settings on follow-ups ([#1646], [#1652], [#1656], [#1659], [#1707]).

### Deprecated
- **Imagen Models:** Deprecate legacy Imagen endpoints across Google Cloud and Vertex AI (shut down August 17, 2026) in favor of Nano Banana (Gemini Image Generation). See the [Imagen models migration guide](https://firebase.google.com/docs/ai-logic/imagen-models-migration?api=dev) ([#1651], [#1654], [#1655], [#1758]).

## [1.12.3] - 2026-07-10

### Added
- **Gemini Omni Library Chooser:** Add library media chooser integration to Gemini Omni upload controls (`gmcs-dfv`, [#1549]).

## [1.12.2] - 2026-07-10

### Fixed
- **Pixie Compositor & Library Tiles:** Fix Pixie Compositor connection context reuse when layering video/audio and resolve Library v2 `list[dataclass]` state serialization crashes (`gmcs-jd9`, `gmcs-mzx`, [#1547]).

## [1.12.1] - 2026-07-09

### Added
- **Gemini 3.1 Flash-Lite Image (Nano Banana 2 Lite):** Add `gemini-3.1-flash-lite-image` support with `1K` image size capability (`gmcs-qpz`, `gmcs-awy`, [#1544]).

## [1.12.0] - 2026-07-08

### Added
- **Gemini Omni Video Studio:** Integrate Gemini Omni Flash video generation and multi-turn editing workspace with GCS signed URL uploads (`gmcs-f09`, `gmcs-65v`, [#1542]).

## [1.11.0] - 2026-06-25

### Added
- **Library v2 & Async Veo Thumbnails:** Modernize the Asset Library (`library_v2`) and generate video thumbnails asynchronously via Cloud Tasks with thread fallback ([#1501], [#1508]).

## [1.10.0] - 2026-06-01

### Added
- **Gemini Image GA & Video Support:** Upgrade Gemini Image models to GA schema with dynamic file upload UI and thumbnail support (`gmcs-lx2`, [#1447]).

## [1.9.0] - 2026-05-24

### Added
- **Starlight Documentation Hub:** Migrate deployment guides, architecture diagrams, and MCP documentation to the Astro Starlight documentation hub ([#1340], [#1428]).

## [1.8.0] - 2026-04-15

### Added
- **Gemini 3.1 TTS Default & Configurable Workflows:** Set Gemini 3.1 TTS as default and add configurable model/duration overrides for Interior Design and Object Rotation ([#1277], [#1366], [#1367], [#1379], [#1390]).

## [1.7.6] - 2026-04-06

### Changed
- **Veo 3.1 GA Defaults & Workflow Fixes:** Update Veo defaults to GA 3.1 models, add retry image critique, deprecate Product in Scene, and fix Lyria and Character Consistency routing ([#1226], [#1233], [#1234], [#1235]).

## [1.6.0] - 2026-04-02

### Added
- **Veo 3.1 Lite & Dynamic Versioning:** Add Veo 3.1 Lite model support and combine build-time JSON metadata with dynamic `pyproject.toml` package versioning (`gmcs-g13`, [#1215]).

## [1.4.0] - 2026-01-15

### Added
- **Veo 3.1 GA Discovery Matrix & C2PA Provenance:** Integrate Veo 3.1 GA capabilities, video extension actions, and server-side C2PA Content Credentials inspection ([#960]).

[1.24.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/85dbcc79
[1.23.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/cbe07a61
[1.22.1]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/f3fcaed1
[1.22.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/f7a4f3e9
[1.21.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/ee2e3929
[1.20.2]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/d67103df
[1.20.1]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/f94bffad
[1.20.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/7c0fadcb
[1.19.1]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/e894e63c
[1.19.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/2cb4b8b2
[1.18.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/96455c2a
[1.17.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/2a21bac9
[1.16.1]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/aa05f70c
[1.16.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/50920a76
[1.15.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/998acfd6
[1.14.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/a3a998a6
[1.13.1]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/ae4be8ca
[1.13.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/8e6be155
[1.12.3]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/e3785236
[1.12.2]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/752d3978
[1.12.1]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/2bc025ae
[1.12.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/45ff7e55
[1.11.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/b8e7325c
[1.10.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/cf673467
[1.9.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/10754daf
[1.8.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/22bf295d
[1.7.6]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/e8f687ca
[1.6.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/45f3d87e
[1.4.0]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/c58dd1e0
[#2168]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2168
[#2166]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2166
[#2163]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2163
[#2162]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2162
[#2159]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2159
[#2158]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2158
[#2157]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2157
[#2156]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2156
[#2155]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2155
[#2154]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2154
[#2153]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2153
[#2152]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2152
[#2151]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2151
[#2150]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2150
[#2144]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2144
[#2143]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2143
[#2141]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2141
[#2140]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2140
[#2138]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2138
[#2137]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2137
[#2136]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2136
[#2130]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2130
[#2097]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2097
[#2096]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2096
[#2086]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2086
[#2084]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2084
[#2083]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2083
[#2079]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2079
[#2073]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2073
[#2072]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/2072
[#1993]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1993
[#1992]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1992
[#1986]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1986
[#1983]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1983
[#1982]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1982
[#1980]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1980
[#1971]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1971
[#1970]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1970
[#1945]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1945
[#1937]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1937
[#1930]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1930
[#1923]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1923
[#1920]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1920
[#1908]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1908
[#1905]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1905
[#1902]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1902
[#1900]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1900
[#1895]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1895
[#1884]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1884
[#1883]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1883
[#1872]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1872
[#1871]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1871
[#1870]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1870
[#1855]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1855
[#1844]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1844
[#1780]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1780
[#1758]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1758
[#1756]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1756
[#1753]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1753
[#1707]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1707
[#1661]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1661
[#1659]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1659
[#1656]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1656
[#1655]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1655
[#1654]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1654
[#1652]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1652
[#1651]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1651
[#1648]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1648
[#1647]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1647
[#1646]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1646
[#1645]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1645
[#1642]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1642
[#1639]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1639
[#1638]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1638
[#1549]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1549
[#1547]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1547
[#1544]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1544
[#1542]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1542
[#1508]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1508
[#1501]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1501
[#1447]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1447
[#1428]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1428
[#1390]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1390
[#1379]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1379
[#1367]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1367
[#1366]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1366
[#1340]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1340
[#1277]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1277
[#1235]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1235
[#1234]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1234
[#1233]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1233
[#1226]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1226
[#1215]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1215
[#960]: https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/960
