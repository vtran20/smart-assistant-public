# P00 — shared contracts and local Git baseline

Status: independently reviewed and frozen for implementation. Scope is P00 only; P01–P09 remain unimplemented.

## Outcome and mandatory cycle

Establish a versioned Python contract boundary for later independent packages and a local committed Git baseline. Every task and agent must design, implement, obtain independent review, record and resolve feedback, run final tests, and repeat after corrections until all acceptance criteria pass. This is a completion requirement, not an optional recommendation. A limit or blocker preserves progress and never justifies a false completion claim.

## Binding sources

- [System design](../../superpowers/specs/2026-10-12-smart-assistant-system-design.md), especially Local helper boundaries and contracts.
- [Implementation plan](../../superpowers/plans/2026-10-12-smart-assistant-implementation-plan.md), P00 and global constraints.
- [Agent rules](../../../AGENTS.md).

## Acceptance criteria

| ID | Outcome | Verification |
| --- | --- | --- |
| p00-contracts | Every v1 contract in the spec has an exported dataclass or typed enum, including capability lifecycle and preflight records and common exceptions. Nested records retain explicit types. | Inventory review and synthetic valid fixtures. |
| p00-validation | Recursive validation rejects missing/unknown fields, unknown record kinds, unsupported schema versions, malformed IDs/versions/digests/timestamps/relative paths, incorrect scalar or collection types, invalid enums, and inconsistent gate/snapshot metadata. Booleans do not count as integers. | Meaningful invalid fixtures and unit tests. |
| p00-serialization | Public to_dict returns JSON-compatible records with enum values, rejects non-JSON values and non-finite numbers, and deterministic fingerprints follow the spec. JSON decode can reconstruct nested typed records through a documented public decoder. | Round-trip and independently calculated hash tests. |
| p00-boundaries | Contract validation has no model, network, deployment, permission-grant, task-store or completion-gate side effects. Relative paths are lexically safe; root containment and live symlink checks are explicitly reserved for later filesystem consumers. | Independent code review and path cases. |
| p00-tests | A failing test is observed before contract behavior is implemented; final targeted and full discovered suites pass after all feedback corrections. | Saved test commands, outcomes and reviewed candidate hashes. |
| p00-baseline | Local Git exists on p00-foundation, accepted planning/contracts are committed, and runtime state, scratch, worktrees, bytecode, IDE-local metadata and private outputs are ignored. No remote is created. | Git status, log, remotes and check-ignore. |
| p00-cycle | Final candidate has independent review; all findings have explicit dispositions; fresh tests bind to reviewed candidate bytes. | Feedback and verification records. |

## Serialization decisions to freeze in design review

Use Python >=3.11 and the standard library only. All fields listed as required in the spec remain required on input, including nullable fields; Limits alone supplies its documented constructor defaults. Schema-bearing records require schema_version=1. Supporting nested records have no invented schema_version. Reject unknown fields in v1 so drift cannot be silently discarded. Export validate_record(kind, data), to_dict(record), and a validating from_dict(kind, data) decoder. validate_record returns GateResult; failures populate GateResult.errors with ErrorDetail records using stable codes and nested paths; decoder failures raise ValidationError carrying those details. RevisionConflict remains available to later stores.

Use enums for task status/phase, capability kind/state, action kind/host decision, disposition, check method/outcome, handoff result and probe purpose. Finding severity uses critical, major, minor, info, documented here because the original table did not enumerate it. Opaque source/evidence/tool/role references remain nonempty strings; actual record IDs use the specified ID syntax. Scope is a nonempty string and does not imply authorization. Handoff criteria_coverage maps criterion IDs to lists of evidence references. Selection uses explicit selected-capability records. Context facts, pending actions, and deployment files use explicit supporting dataclasses.

CandidateSnapshot serializes artifacts and candidate_id. Its digest input is the canonical JSON artifact list, sorted by artifact ID, excluding candidate_id and all receipts. AcceptanceSnapshot serializes criteria, design_sha256 and acceptance_id. Its digest input is the object with sorted criteria and design_sha256, excluding acceptance_id. DeploymentManifest serializes files and manifest_sha256; the digest input is the complete file list sorted by relative_path. Canonical JSON uses UTF-8, sorted keys, compact separators, ensure_ascii=False, and rejects non-finite numbers. All strings and mapping keys must be UTF-8 encodable Unicode scalar text; lone surrogates reject with structured not_json errors before hashing. Error paths escape invalid keys so error records themselves remain UTF-8 encodable. Valid non-ASCII and supplementary-plane Unicode remain literal in canonical payloads. Require lowercase SHA-256 hex strings. Snapshots verify declared hashes and sorted unique identities; no real file is opened by contracts.

