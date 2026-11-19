# Tom orchestration implementation sequence

> Agent workers must use isolated worktrees, exact ownership and the project's design → implement → independent review → feedback → final tests cycle. No commits, merges, pushes or managed activation without applicable authorization and evidence.

Goal: implement the approved [Tom/Jerry design](../specs/2026-11-02-tom-jerry-orchestration-design.md), preserving existing deployments and customer work.

Architecture: additive versioned delivery records and evidence validation around existing v1 contracts; Tom owns root state, Jerry proposes technical assignments. Installed-client behavior remains a separate acceptance gate.

Stack: Python 3.11+, standard library, existing local CLI and native role lifecycle.

## Execution boundaries

User approved architecture and implementation on 2026-11-03. Existing uncommitted Xstore assets and design documents remain in canonical checkout. Two isolated worktrees were created from committed HEAD081db87 under the configured worktree root. The approved specification was copied into each worktree as an uncommitted input. Live user task state is not shared with workers. No new model/effort settings or native activation are authorized merely by a passing source test.

## Wave 1: concrete package plans and foundation

- [ ] P11 worker writes exact record/store APIs and executable failing-test-first plan; root independently reviews interfaces before implementation.
- [ ] P14 worker writes exact read-only knowledge selection APIs and executable plan; root independently reviews before implementation.
- [ ] Baseline: run `python3 -B -m unittest discover -s tests -q` independently in both worktrees. Delivery result: 336 tests passed. Knowledge result tracked in progress evidence.
- [ ] P11 implements its reviewed record validation, dependency/ownership and persistence slice. Only delivery_records.py, delivery_store.py and matching tests are owned. Strict v1 contracts stay unchanged.
- [ ] P14 implements its reviewed standalone selector/validator and matching tests. Fixture-only tests; no writes to real KB.
- [ ] Obtain separate spec-compliance and code-quality review of each exact candidate. Record findings/dispositions; return changes to their author; rerun fresh targeted and full tests after corrections.
- [ ] Integrate accepted files serially under root ownership without overwriting unrelated work; rerun combined tests. Source acceptance never implies native activation.

## Wave 2: evidence and roles

- [ ] P12 writes a detailed plan against accepted P11 APIs: EvidenceManifest, VerificationMatrix, before/after scenario and evidence levels, immutable content hashes, coverage and provenance limitations. Tests fail for missing/tampered/stale/blocked evidence, wrong scenario/build and invalid waivers.
- [ ] Root independently reviews the plan and freezes the interfaces, then a fresh worker implements only delivery_evidence.py and its tests. Review, correct and rerun tests.
- [ ] P13 separately plans supporting implementer, code-reviewer, qa-verifier, researcher and knowledge-curator role sources and scoped skills. Source definitions explicitly inherit host settings and remain DRAFT.
- [ ] Create positive/negative behavior cases and independent source review. Actual native evaluation must have finite explicit allocation and supported exact-definition binding. Preserve blockers; do not reuse historical Xstore receipts.

## Wave 3: orchestration and mandatory completion

- [ ] P10 plans team display profile (Tom root, Jerry stable engineering-lead ID) and versioned routing/delegation guidance against accepted delivery APIs. Test request classification, owner continuity, unavailable capabilities and shared budget handling.
- [ ] P16 root alone plans state.py/cli.py changes. Shared mandatory delivery gate applies to complete, update-to-completed and supported direct-store completion; immutable policy marker cannot be removed; caller callback cannot bypass it.
- [ ] Test interrupted registration/dispatch, stale envelopes and crossed same-role handoffs, unaccepted dependencies, transitive invalidation, unknown native runs, history mutation and legacy linked-task migration.
- [ ] Obtain independent combined review, address findings and run final full tests. No generic subagent is labeled an activated managed role.

## Wave 4: scoped learning and acceptance

- [ ] P15 separately plans project-local lesson capture and shared maintenance policy reconciliation against the actual XDA folder instructions. Keep customer evidence local; no self-authored evaluation truth or permission changes.
- [ ] Implement authorized reviewed procedures; test provenance, candidate/superseded exclusion, source pin drift, sanitization and fresh-context retrieval. Retain actual human acceptance gates.
- [ ] Run A01–A20 against exact reviewed candidate; record each actual result and proof scope. Use a safe seeded local bug for end-to-end evidence before any separate authorized customer-runtime scenario.
- [ ] Tom reports coverage, independent reviewers, authentic before/after evidence, test results and unresolved native/runtime gaps. Complete saved task only through actual completion gate when all criteria pass.

## Review and preservation

Package plans live in their respective worktrees until accepted. Root reviews review artifacts without recursive reviewer chains. Correction bounds remain three per dispatch. Unresolved findings, unavailable native proof or runtime verification prevent the affected acceptance claim. Existing main, active catalog/native files and unrelated work remain unchanged. The live implementation task is `tom-orchestration`; status is running, not complete.
