# Smart Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. Every package also follows the mandatory cycle in the project AGENTS.md.

**Goal:** Deliver M1 and M2 as a Codex assistant that routes requests, produces verified local results, and adds validated agents and skills through chat.

**Architecture:** Codex supplies the conversation, skills, tools, and subagent runtime. Standard-library Python helpers preserve task records, validate capabilities, and check completion evidence. One coordinator owns shared live state and integrates disjoint worktree changes.

**Tech Stack:** Python 3.11 or later; standard-library unittest, dataclasses, JSON, TOML parsing, hashing, file locks, and atomic replacement; Markdown skills; TOML agent definitions; Git worktrees. No LLM API or standalone service dependency.

**Spec:** [Smart Assistant System Design](../specs/2026-10-12-smart-assistant-system-design.md).

Status: P00–P03 have accepted package implementations through independent review, resolved feedback, and final tests. P01, P02, and P03 were implemented concurrently in isolated worktrees and integrated serially on wave1-foundation. See Wave 1 execution evidence (local historical archive: `../../evidence/wave1/progress.md`) for package identities and combined acceptance. P04–P06 source implementations are integrated on wave2-chat-workflows with independently reviewed corrections and coordinator code checks. Native/combined acceptance for P04–P06 is tracked in Wave 2 evidence (local historical archive: `../../evidence/wave2/progress.md`). P07 reference writing/verification has passed its scoped native lifecycle, correction/resume and actual full-eight task completion; see P07 acceptance (local historical archive: `../../evidence/p07/acceptance.md`). Final independent delivery review and local publication passed. P08 bounded local delegation passed independent final review, 293 tests and all eight actual task criteria; both native capabilities are ACTIVE. Failed runs and recovery limits remain in P08 evidence (local historical archive: `../../evidence/p08/acceptance.md`). P09 selected M1/M2 integrated acceptance passed all12 actual task criteria and 323 tests on macOS/Linux after independent review; see P09 acceptance (local historical archive: `../../evidence/p09/acceptance.md`).

## Global constraints

- First release uses the existing Codex chat interface; no custom frontend, LLM API service, or always-on daemon.
- Local helpers use Python 3.11 or later and the standard library; first release supports macOS and Linux.
- All tasks follow design → implement → independent review → feedback → test → repeat until acceptance criteria are satisfied.
- Completion evidence binds to the final candidate fingerprint; changed candidates require fresh review and relevant testing.
- The coordinator is the only writer of shared live task state and active capability deployment.
- Each test and development worktree uses an isolated state directory; no tests read or modify live user state.
- Agent and skill activation requires structural validation, behavior evaluation, and native discovery evidence.
- Runtime instructions, catalogs, and helper validation do not override Codex permissions or create new authorization.
- First release performs on-demand local workflows; external writes, recurring schedules, and event listeners are later milestones.
- No capability backlog item is Done merely because its design or definition file exists.

## Review focus

1. A deployed but disabled or unprobed capability must not remain eligible; native discovery removal must be observed. Covered by P02, P05, and P06.
2. Two writes based on the same task or catalog revision must not silently overwrite each other. Covered by P01 and P02.
3. An artifact changed after review or tests must not retain completion eligibility. Covered by P03 and P09.
4. A role naming a tool must not be treated as user authorization or platform access. Covered by P03 and P04.
5. Interrupted deployment, blocked delegation, and review-only tasks must preserve useful state without recursive review or false completion. Covered by P02, P08, and P09.

## Package ownership and dependencies

