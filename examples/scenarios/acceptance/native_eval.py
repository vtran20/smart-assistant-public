"""Explicit one-shot installed CLI source evaluator; observations never activation proof."""
import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROLES = ('engineering-lead', 'writer', 'reviewer')
SKILLS = ('request-coordination', 'manage-agent', 'manage-skill', 'delegate-work', 'draft-document', 'verify-completion')
DEFAULT_CLI = '/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def manifest(root, paths):
    if not all(regular(path) for path in paths):
        raise ValueError('Manifest input is missing or unsafe')
    return {str(path.relative_to(root)): sha(path) for path in sorted(paths)}


def regular(path):
    """Do not follow a symlink in any ancestor when collecting evidence."""
    return not any(part.is_symlink() for part in (path, *path.parents)) and path.is_file()


def tree_files(tree):
    if any(part.is_symlink() for part in (tree, *tree.parents)) or not tree.is_dir():
        raise ValueError('Missing or symlinked source/fixture tree: ' + str(tree))
    entries = list(tree.rglob('*'))
    if any(path.is_symlink() or not (path.is_file() or path.is_dir()) for path in entries):
        raise ValueError('Symlink or nonregular tree entry: ' + str(tree))
    return [path for path in entries if path.is_file()]


def native_inventory(root):
    result = {}
    for name in ('.codex/agents', '.agents/skills'):
        tree = root / name
        try:
            result.update(manifest(root, tree_files(tree)))
        except ValueError as error:
            result[name] = {'unsafe_or_missing': str(error)}
    return result


def prepare(project, fixture, output):
    """No model calls. Exact pinned source copy; new output directory only."""
    project, fixture, output = map(lambda path: Path(path).absolute(), (project, fixture, output))
    tree_files(project / 'smart_assistant')
    tree_files(fixture)
    if any(part.is_symlink() for part in (project, *project.parents, output, *output.parents)):
        raise ValueError('Symlinked project/output path rejected')
    project, fixture, output = project.resolve(), fixture.resolve(), output.resolve()
    fixtures = tree_files(fixture)
    if output.is_relative_to(project) or output.is_relative_to(fixture):
        raise ValueError('Output must be outside project and fixture')
    if output.exists():
        raise ValueError('Output exists; preserve earlier evaluation, supply a new path')
    sources = [path for path in tree_files(project / 'smart_assistant') if path.suffix == '.py']
    for role in ROLES:
        source = project / '.codex/agents' / (role + '.toml')
        if not regular(source):
            raise ValueError('Required native role missing or unsafe: ' + role)
        sources.append(source)
    for skill in SKILLS:
        directory = project / '.agents/skills' / skill
        resources = tree_files(directory)
        if not regular(directory / 'SKILL.md'):
            raise ValueError('Missing native skill: ' + skill)
        sources.extend(resources)
    if not regular(project / 'smart_assistant/__init__.py'):
        raise ValueError('Missing helper package')
    reserved = {'.codex', '.agents', 'smart_assistant', '.git', '.smart-assistant', 'private-state',
                'AGENTS.md', 'AGENTS.override.md'}
    if any(path.relative_to(fixture).parts[0] in reserved for path in fixture.rglob('*')):
        raise ValueError('Fixture attempts to replace evaluator-owned files or private state')
    source_before, fixture_before = manifest(project, sources), manifest(fixture, fixtures)
    output.mkdir(parents=True)
    root = output / 'project'
    root.mkdir()
    save(output / 'input-pins.json', {'source_project': str(project), 'fixture': str(fixture),
        'files': source_before, 'fixture_files': fixture_before})
    for source, parent in [(path, project) for path in sources] + [(path, fixture) for path in fixtures]:
        target = root / source.relative_to(parent)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    current_sources = [path for path in tree_files(project / 'smart_assistant') if path.suffix == '.py']
    current_sources.extend(project / '.codex/agents' / (role + '.toml') for role in ROLES)
    for skill in SKILLS:
        current_sources.extend(tree_files(project / '.agents/skills' / skill))
    if manifest(project, current_sources) != source_before or manifest(fixture, tree_files(fixture)) != fixture_before:
        raise ValueError('Source or fixture changed during copying; preserve output for inspection')
    copied = manifest(root, [root / name for name in source_before])
    if copied != source_before or manifest(root, [root / name for name in fixture_before]) != fixture_before:
        raise ValueError('Copy differs from frozen input; preserve output for inspection')
    (root / '.codex/config.toml').write_text('[agents]\nenabled = true\n')
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    save(output / 'manifest-before.json', {'source_project': str(project), 'fixture': str(fixture),
        'files': copied, 'fixture_files': fixture_before,
        'config_sha256': sha(root / '.codex/config.toml'), 'native_assets': native_inventory(root)})
    return root, copied


def trust(root):
    return 'projects={' + json.dumps(str(root)) + '={trust_level="trusted"}}'


def discovery_fields(value, fields):
    """Persist only scalar public discovery metadata, never arbitrary settings."""
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in fields
            if key in value and type(value[key]) in (str, bool)}


