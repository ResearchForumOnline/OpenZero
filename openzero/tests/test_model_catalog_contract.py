import pathlib
import unittest


OPENZERO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ROOT_README = (OPENZERO_ROOT.parent / "README.md").read_text(encoding="utf-8")
APP_SOURCE = (OPENZERO_ROOT / "brain" / "app.py").read_text(encoding="utf-8")
PANEL_SOURCE = (OPENZERO_ROOT / "templates" / "index.html").read_text(encoding="utf-8")


class ModelCatalogContractTests(unittest.TestCase):
    def test_local_catalog_includes_the_runtime_default_and_compatibility_models(self):
        for alias in (
            "hf.co/shafire/OpenZero-Ministral3-8B-Runtime-Agent-GGUF:Q5_K_M",
            "openzerogemma:latest",
            "zero-qwen3-q5:latest",
            "zero-qwen3-f16:latest",
        ):
            self.assertIn(alias, APP_SOURCE)
            self.assertIn(alias, PANEL_SOURCE)
        self.assertIn("visible_openzero_models", APP_SOURCE)
        self.assertIn("for model in visible_openzero_models()", APP_SOURCE)

    def test_ministral_is_the_runtime_default(self):
        config = (OPENZERO_ROOT / "brain" / "openzero_config.py").read_text(encoding="utf-8")
        installer = (OPENZERO_ROOT / "install.sh").read_text(encoding="utf-8")
        model = "hf.co/shafire/OpenZero-Ministral3-8B-Runtime-Agent-GGUF:Q5_K_M"
        self.assertIn(f'"ACTIVE_MODEL": "{model}"', config)
        self.assertIn(f'OPENZERO_DEFAULT_MODEL="{model}"', installer)
        self.assertIn('ollama pull "${OPENZERO_DEFAULT_MODEL}"', installer)

    def test_old_stock_install_buttons_and_resolved_local_reinsertion_are_absent(self):
        self.assertNotIn("installLocalModel('gemma4:e2b')", PANEL_SOURCE)
        self.assertNotIn("installLocalModel('gemma3:12b')", PANEL_SOURCE)
        self.assertNotIn("Resolved Local:", PANEL_SOURCE)

    def test_public_readme_uses_canonical_qwen_aliases(self):
        self.assertIn("zero-qwen3-q5:latest", ROOT_README)
        self.assertIn("zero-qwen3-f16:latest", ROOT_README)
        self.assertNotIn("openzeroqwen3-q5:latest", ROOT_README)
        self.assertNotIn("openzeroqwen3-f16:latest", ROOT_README)


if __name__ == "__main__":
    unittest.main()
