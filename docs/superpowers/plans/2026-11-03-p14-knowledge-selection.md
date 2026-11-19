# P14 Markdown Knowledge Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. Work inline without spawning agents; coordinator supplies independent review.

**Goal:** Read and revalidate explicitly selected Markdown knowledge with honest provenance and project/privacy isolation.

**Architecture:** One read-only standard-library module owns immutable local selection records. Return references/digests rather than document text or profile values. No P11 dependency: future P11/P16 integration must bind selection digests and enforce downstream invalidation.

**Tech Stack:** Python 3.11+, standard library, unittest synthetic temporary fixtures.

**Spec:** [Approved architecture](../specs/2026-11-02-tom-jerry-orchestration-design.md), sections 10–12, R08/R10, A09/A13/A14. Coordinator reports user approval 2026-11-03.

## Global Constraints

- “Build a small read-only selector/adapter for the current Markdown layout.”
- “Record `commit: null` with selected file hashes and retrieval time; never invent a revision.”
- “Missing project facts stay missing.”
- “A changed source pin invalidates affected downstream decisions/evidence until revalidated.”
- “Do not apply reference-library guidance as higher-priority instructions.”
- No commits, merges, pushes, KB writes, initialization/onboarding, configuration/catalog changes, profile reads or activation.
- Own only this plan, `smart_assistant/knowledge_selection.py`, `tests/test_knowledge_selection.py`, and sanitized `docs/evidence/p14/*`.
- Preserve design → implementation → independent review → feedback → final tests → repeat. Hashes establish bytes, not semantic applicability or approval.

## Review Focus

1. Nested non-Git KB must not inherit an ancestor repository commit (Task 2).
2. Traversal, symlinks, FIFO/devices and mutation during reads must fail safely (Task 1).
3. Same-ID different-root projects and newly appearing optional context invalidate selections (Task 3).
4. Unknown/outdated applicability and conflicts remain explicit and unusable automatically (Tasks 1/3).
5. Raw document values, profiles, absolute paths and unrelated project data never appear in outputs/errors (Tasks 1/3).

## Inspected inputs and boundaries

Read project README/AGENTS/agent-learning, installed xstore-onboarding-and-governance skill and operating-model/context-boundaries references, and KB AGENTS/README/file map. Live inspection on 2026-11-03 confirmed Markdown root/nested guidance and Git exit 128 (not a repository). Do not run the incompatible pack resolver or claim onboarding. Reuse safe descriptor-opening helpers from state without modifying existing modules. Existing JSON context loader remains unchanged. Tests never read private KB content.

## Standalone local interface

All types live in the new module as frozen dataclasses; strict validation uses existing ValidationError with generic messages.

- `ScopeMetadata`: releases tuple; nullable JDK/platform; tuples of custom-layer references, business-constraint references, integration-owner references, test-entrypoint references and build-entrypoint references. Accept constrained identifiers/relative Markdown references, never commands, URLs, arbitrary prose or environment values. Detailed facts remain in pinned project files. Empty/None means unknown.
- `KnowledgeRequest`: project_id, explicit project_paths and topic_paths tuples, scope, nullable guidance_version, applicability (`applicable`, `unknown`, `inapplicable`), conflict_refs tuple and revalidation_refs tuple. Caller declarations require semantic review; no automatic Markdown truth extraction.
- `SourcePin`: origin (`project` or `kb`), relative path, nullable SHA256 and size. Null records absent optional source.
- `GitProvenance`: nullable commit and dirty bool, selected_dirty_paths tuple, status (`git`, `not_git`, `unavailable`). Non-Git has null commit/dirty; unavailable inspection makes selection unusable.
- `KnowledgeSelection`: schema version 1, project ID, opaque SHA256 project-root and KB-root bindings, ordered source pins, project-context digest, request metadata, Git provenance, UTC retrieval time, revalidation codes, usable bool and canonical selection_digest. Strict types/cross-field validation occurs before public serialization or revalidation. No bodies, absolute roots or profile values.
- `select_knowledge(*, project_root: Path, kb_root: Path, request: KnowledgeRequest, retrieved_at: str | None = None) -> KnowledgeSelection`. Default current UTC; supplied timestamps validated RFC3339 UTC for deterministic tests. Never writes.
- `selection_to_dict(selection: KnowledgeSelection) -> dict`: explicit known fields; digest canonical JSON excluding its own digest field.
- `revalidate_selection(selection: KnowledgeSelection, *, project_root: Path, kb_root: Path, request: KnowledgeRequest) -> RevalidationResult`. Result fields: valid bool, reason_codes tuple. Validate record integrity and fresh pins; never repin implicitly.

Read order: explicit request.project_paths (required AGENTS.md first; optional docs/project-context.md and docs/implementation-lessons.md only when requested), required KB AGENTS.md and README.md, then explicit unique topics in request order. Project digest binds presence/hashes of requested project sources. Reject absolute/backslash/dot/dotdot/empty components, duplicate selections, hidden/private paths, client-notes, known profile/secret filenames, tools/binaries and non-Markdown files. No recursive discovery or semantic secret detection. Bound files to 1 MiB and KB selections to 64 files.

