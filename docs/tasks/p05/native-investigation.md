# P05 native loading investigation

User scope: investigate P05 while preparing P07's design in parallel. Baseline 472b99c. Keep accepted helper/skill/agent source and the canonical catalog unchanged. P07 is documentation-only in this turn. Root owns this investigation and Git integration; independent reviewers own reports that root checks without reviewer recursion.

## Questions and method

1. Reproduce the observed native role-selection gap with the currently installed bundled CLI and public configuration/schema/prompt interfaces.
2. Separate project-layer trust loading from native role declaration/selection. Prior runtime trust flags did not enable project layers; prior --ignore-user-config sessions must not be mistaken for ordinary configured sessions.
3. Compare current official standalone-agent and agents.<name>.config_file guidance to actual strict native configuration parsing. Use one-variable local/session-only probes against exact reviewed researcher bytes in isolated fixtures.
4. Inspect actual model-visible tool schemas and role discovery through supported public interfaces before considering another model invocation. A name, copied instruction prompt, file presence, or generic child is not configured-role proof.
5. If a supported invocation route exists, evaluate it with source/version/complete-manifest/client/session bindings. Otherwise produce an exact diagnosis, reproducible evidence and concrete next steps, leaving configured-agent acceptance incomplete.

No global trust/configuration edits, credentials copies, private database reads, installation/update, permission bypass, live task state or external accounts. Session flags may declare a role using documented settings, but must not weaken sandbox/approval/managed requirements. Fixtures and scratch logs are private under /private/tmp or ignored work. Committed observations filter out unrelated personal configuration/context.

## Required cycle and acceptance

Design is this note; implementation means public diagnostic probes and a source-backed report, not an unproven helper fix. Obtain independent review of exact report/evidence, dispose feedback and freshly run relevant probe/evidence/document checks. Do not rerun paid model requests or identical full suites without a new concern. Investigation is complete when supported routes and blockers are distinguished with evidence and remaining acceptance is explicit; it does not close P05's native behavior/deployment criteria without genuine proof.

References fetched 2026-10-13: [subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference), [configuration basics](https://learn.chatgpt.com/docs/config-file/config-basic).
