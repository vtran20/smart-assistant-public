# P11 Delivery Records Implementation Plan

> **For agentic workers:** REQUIRED: use superpowers:executing-plans when implementation is authorized. No subagents in this worker; coordinator schedules independent review. Steps use checkbox syntax. No commit, push, merge or activation is authorized.

**Goal:** Add strictly validated, request-bound delivery records and CAS persistence for P12/P16 without changing frozen v1 records or task behavior.

**Architecture:** Independently versioned records wrap unchanged v1 assignments and handoffs. Immutable snapshot revisions and a checked atomic head share TaskStore's per-task lock; explicit recovery preserves staged failures. Evidence semantics and task-store integration remain P12/P16 work.

**Tech Stack:** Python 3.11+, standard-library dataclasses/json/hashlib/pathlib/os/fcntl, unittest and multiprocessing; existing contracts/state filesystem helpers.

---

Date: 2026-11-03. Status: ROUND 1 IMPLEMENTATION CANDIDATE; independent source re-review pending.
Coordinator reports user approved architecture on 2026-11-03. The coordinator independently approved this plan and released implementation on
2026-11-03. First source review required corrections R1–R7; disposition evidence
is under docs/evidence/p11/. Corrected-candidate source re-review remains pending. Architecture source header still says proposed;
this provenance note records the coordinator's current authorization without editing
another owner's specification. Baseline inspected: `081db870ccdf8c4316bbc1309e5d72806bab3094`.

## Chunk 1: contract agreement and validation

### Task 1: Freeze executable package scope

**Owned files:**

- Create `docs/superpowers/plans/2026-11-03-p11-delivery-records.md` (this plan).
- Create `docs/tasks/p11/interfaces.md` (precise candidate API/fields/protocol).
- Future create `smart_assistant/delivery_records.py`, `smart_assistant/delivery_store.py`.
- Future create `tests/test_delivery_records.py`, `tests/test_delivery_store.py`.
- Create progress, review, feedback and validation artifacts only under `docs/evidence/p11/`.

Do not modify contracts.py, state.py, CLI, catalog, active assets, design specification,
P12/P14 implementations, shared task index or another worker's files. Assigned commands
root is `/path/to/local/resource`; integration
root remains `/path/to/smart-assistant`. Use isolated TemporaryDirectory
state roots; never open live `.smart-assistant/` operational state. No spawned agents.

- [ ] Coordinator independently reviews [proposed interfaces](../../tasks/p11/interfaces.md) and this plan, specifically acceptance-state trust boundary, registration sequencing, parent/dependency graph differences, revision semantics and shared lock composition.
- [ ] Record exact review findings/dispositions in docs/evidence/p11/plan-review.md; freeze agreed API before P12/P16 depend on it. Re-review changed plan bytes.
- [ ] Coordinator explicitly releases this worker's implementation checkpoint after independent review. Review pending does not count as passed.
- [ ] Run baseline `python3 -m unittest discover -s tests -q` and capture actual count/exit in docs/evidence/p11/progress.md; baseline failures block unrelated success claims.

### Task 2: Strict additive records and policy binding

**Files:** create smart_assistant/delivery_records.py and tests/test_delivery_records.py.

Follow interfaces.md exactly: support records and core records, separate decoding
registry, canonical digest and reserved source reference; reuse v1 wire conversion
for nested payloads. Do not mutate the v1 registry or introduce dependencies.

- [ ] Write `test_policy_reference_binds_full_request_without_digest_cycle`, `test_round_trip_all_delivery_types` and `test_nested_v1_payload_remains_wire_compatible` first. Fixtures use in-test synthetic v1 examples, unique assignment IDs and explicit observed-run evidence.
- [ ] Run `python3 -m unittest tests.test_delivery_records -v`; confirm RED is missing implementation, not malformed fixture/import environment.
- [ ] Implement exact field types, enum values, digest/timestamp/ID/revision validation, delivery_from_dict/to_dict/digest, request_digest and policy_source_ref. Normalize via fresh validated copies at public boundaries.
- [ ] Add table-driven malformed cases: unknown/missing fields/version/enum, bool revision, NaN/infinity, duplicate JSON keys at store ingress, invalid UTC/date/Unicode, non-JSON values, list duplicates, cyclic dataclass/container graphs, wrong policy/source ref, duplicate/missing reserved reference and request change.
- [ ] Run focused suite; record actual RED/GREEN and candidate file SHA256 values. Policy source digest is a binding supplied by trusted intake, not authenticity proof.

