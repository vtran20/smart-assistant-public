# P02 catalog and deployment transactions

P02 implements the frozen public signatures in the implementation brief. All mutable tests use temporary synthetic projects. No native activation is claimed from synthetic receipts.

## Consistency and evidence

The catalog lives at `capabilities/catalog.json`, begins at revision 1, and has unique IDs and non-overlapping native targets. Agents deploy to `.codex/agents/<basename>.toml`; skills deploy to `.agents/skills/<basename>`. Source assets cannot lie under native discovery directories or overlap their deployment. Every path component and asset tree rejects symlinks, traversal and nonregular files. A skill manifest covers every file; an agent manifest uses the target basename, even if its staged basename differs. SHA-256 is the P00 canonical complete file-list digest.

Each local JSON validation reference has exactly `schema_version:1`, `kind:'validation'|'evaluation'`, `capability_id`, `version`, `manifest_sha256`, `passed`, and `evidence_refs` (nonempty strings). Both successful kinds must bind to the deployed manifest. Discovery references point to a structurally valid NativeProbeReceipt with matching identity/version/manifest, activation purpose, discovered=true and invoked=true, nonempty evidence, and the finalized operation ID. Runtime receipt files are saved at `.smart-assistant/deployments/<operation>/activation-receipt.json` or `absence-receipt.json`. Evidence describes observations; filesystem helpers never manufacture native success.

Catalog validation checks active evidence and deployed bytes. Eligibility filters each record independently for ACTIVE, required tools, valid evidence, complete native manifest, and no pending transaction. Malformed journals fail closed for all records. Disabled and retired versions are never eligible.

## Transaction journal and recovery

A stable `.smart-assistant/catalog.lock` uses exclusive flock for every mutation; expected_revision performs CAS and the journal binds the exact original catalog bytes. One unfinished operation globally prevents new prepare calls. The versioned journal contains operation ID, mode, state, original catalog, candidate, target, original and candidate manifests, old-existed flag, and prospective final catalog. Copies and journal/catalog/receipt writes use file fsync, atomic replace, and parent-directory fsync.

| Interrupted state | Recovery |
| --- | --- |
| preparing | Original native target remains untouched; restore original catalog without revision change. Incomplete backup never authorizes target mutation. |
| replacing | Verified backup restores original target, or removes new target if none existed. |
| prepared | Explicit restore, or matching fresh probe and finalize; candidate stays ineligible. |
| finalizing | Exact final catalog bytes mean commit occurred: reconcile journal to finalized, never roll back. Exact original bytes mean restore is permitted. Any other bytes produce RevisionConflict without overwrite. |
| restoring | Repeat verified restore idempotently, then mark restored. |
| finalized/restored | Terminal; finalized restore refuses and requires a new staged/probed transaction. |
| corrupt journal/backup | Reject mutation and eligibility; preserve surviving files for operator reconciliation. |

Activation prepare validates staged assets and evidence, copies original target to a private backup, journals intent before target mutation, replaces assets from a private prepared copy, then enters prepared. Finalize rehashes deployed assets and validates full probe identity and observations before publishing ACTIVE at revision+1. A failed activation probe triggers restoration. Disable prepare removes assets with the same backup protocol; failed absence evidence leaves the capability unavailable until restore. Disable finalize publishes DISABLED at revision+1 only with purpose=disable, discovered=false, invoked=null and an otherwise matching receipt. Restore checks unchanged catalog before changing files, and validates backup before deleting surviving data.

Atomicity means the catalog commit is atomic and interrupted native changes are journaled and recoverable. Directory replacement has an observable absence window; readers exclude pending operations. No claim of a multi-file filesystem transaction is made. External asset mutation during a pending operation fails finalization; explicit restoration intentionally returns verified original bytes. External catalog edits are never overwritten.

## Verification plan

Tests cover manifest resources and agent basename normalization; duplicate IDs, tools, disabled records and missing evidence; traversal/symlink/source overlap; CAS and explicitly synchronized processes; actual I/O interruption at backup, target replacement, catalog replace and restoration boundaries; backup and journal corruption; external catalog edits; native drift; probe identities and failed disable evidence. Run targeted and full unittest suites, save RED/GREEN logs, hand frozen candidate to root for independent review and feedback corrections.

## Frozen implementation refinements

Eligibility compares the supplied catalog's complete typed wire form with the current canonical catalog before routing, and holds an existing lock in shared mode while checking evidence and native bytes. Catalog loading and prospective validation stay read-only and never reconcile journals. Activation receipt references must match their operation directory and a finalized activation journal; observations must be at or after journal `started_at`. Disable observations additionally use a session different from the removed version's activation session. Nested evidence_refs also name safe existing local regular files.

Public `finalize`, `finalize_disable`, and `restore` reconcile `finalizing` after an atomic catalog commit. Finalize retries return the committed catalog only for identical saved proof and unchanged committed catalog bytes. Restore reconciles a committed operation and refuses rollback. A finalizing journal with unchanged original catalog remains reversible. Missing initial journals, malformed field types, invalid Unicode, path escapes, and corrupted backups fail closed and require explicit operator reconciliation; no read silently changes state. Copies require absent nonsymlink destinations, including restoration scratch paths.

Locks serialize cooperating helper processes. The helper rejects observed external changes; arbitrary adversarial filesystem mutations occurring between checks and filesystem operations are outside this local cooperative concurrency boundary. The atomic commit and recovery protocol is tested by real writes and injected interruptions at actual I/O calls, not by simulating journal state alone.


## Independent review round 1 invariants

Activation proof binds the native discovery location and capability kind as well as ID, version, manifest and operation. Identical bytes copied to a different target do not inherit the original target's probe. Journal original-existence metadata must agree with the saved original catalog: an original ACTIVE version requires original files and a matching backup manifest; a journal denying original files cannot retain a backup. Exact current catalog bytes still gate restoration. Interrupted preparation checks surviving original native bytes and type before declaring restoration.

The generic manifest digest intentionally does not encode file-versus-directory type. Native asset consumers therefore enforce that agents are regular files and skills are directories at staging, deployment, backup, private prepared-copy and restoration-copy boundaries. Digest equality never substitutes for native type checks. Verification precedes native target deletion.

Public catalog consumers validate and normalize using the frozen P00 serializer/decoder, consuming reconstructed nested dataclasses rather than dereferencing accepted nested wire dictionaries. Activation prepare also consumes a normalized candidate. Finalization normalizes receipts inside its recoverable validation path so malformed activation evidence still restores the previous deployment before rejection.

Staging cannot equal, contain, or lie within deployment journal storage. Every private copy separately rejects source/destination overlap in both directions before copy I/O. These checks cover stable inconsistent or malformed durable state inside the cooperative concurrency boundary. No protection is claimed against an actor rewriting all mutually consistent catalog, journal, receipt and evidence records.

## W1-F1 integration correction design

Exact catalog binding includes physical UTF-8 bytes, including JSON whitespace, LF/CRLF line endings and Unicode spelling. The journal keeps its existing string fields: decoding valid UTF-8 directly preserves bytes because encoding the unnormalized string reconstructs the original input. The lifecycle catalog-reading boundary will read bytes and decode strictly rather than use universal-newline text reading. CAS, restore, committed retries and finalizing reconciliation continue to compare the saved strings, now without hidden newline normalization. Earlier acceptance artifacts remain historical; new integration-fix tests and receipts bind this correction separately.
