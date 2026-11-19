# Builtin Worker Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task. Steps use checkbox tracking. Coordinator assigns ownership and independent review; this planning worker spawns nobody.

**Goal:** Complete one observed builtin worker/reviewer seeded-bug task through the mandatory delivery gate.

**Architecture:** Separate strict 2.0 builtin records and request-bound codec reuse common semantics/journal/P12 evidence. Managed wires/hashes stay unchanged; root serializes integration.

**Tech Stack:** Python 3.11+, standard library/unittest, actual builtin host tools, isolated temporary state/artifacts.

**Spec:** sibling 2026-11-03-builtin-worker-execution-design.md; canonical target docs/superpowers/specs/2026-11-03-builtin-worker-execution-design.md. Authority: approved Option B in docs/tasks/tom-orchestration/runtime-decision.md.

Canonical plan target: docs/superpowers/plans/2026-11-03-builtin-worker-execution-plan.md. Staging /private/tmp/tom-builtin-plan; implementation snapshot /private/tmp/smart-assistant-builtin-mode is not a Git worktree. Plan-only stage changes no source, canonical/.git/native/catalog or task state.

## Global Constraints

- Old managed strict types/wires/hashes unchanged; unknown/mixed modes fail closed.
- Configured capability requested but unavailable remains blocked; builtin needs explicit authorized decision and immutable marker.
- Bind actual actor/context/run, submitted prompt/instructions, exact candidate/context/design/criteria, preflight and handoff. Hashes prove integrity, not semantics or authenticity.
- Preserve reproduction before repair, independent actors, every required case/proof, shared two-specialist/three-correction bounds, immutable history and callback-final gate.
- No new permissions, scheduler, model settings, accounts, external effects, activation or Git writes; no deployed ACTIVE manage/delegate edits.

## Review Focus

1. Any reserved mode prefix must trigger strict mandatory denial without policy/sidecar (Task 2).
2. Another token/label for one actor/context is not fresh execution or independence (Tasks 1–3).
3. Prompt/authority/context drift invalidates evidence despite unchanged product bytes (Tasks 1–2).
4. Callback mutation must fail final same-lock revalidation; retain F01 (Task 2).
5. Nonzero exit alone is not the target bug; root checkpoint and semantic reviewer assess actual scenario (Task 3).

## Ownership and interfaces

Core worker: new smart_assistant/{builtin_records,delivery_codec,delivery_semantics}.py, tests/{test_builtin_records,test_delivery_codec}.py and core docs/evidence/builtin-execution/. Root: modifications to delivery_records/store/evidence/gate/state/cli, AGENTS.md, bootstrap request-coordination SKILL.md/references, existing related tests and new tests/test_builtin_delivery.py. No contracts.py/native/catalog/deployed ACTIVE edits. No concurrent shared edits.

Implement exact records and APIs in spec. Core receipt is local BuiltinReceipt, not P12 import. Base decision digest omits only reserved mode marker; full policy/registration/authority request digest retains it. Core does not import codec/P12/persistence. Shared semantic helpers take normalized field views with fixed internal mode semantics, never fake old envelopes.

### Task 1: Builtin core and compatible codec

**Owner:** core worker. **Consumes:** spec and genuine common v1 records. **Produces:** strict builtin serializers/validators, codec and common semantic APIs specified in spec.

- [ ] Capture managed golden wire/hash fixtures from baseline before refactoring.
- [ ] Write failing tests: builtin_strict_roundtrip, managed_hash_unchanged, unknown_mixed_version, counterfeit_managed_fields, base_request_digest_no_cycle, configured_no_fallback, duplicate_unknown_mode_marker, prompt_authority_context_binding, crossed_handoff_wrong_run, same_run_two_tokens, missing_stale_checkpoint, changed_live_baseline_denies_dispatch, repaired_candidate_completes_with_archived_baseline, DAG_overlap_invalidation, ambiguous_capacity, payload_limits_cannot_exceed_shared_plan_policy, nested_assignments_do_not_reset_limits, correction_history. Assert denial and preservation, not merely generic exceptions. Reuse existing policy hard maxima validation rather than adding a duplicate policy rule.
- [ ] Run python3 -m unittest tests.test_builtin_records tests.test_delivery_codec -v; record intended red.
- [ ] Implement new records/codec and new shared semantic helpers WITHOUT editing root-owned delivery_records.py. Task 1 managed codec branch calls existing unchanged managed validator. Root Task 2 later rewires existing wrappers serially with golden fixture parity. Keep old parsers closed, no fake capability metadata; checkpoint records trusted root assessment, not a tool sandbox.
- [ ] Run focused and existing managed record suites; freeze hashes, obtain independent review, record dispositions and red/green fixes; re-review changed bytes.

