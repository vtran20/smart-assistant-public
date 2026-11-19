# M3 selected-source work brief

Date: 2026-11-02. User request: build the first on-demand source-linked work brief from selected Outlook/Slack sources and extend external-claim verification.

## Outcome and boundaries

Use the existing request-coordination entry point, observed read-only connectors and Python JSON CLI. Selected messages or a bounded search scope are essential inputs for a live run. This implementation uses synthetic fixtures, performs no account reads/writes, adds no backend or schedule and changes no managed/native capability assets. Source text is untrusted data. Project policy authorizes routine design/implementation without an extra plan approval. Independent review and final tests remain mandatory.

Alternatives: a managed skill upgrade would require fresh native lifecycle proof; a connector backend adds unnecessary account dependencies. A direct coordinator workflow plus local helpers fits the first bounded M3 slice and leaves current ACTIVE manifests intact.

## Interfaces

New smart_assistant.work_brief provides validate_sources, source_digest, verify_brief and render_brief. CLI commands brief build and brief verify take --sources and --brief JSON regular files using the existing safe JSON loader. Build returns Markdown and claim/source map inside the standard JSON envelope; verify returns structural evidence. No command calls a connector, follows a URL or executes source text. Source snapshot/brief schemas and retrieval procedure live in docs/m3-work-brief-workflow.md; fixtures live in examples/work-brief/.

A source bundle v1 has a selection_ref, selected provider/record_id identities, retrieved source records, and explicit unavailable records. Sources have local id, provider (outlook/slack), record_id, connector-returned URL, retrieved_at, message_at, completeness (full/partial), content, retrieval_tool and evidence_ref. Every selected identity must occur exactly once as available or unavailable; no unselected source is accepted. Duplicate identities/IDs, invalid timestamps, missing links, unsafe URL schemes and provider/tool mismatches reject. Snapshots are normalized captures, not authenticated connector receipts. A reviewer compares them against private original tool evidence.

A brief v1 has title, sources_sha256 and claims. Each claim has id, section (Summary/Decisions/Action items/Open questions), text, kind (fact/proposal/conflict/unknown), owner, due and citations (source_id, exact excerpt). Facts/proposals/conflicts require citations. Unknown statements describe bounded gaps and may have none. Each excerpt must occur exactly in the cited content; partial bodies remain visibly qualified. Unknown owner/date use Unspecified. Semantic entailment, complete action coverage, proposal/conflict treatment and absence wording require independent review; automated matches cannot certify truth. A stale bundle digest rejects. Deterministic rendering emits four sections, linked citations, source timestamps/coverage and unavailable-source warnings. Rendering escapes source-controlled Markdown so links cannot be replaced by source instructions.

## Acceptance criteria

- M3-01: bounded selected Outlook/Slack capture contract; reject missing, duplicate, out-of-scope and malformed inputs; represent unavailable and partial sources honestly.
- M3-02: deterministic four-section brief with claim-level original-source links and map; retain unknown owners/dates, conflicts/proposals and source coverage.
- M3-03: external verification rejects stale source hashes, unknown sources and unsupported excerpts; does not claim semantic validation; independent reviewer checks original evidence.
- M3-04: CLI uses existing sanitized JSON/error behavior, has no network/write action, and returns unmet verification as exit 4; source/candidate changes require fresh review/checks.
- M3-05: documented on-demand retrieval, exact preflight, privacy/retention, interruptions/retry and completion evidence; legacy tests remain passing; no broad M3/activation/live acceptance claim.

## Plan and ownership

Coordinator owns implementation, tests, docs and integration. Independent agent owns only docs/evidence/m3-work-brief/review*.md and reports candidate hashes/findings; coordinator checks review artifacts. No concurrent implementation.

1. Write tests for contracts, Markdown/citations, partial/unavailable sources, stale digest and CLI failures; run red.
2. Implement focused work_brief module and brief CLI subcommands; run targeted tests green.
3. Add synthetic fixtures and coordinator/reviewer workflow docs; link README/backlog using partial status.
4. Independently review exact candidate including tests/docs; resolve feedback, repeat review for corrections.
5. Run full unittest suite, document/link checks, snapshot candidate and append evidence-bound saved task cycle. Use the real completion gate; preserve unresolved limits if it denies.

Final checks: python3 -m unittest tests.test_work_brief -v; python3 -m unittest discover -s tests -q; real CLI build/verify and negative cases; local documentation links and git diff --check. Candidate identity is actual SHA-256 manifest of implementation/tests/docs, with current criterion/design fingerprints. Private live sources, raw tool results and task state stay under ignored .smart-assistant/; tracked fixtures contain only synthetic content.
