import contextlib
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "install.sh").read_text(encoding="utf-8")
TAB_HELPER = (ROOT / "install-tab-pilot.sh").read_text(encoding="utf-8")


class DecentralisedDistributionTests(unittest.TestCase):
    def migrate(self, existing="", offline=False):
        # Execute only the installer's pure configuration migration, never the installer.
        if offline:
            source = (ROOT / "install_offline.sh").read_text()
            block = source.split("python3 - <<PY\n", 1)[1].split("\nPY\n", 1)[0]
            block = block.replace("${INSTALL_DIR}", ".").replace("${ENABLE_VOICE}", "false")
        else:
            block = INSTALLER.split("    python3 - <<PY\n", 1)[1].split("\nPY\n", 1)[0]
        block = block.replace("${TAB_PILOT_URL}", "https://github.com/ResearchForumOnline/OpenZero/tree/main/browser-extension")
        block = block.replace("${OPENZERO_DEFAULT_MODEL}", "fixture-default-model")
        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            try:
                os.chdir(directory)
                Path(".env").write_text(existing, encoding="utf-8")
                exec(compile(block, "installer-env-migration", "exec"), {})
                return dict(line.split("=", 1) for line in Path(".env").read_text().splitlines())
            finally:
                os.chdir(previous)

    def test_fresh_node_has_no_central_route(self):
        env = self.migrate()
        self.assertEqual(env["OPENZERO_DOMAIN"], "http://127.0.0.1:1024")
        self.assertEqual(env["OPENZERO_HIVE_URL"], "")
        self.assertEqual(env["OPENZERO_HIVE_MODE"], "local")
        self.assertEqual(env["HIVE_MIND_ENABLED"], "false")
        self.assertEqual(env["OPENZERO_HIVE_REMOTE_LOOKUP_ENABLED"], "false")
        self.assertEqual(env["OPENZERO_VERSION"], "7.3.0")

    def test_fresh_offline_node_has_no_central_route(self):
        env = self.migrate(offline=True)
        self.assertEqual(env["OPENZERO_DOMAIN"], "http://127.0.0.1:1024")
        self.assertEqual(env["OPENZERO_HIVE_URL"], "")
        self.assertEqual(env["OPENZERO_VERSION"], "7.3.0")

    def test_offline_retired_hive_migration(self):
        env = self.migrate("OPENZERO_HIVE_URL=https://openzero.talktoai.org/api/hive\nHIVE_MIND_ENABLED=true\n", offline=True)
        self.assertEqual(env["OPENZERO_HIVE_URL"], "")
        self.assertEqual(env["HIVE_MIND_ENABLED"], "false")

    def test_offline_custom_endpoint_survives(self):
        env = self.migrate("OPENZERO_HIVE_URL=https://my-node.example/api/hive\nHIVE_MIND_ENABLED=true\n", offline=True)
        self.assertEqual(env["OPENZERO_HIVE_URL"], "https://my-node.example/api/hive")
        self.assertEqual(env["HIVE_MIND_ENABLED"], "true")

    def test_retired_defaults_migrate_without_exposing_password(self):
        env = self.migrate("OPENZERO_HIVE_URL=https://openzero.talktoai.org/api/hive/\nHIVE_MIND_ENABLED=true\nOPENZERO_HIVE_MODE=federated\nOPENZERO_HIVE_REMOTE_LOOKUP_ENABLED=true\nOPENZERO_DOMAIN=https://openzero.talktoai.org/\nOPENZERO_TAB_PILOT_URL=https://openzero.talktoai.org/tab-pilot\nSUDO_PASS=synthetic-fixture\n")
        self.assertEqual(env["OPENZERO_HIVE_URL"], "")
        self.assertEqual(env["HIVE_MIND_ENABLED"], "false")
        self.assertEqual(env["OPENZERO_HIVE_REMOTE_LOOKUP_ENABLED"], "false")
        self.assertEqual(env["OPENZERO_DOMAIN"], "http://127.0.0.1:1024")
        self.assertIn("github.com", env["OPENZERO_TAB_PILOT_URL"])
        self.assertNotIn("SUDO_PASS", env)

    def test_explicit_custom_settings_survive(self):
        env = self.migrate("OPENZERO_HIVE_URL=https://my-node.example/api/hive\nHIVE_MIND_ENABLED=true\nOPENZERO_HIVE_MODE=federated\nOPENZERO_DOMAIN=https://my-panel.example\nACTIVE_MODEL=custom-model\nGROQ_API_KEY=synthetic-fixture\nOPENZERO_HIVE_MIRRORS=https://my-peer.example\n")
        self.assertEqual(env["OPENZERO_HIVE_URL"], "https://my-node.example/api/hive")
        self.assertEqual(env["HIVE_MIND_ENABLED"], "true")
        self.assertEqual(env["OPENZERO_HIVE_MODE"], "federated")
        self.assertEqual(env["OPENZERO_DOMAIN"], "https://my-panel.example")
        self.assertEqual(env["ACTIVE_MODEL"], "custom-model")
        self.assertEqual(env["GROQ_API_KEY"], "synthetic-fixture")
        self.assertEqual(env["OPENZERO_HIVE_MIRRORS"], "https://my-peer.example")

    def test_distribution_endpoints_are_versioned_and_mirrorable(self):
        self.assertIn("releases/download/v7.3.0", INSTALLER)
        self.assertIn("OPENZERO_RELEASE_BASE_URL", INSTALLER)
        updater = (ROOT / "update.sh").read_text()
        self.assertIn("releases/latest/download", updater)
        self.assertIn("OPENZERO_INSTALLER_BASE_URL", updater)
        self.assertIn("sha256sum -c", updater)

    def test_extension_manifest_has_no_retired_update_service(self):
        manifest = json.loads((ROOT.parent / "browser-extension/manifest.json").read_text())
        self.assertEqual(manifest["version"], "0.3.1")
        self.assertNotIn("update_url", manifest)
        self.assertIn("github.com", manifest["homepage_url"])

    def extract_fixture(self, unsafe_name=None, corrupt=False):
        block = TAB_HELPER.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / "stage"
            stage.mkdir()
            node = Path(directory) / "node"
            name = "OpenZero-Tab-Pilot-v0.3.1.zip"
            with zipfile.ZipFile(stage / name, "w") as package:
                package.writestr("manifest.json", json.dumps({"version": "0.3.1"}))
                if unsafe_name:
                    package.writestr(unsafe_name, "fixture")
            digest = hashlib.sha256((stage / name).read_bytes()).hexdigest()
            if corrupt:
                digest = "0" * 64
            (stage / (name + ".sha256")).write_text(f"{digest}  {name}\n")
            with patch("sys.argv", ["fixture", str(stage), str(node), name, "0.3.1"]), contextlib.redirect_stdout(io.StringIO()):
                exec(compile(block, "tab-pilot-extraction", "exec"), {})
            self.assertTrue((node / "extensions/tab-pilot-0.3.1/manifest.json").is_file())

    def test_verified_extension_extracts(self):
        self.extract_fixture()

    def test_corrupt_extension_does_not_extract(self):
        with self.assertRaisesRegex(SystemExit, "checksum mismatch"):
            self.extract_fixture(corrupt=True)

    def test_archive_traversal_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, "Unsafe extension archive path"):
            self.extract_fixture(unsafe_name="../outside.txt")

    def test_windows_helper_checks_digest_and_version(self):
        source = (ROOT / "install-tab-pilot.ps1").read_text()
        self.assertIn(".sha256", source)
        self.assertIn("Get-FileHash", source)
        self.assertIn("$Manifest.version -ne $Version", source)
        self.assertNotIn("openzero.talktoai.org/downloads", source)

    def extract_runtime_fixture(self, extra_path=None, corrupt=False):
        block = INSTALLER.split('python3 - "${stage}" "${payload}" <<\'PY\'\n', 1)[1].split("\nPY\n", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            payload = stage / "payload"
            name = "openzero_release.zip"
            with zipfile.ZipFile(stage / name, "w") as package:
                package.writestr("brain/app.py", "# fixture")
                if extra_path:
                    package.writestr(extra_path, "fixture")
            digest = "0" * 64 if corrupt else hashlib.sha256((stage / name).read_bytes()).hexdigest()
            (stage / (name + ".sha256")).write_text(f"{digest}  {name}\n")
            with patch("sys.argv", ["fixture", str(stage), str(payload)]):
                exec(compile(block, "runtime-extraction", "exec"), {})
            self.assertTrue((payload / "brain/app.py").is_file())

    def test_verified_runtime_extracts(self):
        self.extract_runtime_fixture()

    def test_corrupt_runtime_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, "Runtime checksum mismatch"):
            self.extract_runtime_fixture(corrupt=True)

    def test_runtime_traversal_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, "Unsafe runtime archive path"):
            self.extract_runtime_fixture(extra_path="../outside.txt")

    def test_runtime_cannot_overwrite_private_configuration(self):
        with self.assertRaisesRegex(SystemExit, "private configuration"):
            self.extract_runtime_fixture(extra_path=".env")

    def test_public_and_local_html_links_have_no_retired_origin_or_embedded_commands(self):
        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.urls = []
            def handle_starttag(self, tag, attrs):
                self.urls.extend(value for name, value in attrs if name in {"href", "src"} and value)
        for name in ("index.html", "tab-pilot.html", "tab-pilot-privacy.html", "templates/landing.html", "templates/manual.html"):
            with self.subTest(page=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                self.assertNotIn("\ufffd", source)
                self.assertNotIn("openzero.talktoai.org", source)
                self.assertNotIn("docs.talktoai.org", source)
                links = Links()
                links.feed(source)
                for url in links.urls:
                    self.assertFalse(any(character.isspace() for character in url), url)
                    self.assertNotIn("curl -", url)

    def test_current_installation_guides_do_not_pipe_downloads_to_bash(self):
        for name in ("docs/INSTALL.md", "docs/DOWNLOADS_AND_RELEASES.md", "index.html", "tab-pilot.html", "templates/manual.html"):
            with self.subTest(page=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                for line in source.splitlines():
                    if "curl " in line:
                        self.assertNotIn("| bash", line)


if __name__ == "__main__":
    unittest.main()
