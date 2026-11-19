# P16 mandatory delivery integration plan

Spec: [Tom/Jerry architecture](../specs/2026-11-02-tom-jerry-orchestration-design.md), sections 5–9, A01–A20. User approved continuous implementation2026-11-03. Root owns state.py/cli.py/bootstrap coordination; workers may change them only through an explicit reassigned integration worktree.

## Binding decisions

- Existing v1 wire schemas remain unchanged. Registered delivery uses immutable reserved policy ref defined by P11; unsupported/malformed ref or existing inconsistent delivery directory fails closed. Legacy tasks remain readable; migration means a new linked task.
- Mandatory history preservation/consecutive cycle validation goes into TaskStore shared mutation path. Every supported completion path runs mandatory delivery checks for registered requests before any supplied callback; callers cannot replace them with a passing lambda.
- TaskStore already holds the same per-task lock as DeliveryStore. Do not call DeliveryStore.read/locked while holding it: use an explicit trusted already-locked reader adapter that opens/validates the same anchored directory/lock context. Review API agreement with P11 before implementation.
- Validate actual current task from disk plus proposed completion and persisted authoritative delivery/evidence state under that lock. Proposed store revision is current+1; distinguish delivery's independent revision from task revision. No stale state accepted based on caller copies.
- A registered task can exist queued before registration; dispatch/completion is denied until registration validates. CLI create operation preserves incomplete registration rather than rolling back history.
- Mandatory gate composes current quality gate, unresolved blockers, required accepted assignment graph, no ambiguous/live unconfirmed runs, exact plan/candidate/context and P12 matrix/immutable evidence checks. P11 structural acceptance does not replace independent review or actual host observations.
- Evidence bundles are private immutable revisions under registered delivery storage, with atomic authoritative head and exact delivery-plan binding. Missing/tampered/stale bundle or receipts deny completion. P12 owns format; P16 owns persistence/consumption and reports actual coverage.
- Tom bootstrap consumes the team display profile; Jerry remains engineering-lead. Source DRAFT does not become eligible. Semantic request routing remains Codex workflow; helpers persist/validate decisions, not an invented deterministic understanding engine.

## Implementation tasks

1. Agree already-held-lock and evidence-head contract with accepted P11/P12 interfaces. Write targeted failing tests for direct TaskStore completion with alternative passing callback, CLI complete/update, missing registration/evidence and immutable history mutation. Preserve legacy transition/error expectations and avoid breaking existing accepted cycles.
2. Implement mandatory shared-store gate and safe already-locked adapter. Keep imports acyclic via local imports where needed. Test concurrent task/evidence updates, interrupted registration, stale/malformed records, symlink/FIFO/hardlink/attachment behavior and no nested-lock deadlock (bounded process tests).
3. Add local CLI delivery create/show/update/evidence/check commands with strict input decoding and sanitized errors. Exact action preflight/observed tools and eligibility remain required in coordinator workflow. Helpers do not execute user commands or grant consent.
4. Extend bootstrap coordination and delegation references with Tom/Jerry profile consumption, scoped routing, actual assignment/run binding, reproduction-first behavior and required matrix/evidence checkpoints. Keep active managed source updates separate, versioned and reviewed; do not edit deployed lead instructions in place.
5. Perform a safe seeded local bug end-to-end: reproduce failing actual command and save before output; implement in owned temporary project; obtain independent exact-candidate review; repeat original scenario and save after output; run required tests; persist assignments and real observed review/check evidence; invoke actual gate. Negative paired cases deny missing baseline/required case/review/child/runtime evidence. Seeded local proof never means Xstore runtime acceptance.
6. Independently review exact combined candidate, fix supported findings, re-review corrections and run fresh full/targeted suites. Map all A01–A20 to actual observed evidence and remaining native/runtime limits; never manufacture passing receipts. Complete project task only when all its criteria pass.

## Review checkpoints and exclusions

No commits, main integration, push, messaging, customer runtime actions or real shared KB changes without applicable authority. Native source-binding limitations do not block safe helper development but block role activation and any corresponding acceptance claim. If installed client cannot provide required proof, preserve DRAFT and a concrete blocker rather than weaken checks. P15 shared maintenance policy is independently accepted; native evaluation uses a reviewed finite allocation, not existing Xstore allocation.
