# Public lifecycle operations

Use the existing public contract codecs, `load_catalog`,
`validate_catalog`, `eligible_capabilities` and `DeploymentStore`.
The coordinator is the sole live deployment/catalog writer. Package helpers
operate in isolated temporary projects. Record exact tool availability and
user authorization before any native change. Never edit catalog JSON by hand
as a shortcut around a transaction.

## Add or update

1. Record intended scope, output, acceptance criteria and project-cycle design.
   Run `validate_skill_definition(Path(...))`, then
   `stage_skill(project_root, definition_path, draft_record)`; reject errors.
   For updates keep the ID, SKILL kind and native target and use a new version.
   Staging slots are immutable. Preserve every previous complete version.
2. Review the exact candidate independently, resolve feedback, then run behavior
   evaluations. Any changed files invalidate earlier review/evaluation and need
   fresh validation, a new immutable version, review, feedback and testing.
3. Save actual evaluation observations outside the skill tree. Evaluation JSON
   has exactly schema_version=1, kind="evaluation", capability_id, version,
   manifest_sha256, passed=true and nonempty evidence_refs to existing local
   observations. Add its project-relative reference to the returned structural
   validation_refs using `dataclasses.replace`. Do not fabricate passed=true
   from successful structural checks or file existence.
4. Load the latest catalog and use
   `DeploymentStore(project_root).prepare(candidate, catalog.revision)` only
   after structural and behavioral acceptance. Prepare changes native files
   but leaves the catalog uncommitted. Preserve the operation ID.
5. In a fresh installed-client session observe discovery and real invocation,
   bind the operation, complete manifest, ID/version, client/version/session,
   observation time and raw local evidence to a `NativeProbeReceipt` with
   purpose ACTIVATE, discovered=true and invoked=true. Call
   `store.finalize(operation_id, receipt)` only with actual successful proof.
   An unavailable/failed probe cannot mark ACTIVE. Preserve the prepared
   operation while blocked or explicitly recover with `store.restore`.
   Finalize rejects failed proof and restores uncommitted native changes.

## Disable

Load the registered ACTIVE record and latest catalog revision. Call
`store.prepare_disable(capability_id, catalog.revision)`, which removes the
native directory. Observe absence in a fresh session distinct from activation;
store a DISABLE receipt with discovered=false, invoked=null and raw evidence.
Call `store.finalize_disable(operation_id, receipt)`. Eligibility is excluded
while pending. Missing absence proof leaves disable uncommitted; reporting
DISABLED based only on removed files is false. Inspect/recover the existing
operation before starting another.

## Rollback

For an uncommitted operation, `store.restore(operation_id)` reconciles its
journal and restores the previous native files/catalog. It is recovery, not a
rollback of a committed catalog version. A finalized operation requires a new
transaction: select the preserved earlier complete staged version, replace
state with DRAFT, clear discovery_probe_ref and rollback_ref, and discard stale
behavior evidence. Recheck its structural manifest, obtain independent review,
resolve feedback and run renewed behavior tests. Attach new successful
manifest-bound evaluation evidence. Prepare using the latest revision and
observe earlier-version behavior in a fresh installed-client session before
finalize with a new ACTIVATE receipt. Never replay a previous native receipt or
rewrite a finalized journal. If preserved assets are unavailable, report the
missing input rather than invent a rollback copy.