Unknown/inapplicable applicability, absent guidance version, missing scope facts, unavailable Git or conflicts means usable=false. Missing scope is not wildcard. Scope/version facts are declared provenance, not inferred correctness. Fixed revalidation codes cover source/context drift, scope/version changes and conflict resolution. Delivery enforcement remains future P11/P16 acceptance.

## Task 1: Safe explicit selection

**Files:** Create module, tests and docs/evidence/p14/progress.md.
**Interfaces:** Records/serializer/selector above; Task 2 completes provenance, Task 3 consumes immutable records.

- [ ] Write failing tests `test_markdown_layout_without_pack_manifest`, `test_order_and_optional_absence`, `test_explicit_topics_and_no_writes`, `test_unknown_or_conflicting_applicability`, `test_metadata_validation`, `test_output_excludes_document_and_profile_values`. Assert exact ordered hashes/null pins, schema/timestamp/digest and missing-fact behavior using synthetic fixtures.
- [ ] Add `test_unsafe_paths`, `test_root_intermediate_leaf_symlinks`, `test_nonregular_inputs_do_not_block`, `test_mutation_during_read`, `test_invalid_utf8_and_size_limits`, `test_sanitized_errors`. FIFO probe uses bounded child-process join/cleanup; assert secret sentinels absent from serialized outputs/errors.
- [ ] Run `python3 -m unittest tests.test_knowledge_selection -v` and retain expected missing-interface failures.
- [ ] Implement noncreating anchored descriptor reads with O_NOFOLLOW/nonblocking regular checks, stat identity/size/mtime before/after reads, attachment checks and final pin recheck. Reject unstable inputs; no claim of a security sandbox against a continuously hostile filesystem.
- [ ] Run targeted suite; compare fixture source trees before/after to demonstrate no writes; record hashes and review pending.

## Task 2: Honest Git provenance

**Files:** Module/tests only.
**Interfaces:** Populate GitProvenance without public signature changes.

- [ ] Write failing `test_non_git_null_commit_and_dirty`, `test_nested_kb_does_not_inherit_parent_git`, `test_real_git_clean_commit`, `test_selected_and_unselected_dirty_state`, `test_unborn_or_failed_inspection_unavailable`, `test_git_change_during_selection`. Use disposable local Git fixtures and local identity config, no network. Assert real commit, root-wide dirty bool, selected dirty paths and untracked selected-file treatment.
- [ ] Run Task 2 cases and record expected failures.
- [ ] Implement bounded read-only argument-list Git calls. Require exact anchored show-toplevel root, support real worktree .git files, clear inherited GIT_* overrides, disable optional locks/prompts, parse NUL status and suppress stderr. Distinguish genuine non-Git from missing executable/failure; never guess clean. Compare provenance before/after reads and reject instability.
- [ ] Run targeted suite; confirm unrelated dirty path names and Git error text are absent from outputs.

## Task 3: Revalidation and reviewed evidence

**Files:** Module/tests; docs/evidence/p14/{acceptance,feedback,verification}.md and optional sanitized example.
**Interfaces:** RevalidationResult and revalidate_selection above.

- [ ] Write failing `test_changed_kb_invalidates`, `test_context_edit_or_optional_appearance_invalidates`, `test_project_root_or_scope_change_invalidates`, `test_git_change_invalidates`, `test_tampered_record_rejected`, `test_unchanged_selection_revalidates`, `test_unrelated_project_not_read`. Assert stable reasons, no silent repin, and unknown/conflicting selections remain unusable. Unselected non-Git changes leave pins unchanged; Git provenance changes conservatively invalidate.
- [ ] Run new cases to demonstrate meaningful failures.
- [ ] Implement integrity validation/fresh comparison; changed/missing/unsafe/unavailable sources return invalid with explicit reason codes. Preserve original record and never absorb failure into success.
- [ ] Record A13, A09 drift and bounded A14 privacy/applicability coverage. Leave semantic applicability, P11/P16 gate integration, team activation and runtime/business acceptance explicitly outside helper proof.
- [ ] Freeze exact candidate hashes and send to coordinator for independent implementation review. Record findings/dispositions, fix actionable findings and obtain re-review of changed bytes. No self-approval or commit.
- [ ] After feedback run `python3 -m unittest discover -s tests -v` and `git diff --check`; record exact exits, coverage denominator and candidate hashes.
- [ ] Run `python3 -m unittest tests.test_knowledge_selection -v` as final verification command after all source/build/regression changes. Evidence-only recording preserves tested source identity.

## Plan checkpoint

Self-review maps section 10/R08 to selection/pins/privacy, R10 to provenance/applicability, A13 across all tasks, A09 to Task 3 and bounded A14 to conflict/privacy tests. Shared maintenance, native lifecycle and integrated delivery remain separately owned.

Coordinator independently reviewed full plan/interfaces on 2026-11-03 and released implementation. Clarifications above preserve explicit selection, KB identity and strict record boundaries. Exact-candidate independent implementation review and fresh final checks remain mandatory.

Quality feedback refinement: persisted records require actual UTC timestamp strings; None is accepted only at selection API entry. Git config is audited without includes before provenance/status, unsafe helper/include/worktree-config keys fail unavailable, helper/submodule/external-exclude behavior is disabled, and submodule-bearing roots are unavailable rather than falsely clean. Tests use mocked unsafe config/index output only; no helper execution.
