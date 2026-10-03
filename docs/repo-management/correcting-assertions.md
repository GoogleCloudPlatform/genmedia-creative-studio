# Correcting Assertions

> **Purpose:** name the discipline that governs how a wrong claim gets fixed — *the thing you
> correct is the property, not the one sentence someone happened to show you.*

## The principle, in one line

> **When correcting an assertion in comments, documentation, or a contract, the unit of correction
> is the PROPERTY, not the sentence. Enumerate every site that asserts the property, rule on the
> SET, and prove enumeration completeness mechanically before writing any correction.**

## Why this is not just "grep before you edit"

Stripped of its rationale the principle gets closed as obvious, so the rationale travels with it.
It has two halves.

**A property asserted at N sites, corrected where it was noticed, leaves N−1.** Each round searches
for *the previous round's wrong sentence* rather than for *every assertion of the property*. The
round closes, a reviewer signs off, and the property is still wrong in the file.

**Sweep the terse sites deliberately — as a prompt, not as a measured law.** A terse site states the
claim most baldly: no hedge, no qualifier, no evidence next to it. That makes it cheap to miss, and
it shares the least wording with the verbose site you already fixed, so a phrase-search seeded on
that site is the search least likely to reach it. The search you naturally run is biased *against*
the sites that assert the error most plainly.

That reachability claim is demonstrated below by literal greps against a pinned ref. The stronger
claim it is easy to slide into — that terse sites in fact *outlive* the fix more often — is **not
measured here, and this page does not assert it.** In the worked example both sites entered the file
in one commit and were corrected in one commit: identical lifespans, no differential survival in the
record. Terseness earns a place on the checklist because it is cheap to miss, not because anything
here shows it lasts longer.

> **A heuristic you put into the brief will come back confirmed in the report, and the report is
> then not independent evidence for the heuristic.**

## The worked example

> **Note on status.** This comes from **in-flight review work** — an open pull request stack, not
> merged, not applied, not deployed.

> **Terraform apply:** the step where an infrastructure tool creates or changes real resources.
>
> **ReplicaSet:** the Kubernetes object owning the pods for one version of a running application.

One Terraform module comment asserted a property: *`wait_for_rollout = true` causes the apply to
block until the new ReplicaSet is healthy.* That property is **documented by the provider but was
never measured on this program's cluster**. The mechanism is real; what was unsupported was stating
flatly, as a fact about *our* deployment, that this is what would happen.

The file is `deploy/terraform/modules/gke-workload/main.tf`. Unless the surrounding text says
otherwise, every line number below is given **as of ref `f5691c30`** — the **before** state, the
file as it stood ahead of the property-wide sweep — because a bare line number is not a citation.
The corrections were made in the child commit **`de4d6145`**, the **after** state. Both refs sit on
the same pull request; the Terraform text and grep results quoted below are reproduced inline so the
argument stays readable if either ref becomes unreachable.

At the before ref the property is asserted at two sites: the verbose preamble clause at lines
122–124, and the bare trailing comment on the attribute itself at line 268. Both entered the file in
a single commit — `d7ee0e2a`, the parent of the before ref — and both were corrected in `de4d6145`,
so the record holds no example of one of them outliving the other. What it does hold is the search
problem.

### Why site 268 is the proof

Line 268 (as of ref `f5691c30`) read, verbatim:

```terraform
  wait_for_rollout = true # blocks the apply until the new ReplicaSet is healthy (see env ConfigMap comment)
```

**It carries no hedge at all** — the tersest statement of the property in the file, and the one a
phrase-search seeded on the preamble does not reach (the greps are below). That is what makes it
cheap to miss; it is not a claim that it lasted longer, and the commit record shows it did not.
**It also cross-referenced the very block being corrected**, so had the block been fixed and 268
left standing, its pointer would have resolved to a statement contradicting it while going on
lending it borrowed authority. **A cross-reference makes a stale assertion look sourced.** Fixing
the block and leaving 268 would have made 268 *strictly worse than before the fix*.

