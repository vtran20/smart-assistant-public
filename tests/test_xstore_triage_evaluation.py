"""Controller checks never self-certify model semantics."""
import copy
import asyncio
import time
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import AsyncMock, Mock, patch
ROOT=Path(__file__).resolve().parents[1]
SCENARIO=ROOT/'examples/scenarios/xstore-triage'
REAL_POPEN=subprocess.Popen
LAUNCH_GUARD=None
ASYNC_LAUNCH_GUARD=None

def guarded_popen(command,*args,**kwargs):
    # Suite-wide allowlist: only empty Git initialization in a fresh temp fixture.
    allowed=(isinstance(command,list) and len(command)==5
             and command[:4]==['git','init','--template=','-q'])
    if allowed:
        target=Path(command[4]).absolute()
        allowed=(target.name=='project' and target.is_relative_to(Path(tempfile.gettempdir()).resolve())
                 and target.is_dir() and not (target/'.git').exists())
    if not allowed:
        raise AssertionError('Test-wide launch guard rejected process: '+str(command))
    return REAL_POPEN(command,*args,**kwargs)

def setUpModule():
    global LAUNCH_GUARD,ASYNC_LAUNCH_GUARD
    LAUNCH_GUARD=patch('subprocess.Popen',new=guarded_popen)
    LAUNCH_GUARD.start()
    ASYNC_LAUNCH_GUARD=patch('asyncio.create_subprocess_exec',side_effect=AssertionError('Test-wide async actor guard'))
    ASYNC_LAUNCH_GUARD.start()

def tearDownModule():
    ASYNC_LAUNCH_GUARD.stop()
    LAUNCH_GUARD.stop()

