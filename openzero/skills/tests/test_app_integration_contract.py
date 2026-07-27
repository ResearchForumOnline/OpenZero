from __future__ import annotations

import ast
import unittest
from pathlib import Path


APP_PATH = Path(__file__).resolve().parents[2] / "brain" / "app.py"
APP_SOURCE = APP_PATH.read_text(encoding="utf-8")
APP_TREE = ast.parse(APP_SOURCE)


def function_source(name: str) -> str:
    for node in ast.walk(APP_TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(APP_SOURCE, node) or ""
    raise AssertionError(f"Function not found: {name}")


class AppSkillIntegrationContractTests(unittest.TestCase):
    def test_static_placeholder_catalog_was_replaced(self):
        self.assertIn("SKILL_CATALOG = legacy_skill_catalog()", APP_SOURCE)
        self.assertNotIn('"query":"search terms"', APP_SOURCE.replace(" ", ""))

    def test_progressive_skill_api_and_prompt_are_wired(self):
        self.assertIn('@app.route("/api/skills/<skill_id>"', APP_SOURCE)
        step_prompt = function_source("autonomous_step_prompt")
        self.assertIn("runtime_skill_context", step_prompt)
        self.assertIn("SELECTED SKILL CONTRACTS", step_prompt)

    def test_run_creation_selects_skills_and_clamps_budgets(self):
        for function_name in ("create_autonomous_run", "handle_message"):
            source = function_source(function_name)
            self.assertIn("select_skill_ids", source)
            self.assertIn("runtime_skill_budgets", source)
            self.assertIn("skill_ids=skill_ids", source)

    def test_skill_permission_precedes_existing_action_gate(self):
        gate = function_source("autonomous_action_gate")
        self.assertIn("tool_permission_decision", gate)
        self.assertIn("OPENZERO_AUTOMATION_ENABLED", gate)
        self.assertIn("action_policy(action_name, payload)", gate)
        self.assertLess(gate.index("tool_permission_decision"), gate.index("action_policy(action_name, payload)"))

    def test_all_legacy_action_tags_pass_through_the_gate(self):
        runner = function_source("run_tool_action")
        for action in ("bash", "osint", "browse", "speak"):
            tag_position = runner.index(f'r"<{action}>')
            next_position = runner.find("autonomous_action_gate(", tag_position)
            self.assertGreater(next_position, tag_position, action)

    def test_upload_uses_bounded_document_extraction(self):
        upload = function_source("upload_file")
        self.assertIn("extract_document(save_path)", upload)
        self.assertIn("DocumentExtractionError", upload)
        self.assertNotIn('errors="ignore"', upload)
        self.assertIn("indexed", upload)


if __name__ == "__main__":
    unittest.main()
