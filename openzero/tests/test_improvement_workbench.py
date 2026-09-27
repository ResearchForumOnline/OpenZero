"""Isolated workbench and integrity tests; never imports/runs the live server."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'brain'))
import integrity
from improvement_workbench import ImprovementWorkbench,WorkbenchError,register_improvement_routes,digest

class WorkbenchTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
  (self.root/'brain').mkdir();(self.root/'tests').mkdir()
  (self.root/'brain'/'sample.py').write_text('VALUE = 1\n')
  (self.root/'brain'/'integrity.py').write_text('# protected\n')
  (self.root/'tests'/'test_sample.py').write_text('import unittest\nclass TestSample(unittest.TestCase):\n def test_one(self): self.assertEqual(1,1)\n')
  (self.root/'brain'/'openzero_config.py').write_text('# excluded config fixture\n')
  self.work=ImprovementWorkbench(self.root)
 def changed(self):
  item=self.work.create('Improve sample');identifier=item['id'];file=self.work.file(identifier,'brain/sample.py')
  return self.work.edit(identifier,'brain/sample.py','VALUE = 2\n',file['sha256'])
 def test_real_edit_check_apply_rollback(self):
  detail=self.changed();identifier=detail['id'];self.assertEqual((self.root/'brain/sample.py').read_text(),'VALUE = 1\n')
  detail=self.work.check(identifier,'tests');self.assertEqual(detail['checks']['status'],'passed')
  self.assertIn('Ran 1 test',detail['checks']['output'])
  self.work.apply(identifier,detail['review_digest'],True);self.assertEqual((self.root/'brain/sample.py').read_text(),'VALUE = 2\n')
  self.work.rollback(identifier,detail['review_digest'],True);self.assertEqual((self.root/'brain/sample.py').read_text(),'VALUE = 1\n')
 def test_snapshot_excludes_config_and_protects_policy_tests(self):
  detail=self.work.create('Change');self.assertNotIn('brain/openzero_config.py',detail['files'])
  for name in ('brain/integrity.py','tests/test_sample.py'):
   with self.assertRaises(WorkbenchError):self.work.edit(detail['id'],name,'bad',self.work.file(detail['id'],name)['sha256'])
 def test_apply_requires_current_checks_digest_and_explicit_confirmation(self):
  detail=self.changed();identifier=detail['id']
  with self.assertRaises(WorkbenchError):self.work.apply(identifier,detail['review_digest'],True)
  detail=self.work.check(identifier)
  for digest_value,confirm in (('old',True),(detail['review_digest'],False)):
   with self.assertRaises(WorkbenchError):self.work.apply(identifier,digest_value,confirm)
  file=self.work.file(identifier,'brain/sample.py');self.work.edit(identifier,'brain/sample.py','VALUE=3\n',file['sha256'])
  with self.assertRaises(WorkbenchError):self.work.apply(identifier,detail['review_digest'],True)
 def test_live_drift_and_rollback_drift_refused(self):
  detail=self.changed();detail=self.work.check(detail['id']);(self.root/'brain/sample.py').write_text('VALUE=9\n')
  with self.assertRaisesRegex(WorkbenchError,'Live source changed'):self.work.apply(detail['id'],detail['review_digest'],True)
 def test_traversal_rejected_and_syntax_failure_recorded(self):
  detail=self.changed()
  with self.assertRaises(WorkbenchError):self.work.file(detail['id'],'../../secret')
  file=self.work.file(detail['id'],'brain/sample.py');self.work.edit(detail['id'],'brain/sample.py','def broken(:\n',file['sha256'])
  detail=self.work.check(detail['id']);self.assertEqual(detail['checks']['status'],'failed')
 def test_model_proposal_changes_candidate_only(self):
  self.work.proposer=lambda prompt:json.dumps({'edits':[{'path':'brain/sample.py','content':'VALUE=4\n'}]})
  detail=self.work.create('Improve');file=self.work.file(detail['id'],'brain/sample.py')
  self.work.propose(detail['id'],'brain/sample.py',file['sha256'],detail['review_digest'])
  deadline=time.monotonic()+3
  while time.monotonic()<deadline:
   detail=self.work.detail(detail['id'])
   if detail['proposal']['status']!='running':break
   time.sleep(.01)
  self.assertEqual(detail['proposal']['status'],'ready');self.assertEqual((self.root/'brain/sample.py').read_text(),'VALUE = 1\n')
  self.assertEqual(self.work.file(detail['id'],'brain/sample.py')['content'],'VALUE=4\n')
 def test_all_routes_require_auth_and_edit_is_operational(self):
  from flask import Flask
  app=Flask(__name__);allowed=[False];register_improvement_routes(app,self.root,lambda:allowed[0]);client=app.test_client()
  self.assertEqual(client.get('/api/improvement/status').status_code,403)
  self.assertEqual(client.post('/api/improvement/candidates',json={'objective':'x'}).status_code,403)
  allowed[0]=True;response=client.post('/api/improvement/candidates',json={'objective':'Improve'});self.assertEqual(response.status_code,201)
  identifier=response.json['candidate']['id'];file=client.get(f'/api/improvement/candidates/{identifier}/file?path=brain/sample.py').json['file']
  self.assertEqual(client.post(f'/api/improvement/candidates/{identifier}/edit',json={'path':file['path'],'content':'VALUE=5\n','expected_sha256':file['sha256']}).status_code,200)

class IntegrityTests(unittest.TestCase):
 def test_status_does_not_create_files(self):
  with tempfile.TemporaryDirectory() as folder:
   result=integrity.integrity_status(folder);self.assertEqual(result['ethics']['status'],'missing');self.assertEqual(list(Path(folder).iterdir()),[])
 def test_existing_unknown_policy_is_never_blessed_or_overwritten(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'security';path.mkdir();policy=path/'ethics_policy.json';policy.write_text('{"custom":"unknown"}')
   before=policy.read_bytes();self.assertEqual(integrity.ensure_integrity_state(folder)['ethics']['status'],'review_required');self.assertEqual(policy.read_bytes(),before)
   self.assertFalse((path/'ethics_policy.sig').exists());self.assertFalse((path/'integrity_manifest.json').exists())
 def test_tampered_policy_remains_tampered_after_status(self):
  with tempfile.TemporaryDirectory() as folder:
   integrity.ensure_ethics_lock(folder);path=Path(folder)/'security';signature=(path/'ethics_policy.sig').read_bytes()
   (path/'ethics_policy.json').write_text('{"changed":true}')
   for _ in range(2):self.assertTrue(integrity.integrity_status(folder)['ethics']['tampered'])
   self.assertEqual((path/'ethics_policy.sig').read_bytes(),signature)
 def test_existing_seal_repair_requires_explicit_digest(self):
  with tempfile.TemporaryDirectory() as folder:
   integrity.ensure_ethics_lock(folder);path=Path(folder)/'security'/'ethics_policy.sig';path.write_text('tampered')
   self.assertEqual(integrity.ensure_ethics_lock(folder)['status'],'review_required');self.assertEqual(path.read_text(),'tampered')
   expected=digest(integrity._canonical_json(integrity.DEFAULT_ETHICS_POLICY))
   self.assertEqual(integrity.ensure_ethics_lock(folder,reviewed_sha256=expected)['status'],'initialized_reviewed_policy')
   self.assertEqual(integrity.integrity_status(folder)['ethics']['status'],'ok')
 def test_startup_never_rebaselines_source_manifest(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'brain').mkdir();source=root/'brain'/'app.py';source.write_text('original')
   integrity.build_integrity_manifest(folder,[str(source)]);manifest=root/'security'/'integrity_manifest.json';before=manifest.read_bytes();source.write_text('changed')
   integrity.ensure_integrity_state(folder);self.assertEqual(manifest.read_bytes(),before)

if __name__=='__main__':unittest.main()