def load(name):
    path=SCENARIO/(name+'.py')
    if not path.is_file(): raise AssertionError('Missing evaluator implementation: '+name)
    spec=importlib.util.spec_from_file_location('xstore_'+name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.m=load('assessment');self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'build.log').write_text('compile: 2 errors; zero classes\nRuntime predates source\n')
        self.knowledge=dict(id='xstore-triage-procedures',version='1.0.0',sha256='a'*64)
        self.value=dict(schema_version=1,case_id='A1',role_id='xstore-triage',knowledge=self.knowledge.copy(),disposition='ready_for_review',summary='The supplied build failed.',observations=[dict(id='o1',statement='Compile reports errors.',source_refs=[dict(path='build.log',start_line=1,end_line=1)])],gates=[dict(id='compiled',status='contradicted',reason='Errors.',observation_ids=['o1'])],next_checks=[dict(question='Which classpath supplied the unresolved import?',reason='Compile failed.',source_refs=[],execution='not_executed')],blockers=[],limits=['Independent semantic review required; no live acceptance.'])
    def check(self,v=None,selected=None):return self.m.validate_assessment(v or self.value,self.root,selected or ['build.log'],self.knowledge,case_id='A1')
    def test_valid_partial_facts_require_review(self):
        r=self.check();self.assertTrue(r['structural_pass'],r);self.assertTrue(r['semantic_review_required']);self.assertEqual('UNASSESSED',r['acceptance'])
        self.value.update(disposition='blocked',blockers=['Missing release prevents version-specific advice.']);self.assertTrue(self.check()['structural_pass'])
    def test_strict_shape_types_enums(self):
        for key,val in [('extra',1),('schema_version',True),('case_id','other'),('role_id','generic'),('summary',' '),('disposition','completed'),('limits',[]),('blockers','none')]:
            v=copy.deepcopy(self.value);v[key]=val;self.assertFalse(self.check(v)['structural_pass'],key)
        for sec,key,val in [('observations','extra',1),('gates','status','accepted'),('next_checks','execution','executed')]:
            v=copy.deepcopy(self.value);v[sec][0][key]=val;self.assertFalse(self.check(v)['structural_pass'])
        v=copy.deepcopy(self.value);del v['summary'];self.assertFalse(self.check(v)['structural_pass'])
    def test_unique_ids_and_grounded_gates(self):
        for sec in ['observations','gates']:
            v=copy.deepcopy(self.value);v[sec]*=2;self.assertFalse(self.check(v)['structural_pass'])
        for ids in [[],['absent'],['o1','o1']]:
            v=copy.deepcopy(self.value);v['gates'][0]['observation_ids']=ids;self.assertFalse(self.check(v)['structural_pass'])
        self.value['gates'][0].update(status='not_proven',observation_ids=[],reason='No successful record supplied.');self.assertTrue(self.check()['structural_pass'])
    def test_selected_safe_actual_paths_ranges(self):
        for path in ['/etc/passwd','../build.log','file:///build.log','missing.log','other.log']:
            v=copy.deepcopy(self.value);v['observations'][0]['source_refs'][0]['path']=path;self.assertFalse(self.check(v)['structural_pass'])
        for start,end in [(True,1),(0,1),(2,1),(1,3)]:
            v=copy.deepcopy(self.value);v['observations'][0]['source_refs'][0].update(start_line=start,end_line=end);self.assertFalse(self.check(v)['structural_pass'])
        (self.root/'alias.log').symlink_to(self.root/'build.log');self.assertFalse(self.check(selected=['alias.log'])['structural_pass'])
    def test_pack_identity_and_meaningful_blocker(self):
        for key in self.knowledge:
            v=copy.deepcopy(self.value);v['knowledge'][key]='wrong';self.assertFalse(self.check(v)['structural_pass'])
        self.value['disposition']='blocked';self.assertFalse(self.check()['structural_pass']);self.value['blockers']=[' '];self.assertFalse(self.check()['structural_pass'])
    def test_positive_rubric_rejects_abstention_and_known_unsupported_support(self):
        ctl=dict(disposition='ready_for_review',required_gates={'compiled':'contradicted'},forbidden_supported=['business'],required_next_terms=['classpath'])
        self.assertTrue(self.m.evaluate_case(self.value,ctl)['case_checks_pass'])
        v=copy.deepcopy(self.value);v['gates'][0].update(status='not_proven',observation_ids=[])
        self.assertTrue(self.check(v)['structural_pass']);self.assertFalse(self.m.evaluate_case(v,ctl)['case_checks_pass'])
        v=copy.deepcopy(self.value);v['gates'].append(dict(id='business',status='supported',reason='Works.',observation_ids=['o1']));self.assertFalse(self.m.evaluate_case(v,ctl)['case_checks_pass'])
    def test_misleading_paraphrase_can_pass_structure_never_semantics(self):
        self.value['observations'][0]['statement']='The successful compile proves customer payment acceptance.'
        r=self.check();self.assertTrue(r['structural_pass']);self.assertTrue(r['semantic_review_required']);self.assertEqual('UNASSESSED',r['acceptance'])
    def test_malformed_nested_types_are_errors_not_crashes(self):
        for key in self.value:
            for val in [None, {}, [], True, 2]:
                v=copy.deepcopy(self.value);v[key]=val
                result=self.check(v)
                if key not in ('observations','gates','next_checks','blockers') or val != []:
                    self.assertFalse(result['structural_pass'],(key,val))
        for sec in ['observations','gates','next_checks']:
            v=copy.deepcopy(self.value);v[sec]=[None];self.assertFalse(self.check(v)['structural_pass'])
    def test_out_of_scope_without_invented_evidence(self):
        self.value.update(disposition='out_of_scope',observations=[],gates=[],next_checks=[]);self.assertTrue(self.check()['structural_pass'])
