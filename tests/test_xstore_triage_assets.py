"""Source/binding checks only; no model, native, or customer acceptance proof."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib
import unittest

from smart_assistant.agent_lifecycle import validate_agent_definition
from smart_assistant.catalog import deployment_manifest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "examples/agents/xstore-triage"
PACK = ASSETS / "knowledge/1.0.0/pack.json"
DEFINITION = ASSETS / "xstore-triage.toml"
BUILDER = ASSETS / "build_definition.py"
BEGIN = "BEGIN XSTORE KNOWLEDGE PACK\n"
END = "END XSTORE KNOWLEDGE PACK\n"


class XstoreTriageAssetsTests(unittest.TestCase):
    def builder(self):
        self.assertTrue(BUILDER.is_file(), "Xstore deterministic binding builder is missing")
        spec = importlib.util.spec_from_file_location("xstore_definition_builder", BUILDER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def mutated_pack(self, change):
        module = self.builder()
        pack = json.loads(PACK.read_bytes())
        change(pack)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pack.json"
            path.write_text(json.dumps(pack))
            with self.assertRaises(ValueError):
                module.load_pack(path)

    def test_exact_complete_inline_pack_and_native_manifest(self):
        module = self.builder()
        raw = PACK.read_bytes()
        value = tomllib.loads(DEFINITION.read_text())
        self.assertEqual(set(value), {"name", "description", "developer_instructions"})
        self.assertEqual(value["name"], "xstore-triage")
        instructions = value["developer_instructions"]
        self.assertEqual(instructions.count(BEGIN), 1)
        self.assertEqual(instructions.count(END), 1)
        embedded = instructions.split(BEGIN, 1)[1].split(END, 1)[0]
        self.assertEqual(embedded.encode(), raw)
        self.assertIn("knowledge_sha256: " + hashlib.sha256(raw).hexdigest(), instructions)
        gate = validate_agent_definition(DEFINITION)
        self.assertTrue(gate.passed, gate.errors)
        binding = module.check_binding(PACK, DEFINITION)
        manifest = deployment_manifest(DEFINITION)
        self.assertEqual(binding["knowledge_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(binding["manifest_sha256"], manifest.manifest_sha256)
        self.assertEqual([f.relative_path for f in manifest.files], ["xstore-triage.toml"])
        self.assertEqual(DEFINITION.read_text(), module.render_definition(raw))

    def test_pack_provenance_is_portable_and_explicitly_bounded(self):
        pack = self.builder().load_pack(PACK)
        self.assertEqual((pack["id"], pack["version"]), ("xstore-triage-procedures", "1.0.0"))
        self.assertEqual(pack["status"], "candidate")
        self.assertEqual(len(pack["procedures"]), 8)
        self.assertTrue(pack["revalidate_when"])
        self.assertIn("not authoritative product", pack["provenance_limits"])
        self.assertIn("independent", pack["provenance_limits"])
        self.assertNotIn("/Users/", PACK.read_text())
        self.assertNotIn("private_origin_path", PACK.read_text())

    def test_reject_duplicate_procedure_and_source_ids(self):
        for field in ("procedures", "sources"):
            with self.subTest(field=field):
                self.mutated_pack(lambda p: p[field].append(p[field][0].copy()))

    def test_reject_missing_provenance_or_unknown_source(self):
        self.mutated_pack(lambda p: p["sources"][0].pop("sha256"))
        self.mutated_pack(lambda p: p["procedures"][0].update(source_refs=[]))
        self.mutated_pack(lambda p: p["procedures"][0]["source_refs"][0].update(source_id="unknown"))
        self.mutated_pack(lambda p: p["procedures"][0]["source_refs"][0].update(section="invented"))

    def test_reject_unsafe_provenance_and_invalid_ranges(self):
        for path in ("../private.txt", "/private/source.txt", "https://example.invalid/source", "a/../b", "C:\\private.txt"):
            with self.subTest(path=path):
                self.mutated_pack(lambda p: p["sources"][0].update(path=path))
        self.mutated_pack(lambda p: p["sources"][0]["sections"][0].update(start_line=True))
        self.mutated_pack(lambda p: p["sources"][0]["sections"][0].update(end_line=999999))

    def test_reject_malformed_json_and_duplicate_json_keys(self):
        module = self.builder()
        for text in ("{", PACK.read_text().replace('"id":', '"id": "duplicate", "id":', 1)):
            with TemporaryDirectory() as directory:
                path = Path(directory) / "pack.json"
                path.write_text(text)
                with self.assertRaises(ValueError):
                    module.load_pack(path)

    def test_reject_delimiters_inside_decoded_pack_guidance(self):
        self.mutated_pack(lambda p: p["procedures"][0].update(guidance=BEGIN))
        self.mutated_pack(lambda p: p["procedures"][0].update(guidance=END))

    def test_reject_raw_pack_drift_even_when_json_semantics_match(self):
        module = self.builder()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pack.json"
            path.write_bytes(PACK.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                module.check_binding(path, DEFINITION)

    def test_reject_instruction_embedding_and_field_drift(self):
        module = self.builder()
        original = DEFINITION.read_text()
        for changed in (original.replace("BEGIN XSTORE", "ALTERED XSTORE", 1),
                        original.replace("xstore-triage-procedures", "other-procedures", 1),
                        original + '\nmodel = "override"\n'):
            with TemporaryDirectory() as directory:
                path = Path(directory) / "xstore-triage.toml"
                path.write_text(changed)
                with self.assertRaises(ValueError):
                    module.check_binding(PACK, path)

    def test_native_basename_cannot_change(self):
        module = self.builder()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "renamed.toml"
            path.write_bytes(DEFINITION.read_bytes())
            with self.assertRaises(ValueError):
                module.check_binding(PACK, path)

    def test_cli_check_preserves_candidate_and_reports_both_digests(self):
        self.builder()
        before = DEFINITION.read_bytes()
        result = subprocess.run([sys.executable, str(BUILDER), "--check"], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(DEFINITION.read_bytes(), before)
        result_json = json.loads(result.stdout)
        self.assertEqual(result_json["knowledge_sha256"], hashlib.sha256(PACK.read_bytes()).hexdigest())
        self.assertEqual(result_json["manifest_sha256"], deployment_manifest(DEFINITION).manifest_sha256)


if __name__ == "__main__":
    unittest.main()