| Package | Owner role | Dependencies | Exclusive file ownership | Backlog traceability |
| --- | --- | --- | --- | --- |
| P00 | Integrator | Reviewed design and plan | Shared contracts, root scaffolding, Git baseline | S06, S07, S09 |
| P01 | State engineer | P00 | smart_assistant/state.py, smart_assistant/context.py, tests/test_state.py, tests/test_context.py | T16, T17, S06 |
| P02 | Catalog engineer | P00 | smart_assistant/catalog.py, smart_assistant/lifecycle.py, tests/test_catalog.py, tests/test_lifecycle.py | S01, S02, S15 |
| P03 | Quality engineer | P00 | smart_assistant/quality.py, smart_assistant/preflight.py, tests/test_quality.py, tests/test_preflight.py | T09, T22, T23, T25, T48, S07, S09, S16 |
| P04 | Coordinator engineer | P01, P02, P03 | smart_assistant/cli.py, smart_assistant/__main__.py, request-coordination skill, tests/test_cli.py, coordinator scenarios | T15, T18, T30, S05 |
| P05 | Agent lifecycle engineer | P02, P03 | smart_assistant/agent_lifecycle.py, manage-agent skill, agent staging fixtures, tests/test_agent_lifecycle.py | T11, T19, T33, T41, S03 |
| P06 | Skill lifecycle engineer | P02, P03 | smart_assistant/skill_lifecycle.py, manage-skill skill, skill staging fixtures, tests/test_skill_lifecycle.py | T13, S04 |
| P07 | Workflow engineer | P04 | draft-document and verify-completion skills, writer and reviewer definitions, local report examples, workflow scenarios | T12, T36, S14 |
| P08 | Delegation engineer | P04, P05, P06, P07 | delegation skill, engineering lead definition, tests/test_handoff.py, delegation scenarios | T05, T06, T08, T27, T35, T42, T24, S12 |
| P09 | Integration reviewer | P01 through P08 | tests/test_acceptance.py, acceptance report, integration documentation | S07, S14 and integrated selected M1/M2 coverage |

Root AGENTS.md, README.md, shared contracts, .gitignore, canonical catalog changes, and backlog status updates belong to the integrator only. Package workers can request changes to these files; they do not edit them concurrently. Native asset deployment happens serially after package integration.

Do not mark a broad capability Done when a package implements only part of it. P08 adds basic delegation and configuration validation; it does not claim all cloud execution or model-routing use cases are complete. S15 requires observed rollback, not just storing an old file.

## Parallel waves

| Wave | Work | Integration gate |
| --- | --- | --- |
| 0 | P00 contracts and Git baseline | Contracts and fixtures independently reviewed, checked, and committed |
| 1 | P01, P02, P03 in parallel | Each package passes its own cycle; integrator combines and reruns all helper tests |
| 2 | P04, P05, P06 in parallel | Coordinator and lifecycle interfaces agree; no direct shared catalog writes |
| 3 | P07 reference workflows | Real client invocation and artifact verification pass |
| 4 | P08 bounded delegation | Child and parent completion evidence agree |
| 5 | P09 integrated acceptance | Full suite and native client scenarios pass on the integrated candidate |

Four agent slots include the coordinator. Use three workers in a wave and review when one finishes, or two workers plus a reviewer. A fresh independent reviewer checks each implementation package. Do not exceed host capacity.

## Worktree and integration procedure

P00 initializes a local repository after checking for any newly created or inherited repository, adds ignore rules, and commits the accepted baseline. Its reviewed planning and contract baselines are established on p00-foundation; final acceptance identities are recorded in docs/evidence/p00/. Do not create a remote or push merely to enable worktrees.

For each parallel package, use the worktree skill and prefer a managed worktree with an explicit accepted baseline commit. If managed worktrees are unavailable, create a local worktree under an authorized path after checking its placement and ignore rules. Give it a distinct package branch or supported detached checkout. Never assume a guessed default branch exists in a new local repository.

Each worker receives its package, spec, AGENTS.md, baseline identity, owned paths, interfaces, criteria, and handoff template. Tests use a temporary state root. Workers produce isolated fixtures rather than altering the live catalog or user state. The integrator applies accepted commits one at a time, resolves conflicts, verifies the combined revision, then updates the next wave's base.

Preserve review and test evidence before archiving a worktree. A changed integrated candidate receives integration review and fresh checks even when its component commits passed earlier.

## P00 Contracts and baseline

**Files:** Create `smart_assistant/__init__.py`, `smart_assistant/contracts.py`, `.gitignore`, `tests/__init__.py`, `tests/test_contracts.py`, `examples/contracts/*.json`, and `docs/tasks/p00/design.md`.

