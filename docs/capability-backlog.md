# Smart Assistant Capability Backlog

The assistant should turn ordinary chat requests into verified results and grow through additional agents, skills, and routines. This backlog organizes the 50 previously discussed takeaways into nine groups and adds a tenth group for extensibility. Original numbers are retained as T01 through T50; additional proposals use S01 through S16.

The original items are takeaways from the conversation, adapted into project requirements. Some describe working principles; others describe example workflows. A demonstration in the talk does not mean the equivalent capability is already available in this project.

## Tracking rules

Each original item appears in exactly one group. Keep its ID when splitting it into implementation tasks. For example, T13 may produce T13.1 and T13.2 without renumbering later items.

All capabilities begin as **Proposed**. Completing these planning documents does not complete a capability. Suggested owners are roles, not agents already created.

The [system design](superpowers/specs/2026-10-12-smart-assistant-system-design.md) and [parallel implementation plan](superpowers/plans/2026-10-12-smart-assistant-implementation-plan.md) describe the selected M1/M2 foundation. Every implementation package follows the mandatory design, implement, independent review, feedback, and testing cycle in [AGENTS.md](../AGENTS.md). Capability statuses change only with execution evidence. The linked Wave 1 evidence (local historical archive: `evidence/wave1/progress.md`) covers accepted P01–P03 helper implementations; affected capabilities remain In progress until their chat/native workflows satisfy the broader criteria. Wave 2 evidence (local historical archive: `evidence/wave2/progress.md`) tracks integrated P04–P06 source, actual chat/native observations and remaining client limits.

| Status | Meaning |
| --- | --- |
| Proposed | Candidate scope awaiting selection |
| Ready | Scope, dependencies, and acceptance criteria are defined |
| In progress | Implementation is underway |
| Blocked | A specific missing dependency prevents progress |
| Validating | Implemented and being checked against acceptance criteria |
| Done | Acceptance evidence exists and remaining limitations are recorded |
| Deferred | Deliberately excluded from the current milestones |

P0 means foundational, P1 means useful after the foundation, and P2 means advanced or optional. Priorities, owners, and milestones below are recommendations. Reprioritizing an item does not change its identity.

Use the Evidence column for a task link, artifact path, test result, or observed application result. For a blocked item, record the blocker there instead. Changes to capability status belong here; individual execution history will belong in future task records.

## Groups at a glance

| Group | Scope | Original IDs | Original count | Additional proposals |
| --- | --- | --- | --- | --- |
| G01 | Request coordination and context | T08, T16, T17, T18, T19, T27, T30, T41, T42 | 9 | S05, S06, S16 |
| G02 | Training and reusable skills | T11, T12, T13, T14, T15, T20, T33 | 7 | S14, S15 |
| G03 | Design and creative work | T01, T02, T03, T04, T44 | 5 | None |
| G04 | Engineering and delegation | T05, T06, T07, T24, T34, T35 | 6 | None |
| G05 | Verification and quality | T09, T10, T22, T23, T25 | 5 | S07, S08 |
| G06 | Tools and integrations | T31, T32, T48 | 3 | S09, S10 |
| G07 | Personal administration | T28, T29, T37, T38, T39, T40, T49, T50 | 8 | None |
| G08 | Writing publishing and feedback | T26, T36, T43, T45, T46, T47 | 6 | None |
| G09 | Recurring work and usage | T21 | 1 | S11, S12, S13 |
| G10 | Adding agents and skills | None | 0 | S01, S02, S03, S04 |
| Total | | T01 through T50 | 50 | 16 |

## G01 Request coordination and context

Outcome: one coordinator receives requests, retrieves relevant context, chooses specialists, and returns one coherent result. Group discussions from the talk become coordinated specialist input; a native bot group chat is not assumed.

