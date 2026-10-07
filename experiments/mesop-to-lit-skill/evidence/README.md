# Evidence index

The proof artifacts behind the `mesop-to-lit` skill. Together they show the skill **assesses**
Mesop apps accurately across a size range and **assists** a real conversion that passes all three
quality gates.

## Conversion outcome

| File | What it proves |
|---|---|
| `RESULTS.md` | The end-to-end conversion of the Promptlandia checklist slice: exact build/test commands and outcomes (**backend 15 pytest, frontend 16 vitest, clean `vite build`, no mesop imports**); the **G1–G7** gaps the conversion surfaced and how each was fixed in both the slice and the skill references; the §5 quality-gate fixes (path-traversal, error-envelope, `str(exc)` leak, sanitization test); and the documented deviations/limitations. |

## ASSESS validation (the analyzer at range)

| File | What it proves |
|---|---|
| `promptlandia-assessment.md` | The analyzer's assessment of the Promptlandia app — the target that was then converted. |
| `babel-assessment.md` | ASSESS on a small second app (`babel`) — the analyzer generalizes beyond Promptlandia. |
| `gmcs-assessment.md` | ASSESS on GMCS (~28k LOC, 42 routes, `fastapi-hybrid`) — the analyzer scales and stays robust (only 2 parse errors, no crash). |
| `assess-validation-promptlandia.md` | Scored validation of the Promptlandia assessment against ground truth (9/9 + 20/20). |
| `assess-validation-harder.md` | The harder re-validation of ASSESS accuracy on the larger/edge targets. |

## Quality-gate reviews (all APPROVE)

The skill + conversion went through code, security, and test review; code and security had a second
round after fixes. All returned **APPROVE**.

| File | What it proves |
|---|---|
| `code-review.md` | Round 1 code review (returned REQUEST CHANGES with the MUST-FIX/LOW items). |
| `security-review.md` | Round 1 security review (path-traversal CRITICAL, `str(exc)` leak, CSP follow-ups). |
| `test-review.md` | Test review (coverage gaps + the markdown-sanitization regression requirement). |
| `code-review-2.md` | Round 2 code review — **APPROVE** after the MUST-FIX items were addressed. |
| `security-review-2.md` | Round 2 security review — **APPROVE** after the security fixes + hardening. |

For the full narrative tying these together, start with `RESULTS.md`, then the two round-2 reviews.
