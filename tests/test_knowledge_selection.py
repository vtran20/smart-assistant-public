"""Synthetic read-only Markdown selection and provenance tests."""
from dataclasses import asdict, replace
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from smart_assistant.contracts import ValidationError
from smart_assistant.knowledge_selection import (
    KnowledgeRequest, ScopeMetadata, select_knowledge, selection_to_dict,
    revalidate_selection,
)

STAMP = '2026-11-03T12:00:00Z'


def fifo_probe(project, kb, request, outcome):
    try:
        select_knowledge(project_root=project, kb_root=kb, request=request, retrieved_at=STAMP)
        outcome.put('accepted')
    except ValidationError:
        outcome.put('rejected')


class KnowledgeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        self.kb = self.root / 'kb'
        self.project.mkdir()
        self.kb.mkdir()
        (self.project / 'AGENTS.md').write_text('project policy\n')
        (self.project / 'docs').mkdir()
        (self.kb / 'AGENTS.md').write_text('reference instructions\n')
        (self.kb / 'README.md').write_text('index\n')
        (self.kb / 'patterns').mkdir()
        (self.kb / 'patterns' / 'retry.md').write_text('synthetic pattern\n')
        self.scope = ScopeMetadata(
            releases=('26',), jdk='21', platform='desktop',
            custom_layers=('custom',), business_constraints=('constraint-1',),
            integration_ownership=('owner-1',), test_entrypoints=('unit',),
            build_entrypoints=('build',))
        self.request = KnowledgeRequest(
            project_id='project-01', topic_paths=('patterns/retry.md',),
            project_paths=('AGENTS.md', 'docs/project-context.md',
                           'docs/implementation-lessons.md'),
            scope=self.scope, guidance_version='declared-26',
            applicability='applicable')

    def select(self, request=None, **kwargs):
        return select_knowledge(project_root=self.project, kb_root=self.kb,
                                request=request or self.request,
                                retrieved_at=STAMP, **kwargs)

    def valid(self, selection, request=None, project=None):
        return revalidate_selection(selection, project_root=project or self.project,
                                    kb_root=self.kb, request=request or self.request)

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.kb), *args],
                                       stderr=subprocess.DEVNULL).decode().strip()

    def init_git(self):
        self.git('init', '-q')
        self.git('config', 'user.email', 'synthetic@example.invalid')
        self.git('config', 'user.name', 'Synthetic')
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')

    def test_markdown_layout_order_null_commit_and_no_writes(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        result = self.select()
        self.assertTrue(result.usable)
        self.assertEqual(result.git.commit, None)
        self.assertEqual(result.git.dirty, None)
        self.assertEqual(result.git.status, 'not_git')
        self.assertEqual(result.retrieved_at, STAMP)
        self.assertEqual([p.path for p in result.sources], [
            'AGENTS.md', 'docs/project-context.md', 'docs/implementation-lessons.md',
            'AGENTS.md', 'README.md', 'patterns/retry.md'])
        self.assertIsNone(result.sources[1].sha256)
        self.assertEqual(result.sources[-1].sha256,
                         hashlib.sha256(b'synthetic pattern\n').hexdigest())
        self.assertEqual(result.selection_digest, self.select().selection_digest)
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*')))

    def test_explicit_project_context_only(self):
        (self.project / 'docs' / 'project-context.md').write_text('private facts')
        result = self.select(replace(self.request, project_paths=('AGENTS.md',)))
        self.assertEqual([p.path for p in result.sources if p.origin == 'project'], ['AGENTS.md'])

    def test_serialization_excludes_bodies_profiles_and_absolute_paths(self):
        (self.project / '.profile').write_text('SECRET_SENTINEL')
        (self.project / 'docs' / 'project-context.md').write_text('PRIVATE_FACT_SENTINEL')
        text = json.dumps(selection_to_dict(self.select()))
        for forbidden in ('SECRET_SENTINEL', 'PRIVATE_FACT_SENTINEL',
                          str(self.root), 'synthetic pattern', 'reference instructions'):
            self.assertNotIn(forbidden, text)

    def test_unknown_conflicting_and_missing_scope_are_unusable(self):
        for req in (replace(self.request, applicability='unknown'),
                    replace(self.request, applicability='inapplicable'),
                    replace(self.request, guidance_version=None),
                    replace(self.request, conflict_refs=('conflict-1',)),
                    replace(self.request, scope=replace(self.scope, releases=()))):
            with self.subTest(req=req):
                selection = self.select(req)
                self.assertFalse(selection.usable)
                self.assertFalse(self.valid(selection, req).valid)

    def test_unsafe_paths_and_duplicate_sources_rejected(self):
        for path in ('../secret.md', '/secret.md', 'patterns//retry.md', './README.md',
                     'patterns/../README.md', 'patterns\\retry.md', '.profile.md',
                     'client-notes/private.md', 'tools/run.md', 'data.json', 'README.md'):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                self.select(replace(self.request, topic_paths=(path,)))
        with self.assertRaises(ValidationError):
            self.select(replace(self.request, topic_paths=('patterns/retry.md',) * 2))
        with self.assertRaises(ValidationError):
            self.select(replace(self.request, project_paths=('AGENTS.md', '.profile.md')))

    def test_invalid_metadata_and_timestamp_rejected(self):
        for req in (replace(self.request, guidance_version='https://private.invalid/value'),
                    replace(self.request, applicability='invented'),
                    replace(self.request, scope=replace(self.scope, jdk='secret value'))):
            with self.assertRaises(ValidationError):
                self.select(req)
        with self.assertRaises(ValidationError):
            select_knowledge(project_root=self.project, kb_root=self.kb,
                             request=self.request, retrieved_at='yesterday')

    def test_required_file_missing_and_symlink_inputs_rejected(self):
        path = self.kb / 'patterns' / 'retry.md'
        path.unlink()
        with self.assertRaises(ValidationError):
            self.select()
        path.symlink_to(self.kb / 'README.md')
        with self.assertRaises(ValidationError):
            self.select()
        path.unlink()
        (self.kb / 'patterns').rmdir()
        (self.kb / 'patterns').symlink_to(self.project / 'docs', target_is_directory=True)
        with self.assertRaises(ValidationError):
            self.select()
        alias = self.root / 'alias'
        alias.symlink_to(self.project, target_is_directory=True)
        with self.assertRaises(ValidationError):
            select_knowledge(project_root=alias, kb_root=self.kb,
                             request=self.request, retrieved_at=STAMP)

    def test_fifo_invalid_utf8_oversize_and_sanitized_errors(self):
        path = self.kb / 'patterns' / 'retry.md'
        for payload in (b'\xff', b'x' * (1024 * 1024 + 1)):
            path.write_bytes(payload)
            with self.assertRaises(ValidationError) as exc:
                self.select()
            self.assertNotIn(str(self.root), str(exc.exception))
        path.unlink()
        os.mkfifo(path)
        context = multiprocessing.get_context('spawn')
        outcome = context.Queue()
        child = context.Process(target=fifo_probe, args=(self.project, self.kb, self.request, outcome))
        child.start()
        child.join(5)
        if child.is_alive():
            child.terminate()
            child.join(5)
            self.fail('FIFO selection blocked')
        self.assertEqual(outcome.get(timeout=2), 'rejected')
        outcome.close()
        outcome.join_thread()

    def test_private_secret_filenames_rejected(self):
        for name in ('credentials.md', 'secrets.md', 'profile.md', 'profiles/local.md'):
            (self.kb / name).parent.mkdir(parents=True, exist_ok=True)
            (self.kb / name).write_text('SECRET_SENTINEL')
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.select(replace(self.request, topic_paths=(name,)))

    def test_identical_bytes_in_another_kb_root_invalidates(self):
        result = self.select()
        other = self.root / 'other-kb'
        import shutil
        shutil.copytree(self.kb, other)
        fresh = revalidate_selection(result, project_root=self.project, kb_root=other,
                                     request=self.request)
        self.assertFalse(fresh.valid)

    def test_mutation_during_read_rejected(self):
        from smart_assistant import knowledge_selection as module
        original = module._read
        mutated = False

        def read(*args):
            nonlocal mutated
            result = original(*args)
            if result.origin == 'kb' and result.path == 'patterns/retry.md' and not mutated:
                mutated = True
                (self.kb / 'patterns' / 'retry.md').write_text('changed during read')
            return result

        with patch.object(module, '_read', side_effect=read), self.assertRaises(ValidationError):
            self.select()

    def test_git_changes_during_selection_rejected(self):
        from smart_assistant import knowledge_selection as module
        original = module._git
        count = 0

        def provenance(*args):
            nonlocal count
            result = original(*args)
            count += 1
            if count == 1:
                self.init_git()
            return result

        with patch.object(module, '_git', side_effect=provenance), self.assertRaises(ValidationError):
            self.select()

    def test_source_and_context_changes_invalidate_without_repinning(self):
        result = self.select()
        self.assertTrue(self.valid(result).valid)
        (self.kb / 'unselected.md').write_text('unselected')
        self.assertTrue(self.valid(result).valid)
        (self.project / 'docs' / 'project-context.md').write_text('new fact')
        self.assertFalse(self.valid(result).valid)
        (self.project / 'docs' / 'project-context.md').unlink()
        (self.kb / 'patterns' / 'retry.md').write_text('changed')
        self.assertFalse(self.valid(result).valid)
        self.assertEqual(result.sources[-1].sha256,
                         hashlib.sha256(b'synthetic pattern\n').hexdigest())

    def test_root_scope_and_record_tampering_invalidate(self):
        result = self.select()
        other = self.root / 'other'
        other.mkdir()
        (other / 'AGENTS.md').write_text('project policy\n')
        self.assertFalse(self.valid(result, project=other).valid)
        self.assertFalse(self.valid(result, replace(self.request, guidance_version='27')).valid)
        self.assertFalse(self.valid(replace(result, project_context_digest='0' * 64)).valid)

    def test_real_git_clean_and_dirty_provenance(self):
        self.init_git()
        clean = self.select()
        self.assertEqual(clean.git.commit, self.git('rev-parse', 'HEAD'))
        self.assertFalse(clean.git.dirty)
        (self.kb / 'unrelated.md').write_text('other')
        dirty = self.select()
        self.assertTrue(dirty.git.dirty)
        self.assertEqual(dirty.git.selected_dirty_paths, ())
        self.assertFalse(self.valid(clean).valid)
        (self.kb / 'patterns' / 'retry.md').write_text('modified')
        self.assertEqual(self.select().git.selected_dirty_paths, ('patterns/retry.md',))

    def test_non_git_to_git_and_unborn_git_invalidate(self):
        plain = self.select()
        self.git('init', '-q')
        unborn = self.select()
        self.assertEqual(unborn.git.status, 'unavailable')
        self.assertIsNone(unborn.git.commit)
        self.assertFalse(unborn.usable)
        self.assertFalse(self.valid(plain).valid)

    def test_nested_kb_does_not_inherit_parent_git(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.assertEqual(self.select().git.status, 'not_git')
        self.assertIsNone(self.select().git.commit)

    def test_failed_git_inspection_is_not_clean(self):
        self.init_git()
        with patch('smart_assistant.knowledge_selection.subprocess.run', side_effect=OSError):
            result = self.select()
        self.assertEqual(result.git.status, 'unavailable')
        self.assertFalse(result.usable)

    def test_unrelated_project_not_read(self):
        other = self.root / 'other-project'
        other.mkdir()
        (other / 'secret.md').write_text('OTHER_SECRET')
        result = self.select()
        self.assertNotIn('OTHER_SECRET', json.dumps(selection_to_dict(result)))

    def test_forged_identity_policy_and_malformed_records_rejected(self):
        selection = self.select()
        variants = (
            replace(selection, project_id='wrong-project'),
            replace(selection, revalidation_codes=()),
            replace(selection, schema_version=True),
            replace(selection, sources=(replace(selection.sources[0], size_bytes='PRIVATE_VALUE'),
                                        *selection.sources[1:])),
            replace(selection, git=replace(selection.git, status='git', commit=None)),
            replace(selection, usable='PRIVATE_VALUE'),
            replace(selection, retrieved_at=None),
        )
        for malformed in variants:
            wire = asdict(malformed)
            del wire['selection_digest']
            digest = hashlib.sha256(json.dumps(wire, sort_keys=True, separators=(',', ':'),
                                               ensure_ascii=True).encode()).hexdigest()
            forged = replace(malformed, selection_digest=digest)
            with self.subTest(record=malformed):
                self.assertFalse(self.valid(forged).valid)
                with self.assertRaises(ValidationError) as exc:
                    selection_to_dict(forged)
                self.assertNotIn('PRIVATE_VALUE', str(exc.exception))

    def test_git_executable_and_include_config_unavailable_without_status(self):
        self.init_git()
        original = subprocess.run
        for key in ('core.fsmonitor', 'filter.synthetic.clean', 'include.path',
                    'includeif.synthetic.path', 'extensions.worktreeconfig', 'diff.synthetic.textconv'):
            calls = []

            def run(args, **kwargs):
                calls.append(args)
                if 'config' in args:
                    return subprocess.CompletedProcess(args, 0, (key + '\nplaceholder\0').encode(), b'')
                return original(args, **kwargs)

            with self.subTest(key=key), patch('smart_assistant.knowledge_selection.subprocess.run', side_effect=run):
                result = self.select()
                self.assertEqual(result.git.status, 'unavailable')
                self.assertFalse(result.usable)
                self.assertTrue(any('config' in args for args in calls))
                self.assertFalse(any('status' in args for args in calls))

    def test_git_calls_disable_helpers_and_submodules(self):
        self.init_git()
        original = subprocess.run
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            return original(args, **kwargs)

        with patch('smart_assistant.knowledge_selection.subprocess.run', side_effect=run):
            self.assertTrue(self.select().usable)
        for args in calls:
            self.assertIn('core.fsmonitor=false', args)
            self.assertIn('submodule.recurse=false', args)
            self.assertIn('core.excludesFile=' + os.devnull, args)
        status_calls = [args for args in calls if 'status' in args]
        self.assertTrue(status_calls)
        self.assertTrue(all('--ignore-submodules=all' in args for args in status_calls))

    def test_git_submodules_and_malformed_config_unavailable(self):
        self.init_git()
        original = subprocess.run
        for config, index in ((b'malformed', b''), (b'unknown\0', b''),
                              (b'core.bare\nfalse\0', b'160000 ' + b'a' * 40 + b' 0\tchild\0')):
            calls = []

            def run(args, **kwargs):
                calls.append(args)
                if 'config' in args:
                    return subprocess.CompletedProcess(args, 0, config, b'')
                if 'ls-files' in args:
                    return subprocess.CompletedProcess(args, 0, index, b'')
                return original(args, **kwargs)

            with self.subTest(config=config, index=index), patch(
                    'smart_assistant.knowledge_selection.subprocess.run', side_effect=run):
                result = self.select()
                self.assertEqual(result.git.status, 'unavailable')
                self.assertFalse(any('status' in args for args in calls))
        (self.kb / '.gitmodules').write_text('synthetic placeholder')
        with patch('smart_assistant.knowledge_selection.subprocess.run') as mocked:
            self.assertEqual(self.select().git.status, 'unavailable')
            self.assertEqual(mocked.call_count, 0)


if __name__ == '__main__':
    unittest.main()
