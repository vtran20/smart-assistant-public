# P11 delivery records: proposed interfaces

Date: 2026-11-03. Status: ROUND 1 CORRECTED CANDIDATE; independent source re-review pending. This is a
proposed additive contract for P12/P14/P16, not implemented behavior or activation.
Source: [approved architecture](../../superpowers/specs/2026-11-02-tom-jerry-orchestration-design.md), sections 5–6 and acceptance A03–A05/A12/A17–A20.
Coordinator reports user architecture approval on 2026-11-03. Frozen v1 wire types,
TaskStore, CLI, catalog and deployed capabilities remain outside P11 ownership.

## Encoding and errors

`smart_assistant.delivery_records` will own delivery schema `"1.0"`, independently
versioned from frozen v1. Public dataclasses are frozen; readers return validated
copies, never shared mutable cache objects. Nested lists/dicts are still validated
on every public boundary; frozen dataclasses alone are not deep immutability.
All fields below are required, including explicitly nullable fields. Unknown
fields, unknown enum values/schema versions, duplicate JSON keys, non-finite
numbers, bool-as-int revisions, invalid Unicode, blank identities and cyclic
Python containers fail closed. IDs use existing 2–64 character lowercase record
ID convention; SHA256 is 64 lowercase hexadecimal characters; revisions start at
1; UTC timestamps use explicit `YYYY-MM-DDTHH:MM:SS[.fraction]Z` and calendar parsing.

Use existing `ErrorDetail`, `GateResult`, `ValidationError`, `RevisionConflict`,
`canonical_json`, v1 `from_dict`/`to_dict` and `validate_handoff` without editing
their registries. Delivery encoding is a separate registry:

```python
def delivery_from_dict(kind: str, data: dict) -> DeliveryRecord: ...
def delivery_to_dict(record: DeliveryRecord) -> dict: ...
def delivery_digest(record: DeliveryRecord) -> str: ...
def request_digest(request: RequestEnvelope) -> str: ...
def policy_source_ref(policy: DeliveryPolicy) -> str: ...
```

`DeliveryRecord` is a closed union of the record classes below (including support
records); callers supply typed records, not arbitrary dictionaries. Digest means
SHA256 of existing canonical_json applied to the full validated wire object,
without an embedded self-digest. Exact serialized list order is significant.
`request_digest` hashes the complete unchanged v1 RequestEnvelope including its
source_refs; it is independent of mutable task status/revision/cycles.
`policy_source_ref` returns exactly
`smart-assistant:delivery-policy:1.0:<policy_id>:<policy_digest>`.
A registered request has exactly one reference with reserved prefix
`smart-assistant:delivery-policy:`; malformed, duplicate or unsupported reserved
references deny registration/loading. No reserved reference means legacy only in
P16's explicit legacy routing; it never means a missing registered policy is OK.
Policy has no request digest, preventing a circular policy/request binding.
Digests establish byte binding, not signatures, authentic actors or user approval.

Common diagnostics include `invalid_type`, `unknown_field`, `unsupported_version`,
`invalid_id`, `invalid_revision`, `invalid_digest`, `invalid_timestamp`,
`request_mismatch`, `policy_mismatch`, `invalid_graph`, `ownership_overlap`,
`stale_dependency`, `stale_assignment`, `wrong_run`, `invalid_transition`,
`unsafe_path`, `malformed_json`, `missing_registration`, `recovery_required`,
`history_mismatch`, `duplicate_submission`; stale CAS raises RevisionConflict.
Paths use JSONPath-style fields as in existing validators. IO failures preserve
state and propagate OSError unless translated to a specific unsafe/malformed error.

## Record fields

`schema_version: Literal["1.0"]` is required on every record below, including nested
support records. `Ref` below means nonblank string reference, not a path to open.
Only explicitly named path fields are interpreted as paths.

