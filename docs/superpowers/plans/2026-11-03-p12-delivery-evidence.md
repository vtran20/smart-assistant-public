# P12 delivery evidence implementation plan

Goal: enforce declared-level bug reproduction and complete requirements/test coverage on current immutable evidence. Hashes do not establish semantic or native proof.

Spec: [approved architecture](../specs/2026-11-02-tom-jerry-orchestration-design.md), sections 7–8 and A06–A10.

## Ownership and constraints

Own smart_assistant/delivery_evidence.py, tests/test_delivery_evidence.py and docs/evidence/p12/ only. Root owns contracts/state/CLI/catalog. Keep v1 unchanged. Isolated synthetic fixtures; no commits, merges, pushes, external writes or child agents. Design → implement → independent review → feedback → fresh tests → repeat. Two specialists maximum/tree, three correction cycles/dispatch.

## API

`evidence_from_dict(data) -> EvidenceBundle`, `evidence_to_dict(bundle) -> dict`, `evidence_digest(bundle) -> str`, `validate_delivery_evidence(task, delivery, bundle, artifact_root: Path) -> GateResult`. Use strict local schema1 records, existing canonical_json/ValidationError/ErrorDetail/GateResult. No command execution. Freeze detailed fields in docs/evidence/p12/interfaces.md for root review before code.

EvidenceBundle binds task_id, delivery_revision, digest of current DeliveryPlan, actual final candidate_id and acceptance_id, requirement/case matrix, immutable evidence entries and observed review references. Before entries bind the baseline; after/test/review entries bind the final candidate.

EvidenceEntry: unique ID; safe relative evidence path/hash; requirement/case/scenario IDs; before/after/test/review/observation kind; declared proof level; UTC capture time; actor/run/capture-source references; environment/build/input hashes; baseline/final candidate binding; expected/observed outcome; command+exit or observation; privacy classification; independent semantic assessment reference. Assessment/receipt references themselves must bind actual regular file hashes. References are consistency checks, not cryptographic host authentication.

VerificationCase: unique ID; valid requirement IDs; scenario; required flag; applicability rationale/review; expected result; required levels; pass/fail/blocked/not_run/not_applicable status; before/after/test evidence IDs. Every task criterion needs passing required coverage. Every required case passes; none can be waived as nonapplicable. Optional cases do not fill required gaps.

Observed review records bind distinct actual implementer/reviewer run references, current candidate/acceptance and semantic evidence. Different labels with the same observed context do not establish independence. Actual observations must come from host execution; JSON alone cannot prove origin.

## Tasks

1. Write failing strict-decoding tests: duplicate/unknown/missing fields, types, invalid dates/hashes/IDs, bool integers, unknown criteria, inconsistent observations/provenance. Implement deterministic encoding/digest without v1 registry changes. Feature/research/document cases do not fabricate bug baselines.
2. Write missing/tampered/symlink/FIFO/traversal evidence tests, stale candidate/design/acceptance/plan/revision cases, altered receipts, wrong-case reuse and product-as-evidence rejection. Implement anchored bounded reads and immutable hash binding. Derive current candidate/acceptance through existing quality APIs; claimed digest alone is insufficient.
3. Write bug-policy failing cases: no before, wrong symptom/scenario/input/environment, unexplained differences, missing final after/regression or proof levels, fabricated evidence declarations. Validate before/after pairing at declared scope; fixture success never satisfies POS/runtime. Check every required case and criterion bidirectionally, blocked/not_run/invalid waiver, stale or absent independent semantic review. Preserve honest limits.
4. Freeze candidate, obtain independent spec+quality review, record dispositions, correct and re-review changed bytes; run fresh focused/full suites and retain exact commands/outcomes/hashes. No native activation or runtime completion claim.

## P16 boundary

P16 stores immutable evidence bundle revisions/digests and passes actual registered task/delivery under shared lock. Missing required bundle fails closed. P12 does not mutate parent state, select roles, launch tools, authorize actions or enforce whole-tree scheduling. Those remain P16 obligations. Native discovery and customer-runtime acceptance remain separate.
