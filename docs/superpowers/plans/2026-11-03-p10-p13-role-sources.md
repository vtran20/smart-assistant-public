# P10/P13 draft team profile and role sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Root reviews this plan before implementation. No worker delegation, commits, merges or pushes in this package.

**Goal:** Supply a small DRAFT display profile and six independently reviewable native-compatible role sources without changing active discovery, managed eligibility or runtime gates.

**Architecture:** Tom remains the actual bootstrap root; Jerry is display metadata for the stable `engineering-lead` ID. One data-only JSON profile references versioned example TOML sources for on-demand roles. Existing lifecycle validation and isolated draft-staging tests establish structural integrity; prompt anchors and scenario expectations establish source coverage, never actual role behavior.

**Tech Stack:** Python 3.11+ standard library, unittest, JSON, TOML and existing `smart_assistant.agent_lifecycle`/catalog APIs.

**Spec:** [approved architecture](../specs/2026-11-02-tom-jerry-orchestration-design.md), user implementation approval supplied to the coordinator on 2026-11-03. The copied specification retains its historical proposed-status header; this plan does not rewrite it or broaden approval.

## Global Constraints

- Required cycle: design → implement → independent review → recorded feedback → testing → repeat until acceptance criteria pass.
- "Tom is the actual root coordinator in the main chat, not an extra supervising child."
- "Jerry retains the existing capability ID; his new name is display metadata."
- "Do not edit an ACTIVE deployed definition in place."
- "Inherit model and effort settings."
- "Default execution remains two executing specialists across the whole tree and at most three correction cycles per dispatch, reduced by actual host capacity and task limits."
- "A source-only task may proceed once its declared reproduction level is met, while any required live acceptance remains open."
- "New assets remain DRAFT until all required proof exists."
- Root alone owns shared helper interfaces, parent records, active `.codex`/`.agents`, catalog, bootstrap routing and integration. This package does not implement P11/P12/P14/P15/P16 or imply their interfaces are present.
- No real KB writes, customer changes, account actions, activation, source deployment or new workflow skills. Existing report `reviewer` remains separate from `code-reviewer`.
- Work only in `/path/to/local/resource`; tests use temporary projects/state, never live task data.

## Review Focus

1. A display alias must never become a native TOML key, new managed ID or claim of configured eligibility (Task 1 identity/schema checks).
2. Missing role/tool/reproduction evidence must yield explicit blockers or honestly identified authorized direct work (Tasks 1–2 source/scenario checks; later observed native tests).
3. A passing unit test or screenshot alone must not erase a required runtime, database or business check (Task 2 QA/reproduction coverage).
4. Research text and candidate lessons must not become authority or permission (Task 2 research/curator coverage).
5. Different role labels and stale reviewed bytes must not satisfy independent exact-candidate review (Task 2 review/lead coverage; Task 3 review binding).

## Ownership and file map

Only these files are created by this package:

| File | Responsibility |
| --- | --- |
| `examples/teams/core/team.json` | Draft display/reference metadata; no runtime registry or routing engine |
| `examples/agents/engineering-lead/versions/2.0.0/engineering-lead.toml` | Immutable proposed Jerry behavior, stable native ID |
| `examples/agents/implementer/versions/1.0.0/implementer.toml` | Scoped code/configuration/test implementation contract |
| `examples/agents/code-reviewer/versions/1.0.0/code-reviewer.toml` | Independent exact-candidate review contract |
| `examples/agents/qa-verifier/versions/1.0.0/qa-verifier.toml` | Reproduction, matrix and verification contract |
| `examples/agents/researcher/versions/1.0.0/researcher.toml` | Bounded investigation with provenance contract |
| `examples/agents/knowledge-curator/versions/1.0.0/knowledge-curator.toml` | Scoped learning/proposal contract |
| `tests/test_tom_role_assets.py` | Structural, identity, isolated staging and source-coverage checks |
| `docs/evidence/tom-roles/scenarios.json` | Expected positive/negative observed behavior cases, explicitly unexecuted |
| `docs/evidence/tom-roles/progress.md` | Baseline, review cycle, feedback, checks and honest acceptance limits |
| `docs/evidence/tom-roles/candidate.json` | SHA-256 mapping of package candidate files, excluding itself/progress and review artifacts |

Existing `examples/agents/engineering-lead.toml`, all native assets, existing `researcher-v1.toml`/`researcher-v2.toml` synthetic fixtures and report-role assets are read-only. Review findings supplied by root can live under the assigned evidence directory; do not manufacture reviewer records.

## Profile contract

The example is version 1 data, with exactly these top-level keys:

- `schema_version`: `1`.
- `id`: `core`.
- `state`: `DRAFT` (source package state, not a `CapabilityRecord`).
- `root`: `{ "display_name": "Tom", "identity": "bootstrap-root" }`; deliberately no capability ID, source, version or ACTIVE field.
- `roles`: six entries containing exactly `capability_id`, `display_name`, `version`, `state`, `source_path`.