| ID | Capability | Priority | Milestone | Suggested owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T08 | Bring PM, design, and engineering perspectives together when reviewing an idea | P1 | M2 | Coordinator | Proposed | — |
| T16 | Keep reusable agent roles with separate conversations or records for individual projects | P0 | M1 | Coordinator | In progress | [P01](tasks/p01/design.md) scoped project/role storage; P07 roles (local historical archive: `evidence/p07/canonical-role-final-review.md`) genuine separate configured contexts; broader project conversation management remains partial |
| T17 | Preserve each role's relevant memory and preferences | P0 | M1 | Coordinator | In progress | [P01](tasks/p01/design.md): scoped preference loading; workflow consumption pending |
| T18 | Use a chief of staff to route requests with unclear ownership | P0 | M1 | Coordinator | In progress | [P04](tasks/p04/design.md): semantic coordination skill and CLI; native acceptance tracked in Wave 2 |
| T19 | Split a role when its responsibilities and context become too broad | P1 | M2 | Coordinator | Proposed | — |
| T27 | Exchange relevant context between specialists without making the user copy it manually | P0 | M2 | Coordinator | In progress | P08 (local historical archive: `evidence/p08/acceptance.md`) P08 scoped assignment/context and actual child handoffs; broader specialist contexts pending |
| T30 | Let the user manage systems and boundaries while the assistant handles execution | P0 | M1 | Coordinator | In progress | [P04](tasks/p04/design.md): scoped authorization/preflight and durable execution |
| T41 | Address a named specialist directly when the user wants its response | P1 | M2 | Coordinator | Proposed | — |
| T42 | Show a specialist's delegated task status through the coordinator and available agent thread | P1 | M2 | Coordinator | In progress | P08 (local historical archive: `evidence/p08/acceptance.md`) P08 actual child status/provenance and preserved timeout; broader coordinator coverage pending |

## G02 Training and reusable skills

Outcome: corrected workflows become reusable skills with evidence of reliable behavior. Learning is explicit and reviewable; successful conversations do not silently rewrite operating instructions.

| ID | Capability | Priority | Milestone | Suggested owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T11 | Onboard agents before giving them independent responsibilities | P0 | M2 | Capability manager | In progress | [P05](tasks/p05/design.md) validated staging; P07 roles (local historical archive: `evidence/p07/canonical-role-final-review.md`) observed configured writer/reviewer activation, disable and fresh reactivation; broader onboarding remains partial |
| T12 | Observe initial attempts and use corrections to improve the workflow | P0 | M1 | Reviewer | In progress | P07 (local historical archive: `evidence/p07/acceptance.md`): actual initial findings, corrected report, independent review and fresh evidence-bound completion; bounded local workflow demonstrated |
| T13 | Save successful workflows as reusable skills | P0 | M2 | Capability manager | In progress | [P06](tasks/p06/design.md): complete skill staging and native behavior/lifecycle evaluation |
| T14 | Introduce recurring automation after the underlying skill works reliably | P0 | M4 | Automation manager | Proposed | — |
| T15 | Begin with simple tasks and expand responsibilities gradually | P0 | M1 | Coordinator | Proposed | — |
| T20 | Audit agents and suggest better skills, role boundaries, or routines | P1 | M5 | Capability manager | Proposed | — |
| T33 | Encode personal working styles in optional mode skills | P1 | M2 | Capability manager | Proposed | — |

## G03 Design and creative work

Outcome: generate consistent designs from human direction and reusable design rules. These workflows depend on the selected design or image tools and authorized access.

| ID | Capability | Priority | Milestone | Suggested owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | Establish a design system before generating screens | P1 | M5 | Designer | Proposed | — |
| T02 | Expand one reference screen into a complete flow | P1 | M5 | Designer | Proposed | — |
| T03 | Edit designs through an authorized Figma integration | P1 | M5 | Designer | Proposed | — |
| T04 | Document file structure, colors, typography, and spacing | P1 | M5 | Designer | Proposed | — |
| T44 | Transform photos into miniature scenes or other creative assets | P2 | M5 | Designer | Proposed | — |

## G04 Engineering and delegation

Outcome: plan engineering work, delegate bounded tasks, and collect verified changes. Start with small independent tasks; cloud execution and larger teams can follow.

