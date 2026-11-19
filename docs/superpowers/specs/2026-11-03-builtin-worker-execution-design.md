# Explicit builtin-worker execution contract

Date: 2026-11-03. Status: design candidate for independent review. Proposed canonical destination: `docs/superpowers/specs/2026-11-03-builtin-worker-execution-design.md`.

## Outcome and authorization

Implement approved Option B in `docs/tasks/tom-orchestration/runtime-decision.md`. Coordinator supplied the user's 2026-11-03 decision: “Approve separate builtin-worker mode (Recommended)”. This authorizes the separate mode under existing review/test gates, not configured-role activation, new permissions, accounts, model settings, scheduling, external effects or Git writes.

Tom remains root owner. Jerry/implementer/reviewer are builtin responsibility labels, not loaded TOML identities. Explicit configured capability/version requests stay blocked when unavailable. Changing a configured request requires a newly authorized linked immutable request; no covert fallback or history rewrite.

Inspected source: coordinator's `/private/tmp/smart-assistant-builtin-mode` snapshot, including final F01 correction. It is not a Git worktree. Canonical writes and .git/native/catalog changes are excluded from this worker's scope.

## Compatibility and mode routing

Keep contracts.py v1 types/serializers unchanged. Keep old delivery_records.py public 1.0 schemas and closed parsers unchanged. Old TaskAssignment/Handoff/AssignmentEnvelope/DeliverySnapshot never receive builtin fake role IDs, versions, selections or manifests. New builtin records use distinct types with literal schema_version='2.0'; BuiltinSnapshot also has execution_mode='builtin'. Unknown versions/mixed modes fail closed.

Reuse genuine common records with unchanged meanings/wires: DeliveryPolicy, DeliveryRegistration, DeliveryPlan, DependencyPin, ObservedRun, DecisionReceipt and existing P12 EvidenceBundle/entries/cases/reviews. These do not assert configured identity. Hashes establish integrity, not host authenticity or semantic truth.

Builtin tasks carry both existing immutable policy marker and exactly one new marker:

`smart-assistant:execution-mode:builtin:2.0:<sha256-of-BuiltinDecision>`

Managed tasks have no execution marker and remain strict managed 1.0. Reserved unknown/malformed/duplicate markers deny registration/completion. An execution marker without policy marker triggers mandatory denial, never legacy fallback. request.requested_role must be null for builtin; a coordinator decision independently verifies no configured identity was requested in prose. No parser claims to infer all natural-language intent.

Use existing delivery/<task-id>/ lock/journal/revision/recovery storage. A narrow codec selects exact parser from immutable request mode, never parser fallback or newest-file inference. Existing managed public serializers reject builtin records. Historical snapshots must retain one mode; no migration of old bytes.

## Strict builtin record shapes

All new records are frozen, schema_version='2.0', unknown/missing fields rejected. Use current ID/Digest/UTC/path semantics, real JSON lists, strict primitive types, duplicate/cyclic-value rejection and anchored regular receipt reads. Existing shared types below retain their existing schemas.

