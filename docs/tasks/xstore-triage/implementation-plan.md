# Xstore triage implementation plan

> Agentic workers use the subagent-driven-development workflow, the reviewed design and exact assessment contract. User authorization covers autonomous local implementation; no commits/main changes are included. Every task follows design -> implement -> independent review -> feedback -> testing -> repeat.

Goal: add and genuinely evaluate a useful scoped Xstore evidence specialist with auditable inline knowledge and existing managed lifecycle.
Architecture: three-field TOML definition with complete versioned procedural JSON embedded; task-owned source evaluator/proof observer; existing staging/deployment APIs; no backend/helper schema changes.
Tech stack: Python 3.11+ standard library, TOML/JSON, unittest, existing installed Codex client and Git worktrees.

## 1. Role assets — source worker

Worktree: smart-assistant-xstore-triage, branch codex/xstore-triage. Exact ownership:
- examples/agents/xstore-triage/knowledge/1.0.0/pack.json
- examples/agents/xstore-triage/xstore-triage.toml
- examples/agents/xstore-triage/build_definition.py
- examples/agents/xstore-triage/README.md
- tests/test_xstore_triage_assets.py
- docs/evidence/xstore-triage/source/red.log
- docs/evidence/xstore-triage/source/green.log
- docs/evidence/xstore-triage/source/progress.json

- [ ] Write meaningful failing tests for exact full pack embedding/digest, malformed or stale knowledge binding and valid three-field definition; record actual failure before implementation.
- [ ] Implement only the versioned sanitized source assets and deterministic definition generation/binding check using current validate_agent_definition/deployment_manifest interfaces. Scope is supplied-evidence advice, not customer execution. Complete knowledge is inline, portable logical provenance only; model/effort/permissions inherited.
- [ ] Verify focused tests and source pins, self-check and hand off exact hashes to coordinator. Do not read evaluator oracle or concrete held-out cases.
- [ ] Independent spec review, then code-quality/knowledge-semantic review; resolve supported feedback and rerun focused checks against final bytes.

## 2. Evaluation controls — independent evaluator worker

Worktree: smart-assistant-xstore-triage-eval, branch codex/xstore-triage-eval. Same committed baseline and exact copied design/contract. Exact ownership:
- examples/scenarios/xstore-triage/native_eval.py
- examples/scenarios/xstore-triage/assessment.py
- examples/scenarios/xstore-triage/development.json
- examples/scenarios/xstore-triage/README.md
- tests/test_xstore_triage_evaluation.py
- docs/evidence/xstore-triage/evaluation/red.log
- docs/evidence/xstore-triage/evaluation/green.log
- docs/evidence/xstore-triage/evaluation/progress.json

- [ ] Write meaningful failing tests before code: contract/grounding/digest/range/path failures and valid partial-blocked/out-of-scope; reject generic all-abstention for a positive rubric and unsupported positive gate. Expose structural/case-constraint success separately from mandatory semantic review.
- [ ] Implement fresh-root preparation with exact role/helper/input/config copies; exclude oracle and copied canonical eligibility, reject unsafe paths/reuse/mutations; use existing privacy-projected observer/run patterns without changing core helpers or monkeypatching ROLES. Observations are UNASSESSED until external review.
- [ ] Implement no-model local checks for manifest/role/dispatch/version/operation-proof mismatch and bounded failure/timeout capture. Actual native execution remains coordinator-owned; do not run installed-model sessions, stage or activate anything.
- [ ] Provide six development cases/controls within the reviewed A/B/C matrix. Hold concrete unseen A3/B1/C2 variants and activation reserve until source-candidate freeze. Rubrics remain outside model inputs.
- [ ] Independent spec review then quality review; resolve feedback, fresh focused checks and exact handoff.

## 3. Coordinator integration, real behavior and lifecycle

- [ ] Review implementer artifacts and integrate only exact owned files; preserve main, original worktrees/private state. Full suite baseline is 336 passing tests at 081db870ccdf8c4316bbc1309e5d72806bab3094.
- [ ] Freeze exact role, pack, inputs, hidden rubric, runner/helper and config fingerprints. Independent preparation/semantic-rubric review precedes native calls. Three source parents + optional neutral parent + after-prepare parent max; <=5 parent attempts/4 configured children; sequential 300s execution +90s observation, no automatic retry/fallback.
- [ ] Run actual configured-role source cases, audit public parent/child role/source/dispatch and actual tool/output scope. Independent semantic review must establish useful grounded positive findings, honest negatives and concrete next checks, not just schema/keyword checks. Preserve failures/disclosure status.
- [ ] Stage immutable DRAFT via stage_agent; bind real validation/evaluation to same full manifest and exact source dependencies. Source-eval copying alone is not managed activation.
- [ ] If native route is available and source accepted, create canonical local feature branch (preserve main), integrate reviewed files, snapshot six existing native assets/catalog/private state, and serialize prepare. Observe fresh configured discovery+invocation after prepare with actual operation/version/manifest/session/time; independently inspect proof and finalize or restore on failure. No ACTVE claim without it.
- [ ] Final independent candidate review, recorded feedback, focused and full tests, catalog/current eligibility/preservation checks and authentic task completion gate. Document observed availability and usage, knowledge/version limits and precise remaining blockers.

Review-only agents own findings artifacts checked by coordinator; do not recurse. Source/evaluator code workers may run concurrently only in separate worktrees with disjoint ownership. Real native runs and lifecycle mutation are dependent coordinator work. Any need for new files/shared interfaces is returned to coordinator before writing them.
