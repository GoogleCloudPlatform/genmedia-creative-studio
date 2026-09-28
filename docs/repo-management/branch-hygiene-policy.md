# Branch Hygiene Policy

> **Purpose:** give a repeatable policy for deciding when a branch is safe to delete — and the
> safeguard that stops genuinely valuable work from being deleted by mistake.

Over time a repository collects branches: every merged feature tends to leave its branch behind.
The pile grows until nobody can tell which branches still matter. This document is the **reusable
policy** for pruning that pile safely. The one-time cleanup that produced it is cited afterward as
the worked example.

## The policy: decide by PR merge status, not the commit graph

For each candidate branch, look at the **pull request** associated with it and apply these
criteria:

| Branch's situation | Risk | Action |
|---|---|---|
| Behind a **MERGED** PR | None — the content is already on `main`. | **Safe to delete.** |
| Behind a **closed-not-merged** PR | Low — usually owner-closed or abandoned. | **Confirm, then delete.** Check per branch; the work was deliberately not merged. |
| **No PR found, and stale** | Unknown — could be abandoned, could be unmerged work. | **Uniqueness review required** (see below) before any deletion. |
| **Active automation** or **needs owner judgment** | Deleting could break something live. | **Leave untouched** without explicit instruction. |

### The uniqueness review (the critical safeguard)

When a branch has **no PR and is stale**, deletion status is genuinely unknown — so you never
delete it on the naive assumption that "no PR means abandoned." Instead you ask one question:

> **Does this branch hold anything of unique value that is not already on `main`?**

If yes, it is **not** deleted. It is flagged for an owner decision, with a tracked follow-up so the
work isn't silently lost. **Never delete something with unique value without a tracked follow-up.**

### Leave-alone categories

Some branches are deliberately kept regardless of age:

- **Active-automation branches** — for example, `release-please--...` branches (which drive release
  automation) or any branch with a currently open PR.
- **Anything needing owner judgment** — for example, a tooling-metadata ref whose purpose isn't a
  normal development branch.

These are never deleted without an explicit instruction.

### A methodology caution: don't trust "ahead/behind" here

It is tempting to judge whether a branch is merged by counting its unique commits against `main`
(the git "ahead/behind" numbers). **In this repository that signal is unreliable**, for two
reasons:

1. **The history was scrubbed** (with `git-filter-repo`) to remove large legacy binaries. The scrub
   rewrote commit identities, so most branches show as wildly "diverged" from `main` even when their
   content is fully merged.
2. **The repository squash-merges PRs.** A squash-merge collapses a branch into a single new commit
   on `main`, so the branch's original commits are never ancestors of `main` — a merged branch still
   shows "ahead."

Because of both, **PR merge status — not the commit graph — is the authoritative signal** for
whether a branch's content is on `main`. The ahead/behind numbers are noise here.

## Worked example: the 111-branch cleanup

A one-time audit inventoried the upstream repository's branches.

- **111 branches total** (110 candidates, excluding `main`).
- **88 of them sat behind a MERGED PR** — their content was already on `main`, so they were safe to
  delete. This un-pruned merged work was the dominant cause of the pile.
- A common assumption going in was that stale dependency-bot branches were inflating the count.
  **They weren't** — there was exactly **1** bot branch. The pile was almost entirely human feature
  branches left behind after their PRs merged.

Applying the policy sorted the 110 candidates cleanly: the bulk were safe deletes (merged PRs), a
smaller set needed per-branch confirmation (closed-not-merged, or no-PR-and-stale), and a handful
were left untouched (active automation and owner-judgment refs).

## The real catch: a mislabeled branch that held unique work

This is the concrete argument for why the "no-PR-and-stale ⇒ uniqueness review" step exists.

A branch named **`mcp/otel-configure`** looked like abandoned observability ("OTel") configuration
work — no PR, stale for ~11 months. The naive rule ("no PR + stale ⇒ delete") would have deleted it.

The uniqueness review found that **the branch name was wrong.** It contained **no OTel work at
all.** It actually held a genuine, unmerged **VTO ("Virtual Try-On") critique feature**:

> **VTO (Virtual Try-On):** the app takes a photo of a person and a photo of a garment and
> generates an image of that person *wearing* the garment. The feature on this branch adds an
> automatic **critique** step that runs afterward — it hands the garment image and the generated
> result to **Gemini as a judge** and asks, in effect, *"does the garment look well-placed on the
> model?"*, then displays the answer.

Checking the branch's actual content against `main` confirmed this feature existed **nowhere on
`main`** — it was real, unique, unmerged work. (It was an unfinished prototype, not a shippable
feature, but that is a reason to *hand it to the owner*, not to silently delete it.)

**So instead of deletion, it was flagged for an owner decision.** That is the safeguard working
exactly as intended: without the uniqueness review, a genuine feature would have been erased because
someone once gave the branch a misleading name.

## The lesson

- **Merge status, not the commit graph, tells you if content is safe to delete** — especially in a
  repository whose history was scrubbed and which squash-merges.
- **"No PR" does not mean "no value."** The uniqueness review is the cheap insurance that catches the
  rare, expensive mistake.
- **When in doubt, flag for a human with a tracked follow-up** — never delete unique work on an
  assumption.
