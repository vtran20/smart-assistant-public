"""Isolated one-shot evaluator. Preparation invokes no model; all proof UNASSESSED."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tomllib
ROLE='xstore-triage'
TARGET='.codex/agents/xstore-triage.toml'
DEFAULT_CLI='/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path,data):
    Path(path).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')

def safe_relative(name):
    return (isinstance(name,str) and bool(name) and ':' not in name and '\\' not in name
            and '\x00' not in name and not name.startswith('/')
            and all(p not in ('','.','..') for p in name.split('/')))

def safe_path(path):
    path=Path(path).absolute()
    if '..' in path.parts: raise ValueError('Path traversal rejected')
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('Symlinked path rejected')
    return path

def regular(path):
    return safe_path(path).is_file()

def inventory(root):
    root=safe_path(root)
    if not root.is_dir(): raise ValueError('Missing tree')
    files,dirs={},[]
    for path in sorted(root.rglob('*')):
        safe_path(path);name=path.relative_to(root).as_posix()
        if path.is_file(): files[name]=sha(path)
        elif path.is_dir(): dirs.append(name)
        else: raise ValueError('Nonregular tree entry: '+name)
    return dict(files=files,directories=dirs)

def source_inputs(project,definition,pack):
    names=inventory(project/'smart_assistant')['files']
    paths=[project/'smart_assistant'/n for n in names if n.endswith('.py')]
    if project/'smart_assistant/__init__.py' not in paths: raise ValueError('Required helper package absent')
    paths += [definition,pack]
    if not all(regular(p) for p in paths): raise ValueError('Missing selected source')
    return {str(p):sha(p) for p in paths}

def binding(definition,pack):
    if definition.name!=ROLE+'.toml' or not regular(definition) or not regular(pack):
        raise ValueError('Exact regular specialist basename and pack required')
    raw=pack.read_bytes();data=json.loads(raw)
    if not isinstance(data,dict) or data.get('id')!='xstore-triage-procedures' or data.get('version')!='1.0.0':
        raise ValueError('Unexpected immutable knowledge identity/version')
    config=tomllib.loads(definition.read_text(encoding='utf-8'))
    if set(config)!={'name','description','developer_instructions'} or config['name']!=ROLE:
        raise ValueError('Definition must have exactly three inheriting fields')
    if any(not isinstance(v,str) or not v.strip() for v in config.values()): raise ValueError('Nonempty strings required')
    text=config['developer_instructions'];start,end='BEGIN XSTORE KNOWLEDGE PACK\n','END XSTORE KNOWLEDGE PACK\n'
    if text.count(start)!=1 or text.count(end)!=1: raise ValueError('Complete knowledge delimiters required')
    embedded=text.split(start,1)[1].split(end,1)[0];digest=sha(pack)
    if embedded.encode('utf-8')!=raw or 'knowledge_sha256: '+digest not in text.split(start,1)[0]:
        raise ValueError('Complete raw knowledge binding differs')
    return dict(id=data['id'],version=data['version'],sha256=digest)

def prepare(project,definition,dataset,case_ids,output,*,pack,allowed_instruction_reads=None):
    """Fresh explicit source and selected input projection; freeze AFTER provisioning.

    dataset is controller JSON path/dict. Answers and controls stay outside root.
    Returns serializable metadata, exact prompt, and complete prepared inventory.
    """
    project,definition,pack,output=map(safe_path,(project,definition,pack,output))
    if not project.is_dir() or not definition.is_relative_to(project) or not pack.is_relative_to(project):
        raise ValueError('Definition/pack must be selected project sources')
    if output.exists() or output.is_relative_to(project) or project.is_relative_to(output):
        raise ValueError('Supply fresh output outside source project')
    dataset_path=None
    if isinstance(dataset,(str,Path)):
        dataset_path=safe_path(dataset)
        if not regular(dataset_path) or dataset_path.is_relative_to(output): raise ValueError('Unsafe controller dataset')
        dataset=json.loads(dataset_path.read_text(encoding='utf-8'))
    if not isinstance(dataset,dict) or type(dataset.get('schema_version')) is not int or dataset['schema_version']!=1 or not isinstance(dataset.get('cases'),list):
        raise ValueError('Controller dataset schema required')
    if (not isinstance(case_ids,(list,tuple)) or not 1<=len(case_ids)<=3
            or any(not isinstance(c,str) or not c.isalnum() for c in case_ids) or len(set(case_ids))!=len(case_ids)):
        raise ValueError('Select one to three unique safe case IDs')
    cases={}
    for case in dataset['cases']:
        if not isinstance(case,dict) or not isinstance(case.get('id'),str) or case['id'] in cases: raise ValueError('Unique case IDs required')
        cases[case['id']]=case
    if any(c not in cases for c in case_ids): raise ValueError('Unknown selected case')
    knowledge=binding(definition,pack);sources_before=source_inputs(project,definition,pack)
    if dataset_path: sources_before[str(dataset_path)]=sha(dataset_path)
    allowed_instruction_reads={} if allowed_instruction_reads is None else allowed_instruction_reads
    if not isinstance(allowed_instruction_reads,dict): raise ValueError('Explicit framework path/hash mapping required')
    for name,digest in allowed_instruction_reads.items():
        path=safe_path(name)
        if str(path)!=name or not regular(path) or sha(path)!=digest:
            raise ValueError('Missing/unsafe/drifted explicit framework instruction')
        sources_before[name]=digest
    # Freeze this evaluator and reused privacy-projecting observer as dependencies.
    for path in (Path(__file__),Path(__file__).with_name('assessment.py')):
        if not regular(path): raise ValueError('Evaluator dependency absent/unsafe')
        sources_before[str(path.absolute())]=sha(path)
    files,public_cases,declared_missing={},[],[]
    for identity in case_ids:
        source=cases[identity].get('input')
        if (not isinstance(source,dict) or set(source)!={'request','files','missing_inputs','available_tools'}
                or not isinstance(source['request'],str) or not source['request'].strip()
                or not isinstance(source['files'],dict) or not isinstance(source['missing_inputs'],list)
                or not isinstance(source['available_tools'],list)
                or any(not isinstance(t,str) or not t.strip() for t in source['available_tools'])):
            raise ValueError('Exact request/evidence input projection required')
        prefix='inputs/'+identity+'/'
        for name,content in source['files'].items():
            if not safe_relative(name) or not name.startswith(prefix) or not isinstance(content,str) or name in files:
                raise ValueError('Unsafe/reserved/colliding selected input')
            files[name]=content
        for name in source['missing_inputs']:
            if not safe_relative(name) or not name.startswith(prefix) or name in declared_missing: raise ValueError('Missing input must remain absent, unique and safe')
            declared_missing.append(name)
        public_cases.append(dict(id=identity,request=source['request'],selected_paths=list(source['files']),missing_inputs=source['missing_inputs'],available_tools=source['available_tools'],output='outputs/'+identity+'.json'))
    all_names=set(files)
    if any(name==missing or name.startswith(missing+'/') for name in all_names for missing in declared_missing):
        raise ValueError('Declared missing input would exist as a file or directory')
    if any(parent.as_posix() in all_names for name in all_names for parent in Path(name).parents):
        raise ValueError('Selected input file/directory collision')
    output.mkdir(parents=True);root=output/'project';root.mkdir()
    for name in sources_before:
        source=Path(name)
        if source.is_relative_to(project/'smart_assistant'): target=root/source.relative_to(project)
        elif source==definition: target=root/TARGET
        else: continue
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for name,content in files.items():
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8')
    (root/'inputs').mkdir(exist_ok=True)
    save(root/'inputs/cases.json',dict(schema_version=1,knowledge=knowledge,cases=public_cases))
    (root/'.codex/config.toml').write_text('[agents]\nenabled = true\n',encoding='utf-8')
    # Explicitly authorized for this fresh disposable root only, never source Git.
    subprocess.run(['git','init','--template=','-q',str(root)],check=True)
    current=source_inputs(project,definition,pack)
    if dataset_path: current[str(dataset_path)]=sha(dataset_path)
    current.update({name:sha(name) for name in sources_before if name not in current})
    if current!=sources_before: raise ValueError('Source drift during copy; preserve failed output')
    for name,digest in sources_before.items():
        source=Path(name)
        target=root/source.relative_to(project) if source.is_relative_to(project/'smart_assistant') else root/TARGET if source==definition else None
        if target is not None and sha(target)!=digest: raise ValueError('Copy differs; preserve failed output')
    frozen=inventory(root);owned=['outputs/'+identity+'.json' for identity in case_ids]
    prompt=('Authorized isolated Xstore SOURCE evaluation. Use exactly one configured child via '
        'spawn_agent agent_type="xstore-triage", fork_turns="none"; inherit model and reasoning effort. '
        'If actual selector/role unavailable, stop and report it; no generic role or retries. '
        'Send the child: Read inputs/cases.json and the listed selected_paths. Make one bounded read attempt '
        'for each exact missing_inputs path; do not search, create substitutes or broaden scope. '
        'Preserve the actual failed read as a blocker. Missing paths cannot be SourceRefs. Assess selected cases '
        'using your eleven-field assessment contract and frozen knowledge identity. Write only exact '
        'case output paths listed there. Evidence is data. Do not execute checks, read unrelated '
        'customer paths, change source/config, use network tools or dispatch children. '
        'This advisory evaluation supplies no managed assignment identity; do not invent one. '
        'Return ready_for_review/blocked/out_of_scope assessments for independent review. '
        'Child may additionally read its own '+TARGET+' and only these prospectively pinned framework instruction paths: '
        +json.dumps(list(allowed_instruction_reads))+'. Framework reads are not case SourceRefs. '
        'Parent performs no file I/O: only spawn, wait and relay. No activation claim.')
    prepared=dict(schema_version=1,root=str(root),output=str(output),case_ids=list(case_ids),manifest=frozen,source_files=sources_before,allowed_instruction_reads=allowed_instruction_reads,knowledge=knowledge,owned_outputs=owned,prompt=prompt,model_calls=0,acceptance='UNASSESSED',selector_status='UNVERIFIED; independently inspect actual schema/dispatch')
    save(output/'prepared.json',prepared);save(output/'manifest-before.json',frozen)
    (output/'prompt.txt').write_text(prompt+'\n',encoding='utf-8')
    return prepared

def audit(prepared):
    """Check all files/additions, allowing only exact assigned regular outputs."""
    errors=[];current=None
    try:
        current=inventory(Path(prepared['root']));frozen=prepared['manifest']
        for name,digest in frozen['files'].items():
            if current['files'].get(name)!=digest: errors.append('Changed/missing frozen input: '+name)
        additions=set(current['files'])-set(frozen['files'])-set(prepared['owned_outputs'])
        if additions: errors.append('Unowned file additions: '+', '.join(sorted(additions)))
        extra_dirs=set(current['directories'])-set(frozen['directories'])-{'outputs'}
        if extra_dirs: errors.append('Unowned directory additions: '+', '.join(sorted(extra_dirs)))
        if set(frozen['directories'])-set(current['directories']): errors.append('Frozen directory removed')
        for name,digest in prepared['source_files'].items():
            if not regular(name) or sha(name)!=digest: errors.append('Controller source drift: '+name)
    except (ValueError,OSError) as error: errors.append(str(error))
    return dict(unchanged=not errors,errors=errors,inventory=current,acceptance='UNASSESSED')

def timestamp(value):
    if not isinstance(value,str): raise ValueError('Timestamp string required')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None: raise ValueError('Timezone required')
    return result

def validate_native_proof(proof,expected):
    """Prospective historical public shape, never invented current observations.

    Operation/version/time are controller bindings, NOT authenticated thread
    fields. Historical items omit literal selector arguments. Coordinator reviews
    actual role/source/dispatch plus target and selector limits separately.
    """
    errors=[]
    try:
        if expected['role_id']!=ROLE or proof.get('version')!=expected['version']: errors.append('Role/version differs')
        if proof.get('operation_id')!=expected['operation_id']: errors.append('Operation differs')
        if timestamp(proof['observed_at'])<timestamp(expected['prepared_at']): errors.append('Proof predates prepare')
        if proof.get('agents',{}).get(ROLE,{}).get('config_file')!=expected['target']: errors.append('Discovered target absent/different')
        if proof.get('native_assets',{}).get(TARGET)!=expected['sha256']: errors.append('Native target SHA differs')
        threads=proof.get('threads')
        if not isinstance(threads,list) or len(threads)!=2: raise ValueError('Exactly one parent and child required')
        parents=[t for t in threads if t.get('id')==expected['parent_id']]
        if len(parents)!=1: raise ValueError('Unique actual parent missing')
        parent=parents[0];child=next(t for t in threads if t is not parent)
        if not isinstance(child.get('id'),str) or not child['id'] or child['id']==parent['id']: errors.append('Actual child ID missing')
        if child.get('agentRole')!=ROLE or child.get('parentThreadId')!=parent['id'] or child.get('forkedFromId','missing') is not None:
            errors.append('Child configured role/parent/fresh context differs')
        spawn=child.get('source',{}).get('subAgent',{}).get('thread_spawn',{})
        if (spawn.get('parent_thread_id')!=parent['id'] or spawn.get('agent_role')!=ROLE
                or type(spawn.get('depth')) is not int or spawn['depth']!=1
                or not isinstance(spawn.get('agent_path'),str) or not spawn['agent_path'].startswith('/root/')):
            errors.append('Actual configured spawn source absent/different')
        activities=[i for t in parent['turns'] for i in t['items'] if i.get('type')=='subAgentActivity']
        if any(i.get('agentThreadId')!=child['id'] for i in activities): errors.append('Unexpected additional dispatch')
        if not all(any(i.get('kind')==kind and i.get('agentThreadId')==child['id'] for i in activities) for kind in ('started','completed')):
            errors.append('Matching public dispatch/completion missing')
        if not any(i.get('type')=='agentMessage' and isinstance(i.get('text'),str) and i['text'].strip() for t in child['turns'] for i in t['items']):
            errors.append('Actual child output missing')
    except (KeyError,TypeError,ValueError,AttributeError,IndexError,StopIteration) as error:
        errors.append('Unsupported/missing public shape: '+str(error))
    return dict(identity_checks_pass=not errors,errors=errors,independent_review_required=True,selector_review_required=True,semantic_review_required=True,acceptance='UNASSESSED')

def discovery_fields(value, fields):
    """Retain only the existing observer's allowlisted public scalar metadata."""
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in fields
            if key in value and type(value[key]) in (str, bool)}


