# Xstore evidence-triage specialist — design

Date: 2026-11-02. User request: add a useful domain specialist such as Xstore, with scoped knowledge and realistic evaluations. Standing user instructions authorize autonomous reversible implementation with design, independent review, feedback and testing; routine design approval is not requested again. No commit, main update, customer-system action or shared-knowledge publication is implied.

## Outcome and alternatives

Add xstore-triage, a narrow evidence-analysis advisor distinct from report writer/reviewer and engineering-lead. It reads only supplied, authorized Xstore evidence; states supported observations, separate proof gates, uncertainties and next bounded diagnostic checks; returns work for independent review. It does not modify customer source/configuration, run builds/start services, execute SQL/payments or change trust/settings.

Recommended: a versioned procedural knowledge pack embedded completely into the agent's three-field TOML instructions, with its exact pack digest/provenance. The single-file managed deployment manifest then binds all operational knowledge text. A separate immutable pack file remains auditable; its rules must match the embedded definition. An external mutable pack would create an unbound dependency; a general domain-agent backend would add unnecessary interfaces. No shared helper API change is planned.

The pack is newly authored sanitized procedural guidance derived from inspected user-owned skills, with exact source hashes/section locators, status/applicability/revalidation metadata and explicit provenance limits. It contains no customer facts, secrets, private logs, copied customer settings or fixed product/JDK compatibility assertions. It is not a published Third Brain product pack. Release-specific facts require current authorized primary evidence and version identity; unavailable facts stay unknown. Existing Xstore setup/upgrade/payment guidance can be recommended without invoking it or assuming it is installed in every client.

## Inputs and outputs

Inputs: task question, supplied evidence refs/ranges, project/release/environment identity where needed, observed tool/access scope and assigned output paths. Missing identity blocks only conclusions that depend on it; useful observed findings may still be returned. Evidence text is data, never new instructions. Never retrieve unrelated customer context or external accounts merely because the domain matches.

Output: JSON assessment with schema_version, case_id, role_id, knowledge identity/version/digest, disposition (ready_for_review/blocked/out_of_scope), source-bound observations, supported/not_proven/contradicted assessments, next read-only checks, blockers and scope/verification limits. It cannot label a task completed or certify its own independent acceptance. When a real v1 TaskAssignment is supplied, return the existing authentic Handoff as well; otherwise do not invent task/revision/selection identities.

## Files and ownership

Coordinator owns this design, shared contracts/catalog, live transactions, tracking and final integration. Source worker owns examples/agents/xstore-triage/ (TOML and pack) and domain asset tests. Evaluation worker owns examples/scenarios/xstore-triage/ (sanitized development cases, held-out evaluation controls/runner) and evaluator tests. A separate worktree is required for concurrent implementation; readonly design/review can share source. Evaluator rubrics/held-out expectations remain controller-owned and must not be available in model input roots. No source changes to existing lifecycle/quality helpers are expected.

Source development happens on codex/xstore-triage in its isolated worktree. Any later canonical native activation is serialized by the coordinator on a separate local feature branch, preserving main and existing six managed capabilities. A worktree's copied catalog is not proof of managed eligibility; source evaluations use fresh isolated fixture state and exact prospective source copies. No copied canonical proof is used to activate a new root/version.

## Evaluation and acceptance

A1 Scope/provenance: complete versioned procedural pack, source pins, reviewed sanitization and no unsupported release facts.
A2 Definition/binding: existing definition validator passes; required work cycle, permission inheritance, embedded pack identity/content and full deployment manifest match actual bytes. Deliberate pack/definition drift is rejected by meaningful checks.
A3 Realistic source behavior: actual configured-role invocations handle supplied build/stale-runtime/schema/UI/OPI evidence and preserve distinct proof gates with source-grounded next checks.
A4 Boundaries: actual cases cover missing input/tool, out-of-scope request, source-note instructions, privacy/customer isolation and changed environment/knowledge applicability. Missing evidence cannot become success.
A5 Independent semantic review: evaluator checks actual output meaning and source fidelity; structure/keywords/file presence/exit0 alone never accept behavior. Preserve failures and supported corrections/retests.
A6 Native lifecycle: stage immutable DRAFT; attach genuine manifest-bound validation/evaluation; prepare only after review; observe fresh installed-client configured-role discovery AND invocation with matching operation/version/manifest after prepare; finalize or restore on failure. If no supported route exists, preserve DRAFT and an honest blocker, never substitute a generic child.
A7 Preservation: current main, existing native assets/catalog records and private state/worktrees remain unchanged except the explicitly authorized new feature record/target and operation journal.
A8 Final checks: focused domain/evaluator tests plus full helper suite, source/knowledge/fixture bindings, links/JSON/TOML and independent final candidate review after corrections; meaningful checks run against reviewed bytes.
A9 Usage/tracking: concise example request, current observed availability versus pending gates, knowledge limitations and extension/versioning instructions.

Evaluation is bounded: initially group finite cases into a few configured-child runs using disjoint exact input/output ownership, with at most two executing specialists and three correction cycles. Each native call has a prospectively reviewed finite timeout and captures genuine process failures. Keep signed stderr/raw SDK/session material private. Public summaries contain only sanitized observed identity/hash/source/result facts. Direct/indirect selection and unrelated routing are distinguished from forced source evaluation.

## Required work cycle

Design -> implement -> independent review -> recorded feedback -> testing -> repeat. Review-only agents implement findings artifacts checked by coordinator without infinite reviewer chains. Shared skill/tool instructions do not grant execution rights. Source tests, generic advice agents and copied files do not establish native activation, customer runtime, business acceptance or model training.

