# mesop-to-lit-skill

An **Agent Skill** that assesses and assists converting a **Mesop** (Python) app to a **FastAPI**
JSON backend + **Lit** web components + **Web Awesome (default)** or **Material 3 (Material Web, opt-in)**, built with **Vite**. Point it
at a Mesop app (or a repo root) and it runs a deterministic analyzer to inventory routes, state, the
UI/logic seam, constructs, serve model, and hard topics, then applies a construct map and a
stock/compose/custom component-decision framework to produce a conversion assessment — and, in its
ASSIST half, drives the scaffold → endpoints → components → tests of the actual port.

> **This is an Agent Skill**, not a runnable app. It is consumed by an agent (Claude Code), which
> discovers it from `skill/mesop-to-lit/SKILL.md` and invokes it when asked to assess, plan, port,
> migrate, or convert a Mesop app off Mesop to Lit/FastAPI with Web Awesome or Material 3. The only executable is a
> standard-library-only Python analyzer the agent runs via Bash.

**Author:** ghchinoy
**License:** Apache-2.0

## What's here

```
mesop-to-lit-skill/
  README.md                              # this file
  skill/mesop-to-lit/                    # the Agent Skill itself
    SKILL.md                             #   frontmatter + ASSESS/ASSIST workflows
    references/                          #   progressive-disclosure depth (construct map, component
                                         #   decisions, state/transport, serve/deploy, hard topics,
                                         #   assist-scaffold/endpoints/components/testing)
    scripts/analyze_mesop_app.py         #   the deterministic, stdlib-only analyzer
  docs/how-to-use-the-skill.md           # operator-facing how-to (when to use, invoke, workflows, pitfalls)
  examples/promptlandia-checklist-slice/ # the converted app SOURCE (proof; build artifacts excluded)
  evidence/                              # assessment reports, conversion results, quality-gate reviews
```

Start with `docs/how-to-use-the-skill.md` to operate the skill; read `skill/mesop-to-lit/SKILL.md`
for the authoritative workflow; see `examples/` to reproduce the proof and `evidence/` for the
reports that back it.

## Status / evidence

**Proven.** The skill was validated by converting the Promptlandia **checklist vertical slice**
end-to-end with it (source in `examples/promptlandia-checklist-slice/`). The conversion is green on
all three gates — **backend `pytest` 15 passed**, **frontend `vitest` 16 passed**, **`vite build`
clean**, and **no `mesop` imports remain**. The ASSESS half was additionally validated on a small
app (`babel`) and on GMCS (~28k LOC, 42 routes) without crashing. The skill and the converted slice
passed **code, security, and test quality gates — all APPROVE** (code/security in two rounds, after
fixing a SPA-fallback path-traversal, an error-envelope `str(exc)` leak, and adding a
markdown-sanitization regression test). See `evidence/` (start with `evidence/RESULTS.md`).

## Placement note

This entry is laid out as a top-level `experiments/` experiment. It could alternatively live under
**`experiments/agent_tools/`**, which is the declared home for Agent Skills (alongside MCP servers
and plugins). Because this is an Agent Skill rather than a stand-alone application, `agent_tools/`
may be the more natural home. **Final placement is an owner decision** — the contents are identical
either way.