Task and catalog revisions start at one; assignment revisions and cycle numbers are positive integers; catalog_revision and limits are positive integers. UTC timestamps follow YYYY-MM-DDTHH:MM:SS[.fraction]Z and must represent a real calendar date/time. Relative paths use POSIX separators and reject absolute paths, empty/dot/dot-dot components and backslashes. Artifact roots and external references are opaque at P00; later consumers resolve them safely.

GateResult passed is true iff errors is empty. PreflightResult ready is true iff missing_tools and pending_actions are both empty. NativeProbeReceipt preserves successful and failed observations: activation may have discovered=false or invoked=false/null, and disable may still have discovered=true. Contracts validate boolean/null shape and purpose; P02 alone requires discovered=true/invoked=true for activation or discovered=false/invoked=null for disabling. Failed probes are valid evidence records, never automatic activation approval. Structural validation is distinct from completing tasks or activating assets: later P01–P03 own transitions, current files, authorization decisions and evidence gates.

## Ownership and integration

Integrator owns this design, root guidance, ignore rules, Git operations, feedback record and plan progress. One implementer owns smart_assistant/__init__.py, smart_assistant/contracts.py, tests/__init__.py, tests/test_contracts.py and examples/contracts/*.json. Reviewer owns a review report only. No other package implementation begins in this task.

P00 bootstraps the empty repository in the canonical directory on a feature branch because worktrees require an initial commit. No concurrent implementation occurs before that baseline. P01–P03 consume the frozen types; P02 consumes deployment/probe records; P03 consumes candidate/acceptance/evidence/action contracts; P04 consumes PreflightRequest; P08 consumes assignment/handoff records. Contract tests use synthetic records and temporary directories, never live runtime state.

## Frozen wire inventory

Every listed field is required on JSON input, including null fields. `str` means nonempty string unless explicitly noted. `id` means the spec ID syntax; `ref` is an opaque nonempty string. `digest` means lowercase 64-character SHA-256 hex; `version` means three decimal components; `utc` means a calendar-valid UTC ISO timestamp. `positive` is an integer >=1, excluding bool. Lists are actual JSON arrays, maps are JSON objects with string keys, and nullable means the value can be null but the field cannot be omitted. No extra keys are accepted.

| Record | Exact wire keys and types |
| --- | --- |
| RequestEnvelope | schema_version:int=1; request_id:id; text:str; project_id:id; source_refs:list[ref]; requested_role:id or null |
| ContextFact | text:str; scope:str; source_ref:ref; observed_at:utc |
| ContextBundle | schema_version:int=1; project_id:id; preferences:dict[str, JSON value]; facts:list[ContextFact] |
| Criterion | id:id; description:str; verification_method:str |
| RequestedAction | action_ref:id; kind:ActionKind; resource_ref:ref; required_tool:ref or null; host_decision:HostDecision |
| AuthorizationScope | action_kind:ActionKind; resource_ref:ref; source_ref:ref |
| SelectedCapability | id:id; version:version; deployed_sha256:digest |
| Selection | catalog_revision:positive; agents:list[SelectedCapability]; skills:list[SelectedCapability] |
| Limits | max_correction_cycles:positive; max_parallel_children:positive; Python constructor defaults 3 and 2, JSON fields still required |
| Artifact | id:id; relative_path:safe relative path; sha256:digest |
| CandidateSnapshot | artifacts:list[Artifact]; candidate_id:digest |
| AcceptanceSnapshot | criteria:list[Criterion]; design_sha256:digest; acceptance_id:digest |
| Finding | id:id; severity:Severity; description:str; criterion_ids:list[id] |
| Disposition | finding_id:id; decision:DispositionDecision; reason:str; evidence_refs:list[ref] |
| ReviewReceipt | reviewer_ref:ref; implementer_ref:ref; candidate_id:digest; acceptance_id:digest; observed_at:utc; findings:list[Finding] |
| CheckReceipt | check_id:id; criterion_ids:list[id]; candidate_id:digest; acceptance_id:digest; method:CheckMethod; command:str or null; observation:str or null; environment:dict[str,str]; outcome:CheckOutcome; evidence_ref:ref; observed_at:utc |
| CycleEvidence | cycle_number:positive; design_ref:ref; candidate:CandidateSnapshot; acceptance:AcceptanceSnapshot; review:ReviewReceipt; dispositions:list[Disposition]; checks:list[CheckReceipt] |
| TaskRecord | schema_version:int=1; id:id; revision:positive; request:RequestEnvelope; status:TaskStatus; phase:TaskPhase; parent_task_id:id or null; capability_ids:list[id]; criteria:list[Criterion]; selection:Selection; limits:Limits; authorization:list[AuthorizationScope]; requested_actions:list[RequestedAction]; cycles:list[CycleEvidence]; blockers:list[str]; resume_next_step:string allowing empty; artifact_root:ref |
| TaskAssignment | task_id:id; assignment_revision:positive; role_id:id; selected_skill_ids:list[id]; design_ref:ref; criteria:list[Criterion]; context:ContextBundle; owned_paths:list[safe relative path]; selection:Selection; limits:Limits |
| Handoff | schema_version:int=1; task_id:id; assignment_revision:positive; role_id:id; result:HandoffResult; artifacts:list[Artifact]; criteria_coverage:dict[id,list[ref]]; evidence_refs:list[ref]; blocker:str or null; next_step:string allowing empty |
| PendingAction | action_ref:id; reason:str |
| PreflightResult | ready:bool; missing_tools:list[ref]; pending_actions:list[PendingAction] |
| ErrorDetail | code:str; path:str; message:str |
| GateResult | passed:bool; errors:list[ErrorDetail] |
| DeploymentFile | relative_path:safe relative path; sha256:digest |
| DeploymentManifest | files:list[DeploymentFile]; manifest_sha256:digest |
| NativeProbeReceipt | schema_version:int=1; operation_id:id; capability_id:id; version:version; manifest_sha256:digest; purpose:ProbePurpose; client_name:str; client_version:ref (host versions are opaque); session_ref:ref; discovered:bool; invoked:bool or null; observed_at:utc; evidence_refs:list[ref] |
| PreflightRequest | schema_version:int=1; required_tools:list[ref]; available_tools:list[ref]; requested_actions:list[RequestedAction]; authorization:list[AuthorizationScope] |
| CapabilityRecord | schema_version:int=1; id:id; kind:CapabilityKind; name:str; version:version; state:CapabilityState; source_path:safe relative path; deployed_path:safe relative path or null; deployed_sha256:digest or null; triggers:list[str]; boundaries:list[str]; required_inputs:list[str]; output_contract_ref:ref; tool_dependencies:list[ref]; validation_refs:list[ref]; discovery_probe_ref:ref or null; rollback_ref:ref or null |
| CapabilityCatalog | schema_version:int=1; revision:positive; records:list[CapabilityRecord] |

Enums have precisely these values: TaskStatus = queued/running/waiting_input/waiting_approval/verifying/completed/failed/paused/cancelled; TaskPhase = design/implement/review/feedback/testing; CapabilityKind = agent/skill; CapabilityState = draft/active/disabled/retired; ActionKind = read_local/write_local/external_read/external_write; HostDecision = allowed/approval_required/denied/unknown; Severity = critical/major/minor/info; DispositionDecision = corrected/rejected; CheckMethod = command/observation; CheckOutcome = pass/fail; HandoffResult = ready_for_review/blocked/failed; ProbePurpose = activate/disable.

CheckReceipt requires command!=null and observation=null for method=command, or observation!=null and command=null for method=observation. Gate/preflight consistency and snapshot sorting/uniqueness/hash consistency are P00 structural invariants. Other cross-record acceptance semantics (e.g. criterion coverage, receipt matching, reviewer independence and blocker policy) belong to P03/P08. Empty lists remain structurally valid where later packages must decide eligibility.

Public API: validate_record(kind: str, data: dict) -> GateResult; from_dict(kind: str, data: dict) -> typed record, raising ValidationError with an errors list on rejection; to_dict(record: object) -> dict, validating the record before returning JSON-compatible data. No filesystem/model/network calls. A documented canonical JSON helper may be exported for later packages. Error paths start at `$`, use `.field` for record fields and `[index]` for list elements; mappings with invalid keys identify the offending key. Stable codes: unknown_kind, invalid_type, missing_field, unknown_field, unsupported_schema, invalid_id, invalid_version, invalid_digest, invalid_timestamp, unsafe_path, invalid_enum, invalid_value, duplicate_id, unsorted, digest_mismatch, inconsistent_gate, not_json. Messages are explanatory, not a compatibility boundary.

CapabilityRecord.deployed_sha256 and SelectedCapability.deployed_sha256 mean the complete DeploymentManifest.manifest_sha256, including for one-file agents. They never mean the raw file hash or only SKILL.md's hash. Per-file digests live in DeploymentFile.sha256. P02 validates deployed bytes and relationships; P00 fixtures pin the shared meaning.

Future P08 validate_handoff(assignment, handoff, artifact_root: Path) receives the trusted root explicitly from the parent task. This preserves TaskAssignment's record shape and avoids dependence on reviewer/worker working directories. P08 must verify containment and existence against that root, including validation from a different current directory.