async def observe(cli, root, thread_id, output):
    process = await asyncio.create_subprocess_exec(cli, '-c', trust(root), 'app-server', '--stdio',
        cwd=root, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=(stderr_log := (output / 'public-stderr.log').open('wb')), limit=16 * 1024 * 1024)
    count = 0
    async def request(method, params):
        nonlocal count
        count += 1
        process.stdin.write((json.dumps({'id': count, 'method': method, 'params': params}) + '\n').encode())
        await process.stdin.drain()
        while True:
            raw = await process.stdout.readline()
            if not raw:
                raise RuntimeError('Public app-server closed')
            if method == 'thread/read':
                with (output / 'public-thread-events.jsonl').open('ab') as stream:
                    stream.write(raw)
            reply = json.loads(raw)
            if reply.get('id') == count:
                if 'error' in reply:
                    raise RuntimeError(str(reply['error']))
                return reply['result']
    try:
        await request('initialize', {'clientInfo': {'name': 'p09-source-evaluator', 'version': '1'},
            'capabilities': {'experimentalApi': True}})
        process.stdin.write(b'{"method":"initialized"}\n')
        await process.stdin.drain()
        config = await request('config/read', {'cwd': str(root), 'includeLayers': False})
        current = config.get('config') or {}
        agents = current.get('agents') or {}
        skills = await request('skills/list', {'cwds': [str(root)], 'forceReload': True})
        role_fields = ('description', 'config_file', 'source', 'model', 'model_reasoning_effort')
        skill_fields = ('name', 'path', 'description', 'shortDescription', 'enabled', 'scope', 'source')
        proof = {'agents': {name: discovery_fields(value, role_fields)
                            for name, value in agents.items() if isinstance(value, dict)},
            'settings': discovery_fields(current, ('model', 'model_reasoning_effort')),
            'skills': [discovery_fields(skill, skill_fields)
                       for group in skills.get('data', []) for skill in group.get('skills', [])],
            'native_assets': native_inventory(root), 'threads': [],
            'acceptance': 'UNASSESSED; discovery is not activation or behavior proof'}
        save(output / 'public-proof.json', proof)
        visited = set()
        async def read(identity, depth):
            if identity in visited or depth > 2 or len(visited) >= 16:
                return
            visited.add(identity)
            thread = (await request('thread/read', {'threadId': identity, 'includeTurns': True}))['thread']
            proof['threads'].append(thread)
            save(output / 'public-proof.json', proof)
            for turn in thread.get('turns', []):
                for item in turn.get('items', []):
                    if item.get('type') == 'subAgentActivity' and item.get('agentThreadId'):
                        await read(item['agentThreadId'], depth + 1)
        if thread_id:
            await read(thread_id, 0)
        return proof
    finally:
        if process.returncode is None:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        stderr_log.close()


def capture_after(root, copied, before):
    def digest(name):
        path = root / name
        return sha(path) if regular(path) else None
    sources = {name: digest(name) for name in copied}
    fixtures = {name: digest(name) for name in before['fixture_files']}
    config = digest('.codex/config.toml')
    assets = native_inventory(root)
    try:
        helper = manifest(root, [path for path in tree_files(root / 'smart_assistant') if path.suffix == '.py'])
    except ValueError as error:
        helper = {'unsafe_or_missing': str(error)}
    expected_helper = {name: value for name, value in copied.items() if name.startswith('smart_assistant/')}
    return dict(files=sources, helper_files=helper, fixture_files=fixtures, config_sha256=config,
        native_assets=assets, native_assets_unchanged=assets == before['native_assets'],
        sources_unchanged=sources == copied and helper == expected_helper,
        fixture_unchanged=fixtures == before['fixture_files'],
        config_unchanged=config == before['config_sha256'])


def run(cli, root, output, prompt, timeout, copied):
    if type(timeout) is not int or not 1 <= timeout <= 900:
        raise ValueError('timeout must be between 1 and 900 seconds')
    if (output / 'events.jsonl').exists() or (output / 'result.json').exists():
        raise ValueError('Run already attempted; preserve evidence and prepare a new output')
    execution_error = None
    process = None
    command = [cli, '--no-daemon', '-a', 'on-request', '-s', 'workspace-write', '-C', str(root),
        '-c', trust(root), 'exec', '--json']
    save(output / 'command.json', command)
    (output / 'prompt.txt').write_text(prompt)
    timed_out = False
    with (output / 'events.jsonl').open('w') as events, (output / 'stderr.log').open('w') as errors:
        try:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=events, stderr=errors, text=True)
            try:
                process.communicate(prompt, timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
        except OSError as error:
            execution_error = str(error)
            errors.write(execution_error + '\n')
    thread = None
    for line in (output / 'events.jsonl').read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') == 'thread.started':
            thread = event.get('thread_id')
    before = json.loads((output / 'manifest-before.json').read_text())
    after = capture_after(root, copied, before)
    save(output / 'manifest-after.json', after)
    result = {'exit_code': process.returncode if process else None, 'timed_out': timed_out, 'thread_id': thread,
        'sources_unchanged': after['sources_unchanged'],
        'native_assets_unchanged': after['native_assets_unchanged'],
        'fixture_unchanged': after['fixture_unchanged'], 'config_unchanged': after['config_unchanged'], 'acceptance': 'UNASSESSED; external independent review required'}
    if execution_error:
        result['execution_error'] = execution_error
    save(output / 'result.json', result)
    if execution_error:
        return result
    async def bounded():
        return await asyncio.wait_for(observe(cli, root, thread, output), 90)
    try:
        asyncio.run(bounded())
    except Exception as error:
        result['observation_error'] = str(error)
        save(output / 'result.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('project', 'fixture', 'output', 'prompt'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--cli', default=DEFAULT_CLI)
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--run', action='store_true', help='Execute only after explicit coordinator approval')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 900:
        parser.error('timeout must be between 1 and 900 seconds')
    prompt = args.prompt.resolve(strict=True).read_text()
    root, copied = prepare(args.project, args.fixture, args.output)
    if args.run:
        print(json.dumps(run(args.cli, root, args.output.absolute(), prompt, args.timeout, copied), indent=2))
    else:
        print(json.dumps({'prepared_root': str(root), 'model_calls': 0}))
