# Local commands and evidence records

Run from the Smart Assistant project root. Use a private task state directory (normally passed as `--state-dir .smart-assistant/state`) and never share live task state with a test worktree. The CLI reads files; it does not execute arbitrary commands, approve actions or select specialists.

```sh
python3 -m smart_assistant task create --record task.json --state-dir .smart-assistant/state
python3 -m smart_assistant task show task-01 --state-dir .smart-assistant/state
python3 -m smart_assistant task update --record proposed.json --expected-revision 1 --state-dir .smart-assistant/state
python3 -m smart_assistant task complete task-01 --expected-revision 2 --state-dir .smart-assistant/state
python3 -m smart_assistant catalog validate --project-root .
python3 -m smart_assistant catalog eligible --project-root . --tools observed-tools.json
python3 -m smart_assistant preflight --request preflight.json
```

`main(argv=None)` returns an integer. Every command writes one JSON `{ok,data,errors}` response. Exit 0 succeeds; 2 rejects input, arguments, transitions or catalog validation; 3 means a revision conflict; 4 means unmet preflight/completion. `--help` returns help text in data with 0. Error detail is sanitized; inspect private input/evidence locally for diagnosis. Success show/create/update data contains full requested task records; keep secrets out of input files and logs intended for sharing.

P00 typed schemas are in `project module: smart_assistant/contracts.py`. Start from `project example: examples/contracts/TaskRecord.json` or construct typed records with `from_dict`/`to_dict`; those examples are synthetic wire-format illustrations, not usable completion evidence. New task status is queued with no completed cycles. TaskStore stores revision 1; each successful update increments it. Proposal revision must equal expected revision. The request and task identity remain immutable.

Use APIs to avoid invented hashes:

```python
from pathlib import Path
from smart_assistant.context import load_context
from smart_assistant.contracts import Artifact
from smart_assistant.quality import snapshot, acceptance_snapshot
context = load_context(Path(state_dir), project_id, selected_role_id)
candidate = snapshot(Path(artifact_root), [Artifact("report", "outputs/report.md", "0" * 64)])
acceptance = acceptance_snapshot(criteria, Path(artifact_root) / "design.md")
```

`artifact_root` is an absolute local directory. Design, artifact, feedback evidence and check references are safe relative files within it. Snapshot hashes actual bytes; the zero digest above is an input placeholder replaced by the helper. Keep review/check receipt files outside candidate artifacts. ReviewReceipt records reviewer_ref, implementer_ref, candidate_id, acceptance_id, UTC observed_at and findings. Each disposition binds a finding to corrected/rejected reasoning and real evidence references. CheckReceipt records covered criterion IDs, those same fingerprints, command or observed behavior, environment, pass/fail, local evidence_ref and timestamp. CycleEvidence contains the next consecutive cycle number, design_ref, candidate, acceptance, review, dispositions and checks. Preserve all earlier records unchanged; append a new bundle for later feedback/testing.

PreflightRequest has schema_version 1, required_tools and available_tools lists, requested_actions and authorization lists. RequestedAction needs action_ref, kind (`read_local`, `write_local`, `external_read`, `external_write`), exact resource_ref, required_tool or null, and observed host_decision (`allowed`, `approval_required`, `denied`, `unknown`). AuthorizationScope carries action_kind, that exact resource_ref and the real user source_ref. A declared source string is evidence to inspect, not independently verified consent.

For explicit failed resume: read current task, propose status running, retain its revision and cycles, set an accurate resume_next_step, and call task update. In-progress work is tracked through phase, blockers, resume_next_step and local evidence; append a whole CycleEvidence after its review/feedback/testing bundle exists. Do not discard failed history to make a gate pass.
