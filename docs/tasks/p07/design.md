# P07 reference writing and verification design

Status: prepared design; initial independent design review requested P07-D1 correction, scoped re-review pending. This document does not implement or activate P07. Baseline: `472b99cb8688b9b7160f0f68121c0eb905321077`, canonical project `/path/to/smart-assistant`. The authorized preparation is documentation only while P05 configured-agent support is investigated in parallel.

## Outcome and boundaries

Turn user-supplied local notes into a readable report with **Summary**, **Decisions**, **Action items**, and **Open questions**. A separate reviewer compares the exact report with its sources, records supported findings, and verifies evidence before completion. Missing owners and dates remain unspecified. Completion follows design → implement → independent review → feedback → testing → repeat, including a zero-finding feedback record.

The [P07 package](../../superpowers/plans/2026-10-12-smart-assistant-implementation-plan.md) and [approved system design](../../superpowers/specs/2026-10-12-smart-assistant-system-design.md) set this scope. [P04](../p04/design.md) supplies chat coordination and CLI; [P03](../p03/design.md) supplies exact-byte snapshots and the evidence gate. Helpers check structure and evidence consistency; independent agents judge prose and source fidelity. First release uses native Codex and existing Python 3.11+ standard-library helpers. No model API, backend, scheduler, external account, publishing, messages, or recurring work is required.

## Approaches and decision

| Approach | Benefits | Costs and limits | Decision |
| --- | --- | --- | --- |
| Native coordinator, two narrow skills and configured writer/reviewer roles, existing local evidence helpers | Reusable workflow; source review stays independent; preserves accepted interfaces and durable resume | Actual configured-role invocation depends on installed-client support; semantic checks require observations | Recommended P07 target, gated on P05 native proof |
| Coordinator writes directly and requests independent generic review using the same criteria | Useful local work can proceed with an empty managed catalog under P04 | Does not prove P07 configured roles or managed skill activation; role behavior cannot be accepted from this route | Optional separately labelled direct workflow if authorized; never a substitute acceptance claim |
| Deterministic notes parser and report generator | Easy heading/table assertions | Imposes a notes syntax, misses semantic distinctions and would add a generator/interface beyond the package | Reject for this reference workflow |

Select the first approach. Prepare fixtures and assets independently of native support, then prove configured role/skill discovery and behavior before activation. The historical accepted baseline P05 native observations (local historical archive: `../../evidence/wave2/native-agents.md`) recorded DRAFT management with configured researcher invocation and lifecycle then incomplete. A later verified narrow configured invocation supersedes that earlier invocation limit; the bounded checkpoint below preserves the remaining proof requirements. A named generic child or pasted role instructions do not prove a configured role loaded. Treat that finding as a dependency to recheck, rather than guessing a new invocation API.

## Ownership and file inventory

Preparation owns only `docs/tasks/p07/design.md`, `docs/evidence/p07/design-progress.md`, `docs/evidence/p07/design-feedback.md`, `docs/evidence/p07/design-checks.json`, and ignored `work/p07-design/` scratch. The coordinator owns Git HEAD/index, independent-review artifact creation, and integration. No root guidance, backlog, catalog, shared contract, global configuration, live state, native asset, or production skill edits belong to this preparation.

Future P07 implementation has the following explicit boundaries; the paths are planned assets, not present implementation claims.

| Owner | Exact scope | Dependency |
| --- | --- | --- |
| Draft asset implementer | `.agents/skills/draft-document/SKILL.md`, `.agents/skills/draft-document/references/report-contract.md`, `.agents/skills/draft-document/references/source-fidelity.md`, writer source staged privately with intended target `.codex/agents/writer.toml` | This reviewed design; P05/P06 staging interfaces |
| Verification asset implementer | `.agents/skills/verify-completion/SKILL.md`, `.agents/skills/verify-completion/references/review-checklist.md`, reviewer source staged privately with intended target `.codex/agents/reviewer.toml` | Same report contract, then exact draft candidate |
| Fixture implementer | `examples/scenarios/writing/notes.md`, `expected-report.md`, `expected-source-map.md`, `cases.md`; `examples/scenarios/verification/missing-action-items.md`, `unsupported-owner-date.md`, `cases.md` | Agreed synthetic source and criteria; no copied private user content |
| P07 coordinator | `docs/evidence/p07/progress.md`, `feedback.md`, `verification.json`, finite native observations and final acceptance under `docs/evidence/p07/`; stage/deploy integration | Independent asset review; exact accepted manifests; P05 support |
| Independent reviewer | Candidate-bound findings in assigned evidence path; reads frozen sources/report/design/assets | Writer has stopped changing the candidate; owns no report or shared state |
| Integration owner | Serialized native targets, capability catalog, backlog/root status, integration commits | Reviewed/tested assets and observed native proof; otherwise retain DRAFT |