When the sweep was run property-wide — in `de4d6145`, the **after** state — **the enumeration
returned six sites where the correction that prompted it had named one.** Part of that sentence is
pinned and part of it is not, and they must not be read as one claim. **Pinned:** `f5691c30` is the
sweep's parent, a single-hunk edit to a single clause, whose own message records that
*"Nothing else in the architect's v3 text is touched"*. **Inferred:** that this parent is the
correction that *prompted* the sweep. That connector is read off stack adjacency — a linear stack,
no intervening commit, a short interval, every commit on the stack a review response — and the
public record neither confirms nor denies it. It is marked rather than dropped because it is
load-bearing: strike the causality and the sentence reports six sites where the *preceding*
correction named one, which is two adjacent commits and no argument. As of ref `de4d6145` the
property is asserted directly at lines 124–126 and 299 — the same two sites, renumbered and now
tiered — and is leaned on as a premise for other claims at lines 79, 147–148, 157–158 and 212–213.
All four of those cross-references were written or rewritten by the sweep commit itself as it tied
each dependent claim back to the tiered one; all four stand on the added side of `de4d6145`'s own
diff. The enumeration is what turned two sites into six; the count is the point, not the discovery
of older hidden text.

### The sweep left residue, and the repair left a defect

The sweep is not where the story stops, and the two commits after it on the same file are the
sharper evidence:

- One commit later, **`5c3c0d49`** is titled, in part, *"tier the remaining stall-path claim"*. The
  sweep had covered three properties — ordering, wait and stall-path — and it had rewritten that
  `locals` comment wholesale, reworking the tier language inside it. It still left the stall-path
  claim two lines further down untiered, and `5c3c0d49` had to add it. **A sweep run as a sweep,
  rewriting the very block, still left N−1.**
- The commit after that, **`907a6110`**, is titled, in part, *"repair a hyphen-join artifact
  introduced by 5c3c0d49's comment reflow"* — **a correction introducing a fresh defect in the file
  it was correcting**, the second correction in a row to go wrong, in a different way.

Both are harder claims than "the fix missed a site", and both are checkable: the commit subjects and
their diffs are on the public record, not in anyone's recollection.

## The second-order finding

When the defect was escalated, the reviewer ruled on the site they had been shown and wrote an
acceptance check for the fix. **That check reproduced the very defect it was written to prevent**,
twice over: it was **scoped to the preamble**, so it would have gone green with line 268 intact; and
its negative test was the preamble's **exact substring**, while 268 used inverted word order. Both
greps ran against the file at ref `f5691c30`:

```text
grep -nF "so the apply blocks until the new ReplicaSet is healthy" deploy/terraform/modules/gke-workload/main.tf
  → line 124 only
grep -nF "blocks the apply until the new ReplicaSet is healthy" deploy/terraform/modules/gke-workload/main.tf
  → line 268 only
```

*So the apply blocks* versus *blocks the apply*. Had the preamble been corrected and 268 left
standing, **a literal grep for the check's own string would have returned clean on a file that still
asserted the property** — a state no ref in the record actually holds, because `de4d6145` corrected
both sites at once. The failure survived contact with someone who had *just named it*. **A checker
derived from the instance you were shown inherits that instance's scope.** Re-derive the check from
the property.

## The document as its own specimen

While this page was being written it asserted its own in-flight status at three sites: the status
note under the worked example — "not merged, not applied, not deployed" — a clause in the paragraph
naming the refs, "Both sit on the same open, unmerged pull request", and a bare two-word aside in
the sentence about the sweep, "still unmerged". The aside is the tersest of the three and shares no
multi-word phrase with any of the others. With the prominent status note — the site a fixer goes to
first — it shares not one whole word, only the substring *merged*, which that note carries negated.
Had it been left, whoever next updated that status note would have gone to the prominent site and
would likely have left the aside standing — a prediction from reachability and salience, not a
measurement of how long terse sites last. A document arguing that the unit of correction is the
property was on track to become an instance of its own subject. The remedy applied was the one
prescribed here: make the status note the one place on the page that asserts it, and drop the claim
from the other two sites outright. It is worth recording because it is the one specimen on this page
that needs no external referent at all — the artifact is the document, and the audience is holding
it.

## This is a family

The same shape has produced four other defects on this program:

- **A pre-registration** — a commitment written down before the result, so it cannot be rationalised
  afterwards — that fixed the *interpretation* of each branch but not the *disposition*. Branches
  resolving to the same resting state went unspecified because they felt decisionless. Half a
  commitment device.
- **A negative control** — a run that removes the suspected cause to show the effect disappears with
  it — that did not isolate a cause, because a second sufficient cause was present and untested in
  the same harness. **Two harnesses that compose are not two that confirm.**
- **Independence of execution is not independence of method.** Two agents running different
  harnesses can still share one unexamined reasoning step.
- **A protective instruction scoped to a paragraph when the ruling it protected was scoped to a
  clause**, so it shielded text the ruling never examined. The coordinator's own error, recorded as
  such: the pattern does not spare the people naming it.