**Interfaces:** Define every v1 contract in the spec as a dataclass or typed enum with explicit serialization. Export `validate_record(kind: str, data: dict) -> GateResult` and `to_dict(record: object) -> dict`. Keep required fields and enum values aligned with the spec. Helpers reject unknown schema versions and malformed IDs; versions use three decimal components. Candidate IDs exclude receipts to avoid self-referential hashing.

- [x] **Design:** write P00 acceptance criteria and the supported serialization types; verify Python is at least 3.11. Freeze contracts only after independent review.
- [x] **Implement:** add a meaningful failing contract suite, run `python3 -m unittest tests.test_contracts -v`, then implement the contracts and synthetic fixtures. Initialize the local Git baseline and ignore `.smart-assistant/`, `work/`, `.worktrees/`, bytecode, and private outputs.
- [x] **Review:** independently check schema completeness, path rules, terminal states, and all later package interface types.
- [x] **Feedback:** resolve findings and record dispositions in `docs/evidence/p00/feedback.md`.
- [x] **Test:** rerun `python3 -m unittest tests.test_contracts -v` against the final candidate; record output and hashes. All valid fixtures pass; invalid schema versions, malformed IDs, invalid enums, and missing required fields fail precisely.
- [x] **Repeat and integrate:** refresh review after changes, commit accepted contracts and planning baseline, record the commit in the handoff, and release Wave 1.

Example assertion to pin compatibility:

```python
result = validate_record("RequestEnvelope", {"schema_version": 99})
self.assertFalse(result.passed)
self.assertIn("unsupported_schema", [error.code for error in result.errors])
```

## P01 Task state and scoped context

**Files:** Create `smart_assistant/state.py`, `smart_assistant/context.py`, `tests/test_state.py`, `tests/test_context.py`, and `docs/tasks/p01/design.md`.

**Consumes:** P00 TaskRecord, RequestEnvelope, Criterion, ContextBundle, Limits, and GateResult.

**Produces:** `TaskStore(root: Path, completion_check: Callable[[TaskRecord], GateResult] | None = None)` with `create(record: TaskRecord) -> TaskRecord`, `read(task_id: str) -> TaskRecord`, and `update(record: TaskRecord, expected_revision: int) -> TaskRecord`; `load_context(root: Path, project_id: str, role_id: str | None = None) -> ContextBundle`. Create stores revision 1; every accepted update increments revision once. A completion transition requires the injected checker to pass; absent checker means completion is denied. Context reads use local scoped JSON, return empty optional preferences when absent, and distinguish malformed context from missing optional context.

- [x] **Design:** specify lock locations, atomic file replacement, transition validation, and project/role context selection.
- [x] **Implement:** write failing `test_stale_revision_preserves_newer_record`, `test_completion_without_checker_is_denied`, `test_interrupted_record_can_resume`, `test_terminal_record_cannot_reopen`, and context scope/malformed-input tests; run `python3 -m unittest tests.test_state tests.test_context -v`, then implement.
- [x] **Review:** independently inspect lost-update behavior, lock cleanup, filesystem escape, and whether role context leaks unrelated project facts.
- [x] **Feedback:** record and fix findings in `docs/evidence/p01/feedback.md`.
- [x] **Test:** rerun the targeted command using temporary state roots; simulate two writers from revision 1 and interruption before atomic replacement. Confirm the older writer fails and the last valid record remains readable.
- [x] **Repeat and integrate:** obtain final-candidate review and handoff; integrator reruns tests after applying the package.

Example assertion:

```python
with self.assertRaises(RevisionConflict):
    store.update(stale_record, expected_revision=1)
self.assertEqual(store.read(task_id).revision, 2)
```

P00 defines the common `RevisionConflict` and validation error types used by packages.

## P02 Catalog and deployment transactions

**Files:** Create `smart_assistant/catalog.py`, `smart_assistant/lifecycle.py`, `tests/test_catalog.py`, `tests/test_lifecycle.py`, and `docs/tasks/p02/design.md`. Supply an empty catalog fixture; the integrator owns `capabilities/catalog.json`.