### Task 3: Plan/assignment graph, ownership, run and submission validation

**Files:** same records module/test file.

- [ ] Write RED cases `test_dependency_cycle_and_missing_predecessor_denied`, `test_exact_ownership_aliases_conflict_across_worktrees`, `test_same_role_cross_submission_rejected_before_v1`.
- [ ] Implement validate_delivery with exact task/policy/request/plan/assignment ID sets, independent parent/DAG checks and current accepted dependency pins; iterative traversal avoids recursion-limit surprises.
- [ ] Implement exact ownership checks and state transition table from interfaces.md. Test blank/absolute/traversal/glob/backslash paths, Unicode/case aliases, file-directory prefix conflict, same workspace across worktrees and legal separate workspace identities. Empty supervisor ownership is allowed.
- [ ] Implement append-only history and monotonic revision checks; test ID reuse/deletion, mutable past decisions/submissions, changed request/root owner/policy, changed dispatched scope, invalid accepted outputs and same-state acceptance tampering.
- [ ] Implement dispatch_status and DispatchIntent/ObservedRun consistency; test pending/ambiguous capacity accounting, unconfirmed terminal runs, duplicate tokens/run ownership, old envelope intent pin versus latest observed envelope revision and locally invented token rejected as native identity.
- [ ] Implement validate_submission outer checks before v1 validate_handoff. Spy on v1 validator to assert it is not called for wrong assignment/envelope/token/run/digest. Then delegate unchanged payload validation against anchored current files.
- [ ] Test exact same-role/same-v1-revision cross-submit, old envelope, different host/run/actor, missing observed run, replay submission ID and envelope/run/payload replay, wrong artifact root and symlinked root/components/nonregular artifacts. Passing ready_for_review never automatically accepts.
- [ ] Implement history-aware transitive invalidation checks. Test accepted predecessor supersession, multi-hop/diamond descendants, unrelated sibling preservation, broad design/acceptance/context redesign invalidation and stale pins preventing redispatch.
- [ ] Run `python3 -m unittest tests.test_delivery_records tests.test_handoff -q`. Structural refs remain insufficient for P12 semantic acceptance; record that limit.

## Chunk 2: persistence and interruption recovery

### Task 4: Shared-lock CAS and immutable history

**Files:** create smart_assistant/delivery_store.py and tests/test_delivery_store.py.

- [ ] Write RED tests for missing registration with reserved request, successful register/read/update, task revision conflict, delivery CAS conflict and no mutation of original v1 task JSON.
- [ ] Implement anchored directory/session management using named state.py helpers without changing state.py. LockedDelivery objects expire after context exit; validate IDs before filesystem access and reject reentry/nested locking misuse.
- [ ] Implement strict JSON ingress (duplicate-key detection and parse_constant rejection), immutable snapshot/operation files, authoritative head and initial registration. All regular files must satisfy type/link-count and attachment checks; safe filenames derive from validated fields.
- [ ] Implement register/update protocol exactly as interfaces.md: common per-task lock, read current task from disk, validate task/request/policy and both CAS dimensions, stage immutable bytes, fsync and publish head atomically. Return freshly decoded stored copies; deep-copy callback bypasses are unnecessary because this package supplies no acceptance callback.
- [ ] Add history integrity tests for missing/damaged registration/head/revision/operation, forged filename/content mismatch, altered older revision and broken previous digest. Never select mtime/latest directory entry or silently fall back to legacy.
- [ ] Test terminal create/update denial, failed-task resume boundary, reserved-source migration denial, registration idempotency/conflict, invalid expected revisions and preserved orphan bytes.
- [ ] Run `python3 -m unittest tests.test_delivery_store -v` and record actual checks. Existing TaskStore behavior remains unmodified; P16 must adapt serialization/completion later.

### Task 5: Race, filesystem and crash recovery matrix

**Files:** store module/tests; docs/evidence/p11/verification.md.

