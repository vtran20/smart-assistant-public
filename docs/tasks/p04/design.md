# P04 coordinator and CLI design

Baseline: 04c8a5b. Scope is the command interface, bootstrap request-coordination skill, subprocess behavior tests, and finite coordinator evaluation scenarios. Accepted P00–P03 helpers remain unchanged. Codex interprets intent; this CLI never routes by keyword or executes tools/accounts.

## Interfaces and decisions

`main(argv: list[str] | None = None) -> int` backs `python3 -m smart_assistant`. Commands and flags match P04: task create/show/update/complete, catalog validate/eligible, preflight. Every response is one JSON `{ok,data,errors}` object on stdout with no stderr/traceback: 0 success, 2 invalid input, 3 revision conflict, 4 unmet gate. Help returns `{ok:true,data:{help:...},errors:[]}` and 0; missing/unknown flags return a fixed argument error and 2. Errors preserve stable safe codes while replacing exception messages and paths with fixed descriptions, because contract/catalog error text may contain supplied values. Success data intentionally contains the requested task/catalog/preflight records; callers must keep private runtime inputs private.

Inputs are UTF-8 regular JSON files with no duplicate keys or nonfinite values; P00 decoding handles all typed records. Tools are a list of nonblank strings. TaskStore is always composed with the real P03 completion_gate plus unresolved-blocker rejection. Completion via either update or complete has the same gate; no hidden project-root/tool-inventory global is required. Catalog and observed tool checks belong to the orchestration skill immediately before dispatch. Catalog validate returns GateResult, eligible returns typed records, preflight returns PreflightResult. Non-ready preflight has data explaining missing tools/pending actions and fixed top-level errors.

Update is explicit: a supplied failed→running proposal invokes P01.resume_failed under the same expected revision and immutable-request checks. Other transitions invoke update. Existing CycleEvidence entries form an immutable prefix: evidence is appended as complete cycle records, never edited or dropped; corrections append a fresh cycle with current candidate/acceptance/review/checks. The proposed record still carries the currently expected revision; persistence increments it. Rejected updates preserve saved bytes. CAS and single coordinator writing prevent a competing update from accepting an obsolete history check.

## Coordination workflow

The skill discriminates durable local task/workflow coordination from simple questions. It reads project-scoped context and only a selected role overlay; observes the actual current tool inventory; checks eligible catalog records before selecting/delegating; and records catalog revision plus exact ID/version/deployed manifest. Empty catalogs allow direct bootstrap work with empty selections, without fabricating ACTIVE capabilities. Previously selected stale or ineligible assets cannot dispatch. Explicit user authorization references/destination and actual host decisions feed preflight; role tool dependencies grant no consent. Critical missing input causes a focused clarification; reversible work uses reasonable assumptions. Interrupted records preserve blockers and next step; failed resume uses task update.

Task records contain criteria, request/source references, scoped authorization/actions, exact selections, limits, artifact root and next step. Design comes before changes. Every task, including skill/agent work, follows design → implement → independent review → feedback → test → repeat. Completed cycles bind artifact and acceptance snapshots, reviewer/implementer identities, feedback dispositions and criterion-covered checks. Review-only findings are checked by the coordinator without infinite recursive review. Completion requires current passing evidence and resolved blockers.

## Acceptance and verification

- Subprocess tests exercise all commands, help/argument failures, malformed/secret-bearing input, duplicate records, stale revisions, explicit resume, history truncation/editing, valid completion, stale artifact/criterion evidence and blocker denial through both completion paths.
- Temporary catalog deployment fixtures prove eligibility excludes missing tools/disabled/drifted assets. No fixture is native discovery evidence.
- Five finite scenario requests specify observable outcomes for ordinary, ambiguous, unrelated, interrupted and missing-tool/stale-selection decisions. Structural checks and helper tests do not establish semantic behavior.
- Preserve preimplementation RED, targeted/full GREEN, command/runtime and product hashes under docs/evidence/p04. Self-review is preparatory; root supplies independent candidate review and records feedback, followed by fresh tests. Root owns installed native evaluations and deployment; no native discovery/invocation is claimed by this package.

Owned paths: smart_assistant/cli.py, smart_assistant/__main__.py, tests/test_cli.py, .agents/skills/request-coordination/**, examples/scenarios/coordinator/**, docs/tasks/p04/**, docs/evidence/p04/**. Final handoff freezes product hashes and commit while independent/native acceptance stays pending.
