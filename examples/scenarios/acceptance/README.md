# P09 isolated native observation adapter

This adapter prepares an isolated source evaluation without calling a model. It copies exact current `smart_assistant/**/*.py`, the engineering-lead/writer/reviewer roles, and every regular resource in request-coordination, manage-agent, manage-skill, delegate-work, draft-document and verify-completion. Canonical catalog, staging, deployment journals and private proof are never copied. Required source/fixture trees must contain regular files/directories with no symlink ancestors; fixtures cannot replace native assets, helper code, instructions, Git or private state. Output must be new and outside both inputs; new output parent directories are supported.

Run from the repository root with a separate fixture directory and finite prompt file:

```sh
python3 examples/scenarios/acceptance/native_eval.py --project /absolute/source --fixture /absolute/fixture --output /absolute/new-run --prompt /absolute/prompt.txt
```

Preparation records frozen input pins and `manifest-before.json`, copies sources/fixtures, enables native agents in the isolated config and initializes a disposable Git repository. Prepare prints `model_calls: 0`. Validation failures do not execute; a copying failure retains the partially prepared directory for inspection.

The coordinator must review and freeze inputs/prompt before explicitly adding `--run`. That single attempt uses the installed CLI with `--no-daemon`, `on-request`, `workspace-write`, inherited model/settings and a 1..900 second timeout (default300). `--cli` is an explicit installed CLI path override, not a shell command. No automatic retries occur. An attempted output cannot be reused; revise prospectively and prepare a new output for another attempt. Raw events, stderr, command, prompt, launch errors, timeout and input hashes are retained. Public observation adds at most90 seconds plus process shutdown after execution; timeout limits execution, not the whole evaluation.

`public-proof.json` records an allowlisted scalar projection of dynamic public `config/read` role metadata (description, config_file/source, model/effort), relevant model/effort settings and `skills/list` discovery metadata (name/path/description, enabled, scope/source), current native asset hashes and available thread/subagent events. Full host configuration, configuration layers, arbitrary fields and nested role/skill settings are excluded from saved discovery proof. This supports discovery of new fixture capabilities added later by root through explicitly reviewed isolated lifecycle controls. The adapter grants no lifecycle authorization and does not infer approval from asset changes. `manifest-after.json` compares pinned source/fixture/config hashes and native asset inventory; additions or drift remain visible for external review. Root must freeze approved new asset ownership and inspect their actual native discovery/invocation separately.

Every result stays **UNASSESSED**. Exit0, discovery, unit tests, synthetic CLI fixtures and prior runs are not native behavior, activation, lifecycle or acceptance proof. The adapter writes no evaluation or activation receipt. Fresh native M1 request/clarification/blocker/recovery, M2 extension/direct/indirect/unrelated/disable/rollback and delegation acceptance belong to the real coordinator and independent reviewer. The [P09 design](../../../docs/tasks/p09/design.md) defines those criteria and platform limits.

Adapter contract tests use genuine disposable input trees and an explicitly synthetic local CLI protocol fixture:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest tests.test_acceptance_native_eval -v
```
