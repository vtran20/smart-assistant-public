# Smart Assistant agent rules

## Canonical workspace

Use the current clone root as the Smart Assistant workspace. Resolve repository
paths relative to this directory; never assume the owner's home directory or
other customer workspaces exist. Open this clone as the Codex project folder.
Keep personal preferences, portfolio and customer settings in ignored
`.smart-assistant/` records. Optional `AGENTS.local.md` is ignored; it is not
automatically loaded by this project, so explicitly supply it when needed.

## Required work cycle

Every task and every agent in this project must follow **design → implement → review → feedback → test → repeat until complete**. This applies to code, agent definitions, skills, integrations, automation, and documentation. Do not skip a stage because another task passed it. This is a standing user requirement for this project, reaffirmed on 2026-10-13. Always implement, obtain independent review, provide and resolve feedback, run testing, and repeat after corrections until the task meets every acceptance criterion. Record the loop and its evidence in docs/evidence/<package>/; do not rely on chat memory alone.

1. **Design:** identify the outcome, scope, acceptance criteria, dependencies, affected files, and verification method before changes. Scale the design to the task. Architectural changes need a written design; a small correction can use a short task note.
2. **Implement:** perform the agreed work within assigned ownership. For behavior changes, use a meaningful failing test before implementation where practical. For documentation, implementation means writing the requested artifact.
3. **Review:** obtain an independent agent review of the exact candidate files or commit. Review correctness, requirements, interfaces, permissions, and likely failure cases. The implementer must not be the sole final reviewer. Review-only agents implement their review findings artifact and have that artifact checked by the coordinator; do not create an infinite chain of reviewers reviewing reviewers.
4. **Feedback:** record each finding and its resolution. Fix actionable findings or resolve them with evidence. Do not hide an unresolved issue or reinterpret acceptance criteria to claim completion.
5. **Test:** run the relevant checks against the final candidate after feedback changes. Use functional tests for code, activation and behavior evaluations for agents and skills, and coverage/link/diagram checks for documents. Record command, outcome, and candidate identity. A review of an earlier version does not cover later changes.
6. **Repeat:** changed behavior returns to design when scope or interfaces change; other corrections return to implementation, then independent review and fresh testing. Finish only when acceptance criteria are met, actionable findings are resolved, and final checks pass. "Perfect" means these evidence-based conditions, not a claim that no future defect can exist.

If access, essential input, or a runtime limit prevents completion, preserve progress and report the exact remaining work. Never replace required evidence with a success claim. Respect platform and task limits while iterating.

## Test-first acceptance and regression reporting

Apply to every task, not only bug fixes. Shared project rules are self-contained;
no owner-global rule installation is required. Before implementation,
create or select cases with inputs/steps/expected results; afterward verify the
final candidate against those cases and impacted regressions. Use proportionate
acceptance checks for non-code work. Keep the independent-review cycle above.

Final reports state what regression checks actually ran, when they ran, pass/fail/
skip/blocked/not-run results, matched before/after scope, evidence and remaining
gaps. Distinguish fresh execution from reading saved results; explicitly report
inapplicable or unexecuted regression work. Preserve stronger Xstore rules and
all permission/release gates.

## Coordination and parallel work

- The coordinator may delegate independent tasks to subagents and must pass these rules, the task design, ownership, dependencies, and expected handoff to each worker.
- Workers use their assigned isolated worktree for commands; the canonical root refers to the integration and live project. Workers own disjoint files. One integration owner controls shared contracts, root configuration, canonical catalog changes, backlog updates, and integration commits.
- Use isolated Git worktrees for concurrent implementation when a committed Git baseline exists. Documentation/advisory tasks with explicit disjoint ownership may share a checkout.
- Do not share live user task state between worktrees during tests. Use temporary fixtures and an isolated state directory.
- Return a concise handoff containing design reference, changed files, review findings and resolutions, test evidence, candidate identity, and remaining limitations.
- The coordinator reviews integration and reruns relevant checks on the combined candidate before reporting completion.

## Scope and evidence

- Start with [README.md](README.md), then the relevant design and implementation package. The capability backlog tracks product capability status; a completed document is not an implemented capability.
- Follow the user's current scope and authorization. Instructions and capability catalogs do not grant new account access or override Codex permissions.
- Prefer native Codex chat, skills, subagents, and connected tools for the first release. Do not introduce a backend, scheduler, or external account dependency without a requirement that needs it.
- Do not claim a defined agent or skill is active until discovery and behavior are verified in the installed client.
- Keep credentials and private runtime records outside committed planning artifacts. Do not publish, send messages, or create recurring tasks merely because a design mentions them.
- Before a package has executable code, validate documents with source coverage, local link checks, interface consistency checks, and Mermaid parsing. Once executable code exists, use the commands defined in the implementation package and record fresh results.

## Chat coordination entry point

For durable execution/resumption, use the actually available repository `request-coordination` skill and its documented CLI. For requested agent or skill lifecycle work, use the actually available `manage-agent` or `manage-skill` workflow. Do not force durable orchestration onto simple unrelated questions. Bootstrap skills establish the catalog; additional managed selections still require current eligible ACTIVE records, actual native proof and fresh preflight. Native role selection can be unavailable in a client: preserve a staged DRAFT and report that limit. The user approved a separate builtin-worker mode on 2026-11-03: when no configured capability identity was requested, Tom may assign an actual host worker an explicitly recorded task responsibility through that mode. This does not load or activate the DRAFT role. Never use builtin execution as a covert substitute for a requested configured identity; preserve its blocker. Both modes retain the same permissions, reproduction, independent review, evidence, testing and shared limits.

## Continuous project learning

For meaningful corrections or repeated workflows, read [project learning](docs/agent-learning.md)
and only its relevant evidence. Maintain that record during authorized work; reuse
user_confirmed and applicable agent_validated knowledge without a separate human
promotion request. Do not ask again for a preference already explicitly supplied.
This reduces human interruptions, not the required independent review/test cycle.
Knowledge states do not change capability catalog eligibility, native proof,
activation transactions, task completion checks or existing context contracts.
When independent review is unavailable or prohibited in the current chat, record it
as pending; do not invent a reviewer or claim acceptance. No new runtime learning
service is implied by these conversational file-based records.

## Private and shared material

Follow [sharing guidance](docs/sharing.md). Keep customer data, personal rules,
portfolio records and execution receipts local and ignored. Commit reusable
source, synthetic fixtures and reviewed documentation. Historical evidence is
kept locally under `docs/evidence/`; only reusable interface contracts there are
distributed. Record new private task evidence there as required by the work cycle.

Before coding, apply `coding-guideline` when available. Its fallback rules are:
state material assumptions, use the simplest justified solution, keep the diff
within scope, review the final diff and verify observable acceptance criteria.
Self-review never replaces the independent review required above.