| Record | Fields beyond schema_version |
| --- | --- |
| DeliveryPolicy | policy_id: ID; policy_version: nonblank string; workflow_kind: bug/feature/document/research; source_ref: Ref; source_sha256: SHA256; reproduction_required: bool; independent_review_required: bool; required_verification_levels: nonempty unique list[str]; max_executing: positive int <=2; max_correction_cycles: positive int <=3 |
| DeliveryRegistration | task_id: ID; request_sha256: SHA256; policy_id: ID; policy_sha256: SHA256; registered_at: UTC |
| DeliveryPlan | task_id: ID; revision: positive int; request_sha256: SHA256; policy_sha256: SHA256; root_owner_ref: Ref; design_sha256: SHA256; acceptance_sha256: SHA256; routing_rationale: str; requirement_ids: nonempty unique list[ID]; assignment_ids: unique list[ID]; max_executing: positive int; max_correction_cycles: positive int; context_sha256: SHA256; next_step: str |
| DependencyPin | assignment_id: ID; accepted_revision: positive int or null; output_sha256: SHA256 or null |
| ObservedRun | host_ref: Ref; actor_ref: Ref; run_ref: Ref; dispatch_token: ID; observed_at: UTC; observation_ref: Ref |
| DispatchIntent | dispatch_token: ID; assignment_id: ID; envelope_revision: positive int; envelope_sha256: SHA256; created_at: UTC; state: pending/observed/ambiguous/terminated/absent; observed_run: ObservedRun or null; reconciliation_ref: Ref or null |
| AssignmentEnvelope | assignment_id: ID; revision: positive int; task_id: ID; parent_assignment_id: ID or null; required: bool; payload: unchanged v1 TaskAssignment; selected_role_id: ID; selected_role_version: str; selected_manifest_sha256: SHA256; base_ref: Ref; workspace_id: ID; worktree_root: absolute local POSIX path; owned_paths: unique list[exact relative file paths]; dependencies: list[DependencyPin]; state: proposed/dispatched/working/ready_for_review/changes_requested/accepted/blocked/failed/cancelled/superseded; dispatch_token: ID or null; observed_run: ObservedRun or null; output_sha256: SHA256 or null; handoff_submission_id: ID or null; review_refs: unique list[Ref]; invalidated_by: unique list[ID] |
| HandoffSubmission | submission_id: ID; task_id: ID; assignment_id: ID; envelope_revision: positive int; envelope_sha256: SHA256; payload: unchanged v1 Handoff; handoff_sha256: SHA256; observed_run: ObservedRun; submitted_at: UTC |
| DecisionReceipt | receipt_id: ID; task_id: ID; kind: dispatch/handoff_rejected/handoff_accepted/review/feedback/integration/reassignment/invalidation/cancellation/research/redesign/recovery; actor_ref: Ref; plan_revision: positive int; assignment_id: ID or null; assignment_revision: positive int or null; candidate_sha256: SHA256 or null; evidence_refs: unique list[Ref]; reason: str; created_at: UTC |
| DeliverySnapshot | task_id: ID; revision: positive int; previous_sha256: SHA256 or null; registration: DeliveryRegistration; policy: DeliveryPolicy; plan: DeliveryPlan; assignments: list[AssignmentEnvelope]; dispatches: list[DispatchIntent]; submissions: list[HandoffSubmission]; decisions: list[DecisionReceipt] |

Additional return-only value classes: `RecoveryReport(operation_id, outcome,
head_revision, preserved_refs, blockers)` and `DispatchStatus(allowed,
occupied_tokens, blockers)`. They are local typed results, not evidence certificates.
P12 owns EvidenceManifest/VerificationMatrix and P14 owns KnowledgeSelection;
P11 binds their immutable digests or references only, without defining their schemas.

## Cross-record validation and lifecycle

```python
def validate_delivery(snapshot: DeliverySnapshot, task: TaskRecord,
                      previous: DeliverySnapshot | None = None) -> GateResult: ...
def validate_submission(envelope: AssignmentEnvelope,
                        submission: HandoffSubmission,
                        intent: DispatchIntent,
                        artifact_root: Path, *,
                        dispatched_envelope: AssignmentEnvelope | None = None) -> GateResult: ...
def dispatch_status(snapshot: DeliverySnapshot) -> DispatchStatus: ...
```