### Task 2: Serialized store, evidence, completion and bootstrap integration

**Owner:** root. **Consumes:** accepted Task 1 APIs. **Produces:** real builtin registration/dispatch/handoff/evidence/completion through existing persistence and CLI.

- [ ] Write failing integration tests for builtin registration/update/read/history/recovery, request-under-lock mode selection, strict cross-mode rejection, malformed reserved-prefix without policy/sidecar, no-sidecar writes before validation, same-actor/missing-case/reproduction/proof denial, stale prompt/context/authority/candidate, callback mutation/F01, all supported completion paths and unchanged managed/legacy behavior.
- [ ] Run python3 -m unittest tests.test_builtin_delivery tests.test_delivery_store tests.test_delivery_gate tests.test_delivery_evidence -v; preserve red before edits.
- [ ] Root alone rewires existing managed wrappers to Task 1 shared helpers, proving golden wire/hash and existing managed-test parity. Route store serializer/digest/validator aliases through codec. Session derives mode from actual task under shared lock for registration/history/recovery, never wire alone. Preserve journal schemas, CAS/recovery, borrowed locks and F01 no-sidecar validation before writes.
- [ ] Extend P12 only with exact normalized snapshot-type dispatch and builtin receipt prechecks; unchanged EvidenceBundle/common semantic `_check`. Extend mandatory marker detection to ANY reserved execution prefix; preserve both pre/post-callback checks, immutable cycles and required children/runs/cases.
- [ ] CLI decode derives mode from actual task; managed commands remain valid. Update AGENTS.md/bootstrap to allow explicit builtin responsibility while retaining configured impersonation/covert-fallback prohibition. Do not mutate deployed ACTIVE skills/catalog.
- [ ] Independent integration/spec review, findings/dispositions and re-review; run managed golden fixtures, focused suites, full python3 -m unittest discover -s tests -v and whitespace/document checks. Freeze combined candidate.

### Task 3: Actual observed builtin seeded-bug acceptance

**Owner:** root coordinator, actual bounded builtin workers, separate reviewer and separate verifier. **Files:** docs/evidence/builtin-execution/ sanitized summary; private prompts/transcripts/state/artifacts in ignored/private temp directories. **Consumes:** reviewed Task 2 executable path and root docs/tasks/tom-builtin/seeded-delivery-design.md.

- [ ] Seed normalize_spaces with trim-only defect and root's four requirements/eight named cases: repeated-spaces, repeated-tabs, embedded-newline, mixed-whitespace, edge-whitespace, already-normalized, unicode-punctuation, empty-blank. Use isolated state/artifacts, explicit requirement/case/proof matrix and source/test baseline snapshot+archived copies. Save actual mode decision/policy/registration; preserve managed/native/catalog state.
- [ ] Persist reproduction-only assignment/pending intent before real spawn; capture actual call/response/run/prompt and failing command/output. Root assesses target failure and saves checkpoint before repair authority. Do not fabricate missing host identities/receipts.
- [ ] Dispatch repair in fresh actual context/token after live baseline snapshot reread/checkpoint validation; then separate fresh reviewer and independent verifier contexts. Never reuse one actual run across tokens. Sequence within shared max two specialists, with exact ownership/current preflight. Verifier independently runs all eight cases and original scenario; record its actual assignment/run/handoff and test-entry observation, not implementer reruns.
- [ ] Reviewer assesses actual candidate and all before/after/case evidence independently. Resolve findings, re-review changes and freshly run required checks. Preserve all failed cycles/receipts and limits.
- [ ] On isolated copies exercise missing reproduction, changed-live-baseline repair dispatch and same-actor denial; label synthetic corruption checks. Positive repair→completion must accept changed repaired product while validating immutable archived baseline receipts, never compare final bytes to old baseline. Save valid P12 bundle through actual CLI/store; run actual task complete/readback. Missing observed verifier/worker/reviewer proof stays blocked.
- [ ] Independent exact-candidate demo/evidence review; record findings/dispositions. Run fresh full suite and final focused builtin suite after all source/build/regression changes. Report helper/demo proof boundaries; no configured activation/customer runtime claim.

## Plan review checkpoint

Self-review covers approved Option B, old-wire compatibility, marker/hash circularity, import graph, preflight/reproduction/independence, shared bounds, F01 callback/history and genuine observed demo. Design/plan complete only after root independent review and feedback. No source implementation before root release. Canonical integration remains a separately controlled root action; permission timeouts grant no write authority.