| ID | Capability | Priority | Milestone | Suggested owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T05 | Create an engineering lead role | P1 | M2 | Engineering lead | Done | P08 (local historical archive: `evidence/p08/acceptance.md`) Engineering lead1.0.0 ACTIVE through actual canonical configured-role invocation, independently reviewed native proof and serial lifecycle finalization |
| T06 | Have the engineering lead divide and supervise delegated work | P1 | M2 | Engineering lead | In progress | P08 (local historical archive: `evidence/p08/acceptance.md`) P08 configured lead supervised two writer contexts and supported corrections; aggregate accepted after authenticated filesystem recovery and fresh independent review; local role/skill ACTIVE. Broader engineering supervision remains partial |
| T07 | Execute suitable independent coding tasks with cloud agents when available | P2 | M5 | Engineering lead | Proposed | — |
| T24 | Match available models and reasoning settings to task complexity | P1 | M2 | Coordinator | Proposed | — |
| T34 | Support useful software contributions from non-engineers through clear workflows | P1 | M5 | Engineering lead | Proposed | — |
| T35 | Plan large projects in phases before assigning implementation work | P0 | M2 | Engineering lead | Proposed | — |

## G05 Verification and quality

Outcome: completion means an observed result that satisfies the request. Autonomous merging is an advanced opt-in workflow with its own requirements, not the default for every change.

| ID | Capability | Priority | Milestone | Suggested owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T09 | Verify changes before merging | P0 | M1 | Reviewer | In progress | [P03](tasks/p03/design.md): evidence gate; merge/workflow integration pending |
| T10 | Support automatic merging for explicitly selected repositories and change classes | P2 | M5 | Engineering lead | Proposed | — |
| T22 | Verify work in its intended environment, including a VM when necessary | P0 | M1 | Reviewer | In progress | P07 (local historical archive: `evidence/p07/progress.md`) actual macOS installed-client report review and current completion evidence; VM/cross-platform workflow coverage remains unverified |
| T23 | Evaluate whether the actual requested outcome was achieved | P0 | M1 | Reviewer | In progress | P07 (local historical archive: `evidence/p07/progress.md`) independent source-grounded report review and current evidence gate; broader requested outcomes remain partial |
| T25 | Preserve craft and quality as execution volume grows | P0 | M1 | Reviewer | In progress | P07 (local historical archive: `evidence/p07/progress.md`) bounded independent review/correction/fresh-check loop; larger-volume workflows remain partial |

## G06 Tools and integrations

Outcome: skills use available, authorized tools. Portable instructions do not imply that every client has identical tools, access, or behavior.

| ID | Capability | Priority | Milestone | Suggested owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T31 | Reuse compatible skills across tools such as Codex and Cursor | P2 | M5 | Capability manager | Proposed | — |
| T32 | Package related skills and MCP tools as plugins when useful | P1 | M3 | Integration specialist | Proposed | — |
| T48 | Respect the granted scope of local computer access | P0 | M1 | Coordinator | In progress | [P03](tasks/p03/design.md) exact declared-action preflight; P07 limitation (local historical archive: `evidence/p07/canonical-role-final-post-feedback.json`) configured reviewer ownership observed, ancillary generic-parent write outside declared probe scope retained; global action enforcement not certified |

## G07 Personal administration

Outcome: complete connected administrative workflows, with verification of the destination state and required approvals before consequential actions.

| ID | Capability | Priority | Milestone | Suggested owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T28 | Chain research, writing, publishing, and follow-up into one requested workflow | P1 | M3 | Personal assistant | Proposed | — |
| T29 | Present travel options for review before booking | P2 | M5 | Personal assistant | Proposed | — |
| T37 | Extract actionable tasks from email | P1 | M3 | Personal assistant | In progress | [First M3 slice](m3-work-brief-workflow.md): selected Outlook/Slack capture, source-linked brief and external-citation checks; independent local review and live acceptance tracked in evidence (local historical archive: `evidence/m3-work-brief/acceptance.md`) |
| T38 | Turn screenshots into verified calendar changes | P1 | M3 | Personal assistant | Proposed | — |
| T39 | Update inventory records after approved purchases | P2 | M5 | Personal assistant | Proposed | — |
| T40 | Adjust unsold marketplace listing prices using an authorized recurring rule | P2 | M5 | Personal assistant | Proposed | — |
| T49 | Deliver requested reminders through SMS when an integration is available | P2 | M5 | Personal assistant | Proposed | — |
| T50 | Handle household supplies and lunch logistics within defined purchase limits | P2 | M5 | Personal assistant | Proposed | — |