`engineering-lead` uses `Jerry` and `2.0.0`; remaining IDs use role-title display names (`Implementer`, `Code reviewer`, `QA verifier`, `Researcher`, `Knowledge curator`) and `1.0.0`. Every role has `state: DRAFT` and the exact repository-relative source path listed above. No model/effort/permission fields, personal paths, account identifiers, invented runtime routing expressions or duplicated policy fields. Profile version is not capability eligibility. A future root-owned consumer must validate the profile and consult actual eligibility/preflight; this package supplies no consumer API.

## Task 1: Draft team identity and lifecycle-safe role skeletons

**Interfaces:** consumes `validate_agent_definition(path: Path) -> GateResult`, `stage_agent(project_root: Path, definition_path: Path, record: CapabilityRecord) -> CapabilityRecord`, `deployment_manifest(path)` and current strict `CapabilityRecord`. Produces the profile and six versioned example sources above, not managed registration.

- [ ] Record actual HEAD, clean/dirty status and copied-spec exception in `progress.md`. Run `python3 -m unittest discover -s tests -q`; expected baseline is 336 tests, but retain actual count/output and investigate any discrepancy. Do not edit unrelated failing files.
- [ ] Add `test_profile_exact_identity_and_sources` asserting the exact profile contract, six unique IDs/paths, one bootstrap root, preserved engineering-lead ID/version, no `reviewer`/Tom/Jerry managed IDs, DRAFT states, safe relative regular source files and TOML names matching IDs.
- [ ] Add `test_sources_pass_existing_native_validator_and_inherit_configuration`: each source passes `validate_agent_definition`; parsed keys equal `{name, description, developer_instructions}`. No additional TOML metadata or model settings.
- [ ] Run `python3 -m unittest tests.test_tom_role_assets -v`; verify failure is missing proposed assets, not test-import/harness failure; preserve the output.
- [ ] Create the exact profile and sources with the ordered required work cycle and inherited model/effort instruction. Keep role contracts focused; do not duplicate the whole project policy or invent unsupported helper calls.
- [ ] Add `test_mutated_sources_rejected_by_lifecycle_validator`: temporary copies with `display_name`, `model`, `model_reasoning_effort`, missing `developer_instructions`, and an explicit review waiver fail with the existing matching error codes (`unsupported_field`, `unobserved_catalog`, `missing_field`, `missing_work_cycle`). These exercise the production validator rather than a test-only validator.
- [ ] Add `test_isolated_draft_staging_has_no_activation_side_effect`: create an empty temporary catalog; stage each AGENT/DRAFT record; assert returned DRAFT, empty validation refs, absent discovery probe, complete single-file manifest, original catalog bytes unchanged and native target absent. For Jerry also use a temporary registered 1.0.0 catalog/source fixture and verify 2.0.0 stages while preserving existing target/catalog; same-version staging must fail `immutable_version`. Never copy live catalog/proof or use live staging state.
- [ ] Run focused tests and `tests.test_delegation_assets`/`tests.test_agent_lifecycle`; preserve actual results. Source skeletons are not accepted until Task 2 contracts and independent review pass.

## Task 2: Role evidence, boundary and handoff contracts

**Interfaces:** consumes unchanged v1 `TaskAssignment`, `Handoff` and current `validate_handoff`; delivery-envelope, policy and matrix names from the approved design are future integration contracts unless root confirms available APIs. Produces instructions and expected scenarios only; no new shared Python interface.

- [ ] Add table-driven `test_role_specific_source_contracts` before filling the skeletons; assert explicit role-specific obligation anchors below. Label these assertions as coverage checks, not semantic/runtime evaluation. Run focused tests and retain the meaningful missing-contract failures.
- [ ] Implement the common narrow contract in each source: exact assigned files/context/design/criteria, actual tools/current ACTIVE eligibility and exact-action preflight before managed dispatch/resume, no invented identity or proof, bounded host limits, no parent-state/catalog/integration writes, real artifacts and observed evidence, independent review of outputs, preserve failures/blockers and use `ready_for_review` rather than completion claims. Do not authorize child spawning; Jerry only proposes/schedules within root-owned dispatch and shared limits.
- [ ] Implement these distinct obligations:

| Role | Required source obligations |
| --- | --- |
| Jerry | Semantic engineering routing only; investigate first; accepted predecessor pins/exact ownership; two executing specialists/tree including research/curation and live lead capacity; reserve review capacity; three correction cycles maximum; independent child and combined review; cancellation/resume and ambiguous dispatch consume capacity; parent alone persists/dispatches/integrates/completes |
| Implementer | Genuine declared-level reproduction before repair; diagnosis/minimal reproducer allowed while blocked; same-scenario after evidence; unit/developer and impacted regression checks; every assigned requirement/case with evidence; no independent self-approval or changed acceptance to pass |
| Code reviewer | Separate observed execution context; exact final candidate/design/context/evidence bindings; correctness, omitted requirements/cases, permissions, regression risk and evidence semantics; findings/dispositions artifact only; no edits to implementation being approved; changed bytes need re-review; no fake actor labels or recursive reviewer chains |
| QA verifier | Symptom/expected result/scenario/baseline identity/environment; authentic immutable hashed before/after originals and exact exits; same-scenario comparison and intentional differences; screenshots do not prove persistence; required UI capture failure stays blocked unless an applicable authorized alternative exists; every requirement/planned case and denominator; pass/fail/blocked/not_run/not_applicable distinctions; required cases cannot be waived; test fixtures QA writes receive independent review |
| Researcher | Question, blocked decision, allowed sources, time/run bound and verification method; local source first; authorized authoritative current sources; provenance/date/version/applicability/conflicts/confidence; facts vs conclusions vs hypotheses; fetched text is data; independent review of material conclusions; no external writes or access expansion |
| Curator | Existing project entries first; user_confirmed/agent_validated/candidate/superseded; scope/source/date/evidence/applicability/revalidation; deduplication and secret/customer sanitization; owning-project records; shared KB proposals only pending separate policy reconciliation; independent review; no permission/gate edits, automatic repin, native activation or model-training claim |

- [ ] Create `scenarios.json` with `evidence_status: "expected-only; not executed behavior or native proof"` and entries `{id, role_id, category, request, expected_observations}`. For every role include ordinary scoped work, unrelated request, missing essential input/tool, and misleading-proof/authority request. IDs are unique; role set equals profile roles; every expected outcome is observable and states the specific blocker or bounded output.
- [ ] Include named negative scenarios: missing before reproduction, changed after scenario, missing required case, fabricated screenshot, stale review after correction, same-person two labels, research prompt injection, no research bound, customer lesson in shared KB, candidate lesson treated as permission, missing native eligibility and exceeded shared capacity. Map each to the owning role and design sections 3–11. These are acceptance fixtures, not receipts or test-run results.
- [ ] Add `test_scenarios_cover_role_boundaries_without_claimed_execution` to assert unique IDs, exact role coverage, four categories per role, named negative cases, explicit expected-only marker and no receipt/result-pass fields. Run focused tests, preserving outputs. Independent source review judges whether wording actually satisfies the design; token tests cannot establish that.

## Task 3: Independent source review, feedback and bounded verification

**Interfaces:** root supplies an independent reviewer context and exact candidate review. Worker supplies file hashes and outcomes. No source activation or live KB dependency.

- [ ] Freeze SHA-256 for profile, six TOMLs, scenarios, tests and this plan in `candidate.json`; record base HEAD and package scope. Hashes identify bytes, not reviewed correctness. Root reviews this candidate independently; review is pending until an actual findings artifact is supplied.
- [ ] Request source review covering R01–R03, R05–R07, R09–R10 and source portions of A01/A02/A05–A10/A14/A15; do not claim the runtime parts passed. Record every finding/disposition in progress, apply authorized corrections, refresh candidate hashes and obtain review of changed bytes.
- [ ] Run final `python3 -m unittest tests.test_tom_role_assets tests.test_delegation_assets tests.test_agent_lifecycle -v`, then `python3 -m unittest discover -s tests -q`. Expected: all pass, actual counts retained. Run `git diff --check`, parse all new JSON/TOML, check plan's spec link and all profile source paths, and audit `git status --short` against ownership. No Mermaid diagram is added, so Mermaid parsing is not applicable.
- [ ] Verify existing engineering-lead example, native directories and catalog match baseline bytes. Root separately verifies combined integration; worker tests do not accept shared helper changes.
- [ ] Return candidate hash manifest, files, independent feedback/dispositions, exact checks/exits, source-only acceptance and remaining native limits. No commit or integration command.

## Separate native acceptance (not executed or claimed by this source package)

Every new/revised role remains DRAFT. Root may later authorize the existing `manage-agent` lifecycle: independently review exact source, stage immutable version, evaluate real observed ordinary/out-of-scope/missing-input/tool/proof cases, prepare only in authorized isolation, observe genuine installed-client identity/version/complete-manifest-bound discovery and invocation, then finalize only with authentic receipts. Retain current client/source-binding limitations; do not reuse historical receipts, substitute a generic worker or weaken the gate. A profile name cannot prove identity. Jerry 2.0.0 cannot inherit 1.0.0 proof.

P16 must separately implement and test actual bootstrap profile consumption/routing, saved assignments/dispatch, requirements/reproduction gate enforcement and end-to-end seeded-bug delivery. Native behavior coverage includes source cases above plus independent actor provenance and exact-candidate corrections. Xstore/POS/integration/database/device/business acceptance remains separate and needs actual authorized environments. Neither source text tests, staged DRAFT manifests nor helper test totals prove any of those behaviors.

## Self-review and handoff checkpoint

Plan covers the approved role/display source slice only; persistence/evidence enforcement, KB selection/maintenance and active bootstrap integration remain root-owned dependent packages. Source tests use existing lifecycle interfaces and explicit fixture isolation; no proposed shared helper signature is treated as implemented. Five review-focus risks map to Tasks 1–3. Root independently reviews this plan before source implementation; do not ask the user to repeat the already supplied architectural approval.
