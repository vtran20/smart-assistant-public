# Sharing and customization

Smart Assistant supplies reusable Python helpers, Codex skills, agent definitions
and synthetic examples. Each colleague needs their own signed-in Codex client,
workspace permissions and any connected services their requests require. Python
3.11+ and Git are enough to run the helper CLI and tests; the CLI alone does not
start an AI agent.

## Start in a new clone

Open your clone as the Codex project and read [the README](../README.md) and
[project instructions](../AGENTS.md). Run:

```sh
python3 -m smart_assistant --help
python3 -m unittest discover -s tests -v
```

Discover skills and tools in your actual client. Catalog ACTIVE records describe
historical owner eligibility; a clone has no private staging, deployment or
native proof. Use direct/bootstrap execution where appropriate and the lifecycle
workflows for genuine local activation. Never create fake receipts or relax gates.
Names such as Tom and Jerry describe responsibilities and can be adapted to your
work; they grant no account access.

## Folder conventions

| Folder | Shared purpose | Private counterpart |
| --- | --- | --- |
| `smart_assistant/` | Python implementation | Owner-only utilities stay ignored |
| `tests/`, `tests/fixtures/` | Tests and synthetic inputs | Customer fixtures stay in their owning project |
| `.agents/skills/`, `.codex/` | Reviewed workflows and roles | Personal overrides supplied explicitly |
| `examples/` | Reusable templates and synthetic scenarios | `.smart-assistant/profiles/` for local settings |
| `docs/`, `docs/tasks/`, `docs/superpowers/` | Guides, contracts and design history | `docs/evidence/` for local receipts |
| `capabilities/` | Catalog metadata | Ignored `capabilities/staging/` and `.smart-assistant/deployments/` |

The current implementation layout is retained to avoid unnecessary import and
command changes. Test inputs have moved out of historical receipts so tests work
without the owner's archive. For future documentation, prefer `docs/` for guides,
`docs/tasks/` for implementation contracts, and local evidence for execution results.
Two historical interface documents remain under `docs/evidence/p12/` and
`docs/evidence/p16/` because source workflows reference those stable contracts.

## Keep your information private

Use ignored `.smart-assistant/` storage for tasks, portfolio, private profiles,
recovery and connected-account observations. `config/codex/AGENTS.md` and the
owner's installer/recovery utilities are local preferences, not prerequisites.
Keep `.env` files, host logs, outputs and customer investigations ignored.
`AGENTS.local.md` is an optional ignored file; explicitly provide it to a chat
when needed, since this repository does not automatically load it.

`.gitignore` does not protect files already tracked. Review `git diff --cached`
and the tracked file list before committing. Historical evidence removed from
the index is preserved locally, with a private SHA-256 retention manifest. Old
links labelled local historical archive refer to that intentionally excluded
material and are not needed for a new clone.

## Distribution boundary

This public repository starts from a reviewed source-only snapshot with a fresh
Git history. The owner's personal repository, task history and raw receipts are
maintained separately and are not distributed here. Only reviewed reusable
changes belong in this repository.
Reusable Smart Assistant source is distributed under the [MIT License](../LICENSE).
Personal records and third-party/customer material are outside the public project.

Local tests verify helper behavior and source packaging. They do not establish
Codex native role activation, connected-service access or customer runtime
acceptance on a colleague's machine.