## G08 Writing publishing and feedback

Outcome: produce useful content and connect user feedback to follow-up work. Sending and publishing follow the request's authorization and applicable tool requirements.

| ID | Capability | Priority | Milestone | Suggested owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T26 | Aggregate repeated user reports and route relevant issues to engineering | P1 | M3 | Researcher | Proposed | — |
| T36 | Polish email and Slack drafts for user review | P0 | M1 | Writer | Proposed | — |
| T43 | Convert articles into audio for listening | P2 | M5 | Writer | Proposed | — |
| T45 | Use a bot as a website publishing interface | P2 | M5 | Writer | Proposed | — |
| T46 | Retrieve the current repository playbook before executing a publishing workflow | P1 | M3 | Writer | Proposed | — |
| T47 | Organize annotated bug screenshots into reports, including Notion when connected | P1 | M3 | Researcher | Proposed | — |

## G09 Recurring work and usage

Outcome: predictable recurring work that can be inspected, paused, and stopped. Run a skill successfully on demand before scheduling it.

| ID | Capability | Priority | Milestone | Suggested owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| T21 | Tune routine frequency to control unnecessary wakeups and usage | P0 | M4 | Automation manager | Proposed | — |

## G10 Adding agents and skills

Outcome: add, update, disable, and remove capabilities through a consistent process. These are additional proposals, with the extension flows directly addressing the user's latest request.

| ID | Proposal | Priority | Milestone | Suggested owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| S01 | Agent registry with stable names, responsibilities, allowed tools, and lifecycle state | P0 | M2 | Capability manager | In progress | [P02](tasks/p02/design.md) catalog/eligibility; P07 roles (local historical archive: `evidence/p07/canonical-role-final-review.md`) writer2/reviewer2 ACTIVE at observed catalog13 with real lifecycle proof; registry coverage remains scoped |
| S02 | Skill catalog with triggers, inputs, outputs, dependencies, and verification requirements | P0 | M2 | Capability manager | In progress | [P02](tasks/p02/design.md) complete manifests/eligibility; P07 skills (local historical archive: `evidence/p07/canonical-skill-review.md`) both skills ACTIVE with actual discovery/read/behavior/lifecycle evidence; catalog coverage remains scoped |
| S03 | Add or update an agent through chat, validate its definition, and register it | P0 | M2 | Capability manager | In progress | [P05](tasks/p05/design.md) management/staging; P07 roles (local historical archive: `evidence/p07/canonical-role-final-review.md`) observed configured role support and serialized immutable version2 reactivation; broad chat onboarding remains partial; [Xstore draft](xstore-triage-workflow.md)1.0.1 scoped knowledge and disclosed scenarios; current native proof/behavior acceptance pending |
| S04 | Add a skill through chat, check activation and outputs, then register it | P0 | M2 | Capability manager | In progress | [P06](tasks/p06/design.md) management/resource validation; P07 skills (local historical archive: `evidence/p07/canonical-skill-review.md`) actual narrow skill lifecycle and outputs; broad skill creation remains partial |

## Additional proposals for the other groups

