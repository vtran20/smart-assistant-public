"""Selected project and role context never consumes unrelated scopes."""
import json
import multiprocessing
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from smart_assistant.context import load_context
from smart_assistant.contracts import ValidationError


def fifo_probe(root, outcome):
    try:
        load_context(Path(root), 'project-01')
        outcome.put('accepted')
    except ValidationError:
        outcome.put('rejected')
    except Exception as exc:
        outcome.put(type(exc).__name__)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_bundle(self, project, facts, preferences=None, role=None):
        base = self.root / 'context' / 'projects'
        path = base / f'{project}.json' if role is None else base / project / 'roles' / f'{role}.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'schema_version': 1, 'project_id': project, 'preferences': preferences or {}, 'facts': facts}))
        return path

    def fact(self, text, scope):
        return {'text': text, 'scope': scope, 'source_ref': 'synthetic:source', 'observed_at': '2026-10-13T12:00:00Z'}

    def test_missing_optional_context_is_empty_and_read_only(self):
        result = load_context(self.root, 'project-01')
        self.assertEqual((result.project_id, result.preferences, result.facts), ('project-01', {}, []))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_project_and_role_overlay_is_selected_only(self):
        self.write_bundle('project-01', [self.fact('project fact', 'project:project-01')], {'tone': 'brief', 'locale': 'en'})
        self.write_bundle('project-01', [self.fact('role fact', 'role:writer-01')], {'tone': 'formal'}, role='writer-01')
        self.write_bundle('project-01', [self.fact('other role', 'role:other-01')], role='other-01')
        self.write_bundle('project-02', [self.fact('other project', 'project:project-02')])
        result = load_context(self.root, 'project-01', 'writer-01')
        self.assertEqual(result.preferences, {'tone': 'formal', 'locale': 'en'})
        self.assertEqual([f.text for f in result.facts], ['project fact', 'role fact'])
        self.assertEqual(result.facts[0].observed_at, '2026-10-13T12:00:00Z')
        project_only = load_context(self.root, 'project-01')
        self.assertEqual([f.text for f in project_only.facts], ['project fact'])

    def test_malformed_and_mismatched_scope_rejected(self):
        path = self.write_bundle('project-01', [])
        path.write_text('{')
        with self.assertRaises(ValidationError):
            load_context(self.root, 'project-01')
        path.write_text(json.dumps({'schema_version': 1, 'project_id': 'project-02', 'preferences': {}, 'facts': []}))
        with self.assertRaises(ValidationError):
            load_context(self.root, 'project-01')
        self.write_bundle('project-01', [self.fact('leak', 'project:project-02')])
        with self.assertRaises(ValidationError):
            load_context(self.root, 'project-01')

    def test_role_scope_and_symlink_rejected(self):
        role = self.write_bundle('project-01', [self.fact('leak', 'role:other-01')], role='writer-01')
        with self.assertRaises(ValidationError):
            load_context(self.root, 'project-01', 'writer-01')
        role.unlink()
        outside = self.root / 'outside.json'
        outside.write_text('{}')
        role.symlink_to(outside)
        with self.assertRaises(ValidationError):
            load_context(self.root, 'project-01', 'writer-01')

    def test_unsafe_identifiers_rejected(self):
        for project, role in (('../other', None), ('project-01', '../../other')):
            with self.assertRaises(ValidationError):
                load_context(self.root, project, role)

    def test_parent_swap_at_context_open_cannot_read_outside_root(self):
        self.write_bundle('project-01', [], {'origin': 'inside'})
        projects = self.root / 'context' / 'projects'
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'project-01.json').write_text(json.dumps({
            'schema_version': 1, 'project_id': 'project-01',
            'preferences': {'origin': 'outside'}, 'facts': []}))
        original_open = os.open
        switched = False
        def swap(path, *args, **kwargs):
            nonlocal switched
            if not switched and (Path(path) == projects / 'project-01.json' or
                                 (str(path) == 'project-01.json' and 'dir_fd' in kwargs)):
                switched = True
                projects.rename(self.root / 'context' / 'saved-projects')
                projects.symlink_to(outside, target_is_directory=True)
            return original_open(path, *args, **kwargs)
        with patch('smart_assistant.context.os.open', side_effect=swap):
            try:
                result = load_context(self.root, 'project-01')
            except ValidationError:
                result = None
        self.assertTrue(switched)
        if result is not None:
            self.assertEqual(result.preferences, {'origin': 'inside'})

    def test_context_fifo_rejects_without_blocking(self):
        path = self.root / 'context' / 'projects' / 'project-01.json'
        path.parent.mkdir(parents=True)
        os.mkfifo(path)
        ctx = multiprocessing.get_context('spawn')
        outcome = ctx.Queue()
        child = ctx.Process(target=fifo_probe, args=(str(self.root), outcome))
        child.start()
        child.join(timeout=2)
        if child.is_alive():
            child.terminate()
            child.join(timeout=2)
            self.fail('context FIFO blocked')
        self.assertEqual(child.exitcode, 0)
        self.assertEqual(outcome.get(timeout=2), 'rejected')

    def test_arbitrary_root_alias_is_rejected(self):
        actual = self.root / 'actual'
        actual.mkdir()
        alias = self.root / 'alias'
        alias.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValidationError):
            load_context(alias / 'inner', 'project-01')