`validate_delivery` is structural and history-aware; it does not open artifact
files or prove review semantics. Registration binds task.id, full task.request,
reserved source reference and complete policy digest. Policy/registration/root
owner/task/request binding never change. Changing policy requires a new linked
registered task; P16 owns legacy migration. Redesign within unchanged policy
requires a redesign receipt referencing old/new plan evidence and fresh design,
acceptance/context fingerprints. Requirement IDs cannot disappear through an
ordinary update; explicit redesign plus an evidence reference is needed and
invalidates affected assignments. Semantic authorization of redesign is P16's job.

Snapshot revisions increment exactly once; previous_sha256 binds the whole previous
snapshot. Plan revision increments once when plan content changes; otherwise it
remains identical. Assignment revision increments once when its content changes;
new assignment IDs start at 1. No deletion of assignments, dispatches, submissions
or decisions. Previous submissions/decisions are immutable ordered prefixes.
Dispatch updates follow the state rules below; history survives in prior snapshots.
A state/content change never resets an assignment revision or reuses its ID.

The plan assignment IDs exactly equal unique envelope IDs. All envelope task IDs
and v1 payload task IDs equal the root task ID; selected role and ownership match
v1 payload.role_id/owned_paths; selected role/version must appear in v1 selection.
Envelope revision is an outer delivery revision; payload.assignment_revision is the
unchanged v1 task-assignment revision and is not inferred from envelope revision.
Both are independently checked. Parent links refer to distinct existing IDs, form
a rooted forest under the one plan root owner, and cannot cycle. Dependency links
are unique existing IDs, not self; their graph is acyclic independently of parent
links. Accepted_revision/output_sha256 are either both null (planning only) or
both populated. Dispatch requires every dependency to pin the exact currently
accepted envelope revision and its output digest. Only accepted required outputs
satisfy required edges; optional assignments referenced by an edge are required
for that edge too. Blocked/failed/cancelled/superseded predecessors never satisfy it.

Ownership is exact file names, no directory claims/globs, empty components, `.`/`..`,
absolute paths, backslash, colon, NUL or ambiguous case-insensitive aliases.
Use Unicode NFC normalization and casefold comparison conservatively for conflicts;
reject noncanonical spelling rather than silently rewriting paths. Same-file and
file-versus-descendant claims conflict across all live write assignments in the
same workspace_id even in different worktrees. A path can transfer only after its
previous assignment is cancelled/superseded/failed, with an explicit reassignment
receipt. Parent supervisors may have empty ownership; parents do not inherit child
paths. Different workspace_id values must map one-to-one to a canonical project
identity supplied by the trusted coordinator; P11 cannot detect fabricated project
identity. Worktree roots are distinct for concurrent write assignments; P11 lexical
validation does not create worktrees or grant access. Filesystem validation at
submission is anchored and rejects symlinked roots/components and nonregular files.

Allowed assignment transitions:

- proposed -> dispatched, blocked, cancelled, superseded;
- dispatched -> working, ready_for_review, blocked, failed, cancelled, superseded;
- working -> ready_for_review, blocked, failed, cancelled, superseded;
- ready_for_review -> changes_requested, accepted, blocked, failed, cancelled, superseded;
- changes_requested -> working, blocked, failed, cancelled, superseded;
- blocked -> proposed (only never-dispatched), working (only existing observed run), failed, cancelled, superseded;
- accepted -> superseded or changes_requested (transitive invalidation only);
- failed/cancelled/superseded are terminal; retry uses a fresh assignment ID.

Same-state updates may add progress references but cannot mutate a dispatched
payload, selected role, ownership, worktree or accepted output silently. Changed
execution scope needs supersession plus a new assignment ID. An accepted envelope
requires output digest (SHA256 of canonical v1 handoff artifact list sorted by ID),
bound ready_for_review submission from the same observed run, nonempty review refs and current dependency
pins. These are structural minimums; P12/P16 must verify actual independent review,
requirements/test matrix and evidence before proposing accepted. P11 never treats
refs, GateResult supplied by arbitrary callers or different actor labels as proof.
An earlier accepted predecessor's supersession invalidates all reachable accepted
descendants in the same CAS: change them to changes_requested with invalidated_by,
clear current acceptance/output/review refs, retain submissions/history and record a
receipt. Any retained accepted descendant makes the update invalid. Nonaccepted
descendants must refresh pins before subsequent dispatch/acceptance. Candidate,
design/acceptance/context changes invalidate affected acceptance similarly; a broad
fingerprint change invalidates every accepted assignment conservatively.

