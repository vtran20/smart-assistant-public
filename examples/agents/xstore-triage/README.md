# Xstore evidence triage — source candidate

`xstore-triage` assesses supplied Xstore evidence and proposes useful next evidence
for independent review. This source candidate is DRAFT; source checks alone prove
neither configured native availability nor customer acceptance. Actual configured
role behavior, independent semantic review and managed activation remain separate
acceptance gates recorded by the coordinator.

Example request: “For case `local-build-review`, assess the selected `build.log`
and `launch.log` ranges for the supplied profile. Explain what the observed build
and runtime identities prove, retain missing proof, and write the eleven-field
assessment to the assigned output path.” Supply the exact selected input inventory,
a case identifier, relevant identity/scope and an authorized output path. Unrelated
requests receive `out_of_scope`; essential missing evidence blocks the requested
conclusion while retaining supported partial observations.

The role may use filesystem tools for exactly selected inputs and assigned
assessment outputs. It does not run customer builds, generation, services, SQL,
payments, trust changes, network requests or customer source edits. It does not
expand the evidence selection or spawn further agents. The host still enforces
actual permissions; behavioral instructions are not a separate filesystem sandbox.

## Pack and deployment binding

The complete UTF-8 bytes of `knowledge/1.0.0/pack.json` are embedded verbatim between
`BEGIN XSTORE KNOWLEDGE PACK` and `END XSTORE KNOWLEDGE PACK` markers in the decoded
`developer_instructions`. Its `knowledge_sha256` hashes the raw pack file, including
whitespace. The managed deployment manifest separately hashes the single native
file with its exact `xstore-triage.toml` basename. They are distinct identities.
Only `name`, `description` and `developer_instructions` appear in TOML, inheriting
the caller's model, effort and permissions. No external knowledge file is imported
at runtime. Logical source references are provenance, not retrieval instructions.

From the repository root, check the exact candidate without modifying it:

```sh
python3 examples/agents/xstore-triage/build_definition.py --check
python3 -m unittest tests.test_xstore_triage_assets -v
```

The first command prints `knowledge_sha256` and `manifest_sha256`; the checks use
the existing `validate_agent_definition` and `deployment_manifest` helpers. It also
accepts explicit `--pack PATH --definition PATH`, preserving the native basename.
Regenerate an authorized working draft explicitly with `--write`; default/check
mode never writes. Generation validates the pack shape, unique IDs, source hashes,
portable relative paths, bounded source sections and procedure references. Checking
rejects changed raw pack bytes, instructions, embedding or extra TOML fields.
These checks cannot determine semantic truth, licensing or product compatibility.

## Knowledge scope and revision

Eight newly authored procedures cover bounded intake, distinct proof gates,
build/runtime identity, runtime chronology, freshness/conflicts, OPI evidence,
authority and knowledge ownership. Seven inspected sources are pinned by logical
repository/path, SHA256, date and source sections. `agent_validated` applies to
source inventory verification; the synthesized pack is `candidate` pending review
and behavior evaluation. No human acceptance is inferred. The sources are user-owned
procedural guidance, with unassessed redistribution rights, rather than product
manuals. Linked source files/scripts were not followed. No copied vendor/customer
text, private origin paths or fixed release compatibility facts are distributed.

The normative [assessment contract](../../../docs/tasks/xstore-triage/assessment-contract.json)
and [design](../../../docs/tasks/xstore-triage/design.md) govern the eleven-field
output. Source ranges refer to actual selected input files, never provenance files
that were not supplied as task evidence. Observed positive facts and unresolved
gates coexist; `ready_for_review` is not completed or self-accepted. A real existing-v1
TaskAssignment additionally needs its authentic Handoff. An unassigned advisory
must not fabricate task/revision/selection identities.

Freeze/version changes require the design -> implement -> independent review ->
recorded feedback -> testing -> repeat cycle. Once a pack version is frozen or
registered, preserve its bytes and create a new version for changed content; update
the generator's explicit version/schema and tests together. Revalidate source pins
and semantic applicability when source, profile, toolchain, launcher, coverage,
provider/specification, permissions or client identity changes. Never automatically
replace a project pin or publish project findings to shared knowledge. Preserve
private evidence within its owning project and redact sensitive task observations.

Source test history and pending gates are recorded in
progress (local historical archive: `../../../docs/evidence/xstore-triage/source/progress.json`).