class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.m=load('native_eval');self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name).resolve()
        self.project=self.base/'source';self.project.mkdir();(self.project/'smart_assistant').mkdir()
        (self.project/'smart_assistant/__init__.py').write_text('');(self.project/'smart_assistant/contracts.py').write_text('# helper\n')
        self.pack=self.project/'pack.json';self.pack.write_text('{"id":"xstore-triage-procedures","version":"1.0.0","entries":["guidance"]}\n')
        self.digest=hashlib.sha256(self.pack.read_bytes()).hexdigest();self.definition=self.project/'xstore-triage.toml'
        instructions='knowledge_sha256: '+self.digest+'\nBEGIN XSTORE KNOWLEDGE PACK\n'+self.pack.read_text()+'END XSTORE KNOWLEDGE PACK\n'
        self.definition.write_text('name="xstore-triage"\ndescription="Evidence advisor"\ndeveloper_instructions='+json.dumps(instructions)+'\n')
        self.dataset=json.loads((SCENARIO/'development.json').read_text());self.output=self.base/'evaluation'
    def prepare(self,ids=None):return self.m.prepare(self.project,self.definition,self.dataset,ids or ['A1','A2'],self.output,pack=self.pack)
    def test_minimal_provision_freezes_after_config_excludes_oracle(self):
        p=self.prepare();root=Path(p['root']);self.assertEqual(0,p['model_calls']);self.assertEqual('UNASSESSED',p['acceptance'])
        for name in ['.codex/config.toml','.codex/agents/xstore-triage.toml','smart_assistant/contracts.py']:self.assertIn(name,p['manifest']['files'])
        text='\n'.join(x.read_text() for x in root.rglob('*') if x.is_file())
        self.assertNotIn('required_gates',text);self.assertNotIn('forbidden_supported',text);self.assertFalse((root/'capabilities').exists())
        self.assertTrue(self.m.audit(p)['unchanged']);self.assertIn('agent_type="xstore-triage"',p['prompt'])
    def test_duplicate_unknown_or_overlarge_batches_fail_before_output(self):
        for ids in [['A1','A1'],['absent'],['A1','A2','B2','B3'],[]]:
            with self.assertRaises(ValueError):self.m.prepare(self.project,self.definition,self.dataset,ids,self.output,pack=self.pack)
            self.assertFalse(self.output.exists())
    def test_reuse_drift_pack_change_and_wrong_basename_rejected(self):
        p=self.prepare()
        with self.assertRaises(ValueError):self.prepare()
        (Path(p['root'])/'.codex/config.toml').write_text('[agents]\nenabled=false\n');self.assertFalse(self.m.audit(p)['unchanged'])
        self.output=self.base/'second';self.pack.write_text(self.pack.read_text()+' ')
        with self.assertRaises(ValueError):self.prepare()
        self.definition=self.project/'renamed.toml';self.definition.write_text('name="xstore-triage"\n')
        with self.assertRaises(ValueError):self.prepare()
    def test_reserved_paths_and_helper_symlinks_fail(self):
        for path in ['../outside','.codex/config.toml','outputs/assessment.json','/tmp/unsafe','http://example.com']:
            d=copy.deepcopy(self.dataset);d['cases'][0]['input']['files']={path:'data'}
            with self.assertRaises(ValueError):self.m.prepare(self.project,self.definition,d,['A1'],self.output,pack=self.pack)
        (self.project/'smart_assistant/link.py').symlink_to(self.pack)
        with self.assertRaises(ValueError):self.prepare()
    def test_audit_additions_owned_outputs_and_missing_fixture(self):
        p=self.prepare();root=Path(p['root']);(root/'unexpected').write_text('drift');self.assertFalse(self.m.audit(p)['unchanged']);(root/'unexpected').unlink()
        (root/'outputs').mkdir();(root/'outputs/A1.json').write_text('{}');self.assertTrue(self.m.audit(p)['unchanged'])
        (root/'outputs/other.json').write_text('{}');self.assertFalse(self.m.audit(p)['unchanged'])
        self.output=self.base/'missing';p=self.prepare(['B3']);root=Path(p['root']);c=json.loads((root/'inputs/cases.json').read_text())['cases'][0]
        self.assertFalse((root/c['missing_inputs'][0]).exists());self.assertNotIn('controls',c)
    def test_explicit_instruction_reads_pinned_without_case_refs_or_oracle(self):
        framework=self.base/'framework.md';framework.write_text('Framework verification instructions')
        allowed={str(framework):hashlib.sha256(framework.read_bytes()).hexdigest()}
        p=self.m.prepare(self.project,self.definition,self.dataset,['A1'],self.output,pack=self.pack,allowed_instruction_reads=allowed)
        self.assertEqual(allowed,p['allowed_instruction_reads']);self.assertIn(str(framework),p['prompt'])
        framework.write_text('changed');self.assertFalse(self.m.audit(p)['unchanged'])
        self.output=self.base/'wrong-pin'
        with self.assertRaises(ValueError):self.m.prepare(self.project,self.definition,self.dataset,['A1'],self.output,pack=self.pack,allowed_instruction_reads=allowed)
    def test_path_traversal_and_colliding_input_files_rejected_before_output(self):
        with self.assertRaises(ValueError):self.m.prepare(self.project,self.project/'..'/'xstore-triage.toml',self.dataset,['A1'],self.output,pack=self.pack)
        d=copy.deepcopy(self.dataset);d['cases'][0]['input']['files']={'inputs/A1/a':'a','inputs/A1/a/b':'b'}
        with self.assertRaises(ValueError):self.m.prepare(self.project,self.definition,d,['A1'],self.output,pack=self.pack)
        self.assertFalse(self.output.exists())
    def test_run_failures_and_timeouts_preserved_without_real_process(self):
        p=self.prepare();ledger=self.base/'budget.json'
        with patch.object(self.m.subprocess,'Popen',side_effect=OSError('unit-test launch denied')) as popen:
            r=self.m.run(p,authorized=True,cli='/nonexistent/deterministic-no-native',budget_path=ledger)
        self.assertEqual(1,popen.call_count);self.assertIn('launch denied',r['execution_error']);self.assertEqual('UNASSESSED',r['acceptance'])
        self.assertEqual(1,len(json.loads(ledger.read_text())['attempts']))
        with self.assertRaises(ValueError):self.m.run(p,authorized=True,cli='/nonexistent/deterministic-no-native',budget_path=ledger)
        self.output=self.base/'timeout';p=self.prepare()
        budget=json.loads(ledger.read_text());budget['route_review']='coordinator_approved';ledger.write_text(json.dumps(budget))
        process=Mock();process.returncode=-9
        process.communicate.side_effect=[self.m.subprocess.TimeoutExpired('unit-test',300),self.m.subprocess.TimeoutExpired('unit-test',5),None]
        with patch.object(self.m.subprocess,'Popen',return_value=process):r=self.m.run(p,authorized=True,cli='/nonexistent/deterministic-no-native',budget_path=ledger)
        self.assertTrue(r['timed_out']);process.terminate.assert_called_once();process.kill.assert_called_once()
    def test_unexpected_failure_consumes_approval_before_launch_and_blocks_fresh_output(self):
        p=self.prepare();ledger=self.base/'budget.json'
        ledger.write_text(json.dumps({'attempts':[{'phase':'incident','configured_children':1}], 'route_review':'coordinator_approved'}))
        at_launch=[]
        def unexpected(*args,**kwargs):
            at_launch.append(json.loads(ledger.read_text())['route_review'])
            raise RuntimeError('hypothetical unexpected launch failure')
        try:
            with patch.object(self.m.subprocess,'Popen',side_effect=unexpected):
                result=self.m.run(p,authorized=True,cli='/nonexistent/deterministic-no-native',budget_path=ledger)
        except RuntimeError:
            result=None
        self.assertEqual(['pending'],at_launch)
        self.assertEqual('pending',json.loads(ledger.read_text())['route_review'])
        self.assertEqual(2,len(json.loads(ledger.read_text())['attempts']))
        self.assertEqual('UNASSESSED',result['acceptance'])
        saved=json.loads((self.output/'result.json').read_text())
        self.assertIn('RuntimeError',saved['unexpected_error'])
        self.output=self.base/'fresh-after-unexpected';fresh=self.prepare()
        with patch.object(self.m.subprocess,'Popen',side_effect=AssertionError('No fresh launch permitted')) as forbidden:
            with self.assertRaises(ValueError):
                self.m.run(fresh,authorized=True,cli='/nonexistent/deterministic-no-native',budget_path=ledger)
        forbidden.assert_not_called()
    def test_b3_missing_file_has_bounded_read_authority_but_no_source_ref_inventory(self):
        p=self.prepare(['B3']);root=Path(p['root'])
        case=json.loads((root/'inputs/cases.json').read_text())['cases'][0]
        missing=case['missing_inputs'][0]
        self.assertFalse((root/missing).exists());self.assertNotIn(missing,case['selected_paths'])
        self.assertIn('one bounded read attempt',p['prompt'])
        self.assertIn('missing_inputs',p['prompt'])
        self.assertIn('Missing paths cannot be SourceRefs',p['prompt'])
    def test_declared_missing_path_cannot_be_created_as_input_directory(self):
        d=copy.deepcopy(self.dataset);d['cases'][0]['input']['files']={'inputs/A1/missing/child.log':'data'}
        d['cases'][0]['input']['missing_inputs']=['inputs/A1/missing']
        with self.assertRaises(ValueError):
            self.m.prepare(self.project,self.definition,d,['A1'],self.output,pack=self.pack)
        self.assertFalse(self.output.exists())
    def test_killed_actor_reap_is_bounded_and_timeout_fact_survives_reap_failure(self):
        p=self.prepare();process=Mock();process.returncode=-9
        process.communicate.side_effect=[self.m.subprocess.TimeoutExpired('unit-test',300),self.m.subprocess.TimeoutExpired('unit-test',5),self.m.subprocess.TimeoutExpired('unit-test',5)]
        with patch.object(self.m.subprocess,'Popen',return_value=process):
            result=self.m.run(p,authorized=True,cli='/nonexistent/deterministic-no-native',budget_path=self.base/'budget.json')
        self.assertEqual({'timeout':5},process.communicate.call_args_list[-1].kwargs)
        self.assertTrue(result['timed_out']);self.assertIn('TimeoutExpired',result['unexpected_error'])
        self.assertEqual('UNASSESSED',result['acceptance']);self.assertTrue((self.output/'result.json').is_file())
    def test_gate_names_are_neutral_input_vocabulary_without_rubric_status_pairs(self):
        for case in self.dataset['cases']:
            gates=case['controls']['required_gates']
            if gates:
                suffix=' Use gate IDs: '+', '.join(gates)+'.'
                self.assertTrue(case['input']['request'].endswith(suffix),case['id'])
            for gate,status in gates.items():
                self.assertNotIn(gate+': '+status,case['input']['request'])
        p=self.prepare();text=(Path(p['root'])/'inputs/cases.json').read_text()
        for hidden in ['required_gates','forbidden_supported','controls','case_checks_pass']:
            self.assertNotIn(hidden,text)
    def test_path_cli_serializes_before_attempt_and_reaches_only_mock_actor(self):
        p=self.prepare();process=Mock();process.returncode=0;process.communicate.return_value=None
        with patch.object(self.m.subprocess,'Popen',return_value=process) as popen:
            result=self.m.run(p,authorized=True,cli=Path('/nonexistent/deterministic-no-native'),budget_path=self.base/'budget.json')
        popen.assert_called_once()
        command=json.loads((self.output/'command.json').read_text())
        self.assertEqual('/nonexistent/deterministic-no-native',command[0])
        self.assertEqual(command,popen.call_args.args[0]);self.assertNotIn('unexpected_error',result)
    def test_observation_timeout_reap_failure_preserved_and_ledger_lock_released(self):
        p=self.prepare();ledger=self.base/'budget.json';m=self.m
        original=getattr(m,'observe',None)
        self.assertTrue(callable(original),'Task-owned bounded observer missing')
        async def run_short(*args,**kwargs):
            kwargs.update(timeout=.02,cleanup_timeout=.02)
            return await original(*args,**kwargs)
        async def stall():await asyncio.Event().wait()
        actor=Mock();actor.returncode=None;actor.pid=12345
        actor.stdin.drain=AsyncMock();actor.stdout.readline=AsyncMock(side_effect=stall);actor.wait=AsyncMock(side_effect=stall)
        cli=Mock();cli.returncode=0
        def fake_cli(command,**kwargs):
            kwargs['stdout'].write(json.dumps({'type':'thread.started','thread_id':'synthetic-parent'})+'\n')
            return cli
        started=time.monotonic()
        with patch.object(m.subprocess,'Popen',side_effect=fake_cli),patch.object(m.asyncio,'create_subprocess_exec',new=AsyncMock(return_value=actor)),patch.object(m,'observe',new=run_short):
            result=m.run(p,authorized=True,cli='/nonexistent/deterministic-no-native',budget_path=ledger)
        self.assertLess(time.monotonic()-started,1.0)
        self.assertEqual('UNASSESSED',result['acceptance']);self.assertIn('TimeoutError',result['observation_error'])
        proof=json.loads((self.output/'public-proof.json').read_text())
        self.assertFalse(proof['actor_cleanup']['reaped']);self.assertTrue(proof['actor_cleanup']['kill_sent'])
        self.assertIn('kill_reap',str(proof['actor_cleanup']['errors']))
        self.assertFalse(ledger.with_name(ledger.name+'.lock').exists())
        self.assertEqual('pending',json.loads(ledger.read_text())['route_review'])
        self.assertIn('detached',proof['actor_cleanup']['limit'])
    def test_task_owned_observer_projects_only_safe_discovery_and_public_threads(self):
        p=self.prepare();m=self.m;observer=getattr(m,'observe',None)
        self.assertTrue(callable(observer),'Task-owned bounded observer missing')
        async def probe():
            replies=asyncio.Queue();actor=Mock();actor.pid=12345;actor.returncode=0
            actor.stdin.drain=AsyncMock();actor.wait=AsyncMock(return_value=0)
            parent={'id':'p','turns':[{'items':[{'type':'subAgentActivity','agentThreadId':'c'}]}]}
            child={'id':'c','agentRole':'xstore-triage','turns':[]}
            def write(raw):
                req=json.loads(raw)
                if 'id' not in req:return
                method=req['method']
                if method=='initialize':result={}
                elif method=='config/read':result={'config':{'api_key':'do-not-leak','model':'inherited','agents':{'xstore-triage':{'config_file':str(Path(p['root'])/'.codex/agents/xstore-triage.toml'),'source':'repository','secret':'do-not-leak'}}}}
                elif method=='skills/list':result={'data':[{'skills':[{'name':'safe','path':'/synthetic/safe','enabled':True,'secret':'do-not-leak'}]}]}
                else:result={'thread':parent if req['params']['threadId']=='p' else child}
                replies.put_nowait((json.dumps({'id':req['id'],'result':result})+'\n').encode())
            actor.stdin.write.side_effect=write;actor.stdout.readline=AsyncMock(side_effect=replies.get)
            with patch.object(m.asyncio,'create_subprocess_exec',new=AsyncMock(return_value=actor)) as create:
                proof=await observer('/nonexistent/deterministic-no-native',Path(p['root']),'p',self.output,authorized=True,timeout=.3,cleanup_timeout=.02)
            self.assertEqual(1,create.await_count);self.assertTrue(proof['observation_complete'])
            self.assertNotIn('do-not-leak',json.dumps(proof));self.assertEqual(['p','c'],[t['id'] for t in proof['threads']])
            self.assertIn('.codex/agents/xstore-triage.toml',proof['native_assets'])
            self.assertEqual('UNASSESSED',proof['acceptance']);self.assertTrue(proof['actor_cleanup']['reaped'])
        asyncio.run(probe())
    def test_interruption_stops_owned_actor_and_preserves_failure(self):
        p=self.prepare();process=Mock();process.returncode=-15
        process.communicate.side_effect=[KeyboardInterrupt(),None]
        with patch.object(self.m.subprocess,'Popen',return_value=process):
            r=self.m.run(p,authorized=True,cli='/nonexistent/deterministic-no-native',budget_path=self.base/'budget.json')
        self.assertTrue(r['interrupted']);process.terminate.assert_called_once()
        self.assertTrue((self.output/'result.json').is_file())
    def test_source_inventory_addition_during_copy_rejected(self):
        original=self.m.shutil.copy2
        def copy_and_add(source,target):
            result=original(source,target)
            (self.project/'smart_assistant/new.py').write_text('# concurrent addition')
            return result
        with patch.object(self.m.shutil,'copy2',side_effect=copy_and_add):
            with self.assertRaises(ValueError):self.prepare()
        self.assertTrue(self.output.exists())
    def test_suite_wide_guard_rejects_every_native_process(self):
        with self.assertRaises(AssertionError):
            subprocess.Popen(['/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex','--version'])
    def test_python_run_requires_explicit_opt_in_and_cli(self):
        p=self.prepare();ledger=self.base/'budget.json'
        with self.assertRaises(ValueError):self.m.run(p,budget_path=ledger)
        with self.assertRaises(ValueError):self.m.run(p,budget_path=ledger,authorized=True)
        with self.assertRaises(ValueError):self.m.run(p,budget_path=ledger,cli='/nonexistent/deterministic-no-native')
    def test_run_bounds_budget_and_lock_fail_without_process(self):
        p=self.prepare();ledger=self.base/'budget.json'
        with patch.object(self.m.subprocess,'Popen',side_effect=AssertionError('No real CLI permitted')) as forbidden:
            for phase in ['unrelated','activation']:
                with self.assertRaises(ValueError):self.m.run(p,authorized=True,cli='/nonexistent/deterministic-no-native',budget_path=ledger,phase=phase)
        forbidden.assert_not_called()
        for timeout in [True,0,301]:
            with self.assertRaises(ValueError):self.m.run(p,authorized=True,cli='/nonexistent/deterministic-no-native',budget_path=ledger,timeout=timeout)
        ledger.write_text(json.dumps({'attempts':[{'phase':'source'}]*3,'route_review':'coordinator_approved'}))
        with patch.object(self.m.subprocess,'Popen') as popen:
            with self.assertRaises(ValueError):self.m.run(p,authorized=True,cli='/nonexistent/deterministic-no-native',budget_path=ledger)
        popen.assert_not_called()
        self.assertFalse(ledger.with_name(ledger.name+'.lock').exists())
    def test_six_development_cases_only(self):
        self.assertEqual({'A1','A2','B2','B3','C1','C3'},{c['id'] for c in self.dataset['cases']})
