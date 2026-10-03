# Deprecation status: `mcp-imagen-go`

> Tracking issue: **[#1588 — Scope: deprecate Imagen references across genmedia](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1588)**

This document records the current deprecation state of the `mcp-imagen-go`
MCP server, audits the remaining references to it across the repository,
and frames the open decision called out in issue #1588 so a maintainer can
close the issue with a clear yes/no on directory removal.

## 1. Background

The Imagen family of models reached its announced sunset on **2026-06-30**
(the "Imagen deprecation as of June 30, 2026" note in `install.sh`).
`experiments/agent_tools` additionally documents that the Imagen endpoints
were shut down and return HTTP 404 as of **2026-08-17**. On the core-app
side, the Character Consistency edit path was ported to Nano Banana
(Gemini 3.1 Flash Image) in **PR #1659**, the `/edit_images` page was
removed in **PR #1651**, the dead `imagen-3.0-*` constants were dropped in
**PR #1654**, and the sunsetting `imagen-3.0-fast-generate-001` /
`imagen-3.0-generate-002` dropdown entries were removed in **PR #1655**.

On the MCP-server side, the closed draft **PR #1245** carried a single
relevant commit (`dc48d1f6`, 11 files, +42/-55) doing documentation and
sample-config reference swaps `imagen → nanobanana/gemini`. Every content
change in that commit is already present on `main` (see §2), so the bulk
of the reference-swap work the issue calls for is done.

## 2. What landed already

- `install.sh:41` and `deploy-cloudrun.sh:27` exclude `mcp-imagen-go`
  from the standard install loop with `! -name 'mcp-imagen-go'`.
- `mcp-genmedia-go/README.md` flags `mcp-imagen-go` as
  *Deprecated — use `mcp-nanobanana-go` or `mcp-gemini-go` for new work;
  Imagen models are deprecated as of June 30, 2026*.
- The `gemini-extension.json` sample configs under
  `sample-agents/geminicli/sample_extensions/google-genmedia*/` no longer
  register an `imagen` entry; they ship `nanobanana` / `gemini` instead.
- `sample-agents/geminicli/sample_settings.json` registers
  `mcp-nanobanana-go` / `mcp-gemini-go` and no longer an `imagen` server.
- `CHANGELOG.md` records the deprecation under the 3.x release notes.

*How the `dc48d1f6` claim was verified:* cherry-picking `dc48d1f6` onto
current `main` conflicts in four files (`GEMINI.md`,
`mcp-genmedia-go/README.md`, `sample-agents/adk/README.md`,
`genkit-agent-js/src/index.js`) purely on context drift; resolving those
conflicts by keeping main's version yields a zero net diff — i.e. every
content change of that commit is already on `main`.

## 3. Audit: remaining references inside `experiments/mcp-genmedia/`

A `grep -rln 'mcp-imagen-go\|imagen_t2i\|mcp_imagen'
experiments/mcp-genmedia/` (GNU grep; see §6 for a caveat about
gitignore-aware searchers) against `main` returns the following hits.
Each is classified as either **acceptable** or **candidate for cleanup**.

| File | Hit | Classification |
|---|---|---|
| `mcp-genmedia-go/install.sh` | `! -name 'mcp-imagen-go'` exclusion | Acceptable — this is the deprecation enforcement |
| `mcp-genmedia-go/deploy-cloudrun.sh` | `! -name 'mcp-imagen-go'` exclusion | Acceptable — same as above |
| `mcp-genmedia-go/CHANGELOG.md` | Historical entries mentioning `mcp-imagen-go` releases | Acceptable — changelog is immutable history |
| `mcp-genmedia-go/README.md` | The "Deprecated" entry in the server list | Acceptable — this is the deprecation notice itself |
| `mcp-genmedia-go/mcp-gemini-go/handlers.go` | Comment comparing its aspect-ratio fallback with the `mcp-imagen-go` pattern | Acceptable — comparison/delta comment |
| `mcp-genmedia-go/mcp-nanobanana-go/handlers.go` | Same comparison comment | Acceptable — comparison/delta comment |
| `mcp-genmedia-go/mcp-veo-go/veo.go` | Comment citing `mcp-imagen-go` as a sibling server | Acceptable — comparison comment |
| `sample-agents/adk-genmedia-series/NAMING.md` | Naming-convention doc mentions `mcp-imagen-go/imagen.go` | Acceptable — illustrative example |
| `mcp-genmedia-go/mcp-imagen-go/imagen.go` | The server implementation | Acceptable while the dir stays — see §4 |
| `mcp-genmedia-go/mcp-imagen-go/server.json` | Server manifest | Acceptable while the dir stays |
| `mcp-genmedia-go/mcp-imagen-go/test_editing.sh` | Local test script | Acceptable while the dir stays |
| `mcp-genmedia-go/mcp-imagen-go/verify.sh` | Local verification script | Acceptable while the dir stays |
| `mcp-genmedia-go/mcp-imagen-go/README.md` | This server's own README | Acceptable — now carries the deprecation banner added by this PR |
| `mcp-genmedia-go/mcp-imagen-go/DEPRECATION.md` | This file (appears in the grep only once this PR lands) | Acceptable — the audit artifact itself |
| `mcp-genmedia-go/go.work` | Workspace includes the `./mcp-imagen-go` module | Acceptable while the dir stays — build file |
| `mcp-genmedia-go/Makefile` | Build-target list includes `mcp-imagen-go` | Acceptable while the dir stays — build file |
| `mcp-genmedia-go/Dockerfile` | Comment names `mcp-imagen-go` as a build-arg example | Acceptable — build file |
| `mcp-genmedia-go/.gitignore` | Ignores the `mcp-imagen-go/mcp-imagen-go` build output | Acceptable — build-artifact ignore rule |
| `mcp-genmedia-go/mcp-imagen-go/go.mod` | The module path itself | Acceptable while the dir stays — in-tree implementation |
| `mcp-genmedia-go/mcp-imagen-go/.gitignore` | Ignores its own built binary | Acceptable — build-artifact ignore rule |
| `mcp-genmedia-go/mcp-imagen-go/makedist` | `TOOLNAME=mcp-imagen-go` in the dist script | Acceptable while the dir stays — build script |

The first fourteen rows are what the §6 `--include` sweep returns; the
seven build/module rows only surface to `git grep -lE` (or a grep without
the `--include` filter), and are listed so that both variants stay 1:1
with this table.

**Conclusion for this tree:** inside `experiments/mcp-genmedia/` there are
no stale user-facing references left. Every hit is either the deprecation
enforcement itself, an immutable changelog entry, an in-tree
implementation or build file (kept while the directory stays), or a
historical/comparison comment. The `imagen`-named server registrations in
the in-tree sample configs were all swapped to `nanobanana` / `gemini` by
`dc48d1f6`.

## 3.1 Audit: references outside `experiments/mcp-genmedia/` (repo-wide)

Running the same pattern repo-wide finds ten more files. They sit outside
the MCP-genmedia tree the issue's checkboxes target, but they are listed
here so the audit is complete and no future maintainer is surprised by a
broader sweep:

| File | Hit | Classification |
|---|---|---|
| `experiments/agent_tools/README.md` | "intentionally not covered" note (Imagen endpoints return 404 since 2026-08-17) | Acceptable — deprecation notice |
| `experiments/agent_tools/smoke_generate_and_verify.sh` | Same note as a comment | Acceptable — deprecation notice |
| `docs-site/src/content/docs/experiments/agent-tools/index.md` | Mirror of the same note | Acceptable — deprecation notice |
| `.github/workflows/mcp-genmedia-go.yml` | Build loop still includes `mcp-imagen-go` | Consistent while the dir stays; drop together with the directory in the removal PR |
| `experiments/.github/workflows/publish-mcp.yml` | Publish matrix still includes `mcp-imagen-go` | Maintainer decision — a deprecated server is still being published; drop together with the directory |
| `docs-site/src/content/docs/experiments/mcp-genmedia/agents/adk.md` | Tells ADK users to start `mcp-imagen-go --transport sse` | **Candidate for cleanup** — stale user-facing setup instruction |
| `docs-site/src/content/docs/experiments/mcp-genmedia/agents/geminicli.md` | Example settings still register an `"imagen"` server running `mcp-imagen-go`, plus troubleshooting references | **Candidate for cleanup** — the equivalent in-tree config (`sample-agents/geminicli/sample_settings.json`) was already swapped by `dc48d1f6`; the hand-maintained docs-site copy was not |
| `docs-site/src/content/docs/experiments/mcp-genmedia/index.md` | Uses `mcp-imagen-go --transport http` as the generic "running the servers" example | **Candidate for cleanup** — swap the example to a non-deprecated server |
| `docs-site/src/content/docs/experiments/mcp-genmedia/mcp-imagen-go/index.md` | Full published page for the server, no deprecation notice, already drifted from the in-repo README | **Candidate for cleanup** — needs a banner or a pointer to this file |
| `docs-site/astro.config.mjs` | Sidebar nav entry for the server page | Flag for the docs-site follow-up — travels with whatever is decided for that page |

**Repo-wide conclusion:** the MCP-genmedia tree itself is clean, but the
hand-maintained docs-site still routes new users to `mcp-imagen-go` in
three places (plus an un-bannered server page). These are reference swaps
of exactly the kind this issue already landed in-tree via `dc48d1f6`, so
they are natural follow-up work; this PR deliberately keeps its scope to
the MCP-genmedia tree and can deliver the docs-site swaps as a follow-up
PR if the maintainer prefers that ordering.

## 4. Open decision (needs maintainer input)

Issue #1588 explicitly asks:

> **References-only deprecation, OR also REMOVE the `mcp-imagen-go`
> server directory itself?** (PR #1245 was references-only.)

The maintainer inventory comment from 2026-08-22 initially flagged
`/imagen-upscale` and Virtual Try-On as Imagen-dependent surfaces with "no
Nano Banana equivalent"
([comment](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1588#issuecomment-5377763324)).
A correction posted the same day, after live verification on Vertex AI
with `gemini-3.1-flash-image`, established that **both surfaces do have
practical Nano Banana approximations**, while documenting where those
approximations fall short of the purpose-built Imagen models
([correction](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1588#issuecomment-5377862634)):

1. **Virtual Try-On** — works as a Nano Banana image-references composite,
   but `virtual-try-on-001` remains the purpose-built, garment-faithful
   option for catalog-grade output.
2. **Upscale** — a "change nothing" prompt plus the Gemini resolution
   parameter reaches 2K/4K with real synthesized detail, but it is a
   re-generation conditioned on the input, not a faithful
   super-resolution; `imagen-4.0-upscale-preview` remains the
   higher-fidelity tool (`models/upscale.py:31`).

Separately, `experiments/agent_tools` documents that the Imagen endpoints
return HTTP 404 as of 2026-08-17, which suggests the in-tree server's
generation path may already be non-functional in practice. So the
directory is kept today as reference and as the home of those two
higher-fidelity model IDs, not as a live user path — `install.sh` and
`deploy-cloudrun.sh` exclude it from installs either way.

**Recommendation (deferred to maintainer):** keep `mcp-imagen-go/`
in-tree for now (references-only, the path the closed PR #1245 took),
until the maintainer decides whether the verified Nano Banana
approximations are acceptable for the upscale and VTO surfaces. If they
are, a follow-up PR can delete the directory wholesale, drop the
`! -name 'mcp-imagen-go'` exclusions from `install.sh` /
`deploy-cloudrun.sh`, and remove the two CI entries listed in §3.1. If
the higher-fidelity Imagen models are still wanted, the directory can
remain inert under the existing exclusions at no operational cost. Either
way the removal, when agreed, is a single mechanical follow-up PR — the
audit above lists everything that references the directory so nothing is
missed.

## 5. Changes in this PR

- Add a deprecation banner to the top of `mcp-imagen-go/README.md`
  pointing users at `mcp-nanobanana-go` / `mcp-gemini-go` and at this
  file.
- Add this `DEPRECATION.md` with the full audit (§3 in-tree, §3.1
  repo-wide) and the framed open decision.

No code changes. No reference removals beyond what is already on `main`.
This PR exists to give issue #1588 a single, linkable artifact that
records (a) that the in-tree reference swaps are complete, (b) that the
remaining stale user-facing references live in the hand-maintained
docs-site (§3.1), and (c) the exact grep audit a future maintainer can
re-run to confirm nothing has regressed.

## 6. How to re-run the audit

```bash
git clone https://github.com/GoogleCloudPlatform/genmedia-creative-studio
cd genmedia-creative-studio

# Inside the MCP-genmedia tree (matches §3):
grep -rln 'mcp-imagen-go\|imagen_t2i\|mcp_imagen' experiments/mcp-genmedia/ \
    --include='*.md' --include='*.json' --include='*.py' \
    --include='*.js' --include='*.ts' --include='*.go' \
    --include='*.sh' --include='*.yaml' --include='*.yml'

# Repo-wide sweep (matches §3.1):
grep -rln 'mcp-imagen-go\|imagen_t2i\|mcp_imagen' . \
    --exclude-dir=node_modules --exclude-dir=.git \
    --include='*.md' --include='*.json' --include='*.py' \
    --include='*.js' --include='*.ts' --include='*.go' \
    --include='*.sh' --include='*.yaml' --include='*.yml'
```

Each hit should be classifiable into one of the rows in §3 / §3.1 — both
for the two `--include` sweeps and for the `git grep -lE` variant.

**Caveat:** use GNU `grep` (the default on Linux). gitignore-aware
searchers such as ripgrep or ugrep silently skip the
`mcp-genmedia-go/mcp-*-go` subtree, because the repo's `.gitignore` has a
`**/mcp-*-go/mcp-*-go` rule meant for untracked build outputs that also
matches those tracked source files. ripgrep users should add `--no-ignore`;
as a robust alternative, `git grep -lE 'mcp-imagen-go|imagen_t2i|mcp_imagen'`
searches exactly the tracked files and is immune to ignore rules.