**Consumes:** P00 CapabilityRecord, CapabilityCatalog, GateResult, and revision errors.

**Produces:** `load_catalog(root: Path) -> CapabilityCatalog`, `eligible_capabilities(catalog: CapabilityCatalog, available_tools: set[str], project_root: Path) -> list[CapabilityRecord]`, `validate_catalog(catalog: CapabilityCatalog, project_root: Path) -> GateResult`, and `deployment_manifest(root: Path) -> DeploymentManifest`; `DeploymentStore(project_root: Path)` with `prepare(candidate: CapabilityRecord, expected_revision: int) -> str`, `finalize(operation_id: str, discovery_receipt: NativeProbeReceipt) -> CapabilityCatalog`, `restore(operation_id: str) -> CapabilityCatalog`, `prepare_disable(capability_id: str, expected_revision: int) -> str`, and `finalize_disable(operation_id: str, absence_receipt: NativeProbeReceipt) -> CapabilityCatalog`. Finalize requires a matching manifest and a passed activation probe. Disable uses a separate absence receipt. Deployment operations use an exclusive catalog lock, journal, compare-and-swap revision, and recoverable file backups. Restore before finalization restores the old catalog revision and deployed files; finalized activation and disabling each create a new catalog revision. Eligibility rehashes the full deployed asset tree and excludes pending deployments.

- [x] **Design:** freeze catalog consistency rules and deployment journal states; define a recovery result for every interrupted stage.
- [x] **Implement:** write failing tests for duplicate IDs, missing tools, disabled records, active records without discovery proof, path/symlink escape, concurrent catalog writes, interrupted replacement, manifest drift in a supporting resource, mismatched probe identity, and failed disable absence evidence. Run `python3 -m unittest tests.test_catalog tests.test_lifecycle -v`, then implement.
- [x] **Review:** independently inspect catalog/native asset drift, staged assets leaking into discovery, atomicity claims, and restoration after partial filesystem changes.
- [x] **Feedback:** fix findings and record them in `docs/evidence/p02/feedback.md`.
- [x] **Test:** rerun the targeted suite; verify a failed probe restores the old deployment and an interrupted journal prevents further activation until reconciliation.
- [x] **Repeat and integrate:** review final candidate, deliver the API and fixtures, and integrate without activating real agents yet.

Example assertion:

```python
self.assertNotIn(disabled.id, [record.id for record in eligible_capabilities(catalog, tools, project_root)])
self.assertFalse(validate_catalog(active_without_probe, project_root).passed)
```

## P03 Preflight and completion evidence

**Files:** Create `smart_assistant/preflight.py`, `smart_assistant/quality.py`, `tests/test_preflight.py`, `tests/test_quality.py`, and `docs/tasks/p03/design.md`.

**Consumes:** P00 Criterion, Artifact, CandidateSnapshot, AcceptanceSnapshot, CycleEvidence, TaskRecord, RequestedAction, AuthorizationScope, PreflightResult, and GateResult.

**Produces:** `preflight(required_tools: set[str], available_tools: set[str], requested_actions: list[RequestedAction], authorization: list[AuthorizationScope]) -> PreflightResult`; `snapshot(artifact_root: Path, artifacts: list[Artifact]) -> CandidateSnapshot`; `acceptance_snapshot(criteria: list[Criterion], design_path: Path) -> AcceptanceSnapshot`; `completion_gate(task: TaskRecord) -> GateResult`. Snapshot hashes current files, not caller-supplied hashes. Receipts are evidence, not candidate artifacts. The gate checks current artifact hashes and acceptance fingerprint, distinct reviewer/implementer references, finding dispositions, criterion coverage, passing checks, and existing local evidence references. It cannot certify reviewer independence or truthfulness cryptographically; that is an orchestration responsibility.