| Record | Additional fields beyond schema_version |
| --- | --- |
| BuiltinDecision | task_id, base_request_sha256, mode='builtin', authorization_source_ref, decided_by_actor_ref, decided_at, rationale, configured_capability_requested=false |
| BuiltinAuthority | task_id, request_sha256, project_id, artifact_root, required_tools list[str], available_tools list[str], requested_actions list[RequestedAction], authorization list[AuthorizationScope], observed_at, observation HashedReceipt |
| BuiltinPayload | task_id, assignment_revision, responsibility (`implementer`,`reviewer`,`qa`,`technical-lead`), design_ref, criteria list[Criterion], context ContextBundle, owned_paths, limits Limits, prompt HashedReceipt, instructions list[HashedReceipt], authority BuiltinAuthority |
| BuiltinAssignment | assignment_id, revision, task_id, parent_assignment_id nullable, required, payload BuiltinPayload, base_ref, workspace_id, worktree_root, owned_paths, dependencies list[DependencyPin], state (existing assignment states), dispatch_token nullable, observed_run ObservedRun nullable, output_sha256 nullable, handoff_submission_id nullable, review_refs, invalidated_by |
| BuiltinHostBinding | task_id, assignment_id, dispatch_token, dispatched_envelope_sha256, prompt_sha256, instruction_sha256 list[Digest] in submitted order, authority_sha256, run ObservedRun, submitted_call HashedReceipt, observed_response HashedReceipt |
| BuiltinDispatch | dispatch_token, assignment_id, envelope_revision, envelope_sha256, created_at, state (existing intent states), observed_run nullable, reconciliation_ref nullable, host_binding BuiltinHostBinding nullable |
| BuiltinHandoff | task_id, assignment_revision, responsibility, result (`ready_for_review`,`blocked`,`failed`), artifacts list[Artifact], criteria_coverage map[ID,list[RelativePath]], evidence_refs list[RelativePath], blocker nullable, next_step |
| BuiltinSubmission | submission_id, task_id, assignment_id, envelope_revision, envelope_sha256, payload BuiltinHandoff, handoff_sha256, observed_run ObservedRun, submitted_at |
| BuiltinSnapshot | execution_mode='builtin', task_id, revision, previous_sha256 nullable, decision BuiltinDecision, registration DeliveryRegistration, policy DeliveryPolicy, plan DeliveryPlan, assignments list[BuiltinAssignment], dispatches list[BuiltinDispatch], submissions list[BuiltinSubmission], decisions list[DecisionReceipt] |

Decision is immutable and equals mode marker digest. `base_request_digest(request, *, allow_unmarked=False)` hashes canonical v1 request with ONLY its exactly one execution-mode source ref omitted; preserve policy marker and every other field/ref/order. Default requires one valid supported marker. Constructor-only allow_unmarked=True permits zero markers before creating a new request; never permits duplicate/unknown markers. Append decision marker before task creation. Validate marked requests after strict marker cardinality/version checks. Registration/plan/authority retain full P11 request_digest including mode marker. This avoids circular hashes without placeholders or mutation.

Receipt fields in builtin records use new `BuiltinReceipt(path, sha256)` declared locally with exactly those two fields; the table's HashedReceipt spelling denotes that wire shape, not an import from delivery_evidence.py. Existing P12 HashedReceipt class/wire stays untouched. Core imports contracts/state/quality/preflight and shared record primitives, never P12/gate/store. Authority binds actual tool/action/host-decision observations and recomputes existing preflight, not a ready flag. Refresh preflight before dispatch/resume; changed authority requires a new undispatched assignment. Initial mode supports authorized local actions and builtin dispatch/review only.

Prompt/instructions hash exact submitted bytes, not unavailable hidden host/system instructions. Context text is data. Inherit host settings without overrides. HostBinding records actual submitted call parameters/response/run; coordinator observations plus independent review remain trust roots.

## Reproduction checkpoint and observed sequence

BuiltinPayload additionally contains purpose (`reproduce`,`repair`,`review`,`other`) and nullable repair_authorization. BuiltinRepairAuthorization is a small strict 2.0 record: task_id, request_sha256, design_sha256, acceptance_sha256, context_sha256, baseline_candidate CandidateSnapshot, baseline_archive map[RelativePath,BuiltinReceipt], before_receipts list[BuiltinReceipt], assessed_by_actor_ref, assessed_at UTC, assessment_ref BuiltinReceipt. Archive keys equal baseline artifact original paths; each immutable archived copy's hash equals that original artifact hash. Root observes the expected failure and saves its assessment before authorizing repair; this is not final independent code review or a new proof engine.