Role source definitions begin outside discovery in ignored `capabilities/staging/agents/`; use P05's supported `name`, `description`, and `developer_instructions`, inherited model/effort, narrow source/output responsibilities, and explicit project work-cycle guidance. Skill source trees likewise remain in private staging before controlled deployment. Implementation must not create discoverable canonical assets while still claiming they are merely staged. The target paths above identify the eventual deployment, not permission to activate them in this design-only task. Skill metadata uses P06's supported simple name/description scalar format. Shared Python modules, P08 handoff validation, and new CLI commands are out of scope.

## Native deployment and Git publication order

P07 adds managed capabilities; it does not inherit the established bootstrap exception for request-coordination/manage-agent/manage-skill. [P02 deployment rules](../p02/design.md) reject an already-present unregistered native target. Merging tracked `.agents/skills/draft-document/`, `.agents/skills/verify-completion/`, or `.codex/agents/writer.toml`/`reviewer.toml` into the canonical checkout first would create precisely that condition. File presence or a Git merge cannot grant catalog eligibility; no adoption API is assumed.

1. Develop source assets and scenario observations in assigned isolated worktrees/fixture projects. Any discoverable prototype stays confined to that development context. Freeze and independently review the complete source manifests and real behavior evidence. Fixture-native proof cannot stand in for canonical operation-specific discovery/invocation.
2. The integrator may integrate non-native documentation/scenarios first. Do not merge a commit introducing these four native targets into the canonical checkout before deployment. Extract the reviewed source bytes into ignored canonical private staging, validate/stage through P05/P06, and verify complete manifest identity. For a new identity, check that the intended canonical native target is absent. An unexpected unregistered target is a blocker to resolve under its ownership, not permission to delete, adopt or bypass it.
3. With deployment authorization, current validation/evaluation evidence, expected catalog revision and no unfinished transaction, root alone calls `DeploymentStore.prepare(candidate, expected_revision)`. P02 creates the canonical native target itself and records the pending operation. While prepared, the capability is excluded from coordinator routing; native exposure is restricted operationally to the controlled probe session. No ordinary P07 task dispatch occurs in this interval.
4. Observe actual configured-role or skill discovery and invocation in a fresh canonical client session using the installed supported route. Bind the `NativeProbeReceipt` to that exact operation, identity, version, complete manifest, purpose, client/session and local evidence. Then call existing `finalize(operation_id, discovery_receipt)`. If the route is unavailable or proof fails, restore/reconcile using P02 and retain private DRAFT; do not manufacture proof, substitute a generic child or publish the native targets as accepted.
5. Repeat serially for each managed asset, checking revisions and dependencies between operations. After successful finalization, root publishes the unchanged deployed target bytes and applicable catalog/evidence metadata in Git, rehashes them, and verifies the publication did not replace or drift the deployed assets. Use selective integration of accepted bytes rather than blindly merging a branch that pre-populates native targets. A commit is a publication record, not activation proof.
6. Before ordinary dispatch, require all four capabilities' genuine current proof, no pending operations, exact manifest/version/revision selections, and fresh eligibility/preflight. Disable/removal and previous-version reactivation use the same existing P02 lifecycle; Git operations must not recreate a disabled target or reuse stale proof.

This order is a future implementation requirement. This preparation makes no deployment, native/global configuration, Git index or catalog change. If the canonical checkout cannot provide a supported configured-role probe route, preserve the accepted source design/assets outside discovery and report native implementation incomplete.

