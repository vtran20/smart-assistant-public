---
name: manage-skill
description: Use when asked to add, update, disable, or roll back a repeatable Smart Assistant skill.
---
# Manage a skill

Use when the user requests a skill lifecycle change. Establish the repeatable
workflow, triggers, required inputs, output and tool dependencies; an ordinary
one-off request does not imply creating a skill. Read project AGENTS.md and the
P06 design. Follow design → implement → independent review → feedback → testing
→ repeat until acceptance criteria pass for every change.

Use `validate_skill_definition` and `stage_skill` from
`smart_assistant.skill_lifecycle`. Stage only normalized DRAFT SKILL records;
use minimal name/description scalar metadata and keep optional resources inside
the complete skill directory. Unsupported metadata needs a supported host
validation strategy or a rewritten minimal definition, not invented parsing.
Default implicit invocation stays enabled; do not add an explicit-only policy
without a user request.

Staging supplies structural proof only. Obtain independent review, resolve
feedback, and evaluate behavior on direct, indirect, unrelated, incomplete-input
and failed-tool requests against the complete staged manifest. Save actual
observations as manifest-bound evaluation evidence; missing or failed cases
leave the candidate DRAFT. Read [transaction steps](references/transactions.md)
for add/update, disable and rollback.

Return the candidate ID/version, complete manifest, staged/native paths,
validation/evaluation evidence, review feedback and current transaction state.
Verify these against current files and fresh native observations. File presence,
fixtures, guessed tools and old discovery receipts cannot establish ACTIVE.
Bootstrap management remains available to establish the catalog; additional
workflow routing uses verified ACTIVE records. Preserve user authorization;
this skill creates no account access, external writes or recurring work.
