# Xstore evidence triage — corrective DRAFT 1.0.1

This source draft preserves the [original design](../../../../../docs/tasks/xstore-triage/design.md)
and [eleven-field assessment contract](../../../../../docs/tasks/xstore-triage/assessment-contract.json).
Capability version `1.0.1` is managed-catalog metadata, not a supported TOML key.
The definition still has exactly `name`, `description` and `developer_instructions`;
model, effort and permissions are inherited. No catalog, deployment or activation
change is implied by these source files.

The complete original instructions are retained, with one general request-framing
paragraph added. It requires the requested degree of certainty and scope to remain
unchanged: possibility is not a demand for proof of actuality. A bounded assessment
can await independent review while unrequested live, runtime and business gates
remain unproven. Essential missing requested evidence, access or tools still blocks
the requested conclusion; partial positive findings remain useful. The correction
does not authorize tool fallback, evidence fabrication or automatic readiness.

The immutable [knowledge pack 1.0.0](../../knowledge/1.0.0/pack.json) is unchanged,
embedded completely once in the decoded instructions, with raw SHA256
`7670e47e8212a20f2aa7333f624fa7696c7177f271d66be3d8abef241e24baa1`.
Its logical source references remain provenance only. No customer facts, case
answers or release compatibility facts have been added to the procedural pack.
Scope, privacy, permitted filesystem use, effect restrictions, proof gates and
required design/review/feedback/test cycle remain those of the original definition.

## Validation and manual revision

The unchanged [generator](../../build_definition.py) and its `--check`/`--write`
commands render and pin the original 1.0.0 definition. They do not generate or
validate this corrective instruction variant; do not point `--write` at this file.
This revision was assembled manually from the complete original decoded
instructions plus the request-framing paragraph, preserving the pack bytes.
For later authorized edits, keep immutable versions unchanged, create a new
versioned source, and repeat design, independent review, feedback and fresh checks.
Change the pack only under a separately reviewed new immutable knowledge version.

From the repository root, the following read-only check validates this exact
three-field definition, its complete deployment manifest and the original-pack
binding through the existing evaluator helper. Importing the helper and calling
`binding` does not prepare inputs or execute a model, child or native process.

```sh
python3 -B - <<'PY'
import hashlib
import importlib.util
import json
from pathlib import Path
import tomllib
from smart_assistant.agent_lifecycle import validate_agent_definition
from smart_assistant.catalog import deployment_manifest

definition = Path('examples/agents/xstore-triage/versions/1.0.1/xstore-triage.toml')
pack = Path('examples/agents/xstore-triage/knowledge/1.0.0/pack.json')
config = tomllib.loads(definition.read_text(encoding='utf-8'))
assert set(config) == {'name', 'description', 'developer_instructions'}
assert config['name'] == 'xstore-triage'
text = config['developer_instructions']
start, end = 'BEGIN XSTORE KNOWLEDGE PACK\n', 'END XSTORE KNOWLEDGE PACK\n'
assert text.count(start) == text.count(end) == 1
assert text.split(start, 1)[1].split(end, 1)[0].encode('utf-8') == pack.read_bytes()
assert hashlib.sha256(pack.read_bytes()).hexdigest() == '7670e47e8212a20f2aa7333f624fa7696c7177f271d66be3d8abef241e24baa1'
gate = validate_agent_definition(definition)
assert gate.passed, gate.errors
spec = importlib.util.spec_from_file_location('xstore_source_binding', 'examples/scenarios/xstore-triage/native_eval.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
knowledge = module.binding(definition, pack)
manifest = deployment_manifest(definition)
print(json.dumps({'knowledge': knowledge, 'raw_definition_sha256': hashlib.sha256(definition.read_bytes()).hexdigest(), 'manifest_sha256': manifest.manifest_sha256}, sort_keys=True))
PY
```

Current local source-check results are recorded in
source checks (local historical archive: `../../../../../docs/evidence/xstore-triage/revision-1.0.1/source-checks.json`).
These establish configuration shape and byte binding only. Structural checks do
not verify model semantics or determine report readiness for an actual request.
Independent specification and quality review of these exact candidate bytes, plus
coordinator feedback and final checks, remain required. Native behavior of 1.0.1
is **UNASSESSED**: original 1.0.0 outputs do not validate the changed manifest.
Fresh genuine behavior evaluation, supported configured discovery/invocation and
applicable lifecycle proof remain pending. This source revision is **DRAFT**, with
no claim of ACTIVE eligibility, native availability or customer/business acceptance.
No further native/model execution is authorized by this revision.