**Correcting where you looked is not correcting the property.**

## The authority-reach corollary

> **Tier label:** a marker attached to a claim recording how well supported it is — measured,
> provider-documented, reasoned-but-not-measured, and so on.

A tier label placed in one comment is often doing work for text elsewhere, and nothing marks how far
its authority extends. In the example above, two sites sat a few lines from a disclaimer labelling
the property unmeasured. The recommendation was to leave them: sub-facts in the same block,
inheriting the label **by proximity**. Right outcome, by an argument that does not survive an edit:

> **A tier label reaches exactly the claims the disclaimer names as its grounds and its
> consequence. Not proximity. Not a pointer.**

Proximity fails even when it gives today's right answer, because nothing marks a block boundary: a
later edit moving the disclaimer or the sub-facts silently breaks an inheritance that was never
written down — no error, no suspicious diff. And a reader landing on the sub-fact first never saw
the disclaimer at all.

Which two sites those are is not itself settled by proximity: as of ref `f5691c30` the file holds
two candidate pairs — one at lines 80–82, one at lines 125–128 — and each sits a few lines from a
disclaimer inside the same comment block, so distance cannot tell them apart. What separated them
was naming: at `de4d6145` the disclaimer beside the second pair was rewritten to name exactly that
pair as its grounds — *"documented Kubernetes semantics (envFrom resolved at pod start plus
maxUnavailable=0)"*, lines 158–161 at that ref — while the first block's disclaimer, though also
rewritten, named no such grounds. The evidence that picks the candidate is the corollary's own
remedy, applied to one of them and not the other.

**That discriminator has since expired, and the expiry is pinned here rather than hidden.** It
separated the two pairs at **`de4d6145`**. It stopped separating them at the very next commit to
touch the file, **`5c3c0d49`**, which gave the first pair a tier of its own inside the `locals`
comment — *"documented Kubernetes semantics, not measured in our cluster"*, lines 83–84 at that ref.
From `5c3c0d49` onward both pairs are tiered, so a reader who follows this page's own rule and
re-runs the enumeration at the far end finds that naming no longer picks a winner either. (Both
quotations wrap across comment lines in the source, so search for a fragment, not the whole string.)

Naming both refs is the whole of the point. *"It no longer separates them"* without the ref at which
it did would only swap an uncheckable narrative for an uncheckable epitaph. And a page about residue
that has itself gone stale is **an instance of its subject, not a counterexample to it** —
concealing that would be the exact defect the page is named for.

### The mirror-image pair

Separately each looks like a one-off; they are two faces of one defect.

- **The trailing comment pointed at a block** and would have inherited a *contradiction*. Explicit
  pointer, correct target, stale pointing text.
- **The two mechanism lines sat near a block** and would have inherited a *disclaimer*. Implicit
  nearness, right target, unwritten.

Both are invisible to a reader arriving at the wrong place first, and the remedy is identical: **make
the relationship explicit.** Name the grounds and the consequence in the disclaimer; then every other
site either *is* a named ground (leave it) or carries its own tier (relabel it).

> **Proximity and pointer are both substitutes for naming, and both fail silently.**

### The anti-dilution test

Why not tier everything and be safe? Because **a tier label's job is to flag claims that could be
mistaken for measured**, and applied to every universal-mechanism line it distinguishes nothing; the
documented mechanisms a corrected comment cites are the tier's *basis*, not its targets. **The
test:** does the claim describe how the system behaves — universal, documented, statable as fact —
or what *our* deployment will do? The first is basis; the second is consequence, so tier it.

### Follow every cross-reference

The trailing comment was the stale-pointing-text case: had the block been corrected and the comment
left standing, its own words would have gone stale while the block it pointed at moved on. The
mirror image is the case where the pointer is sound and the *target* has moved: the pointing text
still names a destination that no longer says what it said. Same defect, opposite end — and
invisible from the pointing side, because nothing in the pointer changes when the target does.
Hence:

> **When new text re-tiers a claim, follow every cross-reference the new text makes and re-run the
> enumeration at the far end, across file and repository boundaries.**

A pointer is part of the text's own extent: the sentence it lands on is asserted by the pointing
text as surely as the sentence beside it.

This section exhibits no *live* specimen of the moved-target case — a claim about that case
specifically, not about this document's ability to exhibit specimens at all. (The specimen under
*The document as its own specimen* above is a specimen of the main principle, not of this case.)
Showing one means producing what the far end used to say beside what it says now, and there are two
ways to do that. Where the older text is durably recorded, **repair the pointer and pin the ref at
which the old target stood**. Where it is not recorded, the only way to cite the case is to name a
destination the reader cannot reach, which is the inversion the rule above exists to prevent.

