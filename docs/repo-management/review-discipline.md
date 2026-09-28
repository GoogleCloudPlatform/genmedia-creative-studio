# Review Discipline

> **Purpose:** describe how code review works here — who reviews, how reviewers rotate, when
> escalation stops, and what each severity label means — with a real worked example.

Review discipline applies to human-authored changes of substance (as opposed to the routine bot
bumps handled by the [recurring jobs](./recurring-jobs.md)). Its whole reason for existing is
captured by the worked example below: **an independent reviewer caught a real, silent,
description-invisible regression that would otherwise have shipped.**

## The core rules

### Author ≠ reviewer

The person (or agent) who wrote a change **never reviews their own change.** Self-review misses
exactly the things you were too close to notice. Review is always done by someone else.

### Reviewers rotate across rounds

A change often needs more than one round: review → author fixes → re-review. Reviewers **rotate**
across those rounds rather than one reviewer owning a PR forever. This keeps a fresh pair of eyes
on each round and prevents a single reviewer's blind spots from carrying through.

### A 6-round escalation cap

Review rounds are capped at **6**. If a change can't reach approval within six rounds, that is a
signal the change (or the disagreement about it) needs to be escalated to a human decision rather
than looping indefinitely. The cap prevents endless back-and-forth.

## The severity vocabulary

Every review comment carries a severity label so the author knows what actually blocks a merge and
what's optional. The labels, from most to least serious:

| Severity | Meaning | Blocks merge? |
|---|---|---|
| **Critical** | A correctness, security, or data-loss problem. Must be fixed. | Yes |
| **Required** | A real issue that must be resolved before merge (e.g. a merge conflict, an unexplained regression). | Yes |
| **Nit** | A small quality or style point — trailing newline, a typo, a doc mislabel. Worth fixing, not worth blocking indefinitely. | No |
| **Optional** | A suggestion the author may take or leave. | No |
| **FYI** | Context or an observation; no action expected. | No |

The distinction that matters most in practice is **Required vs. Nit**: a Required item stops the
merge; a Nit is cleaned up but never holds a good change hostage.

## Worked example: PR #1728

**PR #1728** — *`fix(run-veo-run): support multi-client Vertex locations and GA Veo models`* —
was authored by the repository owner. Because the author never reviews their own change, it went
to an independent reviewer. It took three rounds.

### Round 1 — REQUEST-CHANGES

The application code itself was correct and well-scoped (a clean Go client split, a model
migration to generally-available Veo models, some config hardening). But the reviewer found **two
Required issues** — and note that **neither was mentioned in the PR description**:

1. **A merge conflict against `main`.** The branch was behind `main` and conflicted in
   `server/go.mod` / `server/go.sum`. Not fatal to the design, but it had to be resolved before
   merge.
2. **An unexplained dependency regression.** The PR silently **downgraded** the Go GenAI SDK
   (`google.golang.org/genai`) from **v1.67.0 to v1.39.0** — 28 minor versions backward — while
   `main` had already moved *forward* to **v1.68.0**. Nothing in the PR description mentioned this.
   It was the direct cause of the go.mod conflict.

> **Why this is the whole point.** The downgrade was invisible in the description and buried in a
> large auto-generated lockfile diff. CI didn't flag it. Only an independent reviewer, actively
> cross-checking the change against `main`, caught that the SDK was quietly moving the wrong
> direction. Left alone, a regression would have shipped.

The reviewer also noted two **Nits** (non-blocking): two source files were missing a trailing
newline (a formatting-gate risk), and a documentation diagram was relabeled `Gemini 3` → `Gemini
2.5`, contradicting the actual runtime default.

### Rounds 2–3 — the author responds, then APPROVE

The author rebased onto `main` and re-tidied the change — but **Round 2 was itself a
REQUEST-CHANGES.** The genai fix was only partial: re-reading the whole `go.mod` against `main`
surfaced a new, narrowed blocker — a broad backward dependency sweep (storage, grpc, otel,
`golang.org/x/*`, `google.golang.org/api`, and more) plus a `go 1.25.8 → 1.25.2` directive. That
was fixed only in Round 3, by which point every blocking item was verified fixed:

- `go.mod` was **byte-identical to `main`** — the entire backward dependency sweep was reverted and
  the SDK was back at `main`'s v1.68.0.
- Both trailing-newline Nits were fixed.
- The `Gemini 2.5` doc mislabel was reverted to `Gemini 3` (and a related doc corrected as a bonus).

With no merge-blocking items remaining, the verdict was **APPROVE**. (The only non-green state was
a CI check waiting in the queue and the normal branch-protection "needs an approving review" gate —
neither a real failure.)

### What to draw from it

- **Independent review earns its keep on exactly the invisible stuff** — a silent dependency
  downgrade that no description mentioned and no test caught.
- **Severity labels kept the rounds focused:** the two Required items had to be fixed; the two Nits
  were cleaned up along the way but never derailed a fundamentally good change.
- **The author-≠-reviewer rule made the catch possible** — the owner authored a correct-looking
  change; a second set of eyes found what the author couldn't see.

## How this connects

The mindset here is the same one behind the [verification principle](./verification-principle.md):
*don't trust the description — check the actual change.* One applies it to dependency resolvers, the
other to human-authored code. For how a review like this gets sized and dispatched in the first
place, see [extending-the-system.md](./extending-the-system.md).
