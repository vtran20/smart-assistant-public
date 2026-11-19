# P06 skill validation and private staging

Approved inputs: the P06 implementation plan and root Wave 2 design, baseline
04c8a5b9cc18a6f3cd6cc78b09aedf45d0d25792. Own only skill_lifecycle.py,
its tests, manage-skill, examples/skills and P06 task/evidence documentation.
Backlog scope is T13 and S04. Root owns independent review, integration, catalog
mutation, installed-client observations, and activation.

## Interface and boundaries

`validate_skill_definition(path: Path) -> GateResult` accepts a SKILL.md file or
its directory. It checks complete regular-file resources, local links, required
metadata and meaningful instruction categories. `stage_skill(project_root,
definition_path, record: CapabilityRecord) -> CapabilityRecord` normalizes the
P00 contract, requires DRAFT/SKILL, checks metadata/native identity, registered
ID/target collisions and unmanaged or drifted native targets, then creates an
immutable private complete copy at capabilities/staging/<id>/<version>/skill.
The definition may live outside the project but must not cross symlinks.

Version slots are immutable. Updating a registered ID keeps kind and target and
uses a different version. Prior staged versions remain available for rollback;
reactivation uses the preserved version with renewed behavior/native evidence,
not restaging into its immutable slot. Staging does not call DeploymentStore,
change native discovery, or mutate the catalog. It clears stale validation,
evaluation, discovery and rollback references, saving only actual structural
validation tied to the complete P02 manifest. Files go in `skill/`; structural
receipt and its observation live beside it, outside the deployed manifest.

## Explicit metadata format

The installed host accepts broader YAML; this stdlib helper does not parse full
YAML. Support exactly two unique top-level keys, name and description, each on
one line. Name is a lowercase hyphenated identifier under 64 characters.
Description is a nonempty string of at most 1024 characters. Values may be plain
unambiguous strings, JSON-compatible double quoted strings, or single quoted
strings with doubled quote escaping. Blank lines are accepted. Plain scalars
cannot use YAML reserved/implicit boolean, null or numeric values, comments,
colon-space, tags, anchors, collections or multiline syntax. Other keys, nested
metadata, multiline scalars and ambiguous syntax yield unsupported_metadata;
missing required keys yield missing_metadata. No unsupported data is silently
discarded. Optional files such as agents/openai.yaml are copied as resources,
not claimed to have been parsed or policy-validated.

## Body and resources

Bodies describe invocation scope, output, verification, and the project cycle:
design/planning, implementation, independent review, feedback, tests and repeat.
Reasonable prose variants are accepted; explicit instructions to skip review
or tests are rejected. These are structural checks, never behavioral proof.
All resource trees and existing source ancestors must be nonsymlink regular
files/directories; FIFOs and special files are rejected before reads/copies.
Markdown local links and standalone resource paths in inline code must exist
inside the definition tree and cannot contain traversal. Fenced code examples
are ignored as link instructions. External URL links and document anchors do
not imply local files. No script is executed by validation or staging.

## Verification and delivery

Meaningful failing tests first cover metadata, instruction omissions/variants,
external versus unsafe local links, symlinks/FIFOs, identity/kind/state/path
conflicts, full resource copies and immutable versions, fresh evidence and
DeploymentStore compatibility. All tests use temporary roots. The synthetic
repeatable `count-local-items` fixture counts a supplied list with a local
script; it provides finite direct/indirect/unrelated/incomplete/failed-tool and
previous-version cases for root installed-client evaluation. It does not
implement the P07 writing workflow. Management guidance uses public APIs and
DeploymentStore, requires behavioral evidence before prepare, fresh native
receipts before finalize, observed absence on disable, and a new activation
transaction for rollback of a finalized deployment.

Record RED/GREEN and product hashes; self-review before handoff; root dispatches
independent review. Resolve feedback, refresh tests on the reviewed product,
then root performs native observation and integration. No capability is ACTIVE
or complete because a file exists. No accounts, recurring work or deployments
are authorized by this package.

## Corrective design after independent review R1–R4

The initial candidate 1721d763 was independently reviewed with four P2 findings;
all were accepted after coordinator reproduction. The fix retains structural
scope and all frozen APIs. Instruction-reference scanning supports standalone
matching single/multiple-backtick code spans containing POSIX/Windows path
separators, regardless of resource directory name. A whole command containing
spaces and literal Markdown illustrations remain examples, not local resource
references. A bare filename without a path separator must use a Markdown link
to be attested as a resource. This is an explicit reference boundary, not a
full Markdown or semantic intent parser.

Markdown destinations are parsed before title removal/angle unwrapping, so
angle destinations with spaces and optional quoted titles share containment
and existence checks with plain destinations. Reference definitions use the
same destination parser. Scheme-bearing non-file URLs and protocol-relative
network URLs are external documentation; file URLs, drive paths, local absolute
paths and traversal spellings remain forbidden.

Waiver detection matches an omitted review/testing object directly, rather
than treating any nearby word following “without” as omitted. “Review without
bias, then run tests” and “No independent review is complete without tests”
require review/testing and are accepted. Explicit skip/optional/no-need waivers
stay rejected. Structural patterns still cannot establish semantic quality or
permission; actual behavior evaluation remains separate.

Correction verification: add failing reproductions for each R1–R4 and passing
boundary controls, then implement the shared parsing fixes, self-review, record
feedback and refresh package/full-suite checks plus product hashes. Root will
obtain scoped independent re-review and fresh coordinator/native acceptance.

### R5 corrective refinement

Scoped re-review of 92aaeee found that R2's safe-grammar exemption erased
later comma/conjunction clauses containing actual waivers. Root reproduced
both findings. Limit exemption to the requiring/prohibitive prefix through
“without”, only when it introduces a supported review/testing step object.
Keep that object and all later text visible to existing omission/optional
checks. Do not erase a sentence remainder or conjunction clause. Test both
reported compounds, comma-less and alternative-conjunction forms, continued
standalone waiver rejection and the existing positive requiring/prohibitive
controls before implementation. Resource parsing and earlier R1/R3/R4 fixes
remain unchanged. Scoped independent re-review and fresh coordinator checks
are required after the correction.