So the branch the corollary forces is not *repair rather than exhibit*; it is **repair and pin**.
The exhibit is the ref, not the live defect. Keeping a defect in place so that it can be pointed at
is what the rule forbids, because the defect stays hazardous for exactly as long as it is being
admired. Keeping a **ref** that records the defect costs nothing, harms no reader, and still works
after the repair.

Repair-and-pin is not a universal, though, and the bound has to travel with it. Where no ref exists
at which the old text stood, the repair is **asserted and not checkable**, and you say so plainly
rather than let the form of the sentence imply a ref there is none of. **Reproduction is not
pinning:** quoting the old wording inline keeps the argument readable, but it leaves the before
state resting on the author's word, which is the thing a ref is for.

**Exhibit the record, not the wound.**

## Reasons, not answers

The right answer on those two mechanism lines came from a justification that does not survive an
edit, and that matters on its own:

> **A correct result with a stated justification that did not generate it is a defect in its own
> right** — because the next round inherits the written reason, not the outcome.

The general remedy: **establish whether an instrument is in the chain at all before reasoning about
which way it fails.** Provenance is checkable; direction arguments are delicate. This is also why
the rationale above is not decoration: a maxim stripped of its rationale and a correct answer
stripped of its real reason fail the same way, one round later.

## The operational form

A principle with no procedure gets agreed with and not followed. Before writing any correction:

1. **State the property in one sentence, independent of any wording.** If you cannot, you are still
   correcting a sentence, not a property.
2. **Enumerate with multiple independent phrasings**, not one seed string. Treat any list you were
   handed as a **floor**, and include the terse forms deliberately: they are the cheapest to miss
   and the least reachable from the wording you have already fixed.
3. **Produce a hit list with a disposition against every hit:** corrected / already-correct /
   examined-and-deliberately-left-with-reason.
4. **Record the examined-and-left ones.** An examined-and-left site not recorded as examined is
   indistinguishable from a missed one, and the next round pays again to rediscover it.
5. **Re-derive the acceptance check from the property**, never from the example you were shown.

## Where this came from

**Provenance, not evidence — you cannot check this paragraph's account of the principle's origin.**
Nor can you check *This is a family* or *Reasons, not answers*: those rest on review-conversation
provenance and on pattern instances from the same programme, with no citable refs, and they are
offered as illustration, not as support.
The same goes for the three-site before state described under *The document as its own specimen*,
which is reproduced there but pinned at no ref. This page's checkable spine is its pinned refs, its
quoted Terraform and its greps: a claim is on the spine when you can name the ref, the quotation or
the command that settles it and then go and settle it. Anything here that no ref, quotation or
command settles is outside the spine — a test you can apply to any sentence on the page without
consulting a list, by asking what you would run or look up to check it. The passages named just
above are outside it and are offered as illustration only. Others are outside it **and
load-bearing**. Those include the acceptance check under *The second-order finding* — the greps are
pinned and checkable, but the check they reconstruct is on no record; the recommendation under *The
authority-reach corollary* to leave the two mechanism lines as sub-facts inheriting by proximity,
which is on no record either, though the sites and the disclaimers it concerns are pinned; and the
causal connector under *Why site 268 is the proof* — that the sweep's parent is the correction that
*prompted* the sweep — which is read off stack adjacency and which the record neither confirms nor
denies. Those are examples under the rule, not a tally: a further load-bearing claim later found
outside the spine leaves this paragraph **incomplete rather than false**, and the page's own
principle says to add it here rather than repair only the instance you were shown. The
enumerate-before-correcting behaviour was observed on an internal security-hardening workstream,
where a request to correct a single site came back instead as an enumeration of every site that
asserted the property, with a disposition recorded against each, and the rule was extracted from
that practice rather than the practice derived from the rule. Nothing above depends on it: the
argument stands on the pinned refs, the quoted Terraform and the greps — on the spine, except where
an off-spine claim is flagged as load-bearing in the way just described — and this note is here only
to record that the principle was not invented at a desk.

## How this connects

The habit is the one behind the [verification principle](./verification-principle.md): *don't trust
the description — check the actual state.* There it is a dependency resolver; here it is the full
set of places a claim is made. [Review discipline](./review-discipline.md) supplies the enforcement
point: the independent reviewer should be asking "where else is this asserted?", because the author,
closest to the one sentence they were shown, is exactly who will not.
