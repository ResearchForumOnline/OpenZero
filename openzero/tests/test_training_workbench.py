import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from brain.training_workbench import Workbench, acquire_slot, preflight, train_fixture, worker, atomic_json, register_training_routes


class TrainingTests(unittest.TestCase):
    def wait(self,service,identifier):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            job=service.get(identifier)
            if job['status'] not in ('queued','running'):
                while service._active is not None and time.monotonic()<deadline:time.sleep(.01)
                return service.get(identifier)
            time.sleep(.02)
        self.fail('Job exceeded test deadline')

    def test_real_weights_change_base_stays_frozen_and_reload_matches(self):
        with tempfile.TemporaryDirectory() as root:
            result=train_fixture(Path(root),preflight({'backend':'fixture'}))
            self.assertTrue(result['adapter_changed']);self.assertTrue(result['base_unchanged']);self.assertTrue(result['reload_predictions_equal'])
            self.assertLess(result['heldout_loss_after'],result['heldout_loss_before']*.01)
            self.assertFalse(result['promoted'])
            self.assertEqual(result['model_kind'],'synthetic_linear_fixture_not_llm')
            self.assertTrue((Path(root)/'candidate'/'adapter.json').is_file())

    def test_background_job_exports_hashes(self):
        with tempfile.TemporaryDirectory() as root:
            service=Workbench(root);job=service.start({'backend':'fixture'})
            done=self.wait(service,job['id'])
            self.assertEqual(done['status'],'completed')
            self.assertEqual(len(done['result']['artifacts'][0]['sha256']),64)
            self.assertEqual(done['progress']['step'],250)

    def test_cross_instance_slot_prevents_parallel_training(self):
        with tempfile.TemporaryDirectory() as root:
            service=Workbench(root);slot=acquire_slot(root)
            try:
                with self.assertRaises(RuntimeError):service.start({'backend':'fixture'})
            finally:slot.close()

    def test_cancelled_job_does_not_promote(self):
        with tempfile.TemporaryDirectory() as root:
            service=Workbench(root);job=service.start({'backend':'fixture','steps':2000});service.cancel(job['id'])
            done=self.wait(service,job['id'])
            self.assertEqual(done['status'],'cancelled')
            self.assertIsNone(done['result'])

    def test_packaged_fixture_does_not_launch_app_as_python(self):
        with tempfile.TemporaryDirectory() as root,patch('brain.training_workbench.sys.frozen',True,create=True),patch('brain.training_workbench.subprocess.Popen') as launch:
            service=Workbench(root);job=service.start({'backend':'fixture','steps':10});done=self.wait(service,job['id'])
            self.assertEqual(done['status'],'completed');launch.assert_not_called()

    def test_input_limits_and_missing_optional_dependencies(self):
        for request in ({'backend':'fixture','steps':0},{'backend':'fixture','steps':2001},{'backend':'fixture','steps':True},{'backend':'invented'}):
            with self.assertRaises(ValueError):preflight(request)
        with patch('brain.training_workbench.importlib.util.find_spec',return_value=None):
            with self.assertRaisesRegex(ValueError,'No packages or models were downloaded'):preflight({'backend':'lora'})

    def test_unknown_job_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            service=Workbench(root)
            with self.assertRaises(ValueError):service.get('../outside')

    def test_routes_authenticate_and_export_only_unchanged_candidate(self):
        from flask import Flask
        with tempfile.TemporaryDirectory() as root:
            app=Flask(__name__);allowed=[False];service=register_training_routes(app,lambda:allowed[0],root);client=app.test_client()
            self.assertEqual(client.get('/api/training/status').status_code,403)
            self.assertEqual(client.post('/api/training/jobs',json={'backend':'fixture'}).status_code,403)
            allowed[0]=True
            response=client.post('/api/training/jobs',json={'backend':'fixture'})
            self.assertEqual(response.status_code,202);identifier=response.get_json()['job']['id'];done=self.wait(service,identifier)
            self.assertEqual(done['status'],'completed')
            url='/api/training/jobs/'+identifier+'/artifacts/adapter.json'
            exported=client.get(url);self.assertEqual(exported.status_code,200);exported.close()
            (Path(root)/identifier/'candidate'/'adapter.json').write_text('{}')
            self.assertEqual(client.get(url).status_code,400)


if __name__=='__main__':unittest.main()