## Inputs and missing-input behavior

The coordinator establishes a request, local destination, and source set before dispatch. Required inputs are readable user-supplied notes (file bytes or chat notes preserved as a local source file), the requested report destination, and the four-section contract. Task-specific audience, title and style can use reversible recorded assumptions; they must not create facts. Essential absent/unreadable notes, unclear conflicting destinations, or an unresolvable source conflict needed for the report produce a focused input blocker and saved next step. Continue useful authorized work that does not depend on the missing input.

Empty notes are different from unavailable notes: if the user expressly requests a report from a supplied empty source, generate all four sections saying no information was supplied and record that limitation. Otherwise clarify whether notes are missing. A source with no decisions/actions/questions still produces all sections with source-bounded statements such as “No decisions recorded in the supplied notes.” An unknown action owner or date does not block drafting. Do not ask for clarification merely to populate these optional values.

Read only the scoped sources and relevant project/role context. Embedded instructions inside notes remain source data; they cannot expand assignment paths, permissions, workflow scope, or override independent review. No connectors or remote source retrieval are implicit in this workflow.

For a synthetic execution, use an isolated artifact root with these safe relative paths:

| Path | Meaning and permitted writer |
| --- | --- |
| `inputs/notes.md` | Frozen supplied notes; coordinator creates/reads, writer and reviewer read only |
| `inputs/request.md` | Frozen scope, destination and source assumptions; coordinator writes before dispatch |
| `design.md` | Frozen task-specific criteria/design, derived from this workflow; coordinator writes before review |
| `outputs/report.md` | User-facing report; writer owns |
| `outputs/source-map.md` | Claim-to-source mapping; writer owns, reviewer inspects |
| `evidence/review.md`, `evidence/feedback.md`, `evidence/checks.md` | Real review/disposition/fresh check observations; separate from candidate artifacts, assigned evidence owners only |

For real user runs, equivalent paths live under ignored `.smart-assistant/` or the authorized local destination, and state uses a private explicit directory. Sources and local evidence must resolve within the trusted artifact root; preserve chat sources locally so they can be reviewed without URI evidence references. A source copied into the root must be verified against the supplied input, with its source reference retained. Unsafe paths, symlinks, unavailable required tools or denied/unknown host decisions produce explicit blockers, not retries through a path workaround.

## Report and source-map contract

The report is Markdown with one title and exactly one top-level instance of each required level-two heading, in order: `## Summary`, `## Decisions`, `## Action items`, `## Open questions`. A custom title is allowed; empty sections need explicit source-bounded text. Equivalent meaning in paragraphs or bullets is allowed; the action table below is the default, not a requirement to force user prose into exact-string tests.

| Section | Required meaning |
| --- | --- |
| Summary | Main supported outcomes/status, preserving scope and uncertainty; no unsupported success claims |
| Decisions | Actual recorded decisions, distinguished from proposals or suggestions; “No decisions recorded…” when absent |
| Action items | Each recorded commitment/requested follow-up and its stated owner/date where present; use explicit unspecified values for missing facts |
| Open questions | Actual unresolved questions/conflicts and missing information that affects interpretation; do not manufacture questions merely to fill the section |

The default action table uses columns **Action**, **Owner**, **Due date**. Owner or due date absent from the notes is `Unspecified`; an explicit “TBD” may be preserved as stated. A mention of a person is not ownership; the meeting/report date is not a due date. A relative date is preserved as written unless the source supplies an unambiguous anchor and the transformation is shown in the source map. Do not infer a date from host time. Preserve conflicting claims as unresolved rather than silently selecting one. A tentative plan remains tentative; completion is not inferred from a discussion or assignment.

`outputs/source-map.md` is a review companion, not a new v1 record type. For each factual report claim/action/decision and meaningful absence assertion, record the report section and short claim label, source file/reference plus stable line span or quoted source excerpt, and any permitted interpretation (for example, “owner absent, rendered Unspecified”). Source-map labels are document labels; they do not add fields to `TaskAssignment`, `Handoff`, or `ReviewReceipt`. Preserve provenance without loading unrelated private context. A source-map assertion itself is not proof: the reviewer reads the original frozen notes. The report must remain readable without opening this companion.