| ID | Group | Proposal | Priority | Milestone | Suggested owner | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S05 | G01 | Classify each request and automatically select the appropriate workflow and specialists | P0 | M1 | Coordinator | In progress | [P04](tasks/p04/design.md): semantic chat routing and catalog checks; no keyword router |
| S06 | G01 | Durable task records with progress, dependencies, outputs, and resume information | P0 | M1 | Coordinator | In progress | [P01](tasks/p01/design.md) durable records/CAS; P07 (local historical archive: `evidence/p07/progress.md`) failed history preserved through genuine interruption and fresh execution, current evidence-bound completion; broader coordinator request coverage remains partial |
| S07 | G05 | Define completion criteria before execution and attach evidence before marking Done | P0 | M1 | Reviewer | In progress | [P03](tasks/p03/design.md) completion checker; P07 (local historical archive: `evidence/p07/progress.md`) current candidate/acceptance-bound independent review, resolved feedback and criterion checks before saved completion; broader integration pending |
| S08 | G05 | Bound retries and prevent duplicate external actions after interrupted or uncertain runs | P0 | M3 | Coordinator | In progress | [M3 read-only workflow](m3-work-brief-workflow.md) bounds retrieval/resume and excludes external writes; general external-write deduplication remains pending |
| S09 | G06 | Map actions to authorization, tool access, and approval requirements | P0 | M1 | Coordinator | In progress | [P03](tasks/p03/design.md) exact declared action/tool authorization; P07 limitation (local historical archive: `evidence/p07/canonical-role-final-post-feedback.json`) preflight is not global runtime enforcement and a generic-parent ancillary write remains documented |
| S10 | G06 | Keep credentials outside project notes and define retention for sensitive task records | P1 | M3 | Integration specialist | In progress | [M3 private capture/retention](m3-work-brief-workflow.md); broader connector retention enforcement remains pending |
| S11 | G09 | Register on-demand, scheduled, and supported event-triggered workflows separately | P0 | M4 | Automation manager | Proposed | — |
| S12 | G09 | Set agent concurrency, time, retry, and usage limits for each workflow | P0 | M2 | Coordinator | In progress | P08 (local historical archive: `evidence/p08/acceptance.md`) P08 bounded max2 executing specialists, three correction default and explicit native runtime ceilings; wider workflow/usage limits remain partial |
| S13 | G09 | Pause, resume, cancel, and notify on meaningful changes or required action | P0 | M4 | Automation manager | Proposed | — |
| S14 | G02 | Maintain representative examples that catch routing and skill regressions | P0 | M2 | Reviewer | In progress | Wave 2 (local historical archive: `evidence/wave2/progress.md`) finite coordinator/agent/skill cases; P07 (local historical archive: `evidence/p07/progress.md`) positive/negative/correction/missing-input-tool/unrelated/implicit/source-scope/interruption fixtures with real native observations; P08 bounded delegation positive/failure/dependency/cancellation and native boundary cases accepted with failed history retained; P09 (local historical archive: `evidence/p09/acceptance.md`) integrated regressions and actual macOS/Linux helper tests pass; selected native lifecycle and all12 actual acceptance criteria passed; 323 tests pass on macOS/Linux, with broader regression coverage still partial |
| S15 | G02 | Version agent and skill changes and retain a known working rollback point | P1 | M2 | Capability manager | In progress | [P02](tasks/p02/design.md) immutable staging/backup/recovery; P07 lifecycle (local historical archive: `evidence/p07/canonical-role-final-review.md`) actual disable/reactivation, distinct version2 same reviewed role bytes and failed-operation restoration; no universal arbitrary-version rollback claim |
| S16 | G01 | Detect missing tools early and offer a useful fallback or a precise blocker | P0 | M1 | Coordinator | In progress | [P03](tasks/p03/design.md) missing-tool detection; P07 source evaluation (local historical archive: `evidence/p07/ordinary-native-review.md`) actual precise input/tool blockers and no invented output; broader fallback selection partial |

## Suggested delivery milestones

Milestones are candidate implementation batches, not an approved implementation plan. Each selected batch needs concrete task definitions and acceptance criteria before execution.