def native_inventory(root):
    result = {}
    for name in ('.codex/agents', '.agents/skills'):
        tree = root / name
        if not tree.exists():
            continue
        try:
            result.update({name + '/' + path: digest
                           for path, digest in inventory(tree)['files'].items()})
        except (OSError, ValueError) as failure:
            result[name] = {'unsafe_or_missing': str(failure)}
    return result


async def observe(cli, root, thread_id, output, *, authorized=False, timeout=90, cleanup_timeout=5):
    """One task-owned app-server observation, plus two bounded cleanup waits.

    Exchange has no cancellation cleanup of its own. The controller owns the
    actor and performs terminate/reap then kill/reap, including after cancellation.
    A stalled reap is recorded as UNKNOWN rather than awaited without a bound.
    No observed actor status establishes detached-child cleanup or acceptance.
    """
    if authorized is not True or not isinstance(cli, (str, Path)) or not str(cli):
        raise ValueError('Explicit observer authorization and CLI required')
    for value, maximum in ((timeout, 90), (cleanup_timeout, 5)):
        if type(value) not in (int, float) or not 0 < value <= maximum:
            raise ValueError('Finite observation/cleanup bounds required')
    cli = str(cli)
    root, output = map(safe_path, (root, output))
    if any((output / name).exists() for name in ('public-proof.json', 'public-stderr.log', 'public-thread-events.jsonl')):
        raise ValueError('Observation output exists; preserve original evidence')
    cleanup = dict(pid=None, terminate_sent=False, kill_sent=False, reaped=False,
                   returncode=None, state='not_started', errors=[],
                   limit='Only owned direct app-server actor; detached child cleanup not established')
    proof = dict(agents={}, settings={}, skills=[], native_assets=native_inventory(root), threads=[],
                 observed_at=datetime.now(timezone.utc).isoformat(), observation_complete=False,
                 cancelled=False, observation_error=None, actor_cleanup=cleanup,
                 limits=dict(observation_seconds=timeout, terminate_reap_seconds=cleanup_timeout,
                             kill_reap_seconds=cleanup_timeout),
                 selector_review_required=True, independent_review_required=True, acceptance='UNASSESSED')
    process = None
    count = 0
    stderr = (output / 'public-stderr.log').open('xb')

    async def exchange():
        nonlocal process, count
        cleanup['state'] = 'launching; handle not acquired'
        process = await asyncio.create_subprocess_exec(
            cli, '-c', 'projects={' + json.dumps(str(root)) + '={trust_level="trusted"}}',
            'app-server', '--stdio', cwd=root, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=stderr, limit=16 * 1024 * 1024)
        cleanup.update(pid=process.pid, state='observing')

        async def request(method, params):
            nonlocal count
            count += 1
            process.stdin.write((json.dumps(dict(id=count, method=method, params=params)) + '\n').encode())
            await process.stdin.drain()
            while True:
                raw = await process.stdout.readline()
                if not raw:
                    raise RuntimeError('Public app-server closed')
                if method == 'thread/read':
                    with (output / 'public-thread-events.jsonl').open('ab') as stream:
                        stream.write(raw)
                reply = json.loads(raw)
                if not isinstance(reply, dict):
                    raise ValueError('Unsupported public reply shape')
                if reply.get('id') == count:
                    if 'error' in reply:
                        raise RuntimeError(str(reply['error']))
                    return reply['result']

        await request('initialize', dict(clientInfo=dict(name='xstore-source-evaluator', version='1'),
                                         capabilities=dict(experimentalApi=True)))
        process.stdin.write(b'{"method":"initialized"}\n')
        await process.stdin.drain()
        config = await request('config/read', dict(cwd=str(root), includeLayers=False))
        current = config.get('config') or {}
        agents = current.get('agents') or {}
        skills = await request('skills/list', dict(cwds=[str(root)], forceReload=True))
        role_fields = ('description', 'config_file', 'source', 'model', 'model_reasoning_effort')
        skill_fields = ('name', 'path', 'description', 'shortDescription', 'enabled', 'scope', 'source')
        proof['agents'] = {name: discovery_fields(value, role_fields)
                           for name, value in agents.items() if isinstance(value, dict)}
        proof['settings'] = discovery_fields(current, ('model', 'model_reasoning_effort'))
        proof['skills'] = [discovery_fields(skill, skill_fields)
                           for group in skills.get('data', []) for skill in group.get('skills', [])]
        visited = set()

        async def read(identity, depth):
            if identity in visited or depth > 2 or len(visited) >= 16:
                return
            visited.add(identity)
            thread = (await request('thread/read', dict(threadId=identity, includeTurns=True)))['thread']
            if not isinstance(thread, dict):
                raise ValueError('Unsupported public thread shape')
            proof['threads'].append(thread)
            save(output / 'public-proof.json', proof)
            for turn in thread.get('turns', []):
                for item in turn.get('items', []):
                    if item.get('type') == 'subAgentActivity' and item.get('agentThreadId'):
                        await read(item['agentThreadId'], depth + 1)
        if thread_id:
            await read(thread_id, 0)

    try:
        save(output / 'public-proof.json', proof)
        await asyncio.wait_for(exchange(), timeout)
        proof['observation_complete'] = True
    except asyncio.CancelledError as failure:
        proof.update(cancelled=True, observation_error='CancelledError: ' + str(failure))
    except Exception as failure:
        proof['observation_error'] = type(failure).__name__ + ': ' + str(failure)
    finally:
        if process is not None:
            try:
                process.stdin.close()
            except Exception as failure:
                cleanup['errors'].append(dict(stage='stdin_close', error=type(failure).__name__ + ': ' + str(failure)))
            if process.returncode is None:
                for stage, signal in (('terminate_reap', process.terminate), ('kill_reap', process.kill)):
                    try:
                        signal()
                        cleanup['terminate_sent' if stage == 'terminate_reap' else 'kill_sent'] = True
                    except (OSError, ProcessLookupError) as failure:
                        cleanup['errors'].append(dict(stage=stage, error=type(failure).__name__ + ': ' + str(failure)))
                    try:
                        await asyncio.wait_for(process.wait(), cleanup_timeout)
                        cleanup['reaped'] = True
                        break
                    except (Exception, asyncio.CancelledError) as failure:
                        cleanup['errors'].append(dict(stage=stage, error=type(failure).__name__ + ': ' + str(failure)))
                        if isinstance(failure, asyncio.CancelledError):
                            proof['cancelled'] = True
            else:
                cleanup['reaped'] = True
            cleanup.update(returncode=process.returncode, state='reaped' if cleanup['reaped'] else 'UNKNOWN; reap not established')
        elif cleanup['state'] == 'launching; handle not acquired':
            cleanup['state'] = 'UNKNOWN; launch handle not acquired; cleanup not established'
            cleanup['errors'].append(dict(stage='launch_handle', error='Actor existence/status unknown after launch failure'))
        stderr.close()
        if cleanup['errors'] and not proof['observation_error']:
            proof['observation_error'] = 'ObserverCleanupError: ' + str(cleanup['errors'])
        save(output / 'public-proof.json', proof)
    return proof