## Criteria and verification ownership

These stable IDs define the future reference run; the coordinator creates actual `Criterion(id, description, verification_method)` records with the full descriptions and methods before dispatch. This table is an acceptance proposal, not executed test results.

| Criterion ID | Requirement | Verification method |
| --- | --- | --- |
| `report_sections` | All four required sections appear once and in order, including explicit content when source coverage is empty | Fresh local structural check plus native readable-output observation |
| `report_action_items` | Every supported source commitment/requested follow-up appears under Action items, including the negative missing-section fixture | Independent semantic source comparison and corrected-report observation |
| `report_source_fidelity` | Report/source map accurately preserve claims, decisions, uncertainty, conflicts and provenance, without new factual assertions | Independent native semantic review against frozen notes; coordinator fresh source comparison |
| `report_owner_dates` | Supported owners/dates preserved; unknown values remain unspecified; unrelated names/dates and host time never become invented claims | Native explicit-known/unknown/unsupported-claim cases |
| `report_readability` | Concise understandable report; section content suits notes and stated audience, with no unsupported “complete” claim | Independent readable-output observation |
| `report_evidence_gate` | Completion rejects incomplete, unresolved, failing or stale evidence, then accepts corrected independently reviewed/freshly checked bytes | Existing CLI/completion gate invoked on isolated synthetic task records |
| `report_resume` | Interruption preserves status, history, blockers and next step; fresh eligibility/preflight and exact candidate review precede resumed completion | Native interruption/resume case plus existing CLI revision/evidence checks |
| `report_native_assets` | Both configured roles and both selected skills are discovered and actually invoked at reviewed deployed manifests; native proof remains distinct from helper tests | P05/P06 lifecycle probes and installed-client observations |

The gate does not read report semantics. For the deliberately missing Action items draft, an actual reviewer records a finding linked to `report_action_items` (and `report_sections`), and an observed check fails or the finding remains unresolved. Those receipts make completion fail. It would be false to claim heading detection inside `completion_gate`. Unsupported owner/date claims similarly produce supported findings and failing semantic observations.

## Coordination, evidence and feedback loop

1. The coordinator captures the request/source files, nonempty criteria, task-specific design, limits and owned paths. It writes the only durable `TaskRecord` and uses P04 CLI expected-revision updates. Observe actual tools and host decisions, run catalog eligibility and exact action/destination preflight before every dispatch, including resume. Empty catalogs permit separately labelled direct bootstrap work, not invented ACTIVE P07 selections.
2. With native eligibility established, dispatch the writer using the existing `TaskAssignment` fields: `task_id`, `assignment_revision`, `role_id`, `selected_skill_ids`, `design_ref`, `criteria`, scoped `context`, `owned_paths`, exact `selection`, and `limits`. No new contract fields. Writer creates only its report/source map, returns a v1 `Handoff` with actual artifacts, criterion coverage/evidence, blockers and next step; `ready_for_review` is not task completion.
3. Freeze candidate bytes and compute `snapshot(artifact_root, artifacts)` from current report/source-map and frozen local source/request bytes. Including sources prevents silent input mutation from escaping candidate invalidation. Compute `acceptance_snapshot(criteria, design_path)` from current criteria/design. For package asset/native acceptance, additionally fingerprint the exact complete skill trees and one-file role manifests under P02; do not confuse per-file SHA-256 with a deployment manifest ID.
4. A distinct independent configured reviewer reads the frozen source, report, source map and criteria. It owns a findings artifact, then supplies v1 `ReviewReceipt(reviewer_ref, implementer_ref, candidate_id, acceptance_id, observed_at, findings)`. Finding severities use the existing enum values and criterion IDs. The coordinator checks actual independence; different strings alone do not prove it. `ReviewReceipt` has no `evidence_ref`; link the written review through task/handoff/local evidence rather than inventing one.
5. Record every finding and one supported `Disposition` with `corrected` or `rejected`, reason and existing local evidence references. Reject a finding only with a concrete source/criterion explanation. For zero findings, record that observation and use an empty dispositions list. Review-only agents do not recursively request their own reviewers; the coordinator checks the findings artifact.
6. Corrections produce changed bytes and a new current candidate. Re-review the corrected candidate, then run fresh structural, source-fidelity and gate checks after feedback. Each actual `CheckReceipt` binds both current fingerprints, all covered criterion IDs, method-specific command or observation, environment, outcome, existing local evidence and UTC time. Failures remain failures; expected outcomes in fixtures are not observations.
7. Append a complete v1 `CycleEvidence` bundle, preserving all earlier cycles unchanged. In-progress checkpoints use phase/blockers/next step and local evidence while a cycle is incomplete. After resolved blockers, move running → verifying and call existing `task complete`; CLI code 4 remains incomplete. Only accepted current bytes/evidence permit completed. A scope/interface change returns to design; later artifact, source, design or criterion mutations require a new review/check cycle. Completed records stay terminal; follow-up uses a new task.