Dispatch intent exists before spawn and pins the exact dispatched envelope. The
snapshot publishing a proposed -> dispatched transition includes its pending intent.
Intent pins that revision; recording ObservedRun increments envelope revision but
does not rewrite the immutable intent target digest. `validate_submission` requires
the latest envelope digest plus a token whose original dispatch scope matches the
latest envelope's unchanged payload/ownership/selected role/worktree. pending and
ambiguous intents count against max_executing; observed nonterminal runs also count.
observed and terminated require nonnull ObservedRun; pending/ambiguous require null;
absent requires null plus reconciliation_ref. Allowed intent transitions are
pending -> observed/ambiguous/absent; ambiguous -> observed/absent;
observed -> terminated. No timeout alone establishes absent/terminated. Every
reconciliation/termination needs observation evidence supplied by coordinator.
Recording observed run immediately after spawn is P16/host responsibility. A local
token alone is never an observed native identity. P11 checks identity consistency,
not host authenticity or global host capacity; P16 enforces the whole-tree budget,
review reserve and correction-cycle count. Plan limits may narrow policy, never
exceed it; dispatch_status counts all unresolved intents, including terminal
assignments whose runs remain unconfirmed stopped.

`validate_submission` checks assignment/task/token/observed actor+host+run, exact
current envelope revision/digest and handoff content digest before calling unchanged
v1 `validate_handoff(envelope.payload, submission.payload, artifact_root)`.
The root must equal the validated envelope worktree_root. Wrong same-role worker,
old envelope, token-only or ambiguous runs fail before v1 artifact reads. A passing
handoff is ready_for_review only. Duplicate submission IDs or repeat envelope/run/
payload submissions are rejected as replay; rejected proposals are retained as
immutable decision artifacts/references, never silently inserted as accepted records.

## Store API and shared lock contract

`smart_assistant.delivery_store` imports existing private anchored filesystem
primitives from state.py rather than copying or changing them: `_root_fd`,
`_open_directory`, `_open_regular`, `_assert_attached`, `_lock`, `_read_record`.
Their private-helper coupling is explicit and tested. Canonical JSON comes from
contracts.py. Do not reuse `_write_record`: it replaces mutable v1 task JSON.

```python
class DeliveryStore:
    def __init__(self, root: Path): ...
    def read(self, task_id: str) -> DeliverySnapshot: ...
    def dispatch_envelope(self, task_id: str, dispatch_token: str) -> AssignmentEnvelope: ...
    def register(self, initial: DeliverySnapshot,
                 expected_task_revision: int) -> DeliverySnapshot: ...
    def update(self, proposed: DeliverySnapshot, expected_revision: int,
               expected_task_revision: int) -> DeliverySnapshot: ...
    def recover(self, task_id: str, operation_id: str,
                action: Literal["finish", "reject"]) -> RecoveryReport: ...
    @contextmanager
    def locked(self, task_id: str, *, create: bool = False) -> Iterator[LockedDelivery]: ...

class LockedDelivery:
    def read_task(self) -> TaskRecord: ...
    def read(self) -> DeliverySnapshot: ...
    def dispatch_envelope(self, dispatch_token: str) -> AssignmentEnvelope: ...
    def register(self, initial: DeliverySnapshot,
                 expected_task_revision: int) -> DeliverySnapshot: ...
    def update(self, proposed: DeliverySnapshot, expected_revision: int,
               expected_task_revision: int) -> DeliverySnapshot: ...
```

Root is the SAME ignored state root as TaskStore: `root/tasks/<task_id>.json`,
`root/locks/<task_id>.lock`. Ordinary methods acquire that exact per-task lock,
including reads for consistent validation against current task. LockedDelivery is
valid only inside its context, performs no nested flock and never returns raw FDs.
P16 must reuse/adapt this transaction boundary when it modifies state.py, without
calling TaskStore.update under an independently acquired lock (deadlock hazard).
P11 does not offer a second lock or a public bypass of validation.