class ObserverCancellationTests(unittest.TestCase):
    def test_observer_launch_timeout_without_handle_preserves_unknown_actor_status(self):
        m=load('native_eval')
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder).resolve();root=output/'project';root.mkdir()
            async def stall(*args,**kwargs):await asyncio.Event().wait()
            async def probe():
                with patch.object(m.asyncio,'create_subprocess_exec',new=stall):
                    proof=await m.observe('/nonexistent/deterministic-no-native',root,'synthetic-parent',output,authorized=True,timeout=.02,cleanup_timeout=.02)
                self.assertIn('UNKNOWN',proof['actor_cleanup']['state'])
                self.assertFalse(proof['actor_cleanup']['reaped'])
                self.assertIn('TimeoutError',proof['observation_error'])
                self.assertEqual('UNASSESSED',proof['acceptance'])
            asyncio.run(probe())
    def test_cancelled_observer_with_stalled_kill_reap_completes_within_declared_bound(self):
        m=load('native_eval');observer=getattr(m,'observe',None)
        self.assertTrue(callable(observer),'Task-owned bounded observer missing')
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder).resolve();root=output/'project';root.mkdir()
            async def probe():
                created=asyncio.Event();release=asyncio.Event()
                async def stall():await release.wait()
                actor=Mock();actor.returncode=None;actor.pid=12345
                actor.stdin.drain=AsyncMock();actor.stdout.readline=AsyncMock(side_effect=stall);actor.wait=AsyncMock(side_effect=stall)
                async def create(*args,**kwargs):created.set();return actor
                with patch.object(m.asyncio,'create_subprocess_exec',new=create):
                    task=asyncio.create_task(observer('/nonexistent/deterministic-no-native',root,'synthetic-parent',output,authorized=True,timeout=.3,cleanup_timeout=.02))
                    try:
                        await asyncio.wait_for(created.wait(),.2);task.cancel()
                        done,_=await asyncio.wait({task},timeout=.3)
                        self.assertIn(task,done,'Observer cancellation exceeded finite test bound')
                        proof=task.result();self.assertTrue(proof['cancelled'])
                        self.assertFalse(proof['actor_cleanup']['reaped']);actor.terminate.assert_called_once();actor.kill.assert_called_once()
                        self.assertEqual('UNASSESSED',proof['acceptance']);self.assertIn('CancelledError',proof['observation_error'])
                    finally:
                        release.set()
                        if not task.done():await asyncio.wait_for(task,.2)
            asyncio.run(probe())