1. Freeze design, criteria/cases/levels, context/base and exact ownership. For a bug, first capture actual failing baseline at declared proof level. A reproduce-only worker owns evidence outputs, not product source. Root checks the real failure, current baseline bytes and scenario and persists the checkpoint.
2. At repair dispatch, recompute live baseline CandidateSnapshot from actual product paths and compare full artifact set/identity. Require nonempty valid checkpoint/archive receipts and matching design/acceptance/context; otherwise deny dispatch. At completion, validate preserved archive/before/checkpoint bytes and historical dispatch binding, NOT equality of repaired product to old baseline. Final product uses P12 final candidate. Root is trusted workflow authority; hashes do not sandbox tool effects or prove the right bug. Final independent semantic review still assesses actual failure.
3. Render exact submitted prompt from scope/task/assignment/token, excluding its own digest and eventual envelope digest to avoid circular hashes. Persist prompt/instructions, then bind their hashes in dispatched envelope and commit pending intent before host spawn.
4. Capture actual submitted call parameters and returned context/run. If host exposes only context identity, record that actual reference with its bounded meaning, never fabricate loader/turn identity. HostBinding checks actual supported call shape/message bytes, not a summary. Ambiguous startup occupies capacity; reconcile actual observations before retry.
5. A ready submission binds current envelope and original historical dispatch scope, exact token/run/task/assignment/responsibility, owned file hashes and criteria coverage. Wrong run/root/prompt/context/dependency or crossed same-responsibility assignments reject. Ready is not accepted.
6. Use fresh contexts for reproduction, repair, review and independent verification when separate assignments are required. Never reuse one actual host/run across dispatch tokens: existing unique-run rule remains unchanged. Sequence stages within max two active specialists. Root may capture baseline directly only with genuine matching observation, never invented dispatch.
7. Reviewer owns separate review evidence and receives exact product/design/criteria/context plus all before/after evidence. Existing P12 checks distinct actual actors/contexts/tokens/observations, case/proof coverage, scenario/input/environment/build, receipt bytes and review chronology. Findings/dispositions and re-review/retest preserve full immutable history.

Reviewer-ready handoff must return an actual owned review artifact. Final product set and review receipts stay separate to avoid circular self-hashing. Reproduction-only output acceptance does not accept repaired product.

## Codec and shared semantic interfaces

Add delivery_codec.py:

- `mode_for_task(task: TaskRecord) -> Literal['managed','builtin']`: strict reserved markers, policy requirement and configured-fallback rejection.
- `record_from_dict(kind: str, wire: dict, *, mode: str | None = None) -> object`: closed registry; snapshot decode at persistence/CLI requires request-derived mode. Common records use original parser, builtin records use separate parser, no retry fallback.
- `record_to_dict(record: object) -> dict` and `record_digest(record: object) -> str`: exact known type dispatch; managed bytes/hashes unchanged.
- `validate_snapshot(snapshot, task, previous=None) -> GateResult` and `validate_submission(envelope, submission, intent, artifact_root, *, dispatched_envelope=None) -> GateResult`: fixed internal mode branches; no injected permissive validators.

Builtin core APIs in builtin_records.py: `builtin_from_dict(kind, wire)`, `builtin_to_dict(record)`, `builtin_digest(record)`, `validate_builtin(snapshot, task, previous=None)`, `validate_builtin_submission(envelope, submission, intent, artifact_root, *, dispatched_envelope=None)`, `validate_builtin_dispatch(snapshot, assignment_id, artifact_root)`. Validators return existing GateResult. Dispatch rereads actual prompt/instruction/authority/checkpoint and current candidate/design/context receipts.

Core Task 1 introduces/tests neutral DAG/ownership/history/immutable scope/dependency invalidation/capacity helpers in delivery_semantics.py; the existing managed implementation stays unchanged. Root Task 2 serially rewires managed wrappers to accepted helpers, checking golden hashes and all existing managed tests. Fixed internal mode semantics check configured selection/manifest or builtin responsibility/prompt/authority. No fake managed envelope. Managed public validators normalize strict 1.0 first. Builtin handoff uses safe quality primitives with parity tests; contracts.py stays unchanged.

