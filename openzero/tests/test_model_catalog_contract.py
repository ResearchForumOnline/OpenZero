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
        ):
            self.assertIn(alias, APP_SOURCE)
            self.assertIn(alias, PANEL_SOURCE)
        self.assertNotIn('"openzero-qwen-q5"', APP_SOURCE)
        self.assertNotIn('"openzero-qwen-f16"', APP_SOURCE)
        self.assertNotIn("OPENZERO QWEN3", PANEL_SOURCE)
        self.assertNotIn("FUSION", PANEL_SOURCE.upper())
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

    def test_verified_custom_imports_are_visible_without_restoring_rejected_models(self):
        self.assertIn("def registered_custom_model_aliases()", APP_SOURCE)
        self.assertIn("candidates.extend(sorted(registered_custom_model_aliases()", APP_SOURCE)
        self.assertIn("visible_files.update(registered_custom_model_files())", APP_SOURCE)
        self.assertIn("registry = registered_custom_models()", APP_SOURCE)
        self.assertIn("installed_alias = custom_model_alias(alias)", APP_SOURCE)
        for rejected in (
            '"zero-qwen3-f16"',
            '"zero-qwen3-q5"',
            '"hf.co/shafire/openzero-fusion-qwen3-4b-agentic-gguf"',
            '"hf.co/shafire/openzero-qwen3-1.7b-agentic-gguf"',
        ):
            self.assertIn(rejected, APP_SOURCE)

    def test_model_roles_and_api_recommendation_are_coherent(self):
        self.assertIn('"role": "compatibility"', APP_SOURCE)
        self.assertNotIn('"role": "default"', APP_SOURCE[: APP_SOURCE.index("os.makedirs(UPLOAD_FOLDER")])
        self.assertIn('"recommended_model": profile["recommended_model"]', APP_SOURCE)
        self.assertIn('"active_model": resolution["model"]', APP_SOURCE)
        self.assertIn("Compatibility fallback", ROOT_README)
        self.assertNotIn("The Super Panel also shows two optional Qwen3", ROOT_README)

    def test_operator_copy_does_not_restore_the_retired_gemma_default(self):
        manual = (OPENZERO_ROOT / "templates" / "manual.html").read_text(encoding="utf-8")
        for stale_copy in (
            "OpenZero Gemma remains the default",
            "Gemma/Ollama lane",
            "built-in Gemma 4 install buttons",
            "Gemma model store",
        ):
            self.assertNotIn(stale_copy, APP_SOURCE)
            self.assertNotIn(stale_copy, PANEL_SOURCE)
            self.assertNotIn(stale_copy, manual)


if __name__ == "__main__":
    unittest.main()
