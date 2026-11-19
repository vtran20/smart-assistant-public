# P16 exact integration interfaces

Status: proposed 2026-11-03; root lock-adapter and current/proposed task distinction
approved in chat; precise CLI/evidence binding review pending. P12 corrected source
is read-only planning input pending root acceptance. Frozen v1 stays unchanged.
Plan: ../../superpowers/plans/2026-11-03-p16-enforced-delivery.md.

## Lock adapter and shared TaskStore path

`DeliveryStore.borrowed(task_id, *, root_fd, tasks_fd, locks_fd, lock_fd)` is a
context manager returning a scoped LockedDelivery. Root expressly reassigned
additive delivery_store.py work to P16. Only trusted TaskStore internals call it
while holding the exact task's exclusive lock. It never flocks/unlocks or closes
borrowed descriptors. It verifies root matches self.root, task/locks attachments,
lock filename/inode/regular/single-link, and opens existing anchored delivery/task/
revisions/operations/resolutions descriptors without creating missing registration.
Owned descriptors close and session expires on exit. Same nested-session guard as
DeliveryStore.locked applies. Descriptors alone do not prove a held lock: supported
TaskStore caller actually holds it. Missing/unsafe/unresolved registration fails
closed. Never call DeliveryStore.read/locked while TaskStore holds the lock.

Existing TaskStore public signatures stay. Create validates consecutive cycle
numbers from one. Update/resume order: normalize; acquire lock; actual disk task;
existing CAS/identity/request/transition checks; consecutive cycles and immutable
existing cycle prefix; proposed task revision=current+1; mandatory registered gate;
existing supplied callback; final mandatory current-byte revalidation; attachments;
atomic replace. Borrowed session/guard and actual task lock remain held through
callback, final check and task persistence; nested same-task delivery acquisition
fails promptly with structured nested_lock. Disk task must still equal the actual
task read at the beginning of completion. Callback cannot disable
the mandatory gate. Noncompletion updates also preserve history. Legacy transition
and callback priorities stay; completion with no configured callback stays denied.
Registered tasks may be queued before sidecar registration.

A reserved source-ref prefix `smart-assistant:delivery-policy:` (including malformed,
unsupported or duplicate marker), OR existing task delivery directory triggers
mandatory registration on completion. Existing directory without matching marker
fails. Legacy without marker/directory retains existing callback behavior.
Diagnostics (`delivery show`, `delivery evidence show`, `delivery check`) and
rejected registration preserve that legacy routing: default DeliveryStore.locked
opens existing storage without creating delivery directories. This also applies to
unknown IDs, update and recovery. Explicit `locked(create=True)` only authorizes
lazy creation by register after actual task/CAS/status/immutable marker and initial
snapshot checks under the shared lock. Direct locked registration follows the same
validation order. Existing unexplained sidecars remain fail-closed; genuine partial
registration/rejected-retry history is preserved. No diagnostic can create a sidecar
that forces a legacy task to require registration. Normal unknown-ID lock-file
creation remains possible and does not create a delivery policy sidecar.

Registered completion composes current quality gate and parent blockers regardless
of callback; callback still runs afterward. Exact locked denial details reach CLI.

P11 validate_delivery(snapshot,current) receives actual nonterminal disk task;
P12 validate_delivery_evidence(proposed,snapshot,bundle,Path(proposed.artifact_root))
receives proposed completion revision=current+1. P12 recomputes actual candidate,
design, criteria and quality. Completion cannot simultaneously change artifact_root
(change it in preceding nonterminal update). Required assignments must be accepted
and noninvalidated with authoritative dependency validation. Pending/ambiguous or
observed unterminated runs deny. Plan/policy correction-cycle bounds apply.

## Immutable evidence and authoritative head

New delivery_gate.py owns DeliveryEvidenceStore(root), using DeliveryStore.locked
for standalone methods and a borrowed session inside TaskStore:

- read(task_id) -> EvidenceRevision
- save(task_id,bundle,*,expected_revision,expected_task_revision,
  expected_delivery_revision) -> EvidenceRevision
- check(task_id) -> GateResult

EvidenceRevision is a new P16 envelope, not v1. expected_revision is integer zero
for first save, positive current evidence head otherwise; bool rejected. Task and
delivery CAS revisions are independently positive. Strict P12 codec APIs consumed:
evidence_from_dict(dict), evidence_to_dict(bundle), evidence_digest(bundle),
validate_delivery_evidence(task,delivery,bundle,artifact_root)->GateResult.

Private path: delivery/<task>/evidence/head.json and
 evidence/revisions/<revision>-<revision_sha256>.json. Strict revision fields:
schema_version='1.0',task_id,revision,previous_sha256,delivery_revision,
delivery_sha256,plan_sha256,bundle_sha256,bundle (P12 strict dict).
previous_sha256 is null only at revision one. revision_sha256 hashes canonical
entire envelope. Strict head fields: schema_version,revision,revision_sha256.
No task revision binds persisted bundle: task cycles may advance while candidate
and required exact P12 bindings remain valid. Save checks actual task CAS.