class NativeProofTests(unittest.TestCase):
    def setUp(self):
        self.m=load('native_eval');self.b=dict(role_id='xstore-triage',version='1.0.0',sha256='a'*64,target='/tmp/fresh/.codex/agents/xstore-triage.toml',parent_id='p',operation_id='new',prepared_at='2026-11-02T10:00:00Z')
        self.p=dict(observed_at='2026-11-02T10:01:00Z',operation_id='new',version='1.0.0',agents={'xstore-triage':{'config_file':self.b['target']}},native_assets={'.codex/agents/xstore-triage.toml':'a'*64},threads=[dict(id='p',turns=[dict(items=[dict(type='subAgentActivity',kind='started',agentThreadId='c'),dict(type='subAgentActivity',kind='completed',agentThreadId='c')])]),dict(id='c',parentThreadId='p',forkedFromId=None,agentRole='xstore-triage',source={'subAgent':{'thread_spawn':{'parent_thread_id':'p','depth':1,'agent_role':'xstore-triage','agent_path':'/root/xstore'}}},turns=[dict(items=[dict(type='agentMessage',text='Assessment returned.')])])])
    def test_identity_is_only_structural(self):
        r=self.m.validate_native_proof(self.p,self.b);self.assertTrue(r['identity_checks_pass'],r);self.assertEqual('UNASSESSED',r['acceptance']);self.assertTrue(r['independent_review_required'])
    def test_wrong_role_hash_version_stale_operation_and_copied_proof_fail(self):
        bad=[]
        for k,v in [('version','2'),('operation_id','old'),('observed_at','2026-11-02T09:00:00Z')]:
            p=copy.deepcopy(self.p);p[k]=v;bad.append(p)
        for k,v in [('agentRole','generic'),('source','subagent'),('parentThreadId','other'),('forkedFromId','p')]:
            p=copy.deepcopy(self.p);p['threads'][1][k]=v;bad.append(p)
        p=copy.deepcopy(self.p);p['native_assets']['.codex/agents/xstore-triage.toml']='b'*64;bad.append(p)
        p=copy.deepcopy(self.p);p['agents']['xstore-triage']['config_file']='/old/copy.toml';bad.append(p)
        for p in bad:self.assertFalse(self.m.validate_native_proof(p,self.b)['identity_checks_pass'])
    def test_dispatch_completion_extra_child_and_unknown_schema_fail(self):
        for mode in ['dispatch','completion','extra','shape']:
            p=copy.deepcopy(self.p)
            if mode=='dispatch':p['threads'][0]['turns']=[]
            if mode=='completion':p['threads'][0]['turns'][0]['items'].pop()
            if mode=='extra':p['threads'].append(copy.deepcopy(p['threads'][1]))
            if mode=='shape':p['threads'][1]['source']={'invented_role':'xstore-triage'}
            self.assertFalse(self.m.validate_native_proof(p,self.b)['identity_checks_pass'])
if __name__=='__main__':unittest.main()
