"""Display-only team profile and recorded semantic routing decisions."""
import importlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from smart_assistant.contracts import ValidationError

ROOT=Path(__file__).resolve().parents[1]

class TeamProfileTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('smart_assistant.team_profile'))
        return importlib.import_module('smart_assistant.team_profile')

    def test_tom_and_jerry_preserve_bootstrap_and_capability_identity(self):
        m=self.module(); profile=m.load_team_profile(ROOT/'examples/teams/core/team.json')
        self.assertEqual(profile.root.identity,'bootstrap-root')
        self.assertEqual(profile.root.display_name,'Tom')
        self.assertEqual(next(r.display_name for r in profile.roles if r.capability_id=='engineering-lead'),'Jerry')

    def test_draft_role_cannot_route_even_with_claimed_eligible_identity(self):
        m=self.module(); profile=m.load_team_profile(ROOT/'examples/teams/core/team.json')
        result=m.validate_routing_choice(profile,domain='engineering',workflow_kind='bug',
            rationale='Repair a bounded CLI defect',selected_roles=[('engineering-lead','2.0.0')],
            eligible_roles=[('engineering-lead','2.0.0')])
        self.assertFalse(result.passed)

    def test_authorized_direct_choice_requires_explanation_and_no_invented_role(self):
        m=self.module(); profile=m.load_team_profile(ROOT/'examples/teams/core/team.json')
        result=m.validate_routing_choice(profile,domain='employee support',workflow_kind='research',
            rationale='Use available support workflow directly; managed sources remain DRAFT',
            selected_roles=[],eligible_roles=[])
        self.assertTrue(result.passed,result.errors)
        denied=m.validate_routing_choice(profile,domain='engineering',workflow_kind='bug',rationale='',
            selected_roles=[],eligible_roles=[])
        self.assertFalse(denied.passed)

    def test_strict_profile_rejects_duplicate_roles_and_unknown_fields(self):
        m=self.module(); wire=json.loads((ROOT/'examples/teams/core/team.json').read_text())
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'team.json'
            for changed in [dict(wire,extra=True),dict(wire,roles=wire['roles']+[wire['roles'][0]])]:
                path.write_text(json.dumps(changed))
                with self.assertRaises(ValidationError):m.load_team_profile(path)

    def test_truthy_nonstring_source_paths_are_structured_codec_and_load_errors(self):
        m=self.module(); original=json.loads((ROOT/'examples/teams/core/team.json').read_text())
        import copy
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'team.json'
            for value in (7,True,1.5,['truthy'],{'bad':'truthy'}):
                with self.subTest(value=value):
                    wire=copy.deepcopy(original); wire['roles'][0]['source_path']=value
                    with self.assertRaises(ValidationError):m.team_from_dict(wire)
                    path.write_text(json.dumps(wire))
                    with self.assertRaises(ValidationError):m.load_team_profile(path)

    def test_truthy_nonstring_source_paths_return_failed_routing_gate(self):
        from dataclasses import replace
        m=self.module(); profile=m.load_team_profile(ROOT/'examples/teams/core/team.json')
        for value in (7,True,1.5,['truthy'],{'bad':'truthy'}):
            with self.subTest(value=value):
                malformed=replace(profile,roles=[replace(profile.roles[0],source_path=value),*profile.roles[1:]])
                result=m.validate_routing_choice(malformed,domain='engineering',workflow_kind='bug',
                    rationale='Recorded direct workflow',selected_roles=[],eligible_roles=[])
                self.assertFalse(result.passed)
                self.assertIn('invalid_profile',[e.code for e in result.errors])

    def test_truthy_nonstring_source_paths_are_cli_validation_errors(self):
        import subprocess,sys,copy
        original=json.loads((ROOT/'examples/teams/core/team.json').read_text())
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'team.json'
            for value in (7,True,1.5,['truthy'],{'bad':'truthy'}):
                with self.subTest(value=value):
                    wire=copy.deepcopy(original); wire['roles'][0]['source_path']=value
                    path.write_text(json.dumps(wire))
                    result=subprocess.run([sys.executable,'-m','smart_assistant','team','show','--profile',str(path)],
                        cwd=ROOT,text=True,capture_output=True,timeout=15)
                    self.assertEqual(result.returncode,2,result.stdout)
                    payload=json.loads(result.stdout)
                    self.assertIn('invalid_profile',[e['code'] for e in payload['errors']])
                    self.assertTrue(all(e['path']=='$' for e in payload['errors']))
                    self.assertEqual(result.stderr,'')