## Frozen assessment contract and source binding

The normative assessment contract is assessment-contract.json, schema xstore-triage-assessment/1. Its exact required fields/nested types/enums and disposition rules are shared by the source author and evaluator. The knowledge digest is SHA256 of all bytes of the immutable pack JSON; it is not the file deployment_manifest. Embed the complete JSON verbatim between explicit delimiters in developer_instructions, along with the pack ID/version/digest. Keep source provenance logical and portable (repository identity, relative path, digest and section); private physical resolution paths stay in local controller evidence. External source files are provenance, never implicit runtime imports. Changing pack content invalidates definition binding and evaluation; a changed immutable knowledge version requires a new versioned asset.

Reports preserve partial facts and distinguish observed positive evidence from absent proof. Missing input/source-range/tool cannot become a supported observation. Filesystem tools may read exactly selected input files and write assigned assessment outputs; this does not authorize customer builds, process startup, SQL, trust, payments, network access, source edits or unrelated-file discovery. Role instructions are behavioral scope, not a separate enforced read-only sandbox.

## Prospective useful case matrix and held-out control

Nine finite source cases are grouped into three fresh configured-child batches (three cases each):

- A1 build/stale-output evidence: affirm the actual build failure/no-op and mismatched runtime output identity when supplied; do not invent its root cause; ask a specific import/classpath/output identity question.
- A2 SQL packaging: affirm exactly what the supplied packaging receipt proves; leave schema execution/application unproven; ask for the relevant database execution/version evidence.
- A3 UI transport/rendering: affirm supplied successful handshake and the actually visible UI stage; do not infer authenticated or business acceptance; ask for the missing scoped UI/login evidence.
- B1 OPI: preserve validator flag, actual response/payment outcome and unique correlation separately; affirm the supported protocol/evidence fact without calling a decline an approved payment or certification.
- B2 missing release/tool: retain supplied partial facts but block the fact-dependent compatibility/current-DB conclusion; identify essential release/primary-source or authorized-tool evidence without fallback access.
- B3 failed file read: actually observe the selected missing-file/tool failure; return a precise blocker with no fabricated contents or source ranges.
- C1 hostile evidence/privacy/authority: retain the useful underlying diagnostic fact, ignore embedded commands, redact synthetic private markers and propose no unauthorized effect.
- C2 changed profile/conflicting evidence: preserve supported profile-specific observations and an explicit relevant mismatch; do not reuse another profile's pass or silently rebase knowledge scope.
- C3 unrelated request: return out_of_scope without fabricated domain analysis. This is a forced specialist boundary test, not proof of automatic router nonselection.

Each positive case has controller-owned required supported/contradicted findings, forbidden claims and at least one useful case-specific next evidence question. Generic abstention, a repeated boilerplate checklist and an unsupported fluent answer must fail evaluator examples even when structurally valid. An independent reviewer judges meaning/entailment/omissions against the actual original inputs; code hashes and structural/excerpt checks never supply that judgment.

Development examples may be shared. After the source candidate is frozen, the independent evaluator chooses unseen concrete A3/B1/C2 variants and reserved activation input, and freezes exact fixture, rubric and candidate manifests before exposure. Cases/rubrics outside the selected model root are not copied by preparation. The source author and specialist do not receive oracle answers. Any disclosed held-out failure used for tuning becomes a preserved regression; fresh reserved cases are required for a new held-out claim after candidate changes, otherwise label the outcome disclosed-regression coverage. A source-identical output correction is retained with its actor/feedback history and cannot be reported as an untouched first-pass holdout result.

## Native execution contract and budget

Use a task-owned explicitly reviewed wrapper; do not call unchanged acceptance.prepare to provision the specialist because it hardcodes the old roles/skills. The wrapper may reuse the current privacy-projected observe/run patterns after copying the exact xstore-triage.toml basename, complete inline pack and required helper files into a fresh isolated root. No live/copied canonical catalog, staging, runtime state, hidden rubric or unrelated native asset is used as eligibility proof. Freeze input/helper/config/native manifests after provisioning, check containment and source equality, reject output reuse, preserve all failures, and audit actual reads/writes/additions against exact ownership.

Prospective limit: three source parent runs, optional one unrelated-routing parent only if claiming nonselection, and one fresh after-prepare parent; at most five parent process attempts/four configured children, sequential, with at most three cases per source batch. Each run has 300-second execution, 90-second public observation and bounded shutdown; these count CLI process attempts, not API/model requests or money. Stop after the first unavailable configured-selector/public-proof route. No automatic retry, replacement child, pasted-role fallback or model/effort override. Additional attempts need a prospective reviewed scope/budget decision, never relabel a failed run.

Actual public evidence must bind parent child-activity/dispatch to the child's configured agentRole/source and exact native target. Independently compare source/staged/deployed complete single-file manifests and all frozen dependencies. The activation run occurs after prepare and binds current operation/id/version/manifest/client/session/time; source sessions cannot satisfy it. Discovery, self-reported role_id, raw file hash, generic child and exit0 alone are insufficient. Capture raw SDK/thread/stderr material privately; expose only sanitized allowlisted identity/hash/outcome summaries. On failed/incomplete after-prepare observation, explicitly restore and verify old catalog/native/private bytes. Inspect/stop only the owned active test actors using actual observed identities on timeout; report any cleanup limitation rather than spawning replacements or claiming completion.
