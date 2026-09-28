# The Verification Principle

> **Purpose:** name and explain the discipline that governs every merge decision here — *never
> merge on a green CI run and a bot's description alone; verify the change empirically first.*

## The principle, in one line

> **Green CI ≠ resolver-clean.**

A passing Continuous Integration (CI) run tells you the tests that exist still pass. It does **not**
tell you that a new dependency version can actually be installed alongside everything else your
project needs. Those are different questions, and the gap between them is where real breakage
hides.

## Why CI isn't enough

When a bot proposes bumping a library, it edits a version number in a requirements file and writes
a short description of what changed. Two things are easy to assume and both are wrong:

1. **"CI is green, so it installs fine."** In this project, CI does **not** actually `pip install`
   the affected requirements files. It runs the existing test suite, which never exercises the
   dependency-resolution step for the bumped file. So a version that is impossible to install can
   still show all-green.
2. **"The bot's description says it's a safe minor bump, so it's safe."** The description reflects
   the *library's own* release notes. It knows nothing about *your* other pinned dependencies that
   must coexist with it.

The failure mode both assumptions miss is a **`ResolutionImpossible`**: the moment you try to
install the new version together with its real co-dependents, the version constraints contradict
each other and nothing can be installed.

> **Transitive dependency:** a dependency of a dependency. You install library A; A needs library
> B; B is *transitive*. Conflicts often live here — you never named B, but its version rules can
> still block an install.

## The actual check

Before merging any dependency bump, run a real dependency-resolver **dry-run** — a simulated
install that reports what *would* happen without changing anything:

```
pip install --dry-run <bumped-package>==<new-version> <its-real-co-dependents>
# or the equivalent uv command
```

This exercises exactly the conflict CI never sees. If the resolver can satisfy every constraint,
you get a clean "would install …" result. If it can't, you get a verbatim `ResolutionImpossible`
naming the conflicting requirement — a real, reproducible signal, not a guess.

## Two real catches

Both of the following came from the same review pass. **Both had green CI.** Both would have
shipped broken if CI and the bot description had been trusted.

### Catch #1 — deepdiff 8.6.2 → 9.1.0 (PR #1714) — HELD

- **The proposal:** bump `deepdiff` from 8.6.2 to 9.1.0 in the arena experiment's requirements.
- **The hidden constraint:** `deepdiff` is used *transitively* by `mesop` (pinned at `mesop==1.3.4`).
  `mesop 1.3.4` requires `deepdiff<9,>=8.6.1` — that is, deepdiff must stay **below** version 9.
- **What the dry-run produced:** installing `deepdiff==9.1.0` with `mesop==1.3.4` gave a real
  `ResolutionImpossible`: *"mesop 1.3.4 depends on deepdiff<9 and >=8.6.1."*
- **Verdict:** **Held.** Version 9.1.0 violates the `<9` cap. CI never caught it because CI never
  tried the install.

### Catch #2 — firebase-admin 6.9.0 → 7.5.0 (PR #1716) — HELD

- **The proposal:** bump `firebase-admin` from 6.9.0 to 7.5.0.
- **The subtlety worth internalizing:** the project's *actual use* of firebase-admin was fine.
  None of the version-7 breaking changes touched the few functions this project calls. If you only
  read the code and the diff, you would approve it.
- **The real blocker was transitive:** `firebase-admin 7.5.0` requires
  `google-cloud-storage>=3.1.1`, but the project pins `google-cloud-storage==2.19.0`, and the
  one-line bump didn't touch that pin.
- **What the dry-run produced:** installing `firebase-admin==7.5.0` with
  `google-cloud-storage==2.19.0` gave a real `ResolutionImpossible`: *"firebase-admin 7.5.0 depends
  on google-cloud-storage>=3.1.1."*
- **Verdict:** **Held.** The blocker was purely the resolver constraint — something the diff alone
  could **never** reveal. A proper fix would require a coordinated re-resolve that also bumps
  `google-cloud-storage` into the 3.x range (itself a major bump to verify separately).

## The flip side: the same check finds silent, pre-existing drift

The discipline isn't only about blocking bad merges — it also surfaces problems already sitting on
`main`.

### PR #1713 — cffi 1.17.1 → 2.1.1 — APPROVED (and it *fixed* a latent bug)

- `cffi` is used transitively by `cryptography`, which was already pinned at `cryptography==50.0.0`.
- `cryptography 50.0.0` **requires `cffi>=2.0.0`** — but `main` still pinned `cffi 1.17.1`. In other
  words, `main` was **already internally inconsistent**; it just hadn't been noticed because nothing
  had forced a full re-resolve.
- The dry-run confirmed `cffi==2.1.1` with `cryptography==50.0.0` installs cleanly.
- **Verdict:** **Approved** — and it was the highest-value change of the approved PRs, because it
  corrected an existing latent inconsistency rather than introducing a new one.

**Takeaway:** the same empirical check that catches incoming breakage also reveals quiet drift that
is *already there*.

## The structural root cause

Why were the broken bumps broken in the first place? All of these PRs edited a **single line** in a
frozen lock file (`experiments/arena/requirements.txt`) without doing a full re-resolve.

- `requirements.txt` here is a *frozen lock* — a fully-resolved, exported snapshot of every pinned
  version, produced by the `uv` tool via `uv lock`.
- Editing one line by hand does **not** re-run the resolver, so any *new* transitive requirements
  the bump introduces are never reflected. The lock ends up internally inconsistent.
- The correct fix for a bump that changes transitive requirements is a full `uv lock` re-resolve,
  not a hand-edited single line.

You don't need to master `uv` to use this document. The practical lesson is simple: **a one-line
version edit is exactly the kind of change most likely to be silently broken, so it is exactly the
kind that must be verified empirically before merging.**

## Where this principle is applied

- [Bot-PR Cleanup](./recurring-jobs.md#2-dependabotrenovate-bot-pr-cleanup) runs this check before
  every automatic merge — it's step 4 of the merge criteria.
- [General Chore Review](./recurring-jobs.md#3-general-chore--dependency-pr-review) runs it before
  recommending anything for sign-off.
- The same "verify, don't take the description's word for it" mindset drives
  [review discipline](./review-discipline.md), where independent review caught a regression that no
  description mentioned.
