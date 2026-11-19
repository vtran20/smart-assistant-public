# Smart Assistant Agents Skills and Automation Draft

The assistant should accept requests in one Codex chat and choose the appropriate capability automatically. It should also let the user add agents and skills through chat and introduce recurring work once a workflow is reliable. Start with a Codex project and file-based state; introduce a backend only when the required scheduling or orchestration exceeds the native client.

This draft defines candidate behavior for the capability backlog. It does not install agents, create skills, grant access, or enable routines.

For detailed component contracts and coordination diagrams, use the [system design](superpowers/specs/2026-10-12-smart-assistant-system-design.md). The [implementation plan](superpowers/plans/2026-10-12-smart-assistant-implementation-plan.md) divides the selected foundation into parallel packages. All project workers must follow [AGENTS.md](../AGENTS.md), including independent review, recorded feedback, and final testing after corrections.

## Roles workflows and triggers

| Component | Responsibility | Example |
| --- | --- | --- |
| Agent | A role with instructions, relevant context, and selected tools | Writer |
| Skill | A repeatable procedure with inputs, outputs, and verification | Draft a weekly status report |
| Tool | An executable capability exposed by a connector, MCP server, CLI, or browser integration | Retrieve Jira issues |
| Routine | A trigger that invokes a defined workflow | Produce the weekly report on Friday |
| Coordinator | Selects capabilities, manages dependencies, and returns the combined result | Route a Jira report request to research and writing |
| Capability manager | Adds and validates agent definitions and skills | Add a travel research specialist |

Agent roles do not need separate, permanently running processes. Use a specialist only when the task benefits from its instructions or independent work. The coordinator can execute a simple skill itself.

## Request execution

1. Capture the outcome, destination, relevant project, and completion criteria.
2. Load relevant preferences and the active capability catalog.
3. Select a skill and any necessary specialists. Treat a direct role request as a routing preference within that role's scope.
4. Check tool availability and authorization before starting dependent work.
5. Record a small execution plan. Run independent tasks in parallel only when useful and permitted; serialize dependent work and conflicting writes.
6. Verify the artifact or actual destination state. Correct recoverable failures within the workflow's limits.
7. Deliver the result with evidence and unresolved limitations, then preserve task state.

A missing skill does not automatically require a new agent. The coordinator can handle a one-off task directly. If a workflow will recur, it can propose a reusable skill; creating and enabling that skill follows the user's requested scope.

Codex can delegate when asked directly or when applicable project or skill instructions request delegation. Put the intended delegation rule in the future project instructions; available tools, permissions, and session limits still govern execution. [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)

## Adding an agent

Example request: "Add a travel researcher that compares flights and hotels and prepares options for me."

The proposed S03 flow is:

1. Check for an existing role with the same responsibility.
2. Describe the new role's purpose, inputs, expected output, tool dependencies, and boundaries. Ask only for missing information that changes the design materially.
3. Create a project-scoped definition in the installed client's supported format.
4. Evaluate an ordinary request, an out-of-scope request, and a missing-tool case.
5. Register the validated role, record its version, and verify that the current client can select it.
6. Report how to invoke it directly and which requests should route to it automatically.

The proposed registry tracks a stable ID, name, description, definition path, responsibilities, tool dependencies, relevant context files, lifecycle state, version, and validation evidence. States are Draft, Active, Disabled, and Retired.

An Active role is available to route work. Disabled and Retired roles cannot be selected. Adding a role does not grant new account access or create an independent scheduled service.

Local Codex clients support project-scoped custom agent TOML definitions under `.codex/agents/`. Verify the installed client's supported configuration before implementation. [Custom agent definitions](https://learn.chatgpt.com/docs/agent-configuration/subagents)

## Adding a skill

Example request: "Add a skill that summarizes my open Jira issues and drafts a weekly update in my preferred format."

The proposed S04 flow is:

1. Check for an existing skill or overlapping workflow.
2. Define its trigger description, required inputs, output format, relevant tools, decision points, and completion checks.
3. Create its `SKILL.md` and any necessary references or scripts.
4. Evaluate direct and indirect requests, incomplete inputs, an unrelated request, and a tool failure.
5. Register a validated version and confirm that the client discovers and can use it.
6. Keep a known working version so an unsuccessful update can be rolled back.

The catalog tracks a stable ID, description, path, version, input and output contract, tool dependencies, lifecycle state, applicable agents, and validation evidence. Keep each description focused so overlapping triggers do not make routing unreliable.

