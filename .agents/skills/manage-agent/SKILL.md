---
name: manage-agent
description: Create, revise, validate, evaluate, enable, disable, or restore a project Codex agent when the user requests an agent lifecycle change.
---

Build a specialist only when a distinct recurring responsibility or explicit agent request warrants it. Ordinary requests use existing capabilities. Establish its narrow role, trigger boundaries, required inputs, output contract, actual tool dependencies and overlap with current agents before generating a definition. Agent configuration grants no new permissions or account access; preserve current user scope.

Follow the project's design → implement → independent review → recorded feedback → test → repeat until acceptance passes. Bind review and testing to the exact candidate bytes; preserve unresolved findings. For new or changed agents, generate a non-native TOML source with `name`, `description` and `developer_instructions`; include the same project cycle and independent review requirement in those instructions. Keep model and effort inherited: this helper cannot enable overrides without an observed available catalog. It precisely rejects other optional native config, including permission overrides.

Use public Python APIs from the project root:

```python
from pathlib import Path
from smart_assistant.agent_lifecycle import validate_agent_definition, stage_agent
from smart_assistant.catalog import load_catalog
from smart_assistant.contracts import from_dict
from smart_assistant.lifecycle import DeploymentStore

root = Path(project_directory)
gate = validate_agent_definition(root / definition_relative_path)
# Inspect gate.errors; correct failed structure before staging.
candidate = stage_agent(root, root / definition_relative_path,
                        from_dict('CapabilityRecord', draft_record_json))
```

The draft must be AGENT/DRAFT, share its ID with native `name`, and use the project target `native target: .codex/agents/<basename>.toml`. Staging returns a fresh immutable private version with a complete manifest hash and clears stale proof. It writes no catalog/native assets and proves no evaluation/discovery. A registered replacement must retain its kind/target and use a new version.

Evaluate the exact staged candidate against ordinary, out-of-scope and missing-input/tool requests in an isolated environment. Record observed outputs and whether boundaries, grounding and blockers hold. Do not convert an example expectation or structural success into a passing evaluation. For the P02 receipt format and transaction sequence, read [references/transactions.md](references/transactions.md). If no native observation route is available, preserve the draft and report native activation pending.

After independent review and resolved feedback, attach real manifest-bound structural validation and behavioral evaluation evidence, then use `DeploymentStore.prepare(candidate, expected_revision)` only within authorized deployment scope. Root serializes transactions. Fresh installed-client discovery and actual invocation must observe the prepared identity/version/complete manifest before `finalize(operation_id, NativeProbeReceipt)`. Local file existence proves neither discovery nor invocation. Record client version and fresh session evidence.

For disabling, use `prepare_disable(capability_id, expected_revision)`, observe absence in a fresh native session and call `finalize_disable(operation_id, absence_receipt)`. For failed or interrupted uncommitted preparation, use `restore(operation_id)` and verify restored bytes/catalog; P02 automatically restores failed activation receipts. A finalized rollback requires staging the previous verified bytes as a new version, independent review/evaluation, a new prepare and fresh activation proof. Do not reuse finalized `restore`, stale proof or an existing version directory.
