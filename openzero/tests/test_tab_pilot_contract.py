import pathlib
import unittest


OPENZERO_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_SOURCE = (OPENZERO_ROOT / "brain" / "app.py").read_text(encoding="utf-8")
CONFIG_SOURCE = (OPENZERO_ROOT / "brain" / "openzero_config.py").read_text(encoding="utf-8")
INSTALLER_SOURCE = (OPENZERO_ROOT / "install.sh").read_text(encoding="utf-8")
UPDATER_SOURCE = (OPENZERO_ROOT / "update.sh").read_text(encoding="utf-8")
TAB_INSTALLER_SOURCE = (OPENZERO_ROOT / "install-tab-pilot.sh").read_text(encoding="utf-8")
TAB_PAGE_SOURCE = (OPENZERO_ROOT / "tab-pilot.html").read_text(encoding="utf-8")
LANDING_PAGE_SOURCE = (OPENZERO_ROOT / "index.html").read_text(encoding="utf-8")
STORE_URL = "https://chromewebstore.google.com/detail/openzero-tab-pilot/cgaalobjjknalamgchppccbocnhonhbf"


class TabPilotIntegrationContractTests(unittest.TestCase):
    def test_browser_planner_has_a_dedicated_authenticated_route(self):
        self.assertIn('@app.route("/v1/browser/plan", methods=["POST"])', APP_SOURCE)
        self.assertIn("openzero_model_api_authorized(config)", APP_SOURCE)
        self.assertIn("openzero_browser_plan_prompt", APP_SOURCE)
        self.assertIn("openzero_parse_browser_action", APP_SOURCE)

    def test_scoped_token_is_not_accepted_by_general_chat(self):
        chat_start = APP_SOURCE.index("def openzero_chat_completions():")
        chat_end = APP_SOURCE.index('@app.route("/stats")', chat_start)
        chat_route = APP_SOURCE[chat_start:chat_end]
        self.assertIn("openzero_api_authorized(config)", chat_route)
        self.assertNotIn("openzero_model_api_authorized(config)", chat_route)

    def test_default_bind_is_loopback_and_public_bind_is_explicit(self):
        self.assertIn('"OPENZERO_BIND_HOST": "127.0.0.1"', CONFIG_SOURCE)
        self.assertIn('"OPENZERO_ALLOW_PUBLIC_BIND": "false"', CONFIG_SOURCE)
        self.assertIn('bind_host = "127.0.0.1"', APP_SOURCE)

    def test_installer_auto_configures_brave_with_an_opt_out(self):
        self.assertIn("--no-tab-pilot", INSTALLER_SOURCE)
        self.assertIn("install-tab-pilot.sh", INSTALLER_SOURCE)
        self.assertIn("ExtensionInstallForcelist", TAB_INSTALLER_SOURCE)
        self.assertIn("OPENZERO_TAB_PILOT_KEY_HASH", APP_SOURCE)
        self.assertIn("openzerogemma:latest", TAB_INSTALLER_SOURCE)


    def test_published_chrome_web_store_listing_is_canonical_interactive_install(self):
        self.assertIn(STORE_URL, TAB_PAGE_SOURCE)
        self.assertIn(STORE_URL, LANDING_PAGE_SOURCE)
        self.assertNotIn("not yet published in the Chrome Web Store", TAB_PAGE_SOURCE)


    def test_71_installer_migrates_version_and_can_install_brave(self):
        self.assertIn('"OPENZERO_VERSION": "7.1.0"', INSTALLER_SOURCE)
        self.assertIn('current["OPENZERO_VERSION"] = "7.1.0"', INSTALLER_SOURCE)
        self.assertIn("https://dl.brave.com/install.sh", INSTALLER_SOURCE)
        self.assertIn("--brave", INSTALLER_SOURCE)
        self.assertIn("--no-brave", INSTALLER_SOURCE)
        self.assertIn("install_brave_if_requested", INSTALLER_SOURCE)
        self.assertIn("--brave", UPDATER_SOURCE)
        self.assertIn("--no-brave", UPDATER_SOURCE)

if __name__ == "__main__":
    unittest.main()
