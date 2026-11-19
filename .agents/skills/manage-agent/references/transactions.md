# Actual P02 evidence and transactions

`stage_agent` returns a normalized `CapabilityRecord`; its `deployed_sha256` is the complete manifest hash. Both successful validation and successful evaluation JSON references are required by P02. Write receipts from actual observations, never generate unconditional success:

```json
{
  "schema_version": 1,
  "kind": "validation",
  "capability_id": "synthetic-researcher",
  "version": "2.0.0",
  "manifest_sha256": "<candidate.deployed_sha256>",
  "passed": true,
  "evidence_refs": ["docs/evidence/agent-change/observed-validation.md"]
}
```

Evaluation uses the identical fields with `kind: "evaluation"` and actual behavior evidence refs. Every reference must be an existing project-local file. The placeholder is illustrative, not a usable hash. Use `dataclasses.replace(candidate, validation_refs=[validation_ref, evaluation_ref])` after independent review and recorded feedback cover these exact bytes. Rehash the staged file before preparing; drift invalidates evidence.

```python
store = DeploymentStore(root)
catalog = load_catalog(root)
operation_id = store.prepare(candidate, catalog.revision)
# Start a fresh installed-native session and actually discover/invoke the agent.
# Construct a typed NativeProbeReceipt from that session's observations.
catalog = store.finalize(operation_id, observed_receipt)
```

A typed `NativeProbeReceipt` carries schema_version, operation_id, capability_id, version, manifest_sha256, purpose (`ProbePurpose.ACTIVATE` or `DISABLE`), client_name, client_version, session_ref, discovered, invoked, observed_at and evidence_refs. Activation requires discovered=true and invoked=true; disable requires discovered=false and invoked=null. Observation time must follow prepare; disable session must differ from previous activation. Match the exact transaction/identity/version/hash. Evidence stays local and private where appropriate; never publish session records or secrets.

`prepare` writes native assets but does not activate eligibility. `finalize` commits the catalog only with matching successful proof. An invalid activation receipt triggers restoration. If observation itself fails or a prepared transaction is interrupted, explicitly call `store.restore(operation_id)`; report any recovery failure with surviving evidence. Failed disable observations require explicit restore or correction, and must not be represented as final absence. Revision conflicts stop the transaction; do not overwrite another catalog revision.

Use `store.prepare_disable(id, catalog.revision)` and `store.finalize_disable(operation_id, absence_receipt)` for removal, followed by a fresh absence observation. After finalized activation or disable, `restore` cannot roll back a committed transaction. Copy the previous verified source bytes into a newly versioned DRAFT, stage them, bind new review/evaluation and probe proof, then prepare/finalize a new activation. The prior bytes may be reused, the prior version and proof may not.