- [x] **Design:** define authorization matching as exact declared action scope and destination; unrecognized or absent authorization yields a pending action rather than inferred approval. Define error codes for missing review, stale evidence, unresolved feedback, failing checks, and missing criterion coverage.
- [x] **Implement:** write failing tests for stale artifact hashes, changed criterion descriptions or verification methods under unchanged IDs, changed design bytes, same reviewer/implementer reference, unresolved findings, missing evidence files, failed checks, missing tools, and a role listing tools without user authorization. Run `python3 -m unittest tests.test_preflight tests.test_quality -v`, then implement.
- [x] **Review:** independently inspect path validation, stale evidence acceptance, fake completeness through empty criteria, and permissions wording.
- [x] **Feedback:** record corrections in `docs/evidence/p03/feedback.md`.
- [x] **Test:** rerun the targeted command. Mutate a reviewed fixture and assert that completion fails until review and checks bind to the new candidate. An empty criteria list is invalid for completion.
- [x] **Repeat and integrate:** review final candidate and supply the checker for P04's TaskStore composition.

Example assertion:

```python
artifact_path.write_text("changed after review", encoding="utf-8")
result = completion_gate(task)
self.assertFalse(result.passed)
self.assertIn("stale_candidate", [error.code for error in result.errors])
```

## P04 Coordinator and command interface

**Files:** Create `smart_assistant/cli.py`, `smart_assistant/__main__.py`, `.agents/skills/request-coordination/SKILL.md`, `tests/test_cli.py`, `examples/scenarios/coordinator/`, and `docs/tasks/p04/design.md`. Request any root AGENTS.md changes from the integrator.

**Consumes:** P01 TaskStore/context, P02 catalog eligibility, and P03 preflight/completion_gate. Use the exact APIs above; routing remains a Codex decision.

**Produces:** `main(argv: list[str] | None = None) -> int`. Commands: `task create --record FILE --state-dir DIR`; `task show ID --state-dir DIR`; `task update --record FILE --expected-revision N --state-dir DIR`; `task complete ID --expected-revision N --state-dir DIR`; `catalog validate --project-root DIR`; `catalog eligible --project-root DIR --tools FILE`; `preflight --request FILE`. Preflight input is a serialized P00 PreflightRequest; tools input is a JSON list of observed tool names. Preflight returns its PreflightResult in data and exits 4 when ready=false. Responses use JSON `{ok, data, errors}`; success exits 0, invalid input 2, revision conflict 3, unmet completion or preflight gate 4. No raw exception traceback or credential content is written to normal output.

- [x] **Design:** define command inputs and JSON responses and describe how the skill records semantic routing decisions, authorization references, design, and resume information.
- [x] **Implement:** write failing subprocess tests for every command, stale update, missing tool, and denied completion; run `python3 -m unittest tests.test_cli -v`, then implement CLI composition and coordinator skill.
- [x] **Review:** independently assess unnecessary clarification, unsupported success claims, and whether the skill actually checks the catalog before dispatch.
- [x] **Feedback:** record findings and adjust the skill or command interface in `docs/evidence/p04/feedback.md`.
- [ ] **Test:** rerun CLI tests and manually evaluate ordinary, ambiguous, unrelated, interrupted, and missing-tool requests in the installed Codex client. Save sanitized observations tied to the deployed skill fingerprint.
- [ ] **Repeat and integrate:** obtain final review and give one complete local request handoff. Structural CLI tests alone do not complete semantic routing acceptance.

Example assertion:

```python
result = run_cli("task", "complete", task_id, "--expected-revision", "1", "--state-dir", temp_dir)
self.assertEqual(result.returncode, 4)
self.assertFalse(json.loads(result.stdout)["ok"])
```

## P05 Agent lifecycle

**Files:** Create `smart_assistant/agent_lifecycle.py`, `.agents/skills/manage-agent/SKILL.md`, `examples/agents/`, `tests/test_agent_lifecycle.py`, and `docs/tasks/p05/design.md`. No concurrent edits to active `.codex/agents/` or the canonical catalog.

**Consumes:** P02 DeploymentStore and P03 snapshot/gate evidence contracts.

**Produces:** `validate_agent_definition(path: Path) -> GateResult` and `stage_agent(project_root: Path, definition_path: Path, record: CapabilityRecord) -> CapabilityRecord`. Require the installed native schema's name, description, and developer_instructions; include the project work-cycle rule in each deployed definition. Validate configured model and reasoning values against an observed available catalog before enabling an override. Leave model settings inherited unless a deliberate supported selection is needed.

