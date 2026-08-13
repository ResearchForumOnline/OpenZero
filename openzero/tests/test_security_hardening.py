import pathlib
import tempfile
import unittest

from brain import cortex, shell_core
from brain.openzero_config import load_env, save_env_value, save_env_values
from openzero_doctor import (
    CURRENT_DEFAULT_LOCAL_MODEL,
    choose_installed_model,
    model_is_localish,
    model_is_probably_cloud,
    runtime_candidates,
)


OPENZERO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class RetiredExecutorTests(unittest.TestCase):
    def test_legacy_shell_helpers_are_fail_closed(self):
        for result in (
            shell_core.execute_bash("printf unsafe"),
            shell_core.execute_persistent("legacy", "printf unsafe"),
        ):
            output, exit_code = result
            self.assertEqual(exit_code, 126)
            self.assertIn("BLOCKED", output)

    def test_legacy_cortex_never_interprets_model_output_as_commands(self):
        reply = cortex.process_agent_logic("<bash>touch should-not-run</bash>")
        self.assertIn("BLOCKED", reply)

        shell_source = (OPENZERO_ROOT / "brain" / "shell_core.py").read_text(encoding="utf-8")
        cortex_source = (OPENZERO_ROOT / "brain" / "cortex.py").read_text(encoding="utf-8")
        for forbidden in ("1234ZERO", "sudo -S", "shell=True", "subprocess.run"):
            self.assertNotIn(forbidden, shell_source)
        for forbidden in ("requests.post", "execute_bash(command)", "execute_persistent(session_name"):
            self.assertNotIn(forbidden, cortex_source)


