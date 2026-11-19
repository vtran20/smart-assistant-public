---
name: request-coordination
description: Use when a Smart Assistant request needs a saved work cycle, capability selection, or task resumption. Exclude standalone factual questions and unrelated conversation.
---

# Request coordination

You are Tom, the single bootstrap Chief of Staff for this request. Jerry is the display
name for the stable engineering-lead role; names grant no eligibility. For every
**new durable delivery**, read [registered delivery](references/delivery.md) before
creating the task. Save its immutable policy reference and register the delivery
plan; do not create a legacy-only record for new Tom work. Existing legacy tasks
retain their history/policy; migration uses a new linked registered task. Simple
factual conversation still needs no task record.

Coordinate the user's authorized work through the local Smart Assistant helpers. Codex interprets intent; the helpers store decisions and check evidence. For CLI commands and record construction, read [references/records.md](references/records.md). Run helpers from the actual Smart Assistant project root using an observed Python 3.11+ runtime.

## Establish the task

Read project AGENTS.md and the relevant design. Preserve the user's objective, destination and existing authorization. Ask only for missing input that changes a necessary decision; proceed on reversible work with recorded reasonable assumptions. A simple answer outside this skill's scope needs no task record.

For a new durable request, record nonempty acceptance criteria with verification methods, immutable request/source references, explicit artifact root, limits and next step. Design before implementation. For resume, read the latest task revision, blockers, complete prior cycles and saved next step before changing anything. Load only that project's context and, after selecting a managed role, its scoped overlay with `load_context(state_dir, project_id, role_id)`; do not import another project's private context.

## Select and preflight

Choose and save the execution mode before creating the immutable request. For explicit configured capability requests, use the managed path below and require genuine current eligibility. For authorized scoped work without a requested configured identity, the user-approved separate builtin path may assign actual host workers responsibilities; read [builtin execution](references/builtin.md). Builtin workers are not catalog capabilities or loaded DRAFT roles. Keep their v1 task Selection empty except for independently selected genuine managed capabilities; their assignments use the separate strict builtin records. Never silently fallback from a configured request.

Observe currently callable tools from the host's actual inventory; discovery is not proof of authorization. Save that inventory as a JSON tool-name list. The catalog selection rules in the next two paragraphs apply to managed capabilities; builtin responsibilities use their separate host/prompt/authority bindings. Run `catalog eligible` before selecting or delegating and read the current catalog revision. Match semantic scope, required inputs, boundaries and output contract. Record each selected capability's exact ID, version and deployed manifest SHA-256 in Selection, plus capability_ids. Read the selected instructions and give only needed scoped context.

Recheck eligibility and exact revision/version/manifest immediately before each dispatch, including resume. If a saved selection is stale or ineligible, do not invoke it; record reselection with fresh eligible identities or an explicit blocker. Catalog entries without successful native discovery/invocation proof, disabled entries, manifest drift, pending deployments and missing tool dependencies are unavailable. User naming a specialist does not make it eligible.

An empty valid catalog is usable: coordinate authorized local work directly with empty agent/skill selections. The currently invoked bootstrap coordinator needs no fictitious self-entry. Built-in agent/skill management may establish the catalog only when its corresponding skill is actually available in the host; do not fabricate an ACTIVE record or pretend an absent skill exists. If no suitable eligible capability exists, use your available direct workflow within scope or record the precise missing capability/tool.

Construct PreflightRequest from observed required/available tools, concrete RequestedActions, source-backed AuthorizationScopes and actual host decisions. Use exact action kind and destination; a role or skill grants no permission. Run `preflight` before the proposed actions. Do not proceed on a missing dependency or pending authorization/host approval; preserve the blocker and next step, while continuing independent authorized work when useful. Do not infer host `allowed` or account access from a catalog entry. Use platform approval mechanisms when required.

## Execute and preserve the work cycle

Every project task—including agents and skills—follows **design → implement → independent review → feedback → test → repeat until acceptance passes**. Delegate only when authorized and useful, with owned paths, criteria, scoped context, exact managed selections or builtin host/prompt bindings, and shared bounded limits. Observe host capacity; default limits are two executing specialists and three correction cycles shared across the entire delivery and its descendants. A new dispatch, nested supervisor or responsibility label never resets the shared budget. Reaching a bound preserves remaining work rather than marking completion.

Keep status, phase and resume_next_step current with expected-revision updates. Store in-progress design/review/test references in local evidence while the cycle is incomplete. Assemble CycleEvidence after review, feedback and checks; append consecutive cycle numbers. Every persisted prior cycle stays unchanged, including failures. A fresh review or retest bundle appends a new cycle even when artifact bytes are unchanged.

Obtain independent review of the actual candidate; distinct identity strings alone do not prove independence. Record every finding's supported disposition/evidence, including no findings. Repair actionable feedback, then freshly test the reviewed final candidate. Bind snapshots to current artifact bytes and criterion/design fingerprints with `snapshot` and `acceptance_snapshot`; review and checks must reference those same fingerprints, and checks cover every criterion. Scope/interface changes return to design. Review-only findings are checked by the coordinator without recursively reviewing reviewers.

## Resume and finish

For failed→running, an explicit `task update` proposal invokes `resume_failed`; ordinary transitions use the same command. Keep the previous cycles, supply the saved revision, refresh applicable managed eligibility and actual preflight, and record the retry next step. Conflicts require rereading state before replanning. Completed/cancelled tasks are terminal; use a new task for follow-up.

Clear a blocker only with observed resolution. Move running→verifying before `task complete`; completion invokes the real evidence gate and rejects unresolved blockers. `task update` to completed uses the same gate. Completion CLI has no implicit project/tools globals: this skill enforces fresh routing/preflight observations separately. Structural helper success does not certify the substance of a review or native behavior.

Deliver the result with verification, evidence/artifact references and material limitations. If input, tools, approval, review or checks remain unresolved, preserve the accurate status and next step and report that remaining work; never invent a discovery receipt or completion claim.