| Milestone | Scope | Main dependencies | Evidence required to finish |
| --- | --- | --- | --- |
| M1 | Coordinator, preferences, task records, writing, verification, access boundaries | User preferences and a selected initial workflow | A normal request produces a verified artifact; an ambiguous request asks only for essential input; a missing tool produces a precise blocker; an interrupted task can resume |
| M2 | Add agents and skills, delegate suitable work, track versions and limits | M1 and supported local agent configuration | Add a specialist and a skill through chat; route direct and indirect requests correctly; disable either without accidental execution; collect delegated results into one response |
| M3 | Selected external integrations and connected workflows | M1, chosen connector access, and S08 | Read source records, generate a correct output, verify any authorized write, and retry an interrupted run without duplicating an external action |
| M4 | Recurring routines, pause and cancellation, notifications | M2, successful on-demand workflow, required access | One chosen routine runs at the intended cadence, records its result, stays quiet when unchanged, and responds correctly to pause or cancellation |
| M5 | Design, cloud engineering, personal purchases, publishing, advanced autonomy | Relevant earlier milestones and workflow-specific tools | Validate each chosen advanced workflow independently; record its limits and required approvals |

Prioritize M1 and M2 because the immediate goal is a useful chat entry point that can grow. M3 should begin with the integrations the user actually needs. M5 is a menu of optional workflows, not a commitment to implement every demonstration from the talk.

## Progress updates

When implementing a selected item, record its concrete acceptance criteria and dependencies in a linked task record. Keep the backlog's row status synchronized with that record. Update an item to Done only after its criteria are satisfied; describe any partial implementation instead of silently reducing the requirement.

Useful management requests include:

- "Show P0 items that are not Done."
- "Show blockers for M2."
- "Move T43 to Deferred."
- "Break S03 into implementation tasks."
- "Show which capabilities depend on Outlook."

## Source context

Original item wording and numbering come from the two earlier lists in this conversation, based on [the talk's public article notes](https://creatoreconomy.so/p/grok-bot-team-14-best-bots-peng-zheng-lauren-tan) and [the automated episode transcript](https://pod.wave.co/podcast/behind-the-craft/we-built-grok-bot-here-are-our-14-best-bots-peng-zheng-lauren-tan). Grouping, priorities, milestone assignments, Codex adaptations, and S01 through S16 are project proposals.

P07 acceptance (local historical archive: `evidence/p07/acceptance.md`) covers the bounded local report workflow, configured writer/reviewer, both narrow skills, native lifecycle and actual evidence-bound report completion. Broader email/Slack, delegation, external actions, recurring routines and integrated M1/M2 capabilities remain separate.

## Tom/Jerry milestone tracking (2026-11-03)

These packages extend existing capabilities without renumbering T01–T50/S01–S16. Local acceptance does not mark broader native capabilities Done. See actual progress (local historical archive: `evidence/tom-orchestration/progress.json`).

| Package | Local state | Remaining acceptance |
| --- | --- | --- |
| P10 | Tom bootstrap/profile implemented; exact-bundle registered setup observed; aggregate source review passed | Configured role readiness and primary-chat behavior separate |
| P11 | Assignment/ownership/DAG/run binding and CAS/recovery helpers independently reviewed; combined checks passed | Broader runtime scenarios remain separately scoped |
| P12 | Reproduction/matrix/evidence and semantic-review gate independently reviewed | Actual configured native/customer proof separate |
| P13 | Six source roles/profile/scenarios independently reviewed, DRAFT | Genuine configured discovery/invocation/behavior/lifecycle before activation |
| P14 | Read-only knowledge helper reviewed; actual supplied KB read observed | Owning project/version applicability required; no fabricated onboarding |
| P15 | Learning/research workflow and reviewed eight-file KB reconciliation applied | No universal behavior, background learning or model training claim |
| P16 | Shared store/CLI gate, recovery and callback corrections reviewed; canonical checks passed | Configured native acceptance separate |
| P17 | Separate builtin schema/codec and actual seeded-bug delivery accepted; locally integrated, 649 canonical tests passed | No configured-role activation or customer/runtime acceptance |

The user approved Option B in the [runtime decision](tasks/tom-orchestration/runtime-decision.md). Builtin acceptance (local historical archive: `evidence/builtin-execution/acceptance.md`) records the actual scoped delivery and final integration checks. Managed activation criteria remain unchanged; existing unfinished Xstore triage work stays preserved.
