import pathlib
import unittest


OPENZERO_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_SOURCE = (OPENZERO_ROOT / "brain" / "app.py").read_text(encoding="utf-8")
PANEL_SOURCE = (OPENZERO_ROOT / "templates" / "index.html").read_text(encoding="utf-8")


class ModelCatalogContractTests(unittest.TestCase):
    def test_local_catalog_is_limited_to_the_three_current_openzero_models(self):
        for alias in (
            "openzerogemma:latest",
            "zero-qwen3-q5:latest",
            "zero-qwen3-f16:latest",
        ):
            self.assertIn(alias, APP_SOURCE)
            self.assertIn(alias, PANEL_SOURCE)
        self.assertIn("visible_openzero_models", APP_SOURCE)
        self.assertIn("for model in visible_openzero_models()", APP_SOURCE)

    def test_old_stock_install_buttons_and_resolved_local_reinsertion_are_absent(self):
        self.assertNotIn("installLocalModel('gemma4:e2b')", PANEL_SOURCE)
        self.assertNotIn("installLocalModel('gemma3:12b')", PANEL_SOURCE)
        self.assertNotIn("Resolved Local:", PANEL_SOURCE)


if __name__ == "__main__":
    unittest.main()