Project skills can be authored under `.agents/skills/<skill-name>/SKILL.md`. Codex can choose a skill implicitly when its description matches the request; explicit invocation remains available. Skill discovery and catalog registration must both be verified before activation. [Codex skills](https://learn.chatgpt.com/docs/build-skills)

## Three kinds of automatic work

| Mode | Trigger | Proposed behavior | Delivery milestone |
| --- | --- | --- | --- |
| Chat request | User sends a request | Select workflow, execute authorized steps, verify, and respond | M1 and M2 |
| Scheduled routine | Explicitly requested cadence | Invoke a proven workflow, save the run result, notify on meaningful findings | M4 |
| External event | Supported app event or a backend webhook | Select the associated workflow and deduplicate the event before execution | M4 where supported; otherwise later backend work |

Automatic request routing is the first goal. A request such as "summarize these issues" should not silently create a repeating schedule. A request such as "do this every Friday" defines recurring intent, but still requires a supported scheduler and the required tool access.

Native local scheduled tasks need the computer on and the desktop app running. Supported event-triggered tasks are available on eligible plans on web and mobile, not in the desktop app or CLI. They depend on supported services and workspace settings. A custom event listener or always-on local service is additional implementation, not a feature supplied by writing `SKILL.md`. [Scheduled task capabilities](https://learn.chatgpt.com/docs/automations?surface=app)

## Task state and recovery

Use task records separate from the capability backlog. Backlog status describes whether a capability exists; task status describes one execution of that capability.

Each future task record should include:

- Task ID, source request, project, and source record references.
- Selected agent and skill versions.
- Completion criteria, current step, dependencies, and outputs.
- Relevant authorization and any pending approval.
- Attempt history, verification evidence, blockers, and resume instructions.
- External action IDs or deduplication keys where applicable.

Proposed execution states are Queued, Running, Waiting for input, Waiting for approval, Verifying, Completed, Failed, Paused, and Cancelled. An interrupted run resumes from observed state; it must check whether an external action already succeeded before retrying it. Prefer one writer per shared record or file to avoid conflicting updates.

## Autonomy boundaries

Execute authorized research, drafting, local artifacts, and selected implementation steps without unnecessary interruptions. Preserve the user's explicit authorization throughout the task.

Before sending, publishing, purchasing, deleting, or changing access, apply the applicable authorization and approval requirements. A skill or agent definition cannot override platform permissions or authorize actions on the user's behalf. Prepare the concrete result before a required final approval whenever possible.

An extension request can authorize creating a new role or skill. It does not authorize silently connecting new accounts, expanding permissions, or creating indefinite recurring tasks.

## Initial capability set

Keep the initial set small and extend it through S03 and S04.

| Proposed role | Initial responsibility |
| --- | --- |
| Coordinator | Receive requests, load relevant context, route work, maintain progress |
| Researcher | Retrieve evidence and summarize findings |
| Writer | Produce drafts and deliverables in the user's format |
| Reviewer | Check completion criteria and evidence |
| Capability manager | Add, evaluate, update, disable, and version capabilities |

Add an engineering lead, designer, personal assistant, or integration specialist when a selected workflow needs that role. The groups in the backlog organize responsibilities; they do not require ten separate agents.

Suggested first skills are request coordination, source-backed summarization, document drafting, and completion verification. Add a Jira weekly report after the appropriate connection is available and its output contract is defined.

## Limits and notifications

Start with bounded concurrency and explicit limits on retries and execution time. Record usage where the runtime exposes it; do not present estimated spending as a measured hard budget. A reliable cross-run spending cap needs enforcement in a runtime or service, beyond prose instructions.

Recurring workflows should notify on meaningful changes, completion, failure, or required user action. Suppress repeated unchanged findings. Pausing a routine prevents future runs; cancelling an active run stops further work where supported and records any external actions already completed.

## Example management requests

- "Add a researcher for Oracle Retail documentation."
- "Teach the writer my weekly report format and save it as a skill."
- "Use the reviewer to check this result."
- "Disable the travel specialist."
- "Show active agents, skills, and their dependencies."
- "Run the weekly report now."
- "Schedule this report for Friday at 9 AM America/Detroit."
- "Pause the weekly report routine."
- "Resume task TASK-001 from its last verified step."

These are target interactions for the proposed system. Each becomes available after its corresponding backlog capability is implemented and validated.