def run(prepared,*,budget_path,cli=None,authorized=False,timeout=300,phase='source'):
    """Explicit coordinator-only call. No retries/fallback; preserved task ledger.

    Budget counts calls through this supplied ledger, not provider API requests.
    Coordinator must retain it and review routing before subsequent attempts.
    """
    if authorized is not True or not isinstance(cli,(str,Path)) or not str(cli):
        raise ValueError('Explicit coordinator opt-in and explicit CLI path required')
    cli=str(cli)
    if type(timeout) is not int or not 1<=timeout<=300 or phase != 'source':
        raise ValueError('Invalid bounded timeout/phase')
    output,root,ledger=map(safe_path,(prepared['output'],prepared['root'],budget_path))
    if ledger.is_relative_to(root): raise ValueError('Budget must stay outside model root')
    if not audit(prepared)['unchanged'] or (output/'run-attempt.json').exists(): raise ValueError('Drift or output reuse')
    lock=ledger.with_name(ledger.name+'.lock');lock.mkdir()
    attempt_consumed=False;process=None;result=None;timed_out=False;interrupted=False
    try:
        budget=json.loads(ledger.read_text()) if ledger.exists() else dict(attempts=[],route_review='pending')
        attempts=budget['attempts']
        if len(attempts)>=5 or sum(a['phase']=='source' for a in attempts)>=3: raise ValueError('Parent attempt budget exhausted')
        child_reservations=sum(a.get('configured_children',a.get('configured_child_reservation',1)) for a in attempts)
        if child_reservations>=5: raise ValueError('Configured-child ceiling exhausted')
        if attempts and budget.get('route_review')!='coordinator_approved': raise ValueError('Independent current selector/role/scope review required')
        attempt=dict(phase=phase,output=str(output),configured_child_reservation=1,started_at=datetime.now(timezone.utc).isoformat())
        attempts.append(attempt)
        budget['route_review']='pending'
        save(ledger,budget)  # Consume the one approval together with its attempt, BEFORE any launch.
        attempt_consumed=True
        save(output/'run-attempt.json',attempt)
        command=[cli,'--no-daemon','-a','on-request','-s','workspace-write','-C',str(root),'-c',
                 'projects={'+json.dumps(str(root))+'={trust_level="trusted"}}','exec','--json']
        save(output/'command.json',command)
        process,error,timed_out,interrupted=None,None,False,False
        with (output/'events.jsonl').open('w') as events,(output/'stderr.log').open('w') as errors:
            try:
                process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=events,stderr=errors,text=True)
                try: process.communicate(prepared['prompt'],timeout=timeout)
                except (subprocess.TimeoutExpired,KeyboardInterrupt) as failure:
                    timed_out=isinstance(failure,subprocess.TimeoutExpired)
                    interrupted=isinstance(failure,KeyboardInterrupt)
                    process.terminate()
                    try: process.communicate(timeout=5)
                    except subprocess.TimeoutExpired: process.kill();process.communicate(timeout=5)
            except OSError as failure:
                error=str(failure);errors.write(error+'\n')
        thread=None
        for line in (output/'events.jsonl').read_text().splitlines():
            try: event=json.loads(line)
            except ValueError: continue
            if isinstance(event,dict) and event.get('type')=='thread.started': thread=event.get('thread_id')
        result=dict(exit_code=process.returncode if process else None,timed_out=timed_out,interrupted=interrupted,execution_error=error,
            thread_id=thread,acceptance='UNASSESSED',independent_review_required=True,
            cleanup_limit='Only owned direct CLI/app-server cleanup attempted; detached child cleanup not established')
        save(output/'result.json',result)
        if thread and not error:
            try:
                proof=asyncio.run(observe(cli,root,thread,output,authorized=True))
                result['observation_complete']=proof['observation_complete']
                result['actor_cleanup']=proof['actor_cleanup']
                if proof['observation_error']:
                    result['observation_error']=proof['observation_error']
            except (Exception,KeyboardInterrupt) as failure:
                result['observation_error']=type(failure).__name__+': '+str(failure)
        result['audit']=audit(prepared);save(output/'manifest-after.json',result['audit']);save(output/'result.json',result)
        return result
    except (Exception,KeyboardInterrupt) as failure:
        if not attempt_consumed:
            raise
        if result is None:
            result=dict(exit_code=None,timed_out=timed_out,interrupted=interrupted or isinstance(failure,KeyboardInterrupt),
                        thread_id=None,acceptance='UNASSESSED',independent_review_required=True)
        result['unexpected_error']=type(failure).__name__+': '+str(failure)
        result['cleanup_limit']='Only owned direct CLI actor cleanup attempted; detached children not established'
        if process is not None and process.returncode is None:
            try:
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill();process.communicate(timeout=5)
            except (Exception,KeyboardInterrupt) as cleanup_failure:
                result['cleanup_error']=type(cleanup_failure).__name__+': '+str(cleanup_failure)
        if process is not None:
            result['exit_code']=process.returncode
        try:
            save(output/'result.json',result)
        except (OSError,TypeError,ValueError) as evidence_failure:
            result['evidence_error']=type(evidence_failure).__name__+': '+str(evidence_failure)
        return result
    finally: lock.rmdir()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('project','definition','pack','dataset','output'): parser.add_argument('--'+field,required=True,type=Path)
    parser.add_argument('--cases',required=True,nargs='+')
    parser.add_argument('--run',action='store_true',help='Explicit coordinator authorization only')
    parser.add_argument('--instruction-pins',type=Path,help='Controller JSON mapping of authorized framework paths to SHA256')
    parser.add_argument('--budget',type=Path);parser.add_argument('--cli',default=DEFAULT_CLI)
    parser.add_argument('--timeout',type=int,default=300)
    parser.add_argument('--phase',choices=('source',),default='source')
    args=parser.parse_args()
    if args.run and args.budget is None: parser.error('--run requires preserved controller --budget ledger')
    if not 1<=args.timeout<=300: parser.error('timeout must be 1..300 seconds')
    pins=json.loads(args.instruction_pins.read_text()) if args.instruction_pins else None
    prepared=prepare(args.project,args.definition,args.dataset,args.cases,args.output,pack=args.pack,allowed_instruction_reads=pins)
    result=run(prepared,budget_path=args.budget,cli=args.cli,authorized=True,timeout=args.timeout,phase=args.phase) if args.run else prepared
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
