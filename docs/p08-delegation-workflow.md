# Bounded delegation

Use the request-coordination entry point in a fresh Codex chat attached to the canonical project. A suitable engineering request has substantial independent parts, clear source inputs and exact output ownership. Small coherent work stays direct. The `delegate-work` workflow and `engineering-lead` role require current eligible deployment/native proof before ordinary managed selection. The canonical local instance has `engineering-lead`1.0.0 and `delegate-work`1.0.0 ACTIVE at verified catalog15 through separate managed transactions and fresh installed-client discovery/invocation. See activation evidence (local historical archive: `evidence/p08/lifecycle/activation-result.json`). Use a fresh supported session; actual role/tool discovery and current preflight still govern each dispatch. If configured role selection is unavailable, preserve the blocker and next step. Package acceptance is recorded separately in P08 acceptance (local historical archive: `evidence/p08/acceptance.md`).

Example request: “Produce two independent engineering pilot readiness reports from these local notes, delegate the work within two specialists, then integrate and independently verify the result. Save progress and retain blocked-child evidence.” Give the intended output paths and any essential constraints. The coordinator saves criteria/design, checks current selections and preflight, and supplies each specialist only needed context.

At most two specialists execute at once across the tree, reduced by available slots and task limits. Code workers use isolated Git worktrees; disjoint documentation work may share an explicitly assigned artifact directory. Dependent work waits for accepted predecessor outputs. The parent owns shared contracts, durable state and serialized integration. Reviewers own findings; the coordinator checks review-only artifacts without recursively reviewing reviewers.

The parent validates each existing-v1 Handoff against its current TaskAssignment and trusted canonical artifact root. `ready_for_review` requires exact identity/revision/role, owned existing files with current hashes and local criterion/evidence references. Structural success is a request for independent review, not completion. Every child output and the combined candidate need independent review, recorded feedback and fresh tests covering the same bytes.

A required blocked/failed child preserves successful siblings and partial output. Its blocker is copied into parent TaskRecord.blockers; actual completion through the CLI denies unresolved blockers. The raw quality helper checks receipt consistency and does not infer child dependencies. Clear blockers only after actual resolution, refreshed selection/preflight and current review/checks. Three correction cycles per dispatch is the default ceiling; smaller task limits win. At a bound, keep the precise next step. Cancelled/completed records remain terminal; follow-up work gets a new task.

## Local helper examples

```sh
python3 -m unittest tests.test_handoff tests.test_delegation_assets tests.test_delegation_scenarios -v
python3 examples/scenarios/delegation/scenario.py positive
python3 examples/scenarios/delegation/scenario.py blocked
python3 examples/scenarios/delegation/scenario.py failed
python3 examples/scenarios/delegation/scenario.py cancelled
python3 -m unittest discover -s tests -v
```

The deterministic scenarios explicitly use hypothetical review/check receipts to test helper behavior. They do not establish native concurrency, role selection or activation. [Installed-native evaluator instructions](../examples/scenarios/delegation/README.md) describe separately authorized one-shot probes and preserved observations. P09 broad integrated acceptance, cloud agents, automatic model/cost routing and external actions remain separate work.

For a focused helper call, decode actual existing-v1 TaskAssignment and Handoff records with `smart_assistant.contracts.from_dict`, then call `validate_handoff(assignment, handoff, trusted_root.resolve(strict=True))`. Inspect every error before integration. Preserve returned native-authored handoffs after interruption; the coordinator may receive their authenticated current files and retest them without inventing an absent final native response. Prepare infrastructure such as output directories before exact-file dispatch; do not expand file ownership through a directory prefix.