- [x] **Design:** document chat-driven creation, narrow responsibilities, activation probes, disable, version replacement, and rollback. Agent setup grants no new permissions.
- [x] **Implement:** write failing tests for missing fields, malformed TOML, duplicate identity, unsafe deployment paths, and missing work-cycle guidance; run `python3 -m unittest tests.test_agent_lifecycle -v`, then implement staging and the management skill.
- [x] **Review:** independently inspect role overlap, lifecycle API use, permissions, and configuration assumptions against the installed client.
- [x] **Feedback:** resolve findings in `docs/evidence/p05/feedback.md`.
- [ ] **Test:** rerun unit checks, then add a synthetic researcher in an isolated native probe session. Evaluate ordinary, out-of-scope, and missing-tool requests; disable it and observe its absence in fresh discovery; reactivate the previous verified version and repeat the probe.
- [ ] **Repeat and integrate:** refresh review/evidence after changes. The integrator serializes real deployment and records the active version only after native evidence passes.

Example assertion:

```python
result = validate_agent_definition(agent_missing_instructions)
self.assertFalse(result.passed)
self.assertIn("missing_field", [error.code for error in result.errors])
```

## P06 Skill lifecycle

**Files:** Create `smart_assistant/skill_lifecycle.py`, `.agents/skills/manage-skill/SKILL.md`, `examples/skills/`, `tests/test_skill_lifecycle.py`, and `docs/tasks/p06/design.md`.

**Consumes:** P02 DeploymentStore and P03 evidence contracts.

**Produces:** `validate_skill_definition(path: Path) -> GateResult` and `stage_skill(project_root: Path, definition_path: Path, record: CapabilityRecord) -> CapabilityRecord`. Support the standard SKILL.md required name and description metadata; do not invent a full YAML parser with an undocumented syntax subset. Either use host validation for metadata outside the supported minimal format or explicitly return a precise unsupported-metadata result. Standard-library generation uses simple unambiguous quoted or plain scalar name and description. Optional resources must remain inside the staged skill directory.

- [x] **Design:** define scope, triggering, output contract, dependencies, validation cases, disable, and rollback. Build a skill for a requested repeatable workflow rather than automatically creating one for every prompt.
- [x] **Implement:** write failing tests for required metadata, resource escape, overlapping identities, non-skill catalog kind (an agent record must be rejected), and missing verification instructions; run `python3 -m unittest tests.test_skill_lifecycle -v`, then implement staging and management guidance.
- [x] **Review:** independently check trigger boundaries, metadata handling, resource references, and that a disabled skill cannot still be discovered under the deployment strategy.
- [x] **Feedback:** resolve findings in `docs/evidence/p06/feedback.md`.
- [ ] **Test:** rerun unit checks and native direct, indirect, unrelated, incomplete-input, and failed-tool cases. Disable and rollback the synthetic skill in fresh discovery sessions; record each observed result.
- [ ] **Repeat and integrate:** re-review changed candidate and hand off validated assets. The integrator performs serialized activation and catalog changes.

Example assertion:

```python
result = validate_skill_definition(skill_with_escaped_resource)
self.assertFalse(result.passed)
self.assertIn("unsafe_path", [error.code for error in result.errors])
```

## P07 Reference writing and verification workflows

**Files:** Create `.agents/skills/draft-document/SKILL.md`, `.agents/skills/verify-completion/SKILL.md`, `.codex/agents/writer.toml`, `.codex/agents/reviewer.toml`, `examples/scenarios/writing/`, `examples/scenarios/verification/`, and `docs/tasks/p07/design.md`. Native deployment is serialized by the integrator after asset review.

**Consumes:** P04 coordinator and CLI plus v1 assignments, criteria, candidate snapshots, and receipts. Both role definitions include the project work-cycle rule.

**Produces:** a user-supplied-notes-to-report workflow with sections Summary, Decisions, Action items, and Open questions; an independent verification workflow that checks source fidelity, required sections, owner/date claims, and completion evidence.

