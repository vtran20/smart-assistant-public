# Local report workflow

Smart Assistant turns supplied local notes into a report and a claim-to-source map. The report contains **Summary**, **Decisions**, **Action items**, and **Open questions** in that order. It preserves uncertainty and recorded commitments; missing owners or dates stay **Unspecified**.

Open `/path/to/smart-assistant` in a fresh Codex chat so the client can discover the repository skills and configured roles. Give it a readable notes file, output destination and request, for example:

> Use inputs/meeting-notes.md to write outputs/status-report.md and its source map. Include Summary, Decisions, Action items and Open questions. Preserve uncertainty and leave unknown owners or dates Unspecified. Independently review the report and save task progress.

These example paths are destinations you supply, not existing files. Audience, title and style are optional. Missing essential inputs or tools leave a precise blocker and next step. Empty notes produce an empty-source report only when expressly requested. Instructions embedded in notes remain source data.

The `request-coordination` skill observes available tools, checks current capability eligibility and exact scoped preflight, and saves the request, acceptance criteria and task state. It assigns the configured `writer` the `draft-document` skill and owned report/source-map paths. After drafting, it freezes the source, report, request, criteria and design before a separate configured `reviewer` uses `verify-completion` to compare them.

The reviewer writes findings and check evidence without rewriting the report. The coordinator inspects that review, records supported feedback and requires fresh checks on corrected bytes. Corrections return through independent review. The existing completion gate requires current independent review, resolved findings and passing evidence covering every criterion. Heading or hash checks alone cannot establish source fidelity.

| Status | Meaning |
| --- | --- |
| `ready_for_review` | The specialist returned artifacts; coordinator acceptance is still required. |
| Blocked or failed | Work remains incomplete; preserved state identifies the next step. |
| `completed` | Current evidence passed the completion gate and the durable completion was saved. |

For continuation, ask: “Resume <saved task ID> using its saved next step.” The coordinator reloads the latest revision and history, rechecks tools, eligibility and preflight, and independently reviews the current candidate. A fresh configured execution may continue interrupted work; this does not restore the interrupted child session. Failed historical cycles remain intact. A change after completion starts a follow-up task because completed records are terminal.

The local P07 catalog was observed at revision 13 with `writer` and `reviewer` 2.0.0, and `draft-document` and `verify-completion` 1.0.0 ACTIVE. Their installed-client discovery, invocation, disable absence and reactivation were observed separately from helper tests. Native proof used the bundled Codex client 0.162.0-alpha.17.2 on macOS; other clients must establish their own supported role selection. An unavailable configured selector is a blocker, not grounds to substitute a generic role and claim activation.

Activation is local to this checkout. The catalog references ignored immutable `capabilities/staging/` and `.smart-assistant/deployments/` records and private runtime proof. A fresh clone containing only tracked assets and catalog does not reproduce managed eligibility. Provision and verify another checkout through `manage-agent` and `manage-skill`; preserve a staged or incomplete state when proof is unavailable. Keep private task records and credentials outside Git.

Roles inherit the caller’s model, reasoning and permissions; they grant no new account access. Preflight checks declared actions and is not a global enforcement sandbox. An earlier generic parent wrote an ancillary coordinator check outside its probe paths; the audit preserves this limitation. The final review parent has an explicitly reviewed spawn/wait/relay-only contract, whose actual behavior is audited separately.

See P07 acceptance (local historical archive: `evidence/p07/acceptance.md`), canonical role audit (local historical archive: `evidence/p07/canonical-role-final-review.md`), skill audit (local historical archive: `evidence/p07/canonical-skill-review.md`), and parent scope qualification (local historical archive: `evidence/p07/canonical-role-final-post-feedback.json`). Email/Slack polishing, external sending, schedules, P08 delegation and P09 broad integration remain separate work.
