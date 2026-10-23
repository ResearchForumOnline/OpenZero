import ast
import hashlib
from html.parser import HTMLParser
import json
import pathlib
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

from brain.model_routing import CLOUD_MODEL_NAMES, automatic_repair_allowed, cloud_model_for, select_model_route
from brain.openzero_config import load_env
from node_status import independence_report

ROOT = pathlib.Path(__file__).resolve().parents[1]


def isolated_function(relative, name, namespace):
    """Load the exact routing function without starting the app or touching private state."""
    source = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    function = next(item for item in source.body if isinstance(item, ast.FunctionDef) and item.name == name)
    function.decorator_list = []
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(relative), "exec"), namespace)
    return namespace[name]


class NodeIndependenceTests(unittest.TestCase):
    def test_ordinary_local_aliases_never_imply_cloud_routing(self):
        for model in ("llama3:8b", "qwen2.5:7b", "my-gpt-model:latest", "compound-local:latest", "myorg/qwen:latest", "hf.co/myorg/llama-model:Q4_K_M", "hf.co/shafire/OpenZero-Ministral3-8B-Runtime-Agent-GGUF:Q5_K_M"):
            with self.subTest(model=model):
                self.assertEqual(select_model_route("hybrid", model), "local")

    def test_cloud_catalog_requires_mode_selection(self):
        for model in CLOUD_MODEL_NAMES:
            self.assertEqual(select_model_route("local", model), "local")
            self.assertEqual(select_model_route("hybrid", model), "cloud")
        self.assertEqual(select_model_route("cloud", "local-model:latest"), "cloud")
        self.assertEqual(select_model_route("malformed-mode", "groq/compound"), "local")

    def test_cli_local_families_do_not_call_cloud_even_when_key_is_present(self):
        for model in ("llama3:8b", "qwen2.5:7b", "hf.co/owner/my-qwen:Q4_K_M"):
            cloud = Mock(side_effect=AssertionError("cloud must not be contacted"))
            namespace = {"select_model_route": select_model_route, "get_config": lambda: {"COMP_MODE": "hybrid", "ACTIVE_MODEL": model, "GROQ_API_KEY": "synthetic-private-key"}, "brain_local": Mock(return_value="local answer"), "brain_groq": cloud}
            route = isolated_function("zero_core.py", "route_response", namespace)
            self.assertEqual(route("private local prompt"), "local answer")
            cloud.assert_not_called()

    def test_panel_and_cli_use_identical_route_selection(self):
        for mode, model, expected in (("local", "groq/compound", "local"), ("hybrid", "qwen2.5:7b", "local"), ("hybrid", "groq/compound", "cloud"), ("cloud", "llama3:8b", "cloud")):
            config = {"COMP_MODE": mode, "ACTIVE_MODEL": model}
            namespace = {"Dict": dict, "List": list, "select_model_route": select_model_route,
                         "current_config": lambda: config, "get_config": lambda: config,
                         "LOCAL_MODEL_SEMAPHORE": threading.Semaphore(1),
                         "ask_local": Mock(return_value="local"), "ask_groq": Mock(return_value="cloud"),
                         "brain_local": Mock(return_value="local"), "brain_groq": Mock(return_value="cloud")}
            panel = isolated_function("brain/app.py", "autonomous_model_reply", namespace)
            cli = isolated_function("zero_core.py", "route_response", namespace)
            self.assertEqual(panel("prompt", mode, "chat", [], ""), expected)
            self.assertEqual(cli("prompt"), expected)

    def test_unavailable_cloud_does_not_silently_switch_models(self):
        local = Mock(side_effect=AssertionError("no implicit local fallback"))
        route = isolated_function("zero_core.py", "route_response", {"select_model_route": select_model_route, "get_config": lambda: {"COMP_MODE": "cloud"}, "brain_local": local, "brain_groq": Mock(return_value="")})
        self.assertIn("selected cloud route is unavailable", route("prompt"))
        local.assert_not_called()

    def test_cloud_payload_never_uses_local_ollama_model_alias(self):
        self.assertEqual(cloud_model_for("qwen2.5:7b"), "groq/compound-large")
        self.assertEqual(cloud_model_for("qwen/qwen3-32b"), "qwen/qwen3-32b")

    def test_disabled_automatic_repair_spawns_no_worker_or_command(self):
        thread = Mock(side_effect=AssertionError("repair worker must not start"))
        namespace = {"automatic_repair_allowed": automatic_repair_allowed,
                     "current_config": lambda: {"OLLAMA_AUTO_REPAIR_ENABLED": "false"},
                     "threading": Mock(Thread=thread)}
        repair = isolated_function("brain/app.py", "maybe_trigger_runtime_self_heal", namespace)
        self.assertIn("disabled", repair("missing local model"))
        thread.assert_not_called()

    def test_repair_cooldown_does_not_claim_a_new_repair(self):
        namespace = {"automatic_repair_allowed": automatic_repair_allowed, "current_config": lambda: {},
                     "time": Mock(time=lambda: 100), "LAST_RUNTIME_SELF_HEAL_AT": 90,
                     "RUNTIME_SELF_HEAL_COOLDOWN_SECONDS": 60}
        repair = isolated_function("brain/app.py", "maybe_trigger_runtime_self_heal", namespace)
        self.assertIn("cooldown", repair("missing local model"))

    def test_fresh_configuration_and_report_need_no_network_or_keys(self):
        with tempfile.TemporaryDirectory() as directory, patch("socket.socket", side_effect=AssertionError("no network")):
            config = load_env(directory)
            self.assertEqual(config["COMP_MODE"], "local")
            report = independence_report(config)
            self.assertEqual(report["status"], "configured-local")
            self.assertFalse(report["owner_account_required"])
            self.assertFalse(report["owner_coordinator_required"])
            self.assertEqual(list(pathlib.Path(directory).iterdir()), [])

    def test_report_never_exports_secrets_endpoints_or_prompt(self):
        config = {"COMP_MODE": "cloud", "GROQ_API_KEY": "SYNTHETIC_SECRET", "OPENZERO_HIVE_URL": "https://user:private@node.example", "HIVE_MIND_ENABLED": "true", "PROMPT": "PRIVATE_PROMPT"}
        report = str(independence_report(config))
        for private in ("SYNTHETIC_SECRET", "user:private", "node.example", "PRIVATE_PROMPT"):
            self.assertNotIn(private, report)
        self.assertIn("optional-remote-services-selected", report)

    def test_required_workspace_scripts_are_local_and_pinned(self):
        scripts = []
        class Scripts(HTMLParser):
            def handle_starttag(self, tag, attributes):
                if tag == "script":
                    source = dict(attributes).get("src")
                    if source:
                        scripts.append(source)
        Scripts().feed((ROOT / "templates/index.html").read_text(encoding="utf-8"))
        self.assertIn("/static/vendor/socket.io-4.7.1/socket.io.min.js", scripts)
        for source in scripts:
            self.assertTrue(source.startswith("/static/"), source)
            self.assertTrue((ROOT / urlsplit(source).path.lstrip("/")).is_file(), source)
        vendor = ROOT / "static/vendor/socket.io-4.7.1"
        provenance = json.loads((vendor / "PROVENANCE.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["license"], "MIT")
        for name, digest in provenance["files"].items():
            self.assertEqual(hashlib.sha256((vendor / name).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