- [x] **Design:** define source-to-output criteria and expected behavior when an owner or date is absent from the supplied notes; do not invent either.
- [x] **Implement:** create a synthetic source fixture, a draft intentionally missing Action items, and an example with unknown dates. Then author the skills, roles, and expected evidence.
- [x] **Review:** independently review activation scope, source grounding, readable output, and whether the reviewer finds the missing section.
- [x] **Feedback:** repair the missing section and resolve all observed findings in `docs/evidence/p07/feedback.md`.
- [x] **Test:** invoke both roles/skills in Codex against the fixtures. Run `python3 -m unittest discover -s tests -v`; additionally record native observations that all sections exist, unknown dates remain unspecified, and the gate rejects the intentionally incomplete draft.
- [x] **Repeat and integrate:** review the final artifact and deployed asset fingerprints; include the successful end-to-end local report and evidence in the handoff.

Functional evidence: P07 acceptance (local historical archive: `../../evidence/p07/acceptance.md`) preserves exact source/native/session/lifecycle/report/gate identities and separately labelled hypothetical helper fixtures. Final Repeat/integrate closes after independent delivery review and local publication.

Observed assertion: the first draft fails criterion `report_action_items`; the corrected draft satisfies it; unsupported owner/date claims cause findings rather than silently passing. This semantic check is a native evaluation, not a brittle exact-string unit test.

P07 delivery completed after independent correction review and actual local publication: publication proof (local historical archive: `../../evidence/p07/publication.json`), final review (local historical archive: `../../evidence/p07/delivery-review-fixed.md`). P08 bounded delegation is accepted in its local reference scope; P09 selected M1/M2 integrated acceptance passed all12 actual task criteria and 323 tests on macOS/Linux after independent review; see P09 acceptance (local historical archive: `../../evidence/p09/acceptance.md`).

## P08 Bounded delegation

**Files:** Create `.agents/skills/delegate-work/SKILL.md`, `.codex/agents/engineering-lead.toml`, `tests/test_handoff.py`, `examples/scenarios/delegation/`, and `docs/tasks/p08/design.md`.

**Consumes:** accepted coordinator, lifecycle, writing, and quality components plus TaskAssignment/Handoff.

**Produces:** `validate_handoff(assignment: TaskAssignment, handoff: Handoff, artifact_root: Path) -> GateResult` in `smart_assistant/contracts.py` through an integrator-owned contract change. The integration owner lands this small shared change before the package branches. Validate task identity, assignment revision, allowed output paths, role identity, artifact existence, criterion IDs, and blockers. Add delegation skill rules for at most two concurrent specialists, clear file ownership, scoped context, independent review, and integrated verification.

- [x] **Design:** divide a synthetic request into two independent tasks and define their owned paths and parent criteria; treat dependency chains as sequential. Plan reviewer scheduling within four available slots.
- [x] **Implement:** write failing tests for stale revisions, wrong role, output outside ownership, and blocked child handoffs; run `python3 -m unittest tests.test_handoff -v`, then add contract validation and delegation assets.
- [x] **Review:** independently inspect shared-state ownership, failure propagation, cancellation, and whether review-only tasks trigger recursive reviewers.
- [x] **Feedback:** resolve findings in `docs/evidence/p08/feedback.md`.
- [x] **Test:** rerun handoff checks; execute native two-specialist delegation and one blocked-child scenario. Record status, context provided, received handoffs, child evidence, and parent review/tests. Confirm the parent remains incomplete when a required child is blocked.
- [x] **Repeat and integrate:** re-review changes and verify combined artifacts. Capture a valid model/effort configuration if available without requiring a specific model or claiming automatic hard cost routing.

Example assertion:

```python
result = validate_handoff(assignment_revision_2, handoff_revision_1, artifact_root)
self.assertFalse(result.passed)
self.assertIn("stale_assignment", [error.code for error in result.errors])
```

P08 handoff validation receives the trusted artifact root from the parent task; test containment and artifact existence from a different current working directory.

