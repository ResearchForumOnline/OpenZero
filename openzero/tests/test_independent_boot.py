"""Boot a disposable copy of the actual panel with all HTTP transport blocked."""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class IndependentBootTests(unittest.TestCase):
    def test_panel_assets_owner_status_and_socket_handshake_without_external_http(self):
        with tempfile.TemporaryDirectory(prefix="openzero-independent-boot-") as directory:
            node = pathlib.Path(directory) / "node"
            node.mkdir()
            # Copy only public source directories. Never copy .env, models,
            # uploads, local knowledge, keys, runtime state or user databases.
            for name in ("brain", "hivemind", "skills", "templates", "static"):
                shutil.copytree(ROOT / name, node / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            shutil.copyfile(ROOT / "node_status.py", node / "node_status.py")
            (node / ".env").write_text("COMP_MODE=local\nOLLAMA_AUTO_REPAIR_ENABLED=false\n", encoding="utf-8")
            script = r'''
import hashlib,json
from unittest.mock import patch
import requests
attempts=[]
def blocked(session,method,url,*args,**kwargs):
    attempts.append(str(url))
    raise requests.ConnectionError("Synthetic offline transport")
with patch.object(requests.sessions.Session,"request",blocked):
    from brain.wsgi import app
    from brain.app import socketio
    app.config["TESTING"]=True
    client=app.test_client()
    panel=client.get("/",base_url="http://127.0.0.1")
    assert panel.status_code==200
    assert b"cdnjs.cloudflare.com" not in panel.data
    asset=client.get("/static/vendor/socket.io-4.7.1/socket.io.min.js",base_url="http://127.0.0.1")
    assert asset.status_code==200
    assert hashlib.sha256(asset.data).hexdigest()=="706642baf73b0848440da39dc0d45a438b31c8965f04ba93a42ef3889f0fa772"
    response=client.get("/api/node/independence",base_url="http://127.0.0.1")
    assert response.status_code==200
    report=response.get_json()["node"]
    assert report["status"]=="configured-local"
    assert report["automatic_runtime_repair_enabled"] is False
    assert client.get("/api/node/independence",base_url="http://127.0.0.1",environ_overrides={"REMOTE_ADDR":"203.0.113.10"}).status_code==403
    connection=socketio.test_client(app)
    assert connection.is_connected()
    connection.disconnect()
    from urllib.parse import urlsplit
    assert all(urlsplit(url).hostname in {"127.0.0.1","localhost","::1"} for url in attempts),attempts
print(json.dumps({"status":"PASS","panel":200,"local_socket_asset":200,"owner_status":200,"remote_status":403,"socket_handshake":True,"external_http_attempts":0,"inference_performed":False}))
'''
            result = subprocess.run([sys.executable, "-c", script], cwd=node, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('"external_http_attempts": 0', result.stdout)


if __name__ == "__main__":
    unittest.main()
