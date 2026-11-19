"""Host-call metadata tests use real receipt files, without host execution."""
import hashlib,json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from smart_assistant import builtin_records as b,contracts as c
class DefaultHostReceiptTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='host-default-');self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.fd=os.open(self.root,os.O_RDONLY);self.addCleanup(os.close,self.fd)
 def prepare_case(self,extra=None,prompt='assigned prompt',response='worker-run'):
  call={'tool':'collaboration.spawn_agent','arguments':{'task_name':'worker','fork_turns':'none','message':prompt,**(extra or {})}};raw=json.dumps(call).encode();(self.root/'call.json').write_bytes(raw);response_raw=json.dumps({'task_name':response}).encode();(self.root/'response.json').write_bytes(response_raw)
  binding=SimpleNamespace(submitted_call=b.BuiltinReceipt('call.json',hashlib.sha256(raw).hexdigest()),observed_response=b.BuiltinReceipt('response.json',hashlib.sha256(response_raw).hexdigest()));intent=SimpleNamespace(host_binding=binding,observed_run=SimpleNamespace(run_ref='worker-run'))
  return raw,intent
 def run_case(self,extra=None,**kw):
  raw,intent=self.prepare_case(extra,**kw);b._host_files(None,intent,self.fd,b'assigned prompt');return raw,intent
 def denied(self,extra,code='invalid_host_call',**kw):
  with self.assertRaises(c.ValidationError) as got:self.run_case(extra,**kw)
  self.assertIn(code,[x.code for x in got.exception.errors])
 def test_explicit_default_context_is_supported_without_rewriting_receipt(self):
  try:raw,_=self.run_case({'agent_type':'default'})
  except c.ValidationError as e:self.fail('Valid default host call rejected: '+','.join(x.code for x in e.errors))
  self.assertEqual((self.root/'call.json').read_bytes(),raw)
 def test_omitted_default_remains_supported(self):self.run_case()
 def test_other_context_identities_are_not_authorized_by_optional_metadata(self):
  for value in ['worker','reviewer','xstore-triage','Default','default ','']:
   with self.subTest(value=value):self.denied({'agent_type':value})
 def test_non_string_context_metadata_is_denied(self):
  for value in [None,False,1,[],{}]:
   with self.subTest(value=value):self.denied({'agent_type':value})
 def test_model_and_unknown_metadata_remain_denied(self):
  for key in ['model','reasoning_effort','role_id','extra']:
   with self.subTest(key=key):self.denied({'agent_type':'default',key:'value'})
 def test_default_metadata_does_not_relax_prompt_binding(self):self.denied({'agent_type':'default'},code='prompt_mismatch',prompt='changed prompt')
 def test_default_metadata_does_not_relax_returned_context(self):self.denied({'agent_type':'default'},code='wrong_run',response='other-run')
 def test_default_metadata_does_not_relax_raw_receipt_hash(self):
  raw,intent=self.prepare_case({'agent_type':'default'});(self.root/'call.json').write_bytes(raw+b'\n')
  with self.assertRaises(c.ValidationError) as got:b._host_files(None,intent,self.fd,b'assigned prompt')
  self.assertIn('invalid_type',[x.code for x in got.exception.errors])
