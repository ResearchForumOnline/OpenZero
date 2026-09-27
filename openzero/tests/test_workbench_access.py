import importlib.util
from pathlib import Path
import unittest
from flask import Flask

SPEC = importlib.util.spec_from_file_location("workbench_access", Path(__file__).resolve().parents[1] / "brain" / "workbench_access.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class WorkbenchAccessTests(unittest.TestCase):
    def check_access(self, url="http://localhost/api", method="POST", headers=None, local=True, bearer=False):
        with Flask(__name__).test_request_context(url, method=method, headers=headers or {}, json={}):
            return MOD.workbench_request_authorized(lambda: local, lambda: bearer)

    def test_loopback_json_and_same_origin(self):
        self.assertTrue(self.check_access(headers={"Origin": "http://localhost"}))

    def test_cross_origin_and_opaque_origins_rejected(self):
        for origin in ("https://evil.example", "null", "http://localhost:99"):
            self.assertFalse(self.check_access(headers={"Origin": origin}))

    def test_cross_site_fetch_rejected(self):
        self.assertFalse(self.check_access(headers={"Sec-Fetch-Site": "cross-site"}))

    def test_dns_rebinding_host_rejected(self):
        self.assertFalse(self.check_access(url="http://evil.example/api"))

    def test_remote_requires_bearer(self):
        self.assertFalse(self.check_access(url="https://node.example/api", local=False))
        self.assertTrue(self.check_access(url="https://node.example/api", local=False, bearer=True))

    def test_forms_rejected(self):
        with Flask(__name__).test_request_context("/api", method="POST", data={"operation": "apply"}):
            self.assertFalse(MOD.workbench_request_authorized(lambda: True, lambda: False))


if __name__ == "__main__":
    unittest.main()