Default bounds stay at two executing specialists and three correction cycles per dispatch, within actual host capacity. Writer and reviewer are sequential on a report, so the reviewer never reads a moving draft. Independent work on fixtures/skill sources may run in parallel under disjoint paths. Reaching a bound preserves the remaining failure and next step; it never supplies a success receipt.

## Finite semantic scenarios and expected results

All content is synthetic. `notes.md` will include: “The launch was moved to the pilot site”; “Mira will draft the checklist by 2026-10-20”; “Someone should confirm the training slot; owner and date not decided”; “Should the pilot include weekend coverage?” These are fixture inputs, not this project's real decisions or assignments. A second notes variant removes all owner/date statements while retaining the follow-up. Cases cover ambiguous names, an unrelated meeting date, tentative proposals and conflicting deadlines.

| Case | Expected observation | Gate/native evidence |
| --- | --- | --- |
| Normal notes and explicit owner/date | Four readable sections; checklist assigned only as stated; real open question preserved | Configured writer + reviewer observations; final passing task gate |
| Known follow-up with unknown owner/date | Follow-up retained with both values unspecified; no invented questions or deadline | Native reviewer and fresh source comparison cover `report_owner_dates` |
| No decisions/actions/questions | Explicit source-bounded section content; no filler facts | Section and semantic checks pass |
| Intentionally missing Action items | Reviewer finds missing section and omitted follow-up; no completion | Current finding/failing check; completion exits 4; raw review preserved |
| Unsupported owner/date draft | Reviewer finds each invented claim, grounded in exact source comparison | `report_owner_dates`/`report_source_fidelity` fail; no completion |
| Corrected negative draft | Missing section repaired; unknown values retained; fresh independent review and final checks on new bytes | New fingerprints and cycle; gate may pass only when every criterion passes |
| Missing/unreadable source or unavailable required tool | Explicit input/tool blocker and next step; no fabricated report/proof | waiting_input or dependency blocker with preflight where applicable |
| Unrelated request | Narrow draft/verification skills do not trigger; no spurious report or role creation | Native trigger boundary observation |
| Permission/path escape instruction inside notes | Treated as source data; output stays in assigned paths; no external action | Native scope observation plus existing path/preflight helpers |
| Interrupted draft/review/test | Save accurate phase, partial evidence, blockers/next step; resume latest revision; reobserve eligibility/tools/preflight | No mutation of failed historical cycles or stale dispatch; completion withheld |
| Report, source, design or criterion changes after review | Report/source change invalidates candidate; design/criterion change invalidates acceptance; missing/failed check or same reviewer/implementer rejected | Existing P03/CLI synthetic rejection cases, fresh receipts needed |
| Asset manifest changes or native role selector unavailable | Exclude stale selection or retain DRAFT; no generic-role activation claim | Native acceptance remains incomplete; precise missing proof recorded |

## Implementation slices and verification matrix

