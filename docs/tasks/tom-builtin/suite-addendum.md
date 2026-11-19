# Seeded delivery proof and execution addendum

Date: 2026-11-03. Status: candidate for independent exact-text/harness review BEFORE baseline capture. Scope: the disposable builtin normalizer exercise, under the user's approved Option B; no new permissions, native activation, accounts, external effects or Git writes. This clarifies the seeded-delivery-design.md and the independent demo-proof-granularity-review.md; it changes no P12 schema or gate.

## Claims and required cases

Use exactly one P12 VerificationCase, normalize-spaces-full-suite, scenario frozen-normalizer-suite, requiring unit proof for all four requirements. Its expected outcome is: execute exactly the eight required named unit cases and every declared input assertion, with zero failures, errors, skips, expected failures or unexpected successes, and exit zero. This is one composite local suite scenario, not eight independently enforced P12 cases. Preserve every detailed unit result in directly hash-bound, inspected capture receipts. P12 validates the declared suite/receipt/review bindings; the frozen runner and actual independent semantic review enforce detailed membership and completeness. Do not claim P12 itself parses matrix rows.

Wire requirement IDs are r01–r04, displayed R01–R04. Freeze cases.json with eight unique required rows, each containing case_id, requirement_ids, inputs (exact input and expected strings) and proof_level=unit:

| Case | Requirements | Exact inputs and expected values | Predicted baseline only |
| --- | --- | --- | --- |
| repeated-spaces | r01 | `alpha  beta` -> `alpha beta` | fail |
| repeated-tabs | r01 | `alpha\t\tbeta` -> `alpha beta` | fail |
| embedded-newline | r01 | `alpha\nbeta` -> `alpha beta` | fail |
| mixed-whitespace | r01,r02 | ` \talpha \n\t beta \n` -> `alpha beta` | fail |
| edge-whitespace | r02 | ` \talpha beta \n` -> `alpha beta` | pass |
| already-normalized | r03 | `alpha beta` -> unchanged | pass |
| unicode-punctuation | r03 | `Café ☕ — done!` -> unchanged | pass |
| empty-blank | r04 | empty string and ` \t\n ` -> empty string for each | pass |

Backslash escapes in the table denote real whitespace characters in JSON. There are eight named cases and nine input assertions. These baseline predictions are not observations. The deliberately defective product only returns text.strip(). Do not change the seed, inputs, expectation, classification or denominator to obtain passing evidence. Unexpected actual reproduction returns to diagnosis.

## Frozen suite and completeness contract

The template consists of normalize.py (deliberately defective), cases.json, test_normalize.py and run_suite.py plus a focused completeness checker if useful. Repair ownership excludes tests, manifest and runner. Freeze/hash/archive all assets before reproduction; final candidate includes product and verification assets so changing the test context invalidates candidate/review as well as context.

Use standard unittest, with eight fixed named methods and per-input subtests. Record actual function return values before asserting equality. All declared inputs execute even when another subtest fails. Runner compares exact discovered and executed case ID sets, uniqueness, exact per-case input indexes/content/expected values, required requirement membership and actual result counters. Counting eight alone is insufficient. Missing, extra, duplicated, skipped, blocked or unexecuted required cases/inputs, import/collection errors and expected-failure decorators cannot produce eligible success.

Exit 0 means complete execution and all required assertions passed. Exit 1 means all declared cases/inputs executed and actual assertion mismatches reproduced behavior. Exit 2 identifies harness/collection/completeness/execution errors; it cannot establish the target defect. Raw unittest output and structured observed/expected per-input results are embedded in each capture, with actual exit, command, timestamps, interpreter/platform, working directory, source/test/manifest digests and actual observed run provenance. The completeness checker independently rejects an omitted matrix row even if a synthetic caller recomputes its hash.

The same frozen suite, manifest and relative command `python3 run_suite.py --run-info go.json` run in baseline, repaired and independent QA workspaces. Root control packets select unique owned output paths such as captures/reproduce.json, captures/repair.json and captures/qa.json; output destinations are metadata and do not alter the pure-function test inputs. This avoids logical ownership overlap across the shared project even though worker roots differ. Actual paths differ and are recorded. The reviewed equivalence fingerprint covers the same pure-function input manifest, interpreter/platform and frozen verification assets; it does not pretend paths or all hidden environment state are identical. Preserve the actual four passing baseline regressions as passes. Root assessment verifies complete execution, target assertion failures and baseline bytes before authorizing repair.

## Actual contexts, startup and review order

Use actual separate builtin contexts for reproduce, repair, code review, QA and final evidence review. The last context independently reviews the exact final candidate plus QA evidence, satisfying P12's review-after-selected-captures chronology. No source changes follow that review. A final root unit rerun on unchanged bytes may supplement the already reviewed QA proof; do not pretend the reviewer saw a later capture. Each context is one saved assignment/token and has a genuine call/response observation; role labels do not load TOMLs. Share at most two executing specialists and three correction cycles. Initial bounded allocation is five stage contexts; any correction needs a recorded cycle and bounded revised allocation, never silent budget extension.

Before each actual spawn, persist exact prompt/instructions, authority/preflight and pending dispatch intent. The child waits for its root-created go.json. Root saves the actual returned task_name, actual observation time and HostBinding through real store APIs before releasing go.json containing task_id, assignment_id, dispatch_token, safe relative capture_path and the observed run. This avoids a child capture predating the parent's actual observation. Hidden host instructions and unavailable per-turn identities remain unknown; actual run_ref denotes the returned context reference. No context is reused through a new token.

Only the root writes state, lifecycle metadata and startup signals. Workers write only their declared outputs; reproduce owns evidence, repair owns normalize.py and evidence, reviewers own review artifacts, QA owns its capture/report. Read-only copies of frozen inputs are verified against their expected hashes. Root records actual handoff assessments, integrates only exact reviewed bytes and retains all raw calls, observations, failures and source/capture hashes in ignored local evidence. An accepted child handoff is not final task acceptance.

Final semantic reviewer inspects all eight detailed case rows/nine inputs, actual baseline symptom, unchanged tests/manifest, repaired and separately observed QA outcomes, full requirement mapping, actual contexts, raw output and exact scope digest. It explicitly distinguishes one P12 suite case from eight required unit cases. Final ReviewReceipt and SemanticReview use the actual same review-completion instant. No fictitious observation, host identity, screenshot or passing check is allowed.

## Required negatives and acceptance

Before real reproduction, independently review this addendum, frozen template/runner and checker tests. Test synthetic omission of a required test, duplicate/skip/error/expected-failure cases and an omitted detailed matrix row with a recomputed hash: completeness must deny. These are local runner/evidence checks, not invented P12 row-level enforcement.

After actual normal execution, demonstrate existing mandatory gate denial on isolated state copies for missing reproduction, missing declared suite case, same-context review and stale capture/metadata. Preserve exact commands, exits, reasons and original state. A consistently forged semantic approval is outside hash integrity; independent actual review remains required.

Save current P12 evidence through the actual store/CLI, invoke actual task completion and read back the result only after every required check passes. Independently review exact demo evidence and final candidate, resolve findings and run fresh final framework checks. Report actual baseline, repair and QA counts, all four requirements, detailed completeness results, actual contexts, one P12 suite scenario and final gate outcome. Source/unit proof does not establish UI, Xstore/POS/device/business acceptance, configured-role activation or unattended operation. Canonical integration still needs the renamed folder's workspace access.