Single task lock covers reread of task, P11 authoritative delivery, evidence head,
all three CAS checks and P12 semantic validation. Head/revision reads use anchored
no-follow nonblocking regular single-link files, duplicate/nonfinite rejection,
strict types/digests and complete consecutive immutable predecessor chain.
Current head must bind current delivery digest/revision, exact plan and P12
candidate/acceptance/context; historical evidence retains original binding.

Save writes immutable revision with exclusive create/fsync before atomic head
replacement, rechecking task/delivery/head/attachments immediately before commit.
Pre-head interruption leaves nonauthoritative orphan; never auto-adopt newest
filename. Different bytes cannot overwrite orphan. Missing head with unexplained
revisions fails closed and needs explicit local recovery (not a fabricated pass).
An old authoritative head remains readable only if current bindings match. Same
revision concurrent saves have one success/one conflict. No separate evidence lock.
Check holds same task lock, builds hypothetical completion next revision, returns
mandatory result without completing task. Commands stored in evidence never run.

## Exact CLI

Strict existing JSON input loader, sanitized one-line response and exits remain:
0 success,2 invalid/unsafe input,3 CAS conflict,4 unmet gate. Existing task commands
remain; completion/update return actual locked mandatory denial details.

- delivery create --record SNAPSHOT --expected-task-revision N --state-dir ROOT:
  register already-created task; failed registration preserves queued history.
- delivery show ID --state-dir ROOT: authoritative P11 snapshot.
- delivery update --record SNAPSHOT --expected-revision N
  --expected-task-revision N --state-dir ROOT: P11 CAS update.
- delivery evidence save ID --bundle JSON --expected-revision N
  --expected-task-revision N --expected-delivery-revision N --state-dir ROOT:
  validated immutable evidence revision/head.
- delivery evidence show ID --state-dir ROOT: authoritative EvidenceRevision.
- delivery check ID --state-dir ROOT: mandatory gate, no task mutation.
- team show --profile PATH: strict display profile, no eligibility grant.

## Display profile and semantic routing validation

load_team_profile(path)->TeamProfile strictly decodes existing core/team.json.
Root is bootstrap-root with Tom display name; Jerry maps engineering-lead only.
Duplicate role IDs/unknown fields fail. Source DRAFT entries remain ineligible.
validate_routing_choice(profile,*,domain,workflow_kind,rationale,selected_roles,
eligible_roles)->GateResult validates a choice already made by Codex: nonblank
domain/rationale, supported kind, selected IDs/versions present in profile and
independently supplied actual eligible IDs/versions. No keyword-based inference.
Direct scoped authorized workflows may select no roles and explain their limits.
Persist semantic rationale/root owner/context in P11 DeliveryPlan. Actual catalog
eligibility, preflight/authorization and observed source-bound identities remain
workflow gates, not inferred from display/profile strings. Root owns active assets;
P16 proposes bootstrap changes under this evidence directory only.

## Verification and review

TDD direct TaskStore alternate passing callback; CLI complete/update; malformed
policy/missing registration/evidence; history rewrite/gaps; unsafe symlink/FIFO/
hardlink/detachment; stale/tampered binding/CAS; bounded no-deadlock and concurrent
process checks; legacy compatibility; DRAFT/display/routing semantics. Actual safe
seeded CLI before/after where feasible retains exact exits/logs. Synthetic fixtures
never prove native identity or runtime acceptance. Root interface review precedes
code; independent exact-candidate review and fresh checks follow, within three
correction rounds. No commits/merge/push/activation/shared KB writes.

## Approved root amendments and recovery contract

Root independently read and approved this exact interface proposal on 2026-11-03
before production code, with explicit named-orphan recovery required. Additive
borrowed adapter ownership and current/proposed task distinction were approved.
Corrected read-only P12 source SHA256 is
fa7ce8ee4036408a05a573f0ea8066af4a8d6942d53eed2dedc404e0e72b4dcb.

Evidence layout additionally contains evidence/resolutions/<revision>-<hash>.json.
`recover(task_id,revision,revision_sha256,action,*,expected_revision,
expected_task_revision,expected_delivery_revision)` takes exact named bytes and
all three current CAS revisions. `finish` revalidates the same envelope/current
plan/evidence before publishing its head; `reject` preserves the revision and
immutable checked resolution. Neither selects the newest filename nor deletes.
Strict resolution fields: schema_version,task_id,revision,revision_sha256,action,
prior_head,task_revision,delivery_revision. Original prior head/immutable bytes are
checked, finished revisions remain in the authoritative chain, rejected revisions
cannot become authority. A fresh re-reviewed bundle yields distinct bytes after
rejection; a rejected same envelope cannot be silently reused. A committed head
with interrupted finish-resolution write can be reconciled by exact same finish.

CLI addition: delivery evidence recover ID --revision N --revision-sha256 HASH
--action finish|reject --expected-revision N --expected-task-revision N
--expected-delivery-revision N --state-dir ROOT. Recovery decisions retain real
CAS values locally; no public fixture is a real host/runtime acceptance claim.