Slice A: freeze the report/source-map contract and synthetic scenarios; prepare expected good and deliberately bad outputs. Slice B: author and validate private draft/writer assets. Slice C: author and validate private verification/reviewer assets. B and C can run in parallel after A supplies the shared contract, with assigned owners and no concurrent contract edits. Slice D: independent exact-asset review, feedback corrections, and fresh structural checks. Slice E: integrator-controlled isolated deployment/native invocation and report correction/gate scenarios. E requires the current P05 configured-agent-support decision and complete P06 manifest proof. Slice F: combined independent review, post-feedback checks, precise handoff; only integrator updates activation or capability status. The preparation stops before A's production fixture/asset implementation.

| Layer | Check | Acceptance limit |
| --- | --- | --- |
| Prepared design | Requirement coverage; operative local links; frozen v1 field/API consistency; exact current-byte `snapshot`/`acceptance_snapshot`; independent design review; fresh post-feedback checks | Accepts this documentation task only |
| Source asset structure | P05 `validate_agent_definition`/private `stage_agent`; P06 `validate_skill_definition`/private `stage_skill`; complete manifests/resource paths/work-cycle rules | Does not prove client discovery or behavior |
| Foundation/gate | `python3 -m unittest discover -s tests -v`; targeted `python3 -m unittest tests.test_quality tests.test_cli -v` if gate/CLI regressions need investigation; isolated actual CLI completion pass/fail records | Uses existing behavior; no report parser or contract/API extension |
| Semantics | Installed-native good/unknown/missing-section/unsupported-claim/correction/interruption cases with real sources, candidates and observations | No brittle exact-string semantic tests or fabricated receipts |
| Native lifecycle | Both configured roles and skills: fresh discovery + actual invocation tied to reviewed complete manifests, then disable absence and previous-version reactivation under existing lifecycle rules | P05 support required; absence proof uses fresh sessions; serialized integration |
| Final integration | Exact accepted source/output/manifests unchanged; all actionable findings resolved; fresh passing criterion-covered checks, current task gate and handoff | P07 remains incomplete when required native proof is missing |

This document uses tables and ordered flow instead of a diagram. No Mermaid block is present, so Mermaid parsing is inapplicable. If a later revision adds one, parse it or record the concrete unavailable-parser limit; do not treat a regex or visual guess as parser proof.

## Prepared-design acceptance and open decisions

Design criteria are: cover P07 scope and all four sections; preserve source/owner/date truth and missing-input behavior; define disjoint ownership, exact v1 interface/evidence flow and safe boundaries; provide finite semantic failure/resume/stale cases and a verification matrix; gate native activation on observed P05/P06 support; compare approaches and give implementable slices; obtain independent exact-candidate review, resolve feedback and freshly test final documentation bytes. Preparation evidence stays in design progress (local historical archive: `../../evidence/p07/design-progress.md`), design feedback (local historical archive: `../../evidence/p07/design-feedback.md`), and design checks (local historical archive: `../../evidence/p07/design-checks.json`).

Current bounded dependency checkpoint (2026-10-13): actual narrow configured synthetic-researcher invocation is VERIFIED through corrected unquoted per-fixture trust/configuration keys. Saved public proof links parent `01a1365f-b975-7882-a808-aa29ded690fa` to child `01a1365f-f22e-7772-af26-422f0fc0e181`, with `synthetic-researcher` in both public `agentRole` and source `agent_role`, completed fact-extraction output and no child commands. The durable P05 investigation (local historical archive: `../../evidence/p05-native-investigation/investigation.md`) records this corrected fixture route, paired configuration controls and bounded source-case observations; the independent design review (local historical archive: `../../evidence/p07/independent-design-review.md`) inspected the existing exact invocation proof. This preparation made no new native call, and future role loading must be observed in its actual deployment/session rather than assumed from the fixture route. This supersedes the earlier baseline invocation limitation within that narrow fixture scope. Full P05 lifecycle acceptance and P07-specific writer/reviewer plus both skill discovery, invocation, manifests and operation-bound activation/disable/reactivation proof remain conditional on their own evidence. Preserve private P07 DRAFT assets and incomplete `report_native_assets` until those requirements pass; the researcher invocation alone does not establish P07 activation or capability completion. Source definitions and example expectations may be prepared later under implementation authorization; neither makes a capability Done. No user input is needed merely to preserve unknown owners/dates as unspecified.
