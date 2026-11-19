# Isolated bounded delegation scenarios

Run from the project root with Python 3.11+:

```sh
python3 examples/scenarios/delegation/scenario.py positive
python3 examples/scenarios/delegation/scenario.py blocked
python3 examples/scenarios/delegation/scenario.py stale
python3 examples/scenarios/delegation/scenario.py ownership
python3 examples/scenarios/delegation/scenario.py cancelled
python3 examples/scenarios/delegation/scenario.py failed
python3 examples/scenarios/delegation/scenario.py dependent
python3 -m unittest tests.test_delegation_scenarios -v
```

Each command uses new temporary artifacts/state and real validate_handoff/TaskStore APIs. Every deterministic review/check receipt is conspicuously HYPOTHETICAL: these helpers never prove actual native agents, review, activation or concurrency. Dependent work dispatches B only after A handoff acceptance. Cancellation leaves a terminal parent and partial A output. A failed required B child preserves successful A and partial B output. Exact hypothetical assignments, handoffs and gate results are saved before parent propagation; the helper result includes those saved histories. Blocked B is recorded in the parent blockers; the actual CLI completion path rejects unresolved blockers even with otherwise complete hypothetical evidence. The raw quality completion_gate alone does not enforce dependency blockers.

## Installed-native evaluator

[native_eval.py](native_eval.py) prepares a new isolated source-evaluation project from explicit supplied native assets/helpers and fixture files. It requires the installed engineering-lead, writer and reviewer source files and delegate-work, draft-document and verify-completion skill directories. No model calls occur without `--run`. Use a fresh output path each time; failures remain preserved, with no automatic retry.

```sh
python3 examples/scenarios/delegation/native_eval.py \
  --project /absolute/reviewed/project \
  --fixture /absolute/prepared/fixture \
  --output /private/tmp/p08-native-evaluation-unique \
  --prompt /absolute/reviewed/prompt.txt
```

After coordinator source approval, append `--run --timeout 300` to that invocation using a fresh output directory. The explicit supplied prompt controls the actual configured engineering lead and delegate-work request. The [request fixture](request.md) describes the positive workflow and missing-second-input variant. Prepare fixtures containing only the frozen request/notes/design/criteria and permitted ownership instructions, excluding evaluator-owned .codex, .agents, smart_assistant, .git and private-state paths. For the blocked variant omit notes-b.md and require the successful first output be preserved. The outer CLI parent must spawn the actual configured engineering-lead; actual role/spawn identity must be checked from public thread/read metadata, never inferred from text or exit status.

The runner records exact source/fixture SHA-256 files, raw CLI events, errors, command, exit/timeout, source/fixture/config changes and bounded public parent→lead→children observations (depth two, maximum sixteen threads). Observation errors are retained. An exit of zero is UNASSESSED, and requires external independent checking of output, frozen review, concurrency, handoffs and real CLI completion. This runner does not create activation/evaluation success receipts or change canonical catalog/state.