Default locked access opens existing delivery storage only. Read/inspection, update
and recovery never create delivery directories; missing storage returns a structured
missing_registration denial. `locked(task_id, create=True)` permits registration to
create missing storage lazily, after LockedDelivery.register has validated the actual
shared-lock task identity, expected revision, queued/running status, immutable policy
marker/binding and complete initial snapshot. Opening that context alone creates no
delivery storage. DeliveryStore.register uses this explicit context. A direct locked
register caller must request create=True when storage is absent. Existing incomplete
sidecars are denied without filling directories or erasing remnants. All retained
rejected-initial history rules below still apply. The common lock machinery may
create its normal task lock file for an unknown ID; this does not create a task or
a delivery policy sidecar. TaskStore-created task file bytes and existing lock bytes
remain unchanged by rejected inspection/registration.

register requires an existing nonterminal queued/running v1 task with the reserved
immutable policy ref, exact expected task revision, initial delivery/plan revision 1
and previous_sha256 null; no prior head/registration. update requires proposed
snapshot.revision equal expected_revision (store assigns +1), exact current task
revision, previous_sha256 equal current snapshot digest, and all validation/history
checks. Nested changed plan/envelope revisions are already next revisions and are
validated against current contents. Caller-supplied task copies are never authority;
store reads current task under the shared lock. Completed/cancelled tasks cannot
register/update. Failed tasks can be read/recovered but update waits for explicit
v1 resume by P16. register/update return decoded persisted snapshot copies.

P16 task creation sequence: persist queued task with reserved ref, register delivery,
then enable dispatch only when both validate under the same lock. An interruption
between first two writes leaves a reserved-but-unregistered task blocked, never a
legacy task. P11 register cannot atomically create v1 tasks and makes no such claim.
Registration of legacy tasks without the reserved ref is denied; P16 creates a new
linked task and leaves completed/cancelled originals untouched.

### Disk layout and crash protocol

All files are private regular files; directories mode 0700/files mode 0600:

```text
delivery/<task_id>/registration.json              # create once; same as snapshot
                   revisions/<revision>-<sha256>.json  # immutable snapshots
                   operations/<operation_id>.json      # immutable intent
                   resolutions/<operation_id>.json     # immutable recovery outcome
                   pending.json                        # current operation pointer
                   head.json                           # revision/digest/op reference
```

Only filenames generated from checked IDs/revisions/digests are opened; references
from JSON never become arbitrary filesystem paths. Read validates registration,
head, referenced snapshot, complete previous chain and operation consistency against
current task/policy; no fallback to directory scans, newest mtime or an older head.
A reserved request without any component is a missing_registration/recovery error.
Even without reserved ref an existing delivery directory is an inconsistency for
P16 to reject, not permission to fall back to legacy. History bytes are digest-checked.

Under shared lock: validate CAS/task/history, create+fsync immutable operation intent
(binding prior head, candidate digest/revision, expected task revision, registration
digest); publish+fsync pending pointer; create+fsync immutable snapshot and initial
registration when registering; revalidate attachment/lock/task/head; atomically
replace+fsync head (commit point); clear pending+fsync directory. Snapshot writes
use O_EXCL and never overwrite a revision or registration. Temporary head/pointer
files use random O_EXCL names, fsync then os.replace and directory fsync. Identity
checks cover locks, delivery/task/revisions/operations directory attachment and files.
Reject symlinks, directory replacement, FIFO/device/socket targets and hardlinked
mutable files (nlink != 1). Reject aliases to task/lock/head files.

IO error after head replacement may mean committed; caller must read/recover rather
than retrying blindly. A filesystem or power-loss guarantee beyond supported fsync/
atomic rename semantics is not claimed. Immutable staged files persist on failures.
When operations intent exists but pending was never published, no state was exposed;
its presence does not select a new head. If it belongs to interrupted initial
registration (no head), recovery is still required and must name that exact operation.
A populated directory with missing head never auto-registers anew.

