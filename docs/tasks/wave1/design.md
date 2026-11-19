# Wave 1 integration design

Authorized scope: P01 task storage/scoped context, P02 capability catalog/deployment transactions, and P03 preflight/completion checks. P00 contracts are unchanged. Worktrees begin at b98c660f8e36d5120cc1210650a949f251624a86. No P04–P09 product implementation, real native activation or account integration is included.

## Acceptance

| Criterion | Outcome | Verification |
| --- | --- | --- |
| wave1-packages | Each package meets its planned public interfaces and its own design criteria. | Independent candidate review, feedback dispositions, targeted and full package tests. |
| wave1-composition | TaskStore with completion_gate permits a fully evidenced task and denies missing/stale/failing evidence without changing the saved task. | Cross-package functional tests using temporary roots. |
| wave1-catalog | Canonical catalog is a valid empty revision-1 catalog; no capability is claimed installed or active. | Catalog load/validate/eligibility on the integrated project. |
| wave1-isolation | Three package branches and disjoint owned files; tests never touch live state. | Commit/path audit and test evidence review. |
| wave1-integration | Accepted commits combine without changing frozen contracts or breaking earlier tests. | Entire discovered suite, independent integrated review, final fingerprints and clean local Git. |
| wave1-cycle | All findings resolved; changed candidates independently re-reviewed and freshly tested; source and evidence agree. | Package and integration evidence records. |

## Frozen coordination decisions

P01 owns store transition policy, expected revisions and atomic durable writes. P03 accepts a proposed complete TaskRecord from the injected callback and returns GateResult; evidence validation does not replace legal transition checks. Failed-task resume requires explicit resume_failed, not ordinary update. GateResult returned by a callback must itself be structurally valid.

Context source paths are <state-root>/context/projects/<project_id>.json and <state-root>/context/projects/<project_id>/roles/<role_id>.json. Both are exact ContextBundle records with matching project_id. Project facts use project:<id>; role facts use role:<id> within the selected project's path. Role preferences shallowly overlay project preferences. Sources/timestamps remain unchanged; missing files are optional and empty, malformed/scoped-mismatched/symlink files reject.

P02 validation_refs use local JSON evidence with schema_version=1, kind validation or evaluation, capability_id, version, manifest_sha256, passed boolean, and nonempty local evidence_refs. Both validation and evaluation must pass and bind the deployed manifest. Native probe refs name local NativeProbeReceipt records. Full manifests include every supporting resource and normalize one-file agent manifests to the deployed basename. Journals/locks/probe observations live under ignored .smart-assistant. Stable catalog locks, CAS revisions and exact original/new catalog bytes determine crash recovery; catalog reads remain non-mutating. Finalized rollback requires staging/probing the old version through the lifecycle. Precise journal formats and recovery algorithms live in P02's design.

P03 evaluates the latest cycle only with strictly increasing cycle numbers; no fallback to old passing evidence. Current artifact bytes and current criteria/design bytes determine snapshot validity. Design/check/disposition evidence uses local relative regular files under the artifact root. Receipt paths do not become candidate artifacts. Exact declared authorization, host allowed decision, and observed tool availability are all required in preflight. Distinct reviewer/implementer references are a consistency check, not cryptographic proof.

## Root ownership and delivery

Integrator owns capabilities/catalog.json, tests/test_wave1_integration.py, root guidance/README/plan progress, this integration design, and docs/evidence/wave1. Workers cannot write those files. Package worker commits are reviewed in their original worktrees and integrated serially. Root runs combined tests and requests independent integration review of exact product hashes. All corrections return to their owner, receive review and fresh testing before delivery. Test state, staging and synthetic receipts are always temporary.

Native managed worktree creation was unavailable for this chat, so the user-requested isolation uses local ignored .worktrees/p01, p02 and p03. All three baseline suites passed 24 tests. Implementation code is standard-library Python >=3.11; runtime verification here uses macOS/Python 3.14.7 and does not claim Linux or Python 3.11 runtime execution.