P08 scoped acceptance: eight-criterion completion (local historical archive: `../../evidence/p08/acceptance.md`), current independent review (local historical archive: `../../evidence/p08/final-review.md`), local publication (local historical archive: `../../evidence/p08/publication.json`). Native source timeouts were preserved; the current parent received authenticated persisted handoffs and fresh review/checks. P09 selected integrated acceptance is now complete; broader capability coverage remains partial/future as mapped in coverage (local historical archive: `../../evidence/p09/coverage.md`).

## P09 Integrated acceptance

**Files:** Create `tests/test_acceptance.py`, `docs/evidence/p09/acceptance.md`, and `docs/tasks/p09/design.md`. Update README.md and backlog only through the integrator.

**Consumes:** all accepted packages and their candidate-bound review/test evidence.

**Produces:** the integrated M1/M2 acceptance report, capability coverage, limitations, and any unresolved follow-up tasks. Native client checks remain observed evaluations; automated helpers are tested separately.

- [x] **Design:** map every selected first-release criterion to a functional test or a native observed scenario; preserve original IDs and distinguish partial coverage.
- [x] **Implement:** add integrated regression tests for interrupted-record resume, catalog exclusion, mismatched deployment evidence, stale completed artifacts, and denied completion. Record existing guards that already pass without inventing a failing baseline; use meaningful failing tests for changed helper/bootstrap behavior. Implement corrections in the owning package with a new cycle rather than silently changing shared contracts.
- [x] **Review:** use a fresh independent reviewer for the combined candidate, including source fidelity, role/skill discovery, disable/rollback, permissions, and task recovery.
- [x] **Feedback:** resolve findings or leave the relevant capability incomplete with a precise limitation. Record final dispositions in the acceptance report.
- [x] **Test:** run and independently audit native request, clarification, missing-tool, add-agent/add-skill, disable/new-version known-prior renewal and delegation scenarios using their prospectively reviewed exact source copies; preserve each original byte identity, failed caller and finite scope. After final combined review, verify unchanged current source/proof bindings and run the full323-test suite on macOS and Linux. Historical pre-bootstrap source observations retain their original identity; no new native model run after these final suites is claimed. Review and checks bind to their exact candidate snapshots.
- [x] **Repeat and close:** repeat corrections, review, and fresh tests until criteria pass. Update only proven capability statuses and preserve all review and check evidence before cleanup.

Example integrated assertion: changing a report after a successful review invalidates completion; repairing and rereviewing it restores eligibility only after final checks pass. An already completed record stays terminal, so a changed deliverable requires a new follow-up task or corrected execution evidence before the original completion, not silently reopening it.

## Required handoff and evidence

Each package handoff includes package ID, baseline, design reference, owned files, candidate identity, acceptance coverage, independent review findings, every feedback disposition, final checks and output references, and limitations. Store sanitized development evidence under `docs/evidence/<package>/`; keep user/private execution evidence under ignored runtime state.

Review and test receipts bind to a product-file snapshot, not to their own receipt files. Git commits can include the receipts afterward. The integrator confirms the product snapshot is unchanged at acceptance and records the final commit separately. Rehashing product files avoids a commit-hash cycle caused by committing the evidence itself.

Instructions establish the project's required work cycle. Deterministic helpers reject structurally incomplete state when invoked. Independent orchestration checks the substance of reviews and testing; no prose policy or editable evidence file provides a tamper-proof guarantee.

## Execution handoff

Review this plan and the spec before product implementation. Preserve the user's selected parallel method. After review, establish P00's baseline, freeze its contracts, and dispatch Wave 1 with explicit worktree paths and ownership. Later recurring and external-action milestones require their own focused designs and implementation packages.

P09 completed saved task p09-implementation revision12, all12 current criteria PASS; independently reviewed128-file candidate55fff53…, final323 tests PASS on macOS3.14.7 and Linux3.11.17. Genuine native macOS source/activation/disable/new2 known-prior renewal observations are finite and independently audited; timeouts, failed callers and opaque SDK limits remain preserved. See acceptance (local historical archive: `../../evidence/p09/acceptance.md`), final review (local historical archive: `../../evidence/p09/final-review.md`), local publication (local historical archive: `../../evidence/p09/publication.json`).
