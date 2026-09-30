import hashlib
import io
import json
import pathlib
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from flask import Flask
from werkzeug.serving import make_server

from brain.peer_mesh import (MAX_BATCH, MAX_BODY, MAX_NOTES, MAX_PEERS, SCHEMA,
                             PeerError, PeerMesh, canonical, register_peer_routes,
                             token_hash, validate_event, validate_origin)
from brain.openzero_config import load_env
from brain.improvement_workbench import PROTECTED
from brain.workbench_access import workbench_request_authorized


class PeerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.mesh = PeerMesh(self.root / "a")

    def event(self, text="A reviewed note", title="Example"):
        content = {"schema": SCHEMA, "kind": "note", "title": title, "text": text}
        return {"id": hashlib.sha256(canonical(content)).hexdigest(), "content": content, "created_at": time.time()}

    def app(self, mesh_root="api", owner=True):
        app = Flask(mesh_root)
        app.config["TESTING"] = True
        mesh = register_peer_routes(app, self.root / mesh_root, lambda: owner)
        return app, mesh

    def test_default_has_no_endpoints_network_or_keys(self):
        status = self.mesh.status()
        self.assertFalse(status["enabled"])
        self.assertEqual(status["peers"], [])
        self.assertIsNone(status["coordinator"])
        self.assertFalse(status["automatic_sharing"])
        self.assertFalse(self.mesh.path.exists())
        self.assertIn("brain/peer_mesh.py", PROTECTED)

    def test_explicit_toggle_key_rotation_revocation(self):
        token = self.mesh.rotate_receive_key()["receive_key"]
        self.assertFalse(self.mesh.authorized(token))
        self.mesh.configure(True)
        self.assertTrue(self.mesh.authorized(token))
        new = self.mesh.rotate_receive_key()["receive_key"]
        self.assertFalse(self.mesh.authorized(token))
        self.assertTrue(self.mesh.authorized(new))
        self.mesh.rotate_receive_key(revoke=True)
        self.assertFalse(self.mesh.authorized(new))
        self.assertNotIn(new, self.mesh.path.read_text())

    def test_peer_settings_never_expose_tokens(self):
        token = "ozpeer_" + "synthetic" * 6
        self.mesh.add_peer("Own node", "https://node.example", token)
        status = json.dumps(self.mesh.status())
        self.assertNotIn(token, status)
        self.assertIn("https://node.example", status)
        self.assertFalse(self.mesh.status()["enabled"])

    def test_precise_origins_disallow_redirectlike_urls_metadata_and_public_http(self):
        for origin in ("https://user:secret@node.example", "https://node.example/path", "https://node.example?token=x", "https://node.example#frag", "file:///tmp/test", "http://example.com", "https://169.254.169.254", "https://metadata.google.internal", "https://0.0.0.0", "https://[ff02::1]"):
            with self.subTest(origin=origin), self.assertRaises(PeerError):
                validate_origin(origin)
        self.assertEqual(validate_origin("http://127.0.0.1:2024/"), "http://127.0.0.1:2024")
        self.assertEqual(validate_origin("https://node.example/"), "https://node.example")

    def test_peer_count_and_key_validation(self):
        for index in range(MAX_PEERS):
            self.mesh.add_peer(str(index), f"https://node{index}.example", "ozpeer_" + "x" * 40)
        with self.assertRaises(PeerError):
            self.mesh.add_peer("overflow", "https://extra.example", "ozpeer_" + "x" * 40)
        self.mesh.add_peer("updated", "https://node0.example", "ozpeer_" + "y" * 40)
        self.assertEqual(len(self.mesh.status()["peers"]), MAX_PEERS)
        with self.assertRaises(PeerError):
            self.mesh.add_peer("bad", "https://node0.example", "admin-token")

    def test_consent_content_addressing_dedup_and_delete(self):
        with self.assertRaises(PeerError):
            self.mesh.publish("Title", "Text", False)
        first = self.mesh.publish("Title", "Text", True)
        second = self.mesh.publish("Title", "Text", True)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.mesh.status()["published_count"], 1)
        self.mesh.delete_note(first["id"])
        self.assertEqual(self.mesh.status()["published_count"], 0)

    def test_text_format_digests_limits(self):
        good = self.event()
        self.assertEqual(validate_event(good), good)
        for bad in ({**good, "id": "0" * 64}, {**good, "command": "run"}, {**good, "created_at": float("nan")}, {**good, "created_at": time.time() + 1000}):
            with self.assertRaises(PeerError):
                validate_event(bad)
        for title, text in (("x" * 161, "text"), ("ok", "x" * 8001), ("ok", ""), ("ok", "\x00"), ("ok", "界" * 8000)):
            with self.assertRaises(PeerError):
                self.mesh.publish(title, text, True)

    def test_secret_redaction_and_host_filter(self):
        result = self.mesh.publish("key", "api_key=synthetic-key secret=not-real Bearer abcdefghijklmnopqrstuvwxyz ozpeer_abcdefghijklmnopqrstuvwxyz", True)
        self.assertNotIn("synthetic-key", result["content"]["text"])
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", result["content"]["text"])
        self.assertIn("REDACTED", result["content"]["text"])
        denied = PeerMesh(self.root / "denied", filter_note=lambda a, b: {"ok": False})
        with self.assertRaises(PeerError):
            denied.publish("t", "text", True)

    def test_inbox_quarantined_not_forwarded(self):
        self.mesh.configure(True)
        event = self.event("<script>untrusted remote text</script>")
        reply = self.mesh.exchange({"schema": SCHEMA, "events": [event]})
        self.assertEqual(reply["received"], 1)
        self.assertEqual(reply["events"], [])
        inbox = self.mesh.status()["inbox"]
        self.assertTrue(inbox[0]["review_required"])
        self.assertEqual(self.mesh.exchange({"schema": SCHEMA, "events": [event]})["received"], 0)
        self.mesh.delete_note(event["id"], inbox=True)
        self.assertEqual(self.mesh.status()["inbox_count"], 0)

    def test_exchange_batch_atomic_validation_and_rate_bounds(self):
        self.mesh.configure(True)
        event = self.event()
        with self.assertRaises(PeerError):
            self.mesh.exchange({"schema": SCHEMA, "events": [event] * (MAX_BATCH + 1)})
        with self.assertRaises(PeerError):
            self.mesh.exchange({"schema": SCHEMA, "events": [event, {**event, "id": "x"}]})
        self.assertEqual(self.mesh.status()["inbox_count"], 0)
        self.mesh.rate_count = 120
        with self.assertRaises(PeerError):
            self.mesh.exchange({"schema": SCHEMA, "events": []})

    def test_note_store_capacity_and_durability(self):
        with self.mesh.lock:
            state = self.mesh._load()
            state["published"] = [self.event(str(i)) for i in range(MAX_NOTES)]
            self.mesh._save(state)
        with self.assertRaises(PeerError):
            self.mesh.publish("new", "new", True)
        loaded = PeerMesh(self.root / "a")
        self.assertEqual(loaded.status()["published_count"], MAX_NOTES)
        self.assertEqual(len(loaded.status()["published"]), 40)

    def test_failed_peers_are_isolated_and_errors_do_not_leak(self):
        def outbound(peer, payload):
            if peer["label"] == "broken":
                raise ValueError("SECRET " + peer["token"])
            return {"schema": SCHEMA, "events": [self.event("A peer note")]}
        mesh = PeerMesh(self.root / "sync", outbound=outbound)
        mesh.configure(True)
        for name in ("broken", "good"):
            mesh.add_peer(name, f"https://{name}.example", "ozpeer_" + "x" * 40)
        result = mesh.sync(True)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["results"][0]["ok"])
        self.assertTrue(result["results"][1]["ok"])
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertEqual(mesh.status()["inbox_count"], 1)

    def test_sync_requires_consent_enabled_peers_and_single_job(self):
        for consent in (False, None, "true"):
            with self.assertRaises(PeerError):
                self.mesh.sync(consent)
        with self.assertRaises(PeerError):
            self.mesh.sync(True)
        self.mesh.configure(True)
        with self.assertRaises(PeerError):
            self.mesh.sync(True)
        self.mesh.sync_lock.acquire()
        try:
            with self.assertRaises(PeerError):
                self.mesh.sync(True)
        finally:
            self.mesh.sync_lock.release()

    def test_disable_during_fanout_stops_later_requests(self):
        called = []
        def outbound(peer, payload):
            called.append(peer["label"])
            mesh.configure(False)
            return {"schema": SCHEMA, "events": [self.event()]}
        mesh = PeerMesh(self.root / "disable", outbound=outbound)
        mesh.configure(True)
        for i in range(3):
            mesh.add_peer(str(i), f"https://node{i}.example", "ozpeer_" + "x" * 40)
        mesh.sync(True)
        self.assertEqual(called, ["0"])
        self.assertEqual(mesh.status()["inbox_count"], 0)

    def test_route_owner_authority_does_not_accept_peer_key_for_management(self):
        app, mesh = self.app(owner=False)
        key = mesh.rotate_receive_key()["receive_key"]
        mesh.configure(True)
        client = app.test_client()
        for route in ("status", "config", "key", "add", "remove", "publish", "sync", "delete", "inbox/delete"):
            response = client.get("/api/peers/status", headers={"Authorization": "Bearer " + key}) if route == "status" else client.post("/api/peers/" + route, json={}, headers={"Authorization": "Bearer " + key})
            self.assertEqual(response.status_code, 403)

    def test_receive_endpoint_dedicated_auth_json_origin_and_body_limits(self):
        app, mesh = self.app()
        key = mesh.rotate_receive_key()["receive_key"]
        client = app.test_client()
        payload = {"schema": SCHEMA, "events": [self.event()]}
        headers = {"Authorization": "Bearer " + key}
        self.assertEqual(client.post("/api/peers/exchange", json=payload, headers=headers).status_code, 401)
        mesh.configure(True)
        self.assertEqual(client.post("/api/peers/exchange", json=payload).status_code, 401)
        self.assertEqual(client.post("/api/peers/exchange", json=payload, headers={**headers, "Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(client.post("/api/peers/exchange", data="not json", headers=headers).status_code, 400)
        self.assertEqual(client.post("/api/peers/exchange", data="x" * (MAX_BODY + 1), content_type="application/json", headers=headers).status_code, 400)
        self.assertEqual(client.post("/api/peers/exchange", json=payload, headers=headers).status_code, 200)
        self.assertEqual(mesh.status()["inbox_count"], 1)

    def test_chunked_body_read_is_bounded_before_allocation(self):
        app, mesh = self.app("chunked")
        mesh.configure(True)
        key = mesh.rotate_receive_key()["receive_key"]
        class RecordedInput(io.BytesIO):
            def __init__(self, content):
                super().__init__(content)
                self.read_sizes = []
            def read(self, size=-1):
                self.read_sizes.append(size)
                return super().read(size)
        source = RecordedInput(b"x" * (MAX_BODY * 2))
        response = app.test_client().open("/api/peers/exchange", method="POST", content_type="application/json",
                                         headers={"Authorization": "Bearer " + key},
                                         environ_overrides={"wsgi.input": source, "wsgi.input_terminated": True, "CONTENT_LENGTH": ""})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(source.read_sizes, [MAX_BODY + 1])
        self.assertEqual(source.tell(), MAX_BODY + 1)

    def test_outbound_small_chunks_observe_deadline_and_no_redirect_proxy(self):
        class Response:
            status_code = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def iter_content(self, chunk_size):
                self.size = chunk_size
                yield b"{"
        response = Response()
        class Session:
            trust_env = True
            def post(self, url, **kwargs):
                self.options = kwargs
                return response
            def close(self): self.closed = True
        session = Session()
        with patch("brain.peer_mesh.requests.Session", return_value=session), patch("brain.peer_mesh.time.monotonic", side_effect=[0, 7]):
            with self.assertRaises(PeerError):
                self.mesh._http_exchange({"origin": "https://node.example", "token": "synthetic"}, {"schema": SCHEMA, "events": []})
        self.assertFalse(session.trust_env)
        self.assertFalse(session.options["allow_redirects"])
        self.assertTrue(session.options["stream"])
        self.assertEqual(session.options["timeout"], (2, 3))
        self.assertEqual(response.size, 1)
        self.assertTrue(session.closed)

    def test_owner_route_origin_and_dns_rebinding_boundary(self):
        from flask import request
        app = Flask("origin")
        app.config["TESTING"] = True
        register_peer_routes(app, self.root / "origins", lambda: workbench_request_authorized(lambda: request.remote_addr == "127.0.0.1", lambda: False))
        client = app.test_client()
        self.assertEqual(client.post("/api/peers/config", json={"enabled": True}, base_url="http://127.0.0.1:1024").status_code, 200)
        self.assertEqual(client.post("/api/peers/config", json={"enabled": True}, base_url="http://attacker.example").status_code, 403)
        self.assertEqual(client.post("/api/peers/config", json={"enabled": True}, headers={"Origin": "https://evil.example"}).status_code, 403)

    def test_real_loopback_two_node_exchange_without_coordinator(self):
        app_a, mesh_a = self.app("node-a")
        app_b, mesh_b = self.app("node-b")
        server = make_server("127.0.0.1", 0, app_b, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        mesh_a.configure(True)
        mesh_b.configure(True)
        receive = mesh_b.rotate_receive_key()["receive_key"]
        mesh_a.add_peer("Second independent node", f"http://127.0.0.1:{server.server_port}", receive)
        first = mesh_a.publish("A", "A manual note", True)
        second = mesh_b.publish("B", "Another manual note", True)
        result = mesh_a.sync(True)
        self.assertEqual(result["status"], "success")
        self.assertEqual(mesh_b.status()["inbox"][0]["id"], first["id"])
        self.assertEqual(mesh_a.status()["inbox"][0]["id"], second["id"])
        self.assertEqual(mesh_a.sync(True)["results"][0]["received"], 0)
        mesh_b.rotate_receive_key(revoke=True)
        self.assertEqual(mesh_a.sync(True)["status"], "partial")

    def test_real_unicode_near_limit_batches_fit_both_wire_directions(self):
        app_a, mesh_a = self.app("large-node-a")
        app_b, mesh_b = self.app("large-node-b")
        server = make_server("127.0.0.1", 0, app_b, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        mesh_a.configure(True); mesh_b.configure(True)
        receive = mesh_b.rotate_receive_key()["receive_key"]
        mesh_a.add_peer("Large Unicode peer", f"http://127.0.0.1:{server.server_port}", receive)
        for index in range(MAX_BATCH):
            mesh_a.publish("A " + str(index), "é" * 7500 + str(index), True)
            mesh_b.publish("B " + str(index), "界" * 5000 + str(index), True)
        result = mesh_a.sync(True)
        self.assertEqual(result["status"], "success")
        self.assertGreater(mesh_b.status()["inbox_count"], 0)
        self.assertLess(mesh_b.status()["inbox_count"], MAX_BATCH)
        self.assertGreater(mesh_a.status()["inbox_count"], 0)
        reply = mesh_b.exchange({"schema": SCHEMA, "events": []})
        self.assertLessEqual(len(canonical(reply)), MAX_BODY)
        self.assertIn("界", canonical(reply).decode())

    def test_vendor_migration_preserves_custom_endpoint_and_never_rewrites_file(self):
        config_root = self.root / "cfg"
        config_root.mkdir()
        env = config_root / ".env"
        env.write_text("OPENZERO_HIVE_URL=https://openzero.talktoai.org/api/hive\nOPENZERO_HIVE_MIRRORS=https://operator.example/api/hive,https://openzero.talktoai.org/api/hive\nOPENZERO_HIVE_MODE=federated\nHIVE_MIND_ENABLED=true\n")
        before = env.read_bytes()
        config = load_env(str(config_root))
        self.assertEqual(config["OPENZERO_HIVE_URL"], "")
        self.assertEqual(config["OPENZERO_HIVE_MIRRORS"], "https://operator.example/api/hive")
        self.assertEqual(config["HIVE_MIND_ENABLED"], "true")
        self.assertEqual(before, env.read_bytes())
        env.write_text("OPENZERO_HIVE_URL=https://openzero.talktoai.org/api/hive\nHIVE_MIND_ENABLED=true\n")
        config = load_env(str(config_root))
        self.assertEqual(config["OPENZERO_HIVE_MODE"], "local")
        self.assertEqual(config["HIVE_MIND_ENABLED"], "false")

    def test_corrupt_or_linked_state_fails_closed(self):
        self.mesh.root.mkdir()
        self.mesh.path.write_text("invalid")
        with self.assertRaises(ValueError):
            self.mesh.status()
        self.mesh.path.unlink()
        target = self.root / "target.json"
        target.write_text("{}"); self.mesh.path.symlink_to(target)
        with self.assertRaises(PeerError):
            self.mesh.status()


if __name__ == "__main__":
    unittest.main()
