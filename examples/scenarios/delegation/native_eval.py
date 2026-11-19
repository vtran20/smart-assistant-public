"""Explicit one-shot installed CLI source evaluator; observations never activation proof."""
import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROLES = ('engineering-lead', 'writer', 'reviewer')
SKILLS = ('delegate-work', 'draft-document', 'verify-completion')
DEFAULT_CLI = '/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def manifest(root, paths):
    return {str(path.relative_to(root)): sha(path) for path in sorted(paths)}


def prepare(project, fixture, output):
    """No model calls. New output directory only; never overwrite earlier failures."""
    project, fixture = project.resolve(strict=True), fixture.resolve(strict=True)
    output = output.parent.resolve(strict=True) / output.name
    if output.is_relative_to(project) or output.is_relative_to(fixture):
        raise ValueError('Output must be outside project and fixture')
    if output.exists():
        raise ValueError('Output exists; preserve earlier evaluation, supply a new path')
    # Inventory and validate every required source before creating the run root.
    helper = project / 'smart_assistant'
    trees = [helper] + [project / '.agents/skills' / skill for skill in SKILLS]
    for tree in trees:
        if not tree.is_dir() or tree.resolve(strict=True) != tree:
            raise ValueError('Missing or symlinked source tree: ' + str(tree))
        for entry in tree.rglob('*'):
            if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
                raise ValueError('Symlink or nonregular source tree entry: ' + str(entry))
    sources = list(helper.rglob('*.py'))
    for role in ROLES:
        sources.append(project / '.codex/agents' / (role + '.toml'))
    for skill in SKILLS:
        directory = project / '.agents/skills' / skill
        if not (directory / 'SKILL.md').is_file():
            raise ValueError('Missing native skill: ' + skill)
        sources.extend(path for path in directory.rglob('*') if path.is_file())
    if not (project / 'smart_assistant/__init__.py').is_file():
        raise ValueError('Missing helper package')
    if not sources or not all(path.is_file() and path.resolve(strict=True) == path for path in sources):
        raise ValueError('Required source missing or symlinked')
    entries = list(fixture.rglob('*'))
    if any(path.is_symlink() or not (path.is_file() or path.is_dir()) for path in entries):
        raise ValueError('Symlink or nonregular fixture entry rejected')
    fixtures = [path for path in entries if path.is_file()]
    if any(path.is_symlink() for path in fixture.rglob('*')):
        raise ValueError('Fixture symlinks rejected')
    if any(path.relative_to(fixture).parts[0] in ('.codex', '.agents', 'smart_assistant', '.git', 'private-state') for path in fixtures):
        raise ValueError('Fixture attempts to replace evaluator-owned files')
    output.mkdir(parents=True)
    root = output / 'project'
    root.mkdir()
    copied = {}
    for source in sources:
        target = root / source.relative_to(project)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied[str(target.relative_to(root))] = sha(target)
        if sha(source) != sha(target):
            raise ValueError('Source changed during copying')
    for source in fixtures:
        target = root / source.relative_to(fixture)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (root / '.codex/config.toml').write_text('[agents]\nenabled = true\n')
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    save(output / 'manifest-before.json', {'source_project': str(project), 'files': copied,
        'fixture_files': manifest(fixture, fixtures), 'config_sha256': sha(root / '.codex/config.toml')})
    return root, copied


def trust(root):
    return 'projects={' + json.dumps(str(root)) + '={trust_level="trusted"}}'


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
        await request('initialize', {'clientInfo': {'name': 'p08-source-evaluator', 'version': '1'},
            'capabilities': {'experimentalApi': True}})
        process.stdin.write(b'{"method":"initialized"}\n')
        await process.stdin.drain()
        config = await request('config/read', {'cwd': str(root), 'includeLayers': True})
        agents = (config.get('config', {}).get('agents') or {})
        skills = await request('skills/list', {'cwds': [str(root)], 'forceReload': True})
        proof = {'agents': {key: agents[key] for key in ROLES if key in agents},
            'skills': [skill for group in skills.get('data', []) for skill in group.get('skills', [])
                if skill.get('name') in SKILLS], 'threads': []}
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
        return sha(path) if path.is_file() and not path.is_symlink() else None
    sources = {name: digest(name) for name in copied}
    fixtures = {name: digest(name) for name in before['fixture_files']}
    config = digest('.codex/config.toml')
    return dict(files=sources, fixture_files=fixtures, config_sha256=config,
        sources_unchanged=sources == copied,
        fixture_unchanged=fixtures == before['fixture_files'],
        config_unchanged=config == before['config_sha256'])


def run(cli, root, output, prompt, timeout, copied):
    command = [cli, '--no-daemon', '-a', 'on-request', '-s', 'workspace-write', '-C', str(root),
        '-c', trust(root), 'exec', '--json']
    save(output / 'command.json', command)
    (output / 'prompt.txt').write_text(prompt)
    timed_out = False
    with (output / 'events.jsonl').open('w') as events, (output / 'stderr.log').open('w') as errors:
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
    result = {'exit_code': process.returncode, 'timed_out': timed_out, 'thread_id': thread,
        'sources_unchanged': after['sources_unchanged'],
        'fixture_unchanged': after['fixture_unchanged'], 'config_unchanged': after['config_unchanged'], 'acceptance': 'UNASSESSED; external independent review required'}
    save(output / 'result.json', result)
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
