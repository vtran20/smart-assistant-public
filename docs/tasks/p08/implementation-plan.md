# P08 implementation plan

Goal: deliver the bounded delegation contract, native lead/skill and proven integration flow described in [design.md](design.md). Architecture: unchanged v1 records plus explicit parent gate and bounded native orchestration. Tech stack: Python 3.11+, standard library, native Codex agents/skills.

- [x] Independently review design and this plan; record dispositions and fresh document checks.
- [x] Coordinator writes failing identity/ownership/coverage/blocker tests, runs RED, implements validator, reviews exact files, resolves feedback, runs GREEN/full suite and commits shared baseline.
- [x] Create ignored isolated P08 worktrees from shared baseline; run clean baseline checks there. Dispatch assets/scenario workers with explicit disjoint ownership and design/acceptance/evidence contracts.
- [x] Workers implement/test; independent review evaluates requirements and quality; fix findings, re-review changed bytes, run fresh tests and hand off candidate hashes/evidence.
- [x] Integrate reviewed worker outputs sequentially; run combined suite.
- [x] Stage new assets privately through P05/P06; evaluate actual configured native lead and skill (direct/indirect/unrelated/missing-input/tool), two-specialist and blocked-child scenarios, then serialize observed deployment if proof passes.
- [x] Independent final integration review, recorded feedback and fresh exact-candidate checks; preserve failed history. Update README/backlog/package plan only for observed coverage; commit locally and provide usage.

The user has authorized autonomous implementation. Coordinator owns integration and checks review-only findings without recursive review chains. Every implementation follows design → implement → independent review → feedback → test → repeat. Missing native support leaves assets DRAFT and acceptance explicitly incomplete.

Final candidate passed independent review, recorded feedback, 293 tests and the actual eight-criterion task gate. Both capabilities were serialized ACTIVE at catalog15. See acceptance (local historical archive: `../../evidence/p08/acceptance.md`) and local publication (local historical archive: `../../evidence/p08/publication.json`). The separate delivery-document review/check is recorded with closing evidence.
