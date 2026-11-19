# Report, source map and handoff contract

## Report

Use one Markdown title and exactly these four H2 sections, once each and in this order:

1. `## Summary`: supported outcomes/status, preserving uncertainty.
2. `## Decisions`: actual recorded decisions; distinguish proposals.
3. `## Action items`: every supported commitment or requested follow-up.
4. `## Open questions`: recorded unresolved questions or conflicts, without invented filler.

Keep the report concise for the requested audience. Title/style assumptions may be reversible, but cannot add facts. Include explicit source-bounded content in sections without coverage, such as “No decisions recorded in the supplied notes.” For expressly supplied empty notes, each section states that no information was supplied. Empty notes are not unreadable or absent notes.

Default action layout:

| Action | Owner | Due date |
| --- | --- | --- |
| Supported follow-up | Exact supported owner, otherwise Unspecified | Exact supported date, otherwise Unspecified |

Equivalent clear prose or bullets are allowed. Preserve the source's known names/dates; do not attach attendance, a meeting date, a suggestion or host time to an action. Keep disputed deadlines explicitly unresolved rather than choose one. Do not mark follow-ups complete without source evidence.

## Source map

Write a separate Markdown source map covering every factual report claim and every meaningful absence claim (including unknown owners/dates and empty sections). A row can cover repeated occurrences of the same claim if it identifies each section. Each row gives the report section/claim, original source reference, line range or supporting quotation, and the interpretation/qualification that connects evidence to the claim. Use bounded inspected-source references for absence claims, and record the exact zero-byte source for an expressly empty input. Do not manufacture line numbers in an empty file.

For example, from “Someone should confirm the training slot; owner and date not decided,” map both the follow-up and its `Unspecified` values to that quotation. State that neither ownership nor deadline was recorded. Reviewers must inspect the original frozen source; the map is an aid, not independent proof.

## Managed writer handoff

Use only the existing v1 `Handoff` fields: `schema_version` (1), `task_id`, `assignment_revision`, `role_id`, `result`, `artifacts`, `criteria_coverage`, `evidence_refs`, `blocker`, `next_step`. Copy task/revision/role identity from the current actual `TaskAssignment`; never create a guessed assignment or record fields.

Each artifact has only `id`, safe artifact-root-relative `relative_path`, and the SHA-256 of its actual saved bytes in `sha256`. Include report and source map, not hypothetical files. `criteria_coverage` maps actual assignment criterion IDs to existing local references; it records addressed scope, not a passing review. Leave uncovered criteria absent rather than claim native, gate or resume proof. `evidence_refs` contain only existing local evidence supplied or produced within authorization, never expected examples as observed results.

A produced candidate returns `result: ready_for_review`, `blocker: null`, and a next step to freeze/hash the candidate and obtain independent source review followed by feedback and fresh checks. Missing essentials return `result: blocked`, a specific missing-source/tool/destination reason and a precise next step; include only real partial artifacts. If required hashing or safe file writing cannot be performed, report the actual tool blocker. A direct writing request without a managed assignment may deliver its authorized outputs and review needs without inventing v1 task identity.

The writer owns only the assigned report/source map. It does not write task state, findings, review/check receipts, lifecycle proof, catalog status or completion records. After correction or interruption, the coordinator supplies a current assignment and repeats eligibility/preflight; preserve failed history and partial progress through the handoff without editing earlier evidence. Final task completion belongs to the coordinator's current-byte evidence gate.