- [ ] Add multiprocessing spawn test: two writers start from the same task/delivery revisions, synchronize with Event/Queue, exactly one revision wins and one raises RevisionConflict; finite timeouts and checked child exit codes prevent hangs.
- [ ] Add TaskStore-versus-delivery race test using shared lock: task revision advances while delivery writer waits; delivery fails task CAS and preserves its prior head. Test LockedDelivery read/update without nested acquisition and inaccessible session after exit.
- [ ] Add hostile-path tests: root/intermediate/final symlink, malformed generated IDs, FIFO/device/directory leaf, hardlinks, replaced lock, detached/replaced delivery and revisions directories, temporary-name collision. Use bounded child probes for FIFO/hang cases and mocks for replacement windows.
- [ ] Inject crash/failure at operation creation/fsync, pending publication/fsync, initial registration write, snapshot creation/fsync, final revalidation, head replacement, directory fsync and pending cleanup. Observe actual on-disk pre/post-head state rather than assuming exceptions imply rollback.
- [ ] Implement explicit recover(task_id, operation_id, finish/reject), immutable resolutions and idempotence. Test complete/incomplete staging, absent pointer after operation creation, committed-head cleanup, stale task revision, unrelated newer head, malformed journal, reject after commit denial, conflicting resolution actions, unknown operation and repeated exact recovery. Recover never creates missing evidence or a newer accepted revision.
- [ ] Verify rejected initial registration remains blocked and can be explicitly retried with new operation while retaining staged files; rejected update preserves prior readable authoritative head. No destructive orphan cleanup.
- [ ] Run `python3 -m unittest tests.test_delivery_records tests.test_delivery_store tests.test_state tests.test_handoff -q`.

## Chunk 3: independent review, feedback and final evidence

### Task 6: Exact-candidate review and final checks

**Files:** owned implementation/tests/documents and docs/evidence/p11/ only.

- [ ] Freeze SHA256 of every owned candidate file and record baseline Git HEAD. Coordinator arranges independent review of exact bytes; worker never self-approves or spawns extra reviewers.
- [ ] Reviewer checks design traceability, schema consistency, CAS/lock ordering, trust and acceptance boundaries, graph invalidation, symlink/TOCTOU risks, durable-write crash windows and public P12/P16 compatibility.
- [ ] Record each finding, disposition and changed file under docs/evidence/p11/; resolve findings, re-review changed candidate and repeat focused tests. If implementation changes interfaces, reopen design review and notify consumers before freezing them.
- [ ] Run final `python3 -m unittest tests.test_delivery_records tests.test_delivery_store -v`, then `python3 -m unittest discover -s tests -q`; capture exact counts/exit, Python/OS and candidate hashes. Run `git diff --check` and owned-document relative-link checks. No hardcoded passing counts or runtime claims.
- [ ] Return files/candidate hashes, review findings/resolutions, commands/results, consumer obligations and remaining limits to coordinator. Do not commit/push/merge. Coordinator alone integrates and reruns combined acceptance.

## Acceptance and bounded proof

| Criterion | Required evidence |
| --- | --- |
| P11-C01: additive strict record encoding | Roundtrip plus malformed/unknown fields/version tests; unchanged v1 payload fixtures |
| P11-C02: immutable registration/request/policy | Reserved ref/full-request digest tests, missing component denial and policy change denial |
| P11-C03: valid graph and exact ownership | Cycle/missing/stale pins/aliases/parent/overlap/transitive invalidation tests |
| P11-C04: explicit dispatch/run/handoff identity | Cross-submit before v1, run/token mismatch, replay and ambiguous-capacity cases |
| P11-C05: safe CAS persistence/history | Multiprocess conflict, task CAS race, immutable prefix and file/chain tamper cases |
| P11-C06: fail-closed crash recovery | Every protocol boundary interrupted; deterministic same-operation finish/reject with preserved staging |
| P11-C07: review cycle and compatibility | Exact-candidate independent review, dispositions, fresh focused/full suite, agreed P12/P16 APIs |

Architecture A03/A04/A12/A18/A19/A20 receive bounded helper coverage. A05 whole-tree
capacity, A11 all completion paths, A16 actual delivery and A17 migration execution
remain integration/host acceptance. Authentic reviewer independence/evidence,
reproduction, required verification levels, process termination and native activation
are not proved by P11's structural validation or synthetic tests. No end-to-end or
runtime acceptance claim is authorized here. Any unsupported fsync/lock behavior or
unresolved review finding remains an explicit blocker, never an excluded test.
