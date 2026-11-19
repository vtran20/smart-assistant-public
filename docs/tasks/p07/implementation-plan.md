# P07 writing and verification implementation plan

> For agentic workers: use subagent-driven-development with disjoint parallel worktrees. Follow design → implement → independent review → feedback → testing → repeat until every criterion passes.

Goal: install the reviewed writer/reviewer roles and narrow drafting/verification skills, then demonstrate a source-grounded report and rejection/correction/resume workflow through existing native Codex and v1 helpers.

Architecture: keep shared contracts and Python helpers unchanged. Frozen synthetic report/scenario criteria define both asset implementations. Root serializes staging, lifecycle operations, canonical publication, durable state and integration commits. User explicitly authorized P07 implementation and parallel worktrees; no additional approval of the already accepted design is needed.

Baseline fe0713f; approved [design](design.md), current P05 acceptance (local historical archive: `../../evidence/p05-native-investigation/acceptance.md`). Its design-preparation statuses are historical; this plan authorizes source implementation.

## Chunk 1: Frozen inputs and parallel source assets

- [x] A: root creates examples/scenarios/writing/{notes.md,request.md,criteria.json,expected-report.md,expected-source-map.md,cases.md,unknown-owner-date.md,no-actions.md,empty-notes.md,ambiguous.md,relative-date.md,embedded-instruction.md} and examples/scenarios/verification/{missing-action-items.md,unsupported-owner-date.md,cases.md}. Independent review checks source fidelity/scenario coverage and plan before workers start.
- [x] B: drafting worktree owns private capabilities/staging source tree draft-document/{SKILL.md,references/report-contract.md,references/source-fidelity.md} and writer.toml, plus docs/evidence/p07/drafting/*. Source content follows the accepted design and frozen criteria. Observe missing source validation before creation; preserve actual RED/structural GREEN. Skill pressure-baseline observations, if used, record actual behavior; never manufacture failure if default behavior already works.
- [x] C: verification worktree owns private verify-completion/{SKILL.md,references/review-checklist.md} and reviewer.toml, plus docs/evidence/p07/verification/*. Use identical contract/criteria; check frozen original sources, not source-map claims alone. Own no writer sources/shared state. Record actual RED/structural GREEN.

Private sources are ignored and copied into root private staging after exact independent review; workers must not create canonical native targets, catalog entries, credentials/global config, new helper/API or CLI. Workers read skill-creator/writing-skills/TDD; use P05/P06 actual validators/staging helpers in isolated fixtures and inherit native model/effort. Review-only agents do not recurse. Root provides actual native evaluation; worker structural checks do not prove behavior.

## Chunk 2: Review, evaluation and deployment

- [x] D: independent spec compliance then quality/permissions review of exact complete private sources and frozen fixtures. Root checks review artifacts, returns supported feedback to original worker; repeat scoped independent review and fresh structural checks after corrections.
- [x] E: installed bundled CLI/public app-server in temporary isolated source-evaluation fixtures selects actual configured writer/reviewer and discovered skills. Obtain source-grounded good/unknown/empty/ambiguous/negative/missing-input-tool/unrelated/embedded-instruction/interruption observations. Preserve actual outputs/tool activity and parent/child/skill metadata; no generic child substitution or synthetic receipts. Independently review semantic outcomes before attaching successful evaluation evidence.
- [x] F: root private canonical stage through stage_agent/stage_skill, complete manifest identity and absent-target preconditions. Existing P02 prepare → fresh exact canonical native discovery/invocation → typed receipt → finalize, serially four assets. Skill configuration/tool dependency must reflect actually observed tools. Failure restores/reconciles and preserves DRAFT rather than accepting unsupported runtime.
- [x] G: actual disable absence and previous-version reactivation using new immutable agent version or preserved skill-version rules and fresh operation-specific proof. Keep tracked publication synchronized only after finalization; do not Git-merge native targets first.

## Chunk 3: Integrated report gate and delivery

- [x] H: capture supplied inputs, design/criteria and private state with existing v1 TaskAssignment/Handoff/TaskRecord. Fresh catalog eligibility and exact resource preflight precede dispatch. Writer/reviewer sequential on frozen report. Real negative reviewer findings/checks make completion exit4; corrections produce new candidate/re-review/fresh checks; append failure history unchanged. Exercise interruption/resume and report/source/criteria/design drift rejection; no report parser/generator/API is added.
- [x] I: independently review integrated source/native/session/operation/report evidence and root guidance/status changes; supported corrections return to worker/review/test loop. Run full Python unit suite and exact accepted source/manifests/local links/scenario coverage/catalog eligibility/current gate checks. No unresolved finding or missing required native proof permits P07 completion.
- [x] J: publish only unchanged finalized native assets and catalog evidence; preserve live runtime state ignored. Update relevant README/backlog/package acceptance evidence with precise scope. Local commit and retain/clean only P07 worktrees as appropriate; no push/PR/external send/scheduler inferred.

Verification: `/opt/homebrew/bin/python3 -B -m unittest discover -s tests -v`; P05 validate_agent_definition/stage_agent, P06 validate_skill_definition/stage_skill; native actual observations and existing CLI `task complete`. Track every step in docs/evidence/p07/progress.md, findings in feedback.md, exact manifests/snapshots/operations/tests in verification.json. Skills/roles require real native evaluation; fixture expected reports are never passing observations. Unknown facts remain Unspecified.

Functional checkpoint: actual task p07-interrupted-report completed at revision 17 with unchanged eight criteria, current independent source review, five native semantic checks plus three genuine coordinator observations and original failed cycle1 preserved. See acceptance (local historical archive: `../../evidence/p07/acceptance.md`). I/J delivery review and local publication will close after final integrated checks; private runtime remains ignored.

Prepublication integration I accepted after exact independent delivery re-review, corrected copy-provenance finding and fresh unchanged source/manifests/eligibility/gate/link/status checks. J remains pending the actual local commit and post-publication verification.

Delivery J completed: reviewed finalized assets/catalog/evidence/guidance published locally in commit `d416720cae81a6b4d128fdffdd2760fbd65c9caf` on `p07-report-workflow`; postcommit all253candidate bytes, deployedmanifests/eligibility/catalog13 and actualcompletedTask17 gate verified. AllA–J slices complete; both P07 worktrees retained, runtime/staging ignored, no push/PR. Publication (local historical archive: `../../evidence/p07/publication.json`) and delivery review (local historical archive: `../../evidence/p07/delivery-review-fixed.md`) record the final loop. Earlier pending paragraphs are historical checkpoints.
