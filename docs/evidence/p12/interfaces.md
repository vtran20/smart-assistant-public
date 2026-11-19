# P12 interface proposal — 2026-11-03

Status: root independently approved 2026-11-03 before code; hash-scope amendment approved before gate implementation. Correction round 1 provenance/completion refinement independently approved by root before correction code. Frozen v1 unchanged.
API: evidence_from_dict(dict) -> EvidenceBundle; evidence_to_dict(bundle) -> dict;
evidence_digest(bundle) -> str; validate_delivery_evidence(task, delivery, bundle,
artifact_root: Path) -> GateResult. No command execution or state mutation.

Frozen dataclasses. All fields required, unknown rejected. IDs use P11 syntax;
digests lowercase SHA256; explicit real UTC; exact safe POSIX paths; bool != int.
Lists reject duplicates. Null only as indicated.

## Exact fields

- HashedReceipt(path: path, sha256: digest). Actual regular file, anchored no-follow
  nonblocking bounded 16 MiB reads. Reject symlink, FIFO, traversal, missing, changed
  hash and product-as-evidence including hardlinks.
- RunObservation(id: ID, run: P11 ObservedRun, receipt: HashedReceipt). Receipt JSON
  equals complete encoded run. Run exactly matches observed/terminated dispatch.
  Same host/run OR observation_ref is same context despite different actor labels.
- EvidenceEntry(id: ID, receipt: HashedReceipt, requirement_ids: list[ID], case_id: ID,
  scenario_id: ID, kind: before|after|test|review|observation, proof_level: text,
  captured_at: UTC, observation_id: ID, capture_source: text,
  environment_sha256: digest, build_sha256: digest, input_sha256: digest,
  candidate_id: digest, expected_result: text, observed_result: text,
  outcome: pass|fail|blocked, command: text|null, exit_code: int|null,
  observation: text|null, privacy: public|internal|restricted,
  semantic_review_id: ID). Command/exit paired, otherwise observation required.
  Passing command exits zero. Before candidate binds baseline; others final.
- VerificationCase(id: ID, requirement_ids: list[ID], scenario_id: ID, required: bool,
  applicability_rationale: text, applicability_review_id: ID|null,
  expected_result: text, required_levels: list[text],
  status: pass|fail|blocked|not_run|not_applicable, before_ids: list[ID],
  after_ids: list[ID], test_ids: list[ID], differences: text|null,
  differences_review_id: ID|null). Required cannot be waived. Every criterion
  requires passing required coverage. Exact case/scenario/requirements/result
  entry bindings; proper kinds. Required policy levels included. Final after and
  regression evidence cover each required level; bugs need failing before too.
  Input/environment changes need explicit explanation and independent review.
- SemanticReview(id: ID, implementer_observation_id: ID, reviewer_observation_id: ID,
  candidate_id: digest, acceptance_id: digest, entry_ids: list[ID], case_ids: list[ID],
  evidence_sha256: digest, reviewed_at: UTC, approved: bool, assessment: text, unresolved_findings: list[text],
  receipt: HashedReceipt). Receipt JSON equals full review excluding receipt itself.
  Every entry names covering approved review; zero unresolved findings. Distinct
  observed contexts, actor_refs match v1 final implementer/reviewer refs. Review
  covers matrix/applicability and intentional differences on current candidate.
- EvidenceBundle(schema_version: literal 1.0, task_id: ID, delivery_revision: positive
  int, plan_sha256: digest, candidate_id: digest, acceptance_id: digest,
  baseline_candidate_id: digest|null, cases: list[VerificationCase],
  entries: list[EvidenceEntry], observations: list[RunObservation],
  reviews: list[SemanticReview]).

## Gate

Strict normalize task/delivery/bundle. Match task/revision/plan digest and actual
current v1 candidate/design/acceptance/criteria against plan; recompute through
existing quality APIs, never trust claimed hashes. Existing completion_gate is
mandatory additional check. artifact_root equals task.artifact_root. File evidence
is disjoint from product paths/inodes. Unknown requirements, wrong-case reuse,
duplicate IDs and orphan entries fail. Every required case passes; every criterion
has passing required case coverage. Optional cases cannot fill required gaps;
optional not_applicable needs rationale and independent review.

Bug requires baseline != final, failing before, passing final after and regression
at all declared levels. Before predates after. Capture follows source run observation. Explicit review completion follows both implementer/reviewer run observations and all covered captures, and equals the actual v1 cycle.review.observed_at instant. Host run observation is a start/observation event, not review completion.
Feature/document/research have no fabricated baseline or before evidence. Exact
proof levels prevent fixture success from substituting POS/integration acceptance.

Hashes and semantic labels never authenticate origin. P16 must supply real host
observations and immutable registered state under lock. This helper only checks
consistency against P11 observed dispatch records. No native activation or runtime
acceptance claim; those remain separate limitations. No external writes/tools.

## Verification

TDD strict codec/digest, stale bindings, missing/tampered/unsafe files, coverage,
waiver/levels, wrong-case reuse, fake reviewer labels, bug pairing and feature
without fabricated baseline. Retain red/green exits and final hashes; independent
exact-candidate review remains pending until root arranges it.

Review evidence_sha256 hashes canonical JSON with these exact keys:
- plan_sha256: delivery_digest(current delivery.plan).
- context_sha256: current delivery.plan.context_sha256.
- entries: full reviewed entries sorted by ID.
- cases: full reviewed cases sorted by ID.
- observations: full referenced RunObservation records sorted by ID, including
  complete nested ObservedRun and receipt path/hash. The selected ID set is the
  union of review implementer/reviewer observation IDs and every selected entry's
  capture observation ID.

Same-ID metadata/provenance substitution, receipt relocation or changed plan/context
invalidates approval. SemanticReview.reviewed_at is required explicit UTC and is
part of the actual hashed JSON review receipt. It must equal the v1 completion
instant and be at/after both observed runs and every covered capture. Reviewers
may capture evidence later in their own observed run, then complete review. Baseline and final build identities are each internally consistent; inherent build changes do not require environment-difference waiver.
