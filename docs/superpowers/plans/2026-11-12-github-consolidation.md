# GitHub consolidation implementation plan

Goal: publish all current reviewed project source on clean-history main and explain
Tom's architecture, setup and supported capabilities in README.

Design: acceptance, ownership and constraints (local historical archive: `../../evidence/github-consolidation-20261112/design.md`).
Existing user instructions authorize autonomous implementation/review/testing and the
user selected clean-history publication; no additional routine design approval.

- [x] Inventory local/remote refs and worktree changes; preserve source identities.
- [x] Verify each unmerged branch's changed-path content against main; record safe
      equivalent merges; retain divergent older worktree variants separately.
- [x] Include current project source/tests/config/agents/skills/examples/designs;
      exclude ignored runtime, customer evidence and raw signed-URL logs.
- [x] Rewrite README with architecture/flow diagrams, actual quick-start commands,
      capability inventory, fresh-clone limits and remaining activation requirements.
- [x] Independently review the exact publication candidate and supporting private
      record updates; resolve feedback without changing feature acceptance gates.
- [x] Parse Mermaid and local links; validate JSON, catalog, CLI and run all tests.
- [ ] Commit and publish clean main with an exact remote lease; verify remote hash,
      clean local state, exclusions, preserved history and task evidence.

Review focus: stale branch resurrection; omitted uncommitted source; accidental
private/history upload; ACTIVE/DRAFT and clone/runtime confusion; broken diagrams,
links or startup commands. Root integrates; auditors are read-only; one independent
reviewer checks the final candidate. Record actual outcomes in the evidence package.