Shared internal APIs: check_snapshot(snapshot, task, *, mode), check_history(snapshot, previous, *, mode), check_submission_binding(envelope, submission, intent, *, mode), scope_key(envelope, *, mode). They raise ValidationError and use exact types/fixed mode semantics. Public wrappers return GateResult. To avoid imports cycling, delivery_semantics.py imports only contracts and type-neutral primitives; managed/builtin wrappers pass explicit normalized field views and fixed internal binding results, never fake envelopes. Codec imports both strict record modules; store/evidence/gate import codec. No record module imports codec/P12/persistence.

## Serialized integration and acceptance

Root changes store serializer/digest/validator aliases to codec; locked sessions derive mode from immutable task before snapshot load/commit and validate all historical revisions. Keep existing journal/head/operation schemas, CAS, safe descriptors/recovery/borrowed lock and F01 fixes. Do not infer mode from newest files.

P12 accepts exactly normalized managed/builtin snapshot types then runs existing common `_check`; EvidenceBundle stays unchanged. Builtin prechecks revalidate HostBinding/authority/checkpoint receipt bytes on every completion. ANY reserved execution-mode prefix triggers mandatory checks even when malformed, unknown or missing policy/registration/sidecar. Mandatory gate runs before and after optional callback under same lock/session, preserving F01 final authoritative task reread. Both CLI forms and direct TaskStore retain legacy quality, immutable cycles, child acceptance, actual terminated/absent dispatches, blockers and required case/proof coverage. Preserve F01 validation before initial sidecar writes; malformed builtin markers cannot use legacy path.

Reuse existing genuine DeliveryPolicy validation, which ALREADY enforces max_executing<=2 and max_correction_cycles<=3; do not duplicate or weaken it. Builtin plan must fit policy, and every builtin payload/task Limits must fit the same shared plan/policy bounds. Reject larger values at builtin registration/update/dispatch/completion, and use narrower applicable task/payload/host limits. One request tree has one capacity pool: pending/observed/ambiguous runs count; labels/nesting cannot reset it. Retain failed history and transitive dependency invalidation.

Observed demo follows root docs/tasks/tom-builtin/seeded-delivery-design.md. Product normalize_spaces(text) collapses whitespace (R01), trims edges (R02), preserves Unicode/punctuation (R03), and returns empty for blank input (R04); defective baseline only trims. Required cases: repeated-spaces, repeated-tabs, embedded-newline, mixed-whitespace, edge-whitespace, already-normalized, unicode-punctuation, empty-blank. Map R01 to cases 1–4, R02 to 4–5, R03 to 6–7, R04 to 8. A separate observed verifier (qa responsibility) independently runs all eight; implementer reruns cannot substitute. Preserve verifier assignment/run/handoff and link test entries to its observation. Reviewer semantic assessment and verifier actual execution are separate required acceptance activities.

Root updates AGENTS.md and bootstrap request-coordination references to allow explicit separately recorded builtin responsibilities where no configured identity was requested. Retain impersonation/covert-fallback prohibition; do not edit deployed ACTIVE manage/delegate assets, catalog or native definitions.

Acceptance preserves all managed golden wires/hashes and adds cross-mode/unknown version/configured fallback/missing marker-policy/receipt drift/same-actor/missing reproduction-case-proof/wrong handoff/unclear authority/bounds/recovery/callback-mutation negatives. After independent code review run actual safe local seeded bug through observed reproduce/repair worker contexts and separate reviewer, real before/after commands, root checkpoint, exact candidate, review/dispositions, P12 save and actual mandatory completion/readback. Use isolated copies for synthetic denial cases. Missing actual host observation/worker/reviewer proof remains blocked; fixtures cannot replace demo. No customer data/network/KB writes/activation/new permissions or Git effects.