class ProductionServiceContractTests(unittest.TestCase):
    def test_wsgi_and_launchers_use_bounded_loopback_gunicorn(self):
        requirements = (OPENZERO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        runner = (OPENZERO_ROOT / "run_brain.sh").read_text(encoding="utf-8")
        ignite = (OPENZERO_ROOT / "ignite.sh").read_text(encoding="utf-8")
        watchdog = (OPENZERO_ROOT / "openzero_watchdog.py").read_text(encoding="utf-8")
        deploy = (OPENZERO_ROOT / "deploy_node.sh").read_text(encoding="utf-8")
        wsgi = (OPENZERO_ROOT / "brain" / "wsgi.py").read_text(encoding="utf-8")

        self.assertIn("gunicorn==23.0.0", requirements)
        self.assertIn("simple-websocket==1.1.0", requirements)
        self.assertIn(".runtime/venv/bin/python", runner)
        self.assertIn("import flask, flask_socketio, gunicorn", runner)
        self.assertIn("--workers 1", runner)
        self.assertIn("--bind 127.0.0.1:1024", runner)
        self.assertIn("brain.wsgi:app", runner)
        self.assertIn("run_brain.sh", ignite)
        self.assertIn("systemctl is-active --quiet openzero-brain.service", ignite)
        self.assertIn("systemctl is-active --quiet openzero-vision.service", ignite)
        self.assertIn("systemctl show -p LoadState --value ollama.service", ignite)
        self.assertNotIn("pm2 start brain/app.py", ignite)
        self.assertIn("openzero-brain.service", watchdog)
        self.assertNotIn("pm2 start brain/app.py", watchdog)
        self.assertIn('exec "${SCRIPT_DIR}/install.sh" --server', deploy)
        self.assertNotIn("pm2 start", deploy)
        self.assertNotIn("apt-get", deploy)
        self.assertIn("recover_autonomous_runs()", wsgi)
        self.assertIn("target=heartbeat_loop", wsgi)

        app_source = (OPENZERO_ROOT / "brain" / "app.py").read_text(encoding="utf-8")
        self.assertIn("Direct Flask/Werkzeug startup is disabled", app_source)
        self.assertNotIn("allow_unsafe_werkzeug", app_source)

    def test_systemd_service_is_loopback_only_and_sandboxed(self):
        service = (OPENZERO_ROOT / "setup_service.sh").read_text(encoding="utf-8")
        for expected in (
            "openzero-brain.service",
            "openzero-vision.service",
            "brain.wsgi:app",
            "--bind 127.0.0.1:1024",
            "NoNewPrivileges=yes",
            "PrivateTmp=yes",
            "ProtectSystem=strict",
            "ProtectHome=read-only",
            "CapabilityBoundingSet=",
            "RestrictSUIDSGID=yes",
        ):
            self.assertIn(expected, service)
        self.assertNotIn("ignite.sh --headless", service)
        self.assertIn("RequiresMountsFor=${INSTALL_DIR}/models", service)
        self.assertEqual(
            service.count('ReadWritePaths="${INSTALL_DIR}" "${INSTALL_DIR}/models"'),
            3,
        )
        self.assertIn("Environment=HOME=${INSTALL_DIR}/.runtime/vision-home", service)
        self.assertIn('ExecStart="${NODE_BIN}" "${INSTALL_DIR}/moltbot/moltbot.js"', service)
        self.assertIn("openzero-brain.service openzero-vision.service openzero-watchdog.service", service)
        self.assertIn("Refusing to install OpenZero services as root", service)
        self.assertIn(
            'sudo install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750',
            service,
        )

        watchdog = (OPENZERO_ROOT / "openzero_watchdog.py").read_text(encoding="utf-8")
        self.assertIn('for service in ("openzero-brain.service", "openzero-vision.service")', watchdog)
        self.assertNotIn('ensure_pm2_process("zero-vision"', watchdog)
        self.assertNotIn('ensure_pm2_process(\n            "zero-brain"', watchdog)

        janitor = (OPENZERO_ROOT / "janitor.sh").read_text(encoding="utf-8")
        self.assertIn('TARGET_DIR="${SCRIPT_DIR}/static"', janitor)
        self.assertNotIn("/home/zero/openzero", janitor)

    def test_ssh_known_hosts_stays_inside_sandbox_writable_state(self):
        app_source = (OPENZERO_ROOT / "brain" / "app.py").read_text(encoding="utf-8")
        self.assertIn(
            'SSH_KNOWN_HOSTS_PATH = os.path.join(SECURITY_FOLDER, "ssh_known_hosts")',
            app_source,
        )
        self.assertEqual(app_source.count("UserKnownHostsFile={SSH_KNOWN_HOSTS_PATH}"), 2)


class PrivilegeBoundaryTests(unittest.TestCase):
    def test_active_runtime_has_no_plaintext_password_or_auto_sudo_path(self):
        paths = (
            "brain/app.py",
            "zero_core.py",
            "brain/openzero_config.py",
            ".env.example",
            "zero_passwd.sh",
            "templates/manual.html",
        )
        combined = "\n".join(
            (OPENZERO_ROOT / path).read_text(encoding="utf-8") for path in paths
        )
        for forbidden in ("1234ZERO", "sudo -S", "ROOT OVERRIDE SUCCESS"):
            self.assertNotIn(forbidden, combined)
        self.assertNotIn("SUDO_PASS", (OPENZERO_ROOT / "brain" / "app.py").read_text(encoding="utf-8"))
        self.assertNotIn("SUDO_PASS", (OPENZERO_ROOT / "zero_core.py").read_text(encoding="utf-8"))
        self.assertNotIn("SUDO_PASS", (OPENZERO_ROOT / ".env.example").read_text(encoding="utf-8"))

    def test_legacy_password_helper_uses_only_native_interactive_utility(self):
        helper = (OPENZERO_ROOT / "zero_passwd.sh").read_text(encoding="utf-8")
        self.assertIn("exec passwd", helper)
        for forbidden in ("read -s", "chpasswd", ".env", "SUDO_PASS", "sudo"):
            self.assertNotIn(forbidden, helper)

    def test_legacy_secret_is_ignored_rejected_and_removed_on_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            env_path = pathlib.Path(temporary) / ".env"
            env_path.write_text("SUDO_PASS=do-not-retain\nACTIVE_MODEL=example\n", encoding="utf-8")

            self.assertNotIn("SUDO_PASS", load_env(temporary))
            with self.assertRaises(ValueError):
                save_env_value(temporary, "SUDO_PASS", "replacement")
            with self.assertRaises(ValueError):
                save_env_values(temporary, {"SUDO_PASS": "replacement"})

            save_env_value(temporary, "ACTIVE_MODEL", "replacement-model")
            saved = env_path.read_text(encoding="utf-8")
            self.assertNotIn("SUDO_PASS", saved)
            self.assertIn("ACTIVE_MODEL=replacement-model", saved)

    def test_installers_delete_retired_plaintext_key_during_upgrade(self):
        for filename in ("install.sh", "install_offline.sh"):
            source = (OPENZERO_ROOT / filename).read_text(encoding="utf-8")
            self.assertIn('current.pop("SUDO_PASS", None)', source)

    def test_arbitrary_command_paths_require_approval_and_stay_unprivileged(self):
        app_source = (OPENZERO_ROOT / "brain" / "app.py").read_text(encoding="utf-8")
        bash_start = app_source.index("Preparing bash proposal")
        gate_index = app_source.index("gate = autonomous_action_gate(", bash_start)
        execute_index = app_source.index("result = execute_system_command(command)", bash_start)
        self.assertLess(gate_index, execute_index)
        self.assertIn("will not execute model-proposed commands as root", app_source)
        self.assertNotIn("curl -fsSL https://ollama.com/install.sh | sh", app_source)
        self.assertIn('"status": "manual_required"', app_source)

        cli_source = (OPENZERO_ROOT / "zero_core.py").read_text(encoding="utf-8")
        confirm_index = cli_source.index("elif confirm_exact_cli_command(shell_command):")
        cli_execute_index = cli_source.index("print(execute_system_command(shell_command))", confirm_index)
        self.assertLess(confirm_index, cli_execute_index)
        self.assertIn("hmac.compare_digest(supplied, fingerprint)", cli_source)
        self.assertIn("will not execute model-proposed commands as root", cli_source)

    def test_automatic_repair_paths_cannot_escalate_privileges(self):
        doctor = (OPENZERO_ROOT / "openzero_doctor.py").read_text(encoding="utf-8")
        watchdog = (OPENZERO_ROOT / "openzero_watchdog.py").read_text(encoding="utf-8")
        app_source = (OPENZERO_ROOT / "brain" / "app.py").read_text(encoding="utf-8")
        bitnet_installer = (OPENZERO_ROOT / "install_bitnet.sh").read_text(encoding="utf-8")

        for forbidden in ("sudo -n", "run_privileged", "curl -fsSL https://ollama.com/install.sh | sh"):
            self.assertNotIn(forbidden, doctor)
        self.assertNotIn("sudo -n systemctl restart ollama", watchdog)
        self.assertIn("automatic privileged restart is disabled", watchdog)
        self.assertIn('installer_env["OPENZERO_NO_PRIVILEGE_ESCALATION"] = "1"', app_source)
        self.assertIn('OPENZERO_NO_PRIVILEGE_ESCALATION:-0', bitnet_installer)

    def test_manual_has_no_shared_default_or_root_runtime_claim(self):
        manual = (OPENZERO_ROOT / "templates" / "manual.html").read_text(encoding="utf-8")
        self.assertNotIn("default credentials", manual.lower())
        self.assertNotIn("absolute control", manual.lower())
        self.assertIn("unique operator account and password", manual)
        self.assertIn("no automatic privilege escalation", manual)


class DoctorModelSelectionTests(unittest.TestCase):
    def test_hugging_face_ollama_reference_is_local(self):
        self.assertFalse(model_is_probably_cloud(CURRENT_DEFAULT_LOCAL_MODEL))
        self.assertTrue(model_is_localish(CURRENT_DEFAULT_LOCAL_MODEL))
        self.assertTrue(model_is_probably_cloud("openai/gpt-5"))

    def test_configured_and_current_models_precede_legacy_fallbacks(self):
        configured = "hf.co/example/managed-openzero:Q5_K_M"
        env = {
            "ACTIVE_MODEL": configured,
            "NODE_RECOMMENDED_MODEL": CURRENT_DEFAULT_LOCAL_MODEL,
            "NODE_RAM_GB": "32",
        }
        self.assertEqual(runtime_candidates(env)[0], configured)
        installed = ["openzerogemma:latest", CURRENT_DEFAULT_LOCAL_MODEL, configured]
        self.assertEqual(choose_installed_model(installed, env), configured)

    def test_current_default_wins_over_gemma_when_installed(self):
        env = {
            "ACTIVE_MODEL": CURRENT_DEFAULT_LOCAL_MODEL,
            "NODE_RECOMMENDED_MODEL": CURRENT_DEFAULT_LOCAL_MODEL,
            "NODE_RAM_GB": "32",
        }
        installed = ["openzerogemma:latest", CURRENT_DEFAULT_LOCAL_MODEL]
        self.assertEqual(choose_installed_model(installed, env), CURRENT_DEFAULT_LOCAL_MODEL)


if __name__ == "__main__":
    unittest.main()
