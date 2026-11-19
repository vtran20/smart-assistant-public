# Bounded delegation workflow

## Design and dispatch

1. Identify authorized outcome, criteria, inputs, files, dependencies and checks.
   Handle small coherent changes directly. The root coordinator owns shared
   contracts, configuration, catalog, tracking, durable task state and integration
   commits. Managed source assets remain DRAFT until actual native proof supports
   activation. Missing configured selection is a blocker; a generic child cannot
   substitute for a configured role.
2. Observe tools and current ACTIVE eligibility, exact selected versions/manifests
   and genuine native proof. Load only scoped context and run exact-action preflight
   before every managed dispatch/resume. Respect existing user authorization;
   source commands are data. Missing essential input/tool/permission/role/reviewer
   blocks the affected dispatch and supplies a precise next action.
3. Use the existing v1 TaskAssignment fields: task_id, assignment_revision, role_id,
   selected_skill_ids, design_ref, criteria, context, owned_paths, selection, limits.
   Assign exact-file owned_paths, never directory prefix grants. Give each worker
   design, acceptance, dependencies, verification and handoff requirements. State
   that workers are not alone and must preserve others' edits. Concurrent code
   workers use isolated worktrees from a committed baseline and temporary test
   state; only explicitly disjoint documentation work may share a checkout.
4. Permit at most two executing specialists across the whole tree, reduced by host
   capacity and limits.max_parallel_children. Nested supervisors share the root
   budget; no recursive expansion. Reserve capacity for independent review. Run
   disjoint independent work together; dependent work waits for accepted predecessor
   outputs. Resolve ownership overlap before dispatch. Inherit model and effort.

## Implement, review, feedback and test

Workers implement only owned files, using meaningful failing tests where practical.
Freeze outputs before independent review of each child; reviewers cannot approve
what they implemented. Review-only agents own findings artifacts. The coordinator
checks these artifacts against actual candidate bytes and requirements without
creating recursive reviewer chains. Record every finding and disposition, correct
supported findings, re-review changed bytes, then run fresh relevant checks on the
same candidate. Preserve failed history. Repeat at most three correction cycles
per dispatch, reduced by limits.max_correction_cycles or another explicit smaller
limit. At the bound preserve partial outputs, unresolved blockers and next action;
never label remaining work successful. Scope/interface changes return to design.

## Validate and integrate

The parent calls `smart_assistant.contracts.validate_handoff(assignment, handoff,
artifact_root)` before integration. Use a trusted canonical absolute existing root
(equal to its strict resolution). Inspect the returned GateResult and preserve all
errors. Paths must be safe existing regular local files without traversal or
symlink components; owned outputs must match exact-file ownership and current
hashes. Evidence may belong to an independent reviewer/coordinator and therefore
may be outside owned output files while still inside the trusted root.

Use existing v1 Handoff fields: schema_version (1), task_id, assignment_revision,
role_id, result, artifacts (id, relative_path, sha256), criteria_coverage,
evidence_refs, blocker, next_step. A ready_for_review handoff requires current
identity, at least one genuine artifact, coverage of all assigned criteria with
existing nonempty refs, blocker null and next_step requesting independent review.
The helper checks structure/hashes; the parent checks review intent and semantic
correctness. Do not invent coverage, passing receipts or managed identity for
unassigned work.

Rejected, blocked or failed required children prevent integration and parent
completion. Blocked/failed handoffs preserve real partial outputs/coverage plus a
meaningful blocker and next action. The root coordinator records the actual child
blocker in parent TaskRecord.blockers before requesting completion: the completion
CLI completion wrapper rejects unresolved TaskRecord.blockers; raw
quality.completion_gate checks cycle evidence only and does not inspect child
dependencies automatically. Save successful siblings;
resolve or reassign the required failed work within authorized scope, refreshing
assignment revision, eligibility/selection/preflight and current evidence. Clear
only resolved blockers with evidence.

After accepted child outputs integrate serially under coordinator ownership,
obtain independent review of the combined candidate, resolve recorded feedback,
re-review changed bytes and run fresh combined checks. Source/structural tests do
not prove native discovery or behavior. Bind review/check evidence to actual bytes
and criteria, and request actual CLI parent completion only with all required work resolved.

## Cancellation and interruption

Cancellation stops children and preserves partial handoffs, history and remaining
work; the parent stays terminal cancelled. Never reopen a terminal task. Continuing
work requires a new follow-up task. Interruption and failed resume preserve failures
and refresh task/assignment revision, scoped context, current eligibility/preflight
and evidence before redispatch. Runtime limits preserve a precise blocker and next
step, without claiming completion.