read denies unresolved pending or malformed/missing authoritative components.
recover takes an explicit existing operation ID, locks and validates all safe paths,
original request/policy binding and chain. If head already equals candidate, finish
only records resolution/clears pending; reject cannot roll back a committed head.
If head equals prior (or no head for initial registration), finish requires the
original task revision, complete staged bytes and all original checks; reject
preserves staged bytes, writes rejection resolution and clears pending without
advancing head. If staging is incomplete, finish denies; explicit reject preserves
prior authoritative state. Initial registration rejection leaves task blocked until
new explicit valid registration, retaining prior rejected files. An unrelated/newer
head, changed task revision, ambiguous journal or malformed registration blocks
finish; reject cannot erase a valid committed registration. Missing/invalid policy
never permits a weaker policy or an invented success revision. Recovery outcome is
idempotent for the same operation/action; conflicting resolution actions are denied.
Orphan cleanup/deletion is outside P11. Ordinary update never ignores pending state.

## Consumer obligations and bounded acceptance

P12 consumes validated snapshots, request/policy/design/acceptance/context hashes,
assignment IDs/revisions/digests, observed runs and submissions. P12 returns its own
evidence results; no P11 callback marks them authentic. P16 is the trusted writer,
resolves native observations and authorization, invokes P12 plus existing quality
checks, writes DecisionReceipts and enforces completion across ALL public task paths.
P14 supplies a pinned KnowledgeSelection digest as context_sha256; P11 is agnostic
to KB layout. Neither P11 nor a stored hash activates roles, proves reviewer
independence, executes tests, guarantees a host run stopped, or enforces native
whole-tree capacity. Acceptance of P11 is local helper behavior only.

## Round 1 independent-review corrections (2026-11-03)

Root approved the R5 API refinement and additive R4 invalidation receipt kind.
These rules refine the preceding proposed contract and are required boundaries:

- When current envelope differs from the dispatch target, validate_submission MUST
  receive `dispatched_envelope=` containing the original immutable target. The
  new store/session dispatch_envelope method returns it by following validated
  committed history. The gate verifies ID/revision/digest, dispatched state/token,
  absent pre-spawn observation and exact execution scope before v1 reads. It never
  infers original scope from current state or accepts future target revisions.
  Supplied context remains structural data, not a signature or native proof.
- Every ownership transfer needs a NEW reassignment receipt bound to destination
  assignment/revision/current plan. Its evidence_refs includes the exact source
  reference `assignment:<prior_id>:<prior_revision>:<prior_envelope_sha256>`.
  Previous owners must be terminal or become terminal in the same update.
  Historical terminal ownership cannot bypass the receipt; references are not paths.
- Every invalidated accepted envelope needs a NEW `invalidation` receipt bound to
  its new envelope revision, current plan and OLD accepted output digest, with
  nonempty evidence_refs. invalidated_by contains changed accepted assignment IDs
  in that victim's dependency ancestry (including itself), or new evidence-bearing
  redesign receipt IDs for broad fingerprint changes. Unknown/unrelated causes fail.
  Justification/authenticity remains P12/P16 work.
- All public locked mutations deep-normalize caller containers before validating,
  digesting, staging or returning. Same-thread same-root/task nested DeliveryStore
  locking, including another instance, promptly raises nested_lock. Other threads/
  processes still serialize. Direct TaskStore.update under a held delivery lock
  remains prohibited until P16 integrates that boundary; this guard cannot intercept it.
- Reads validate the complete operation/prior-head chain as well as snapshots,
  including historical registration, matching finish resolutions and bound hashes.
  Missing head after ANY committed history denies registration. Only completely
  rejected initial operations with no prior authority allow explicit identical
  registration retry; staged bytes remain. Idempotent finish requires its operation
  in the current valid authoritative chain, so a receipt cannot hide missing history.
- Store submission, acceptance and recovery finish provide original dispatch
  context and recheck actual current artifact bytes using unchanged v1 validation.

### Round 2 R1.1 fail-closed retry clarification, 2026-11-03

Before ANY registration staging, classify base entries and all operation, resolution,
revision and registration remnants. Pristine means no durable record remnants.
Otherwise retry requires positive complete rejected-initial lineage: matching sets
of operation/resolution IDs, every operation has null prior head and the identical
revision-1 candidate/registration digests, every resolution is reject with null head
and exact preserved references, and any retained snapshot/registration matches the
identical proposed initial bytes. Unknown entries, missing operation proof, orphan
resolutions or unexplained revisions deny registration without writing a new
operation/head. No directory enumeration selects replacement authority. Valid
incomplete initial attempts remain explicitly rejectable and identical retries work.
