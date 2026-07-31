from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SKILLS_ROOT = Path(__file__).resolve().parents[1]
OPENZERO_ROOT = SKILLS_ROOT.parent
if str(OPENZERO_ROOT) not in sys.path:
    sys.path.insert(0, str(OPENZERO_ROOT))

from skills.catalog import (  # noqa: E402
    CatalogError,
    budget_decision,
    get_skill_detail,
    legacy_skill_catalog,
    permission_decision,
    runtime_skill_budgets,
    search_catalog,
    select_skill_ids,
    skill_catalog_payload,
    tool_permission_decision,
)
from skills.validate_catalog import validate_catalog  # noqa: E402


class CatalogTests(unittest.TestCase):
    def test_catalog_validates(self):
        self.assertEqual(validate_catalog(SKILLS_ROOT), [])

    def test_metadata_load_does_not_eagerly_include_instructions(self):
        payload = skill_catalog_payload()
        self.assertEqual(payload["count"], 7)
        self.assertTrue(all("instructions" not in item for item in payload["skills"]))

    def test_progressive_disclosure_loads_only_requested_reference(self):
        basic = get_skill_detail("web-research")
        self.assertIn("# Web research", basic["instructions"])
        self.assertEqual(basic["loaded_references"], {})
        detailed = get_skill_detail("web-research", ["references/source-verification.md"])
        self.assertIn("Source verification", detailed["loaded_references"]["references/source-verification.md"])

    def test_undeclared_reference_is_rejected(self):
        with self.assertRaises(CatalogError):
            get_skill_detail("web-research", ["../catalog.json"])

    def test_search_ranking_is_stable_and_relevant(self):
        first = [item["id"] for item in search_catalog("latest pricing sources")]
        second = [item["id"] for item in search_catalog("latest pricing sources")]
        self.assertEqual(first, second)
        self.assertEqual(first[0], "web-research")
        self.assertEqual(search_catalog("ssh deploy service")[0]["id"], "server-ops")
        self.assertEqual(search_catalog("broken docx upload")[0]["id"], "document-reading")
        self.assertEqual(search_catalog("create an OpenZero skill manifest")[0]["id"], "files-code")
        self.assertEqual(search_catalog("give OpenZero better skills")[0]["id"], "files-code")

    def test_plain_conversation_does_not_bind_unrelated_skills(self):
        self.assertEqual(
            select_skill_ids("What is OpenZero? Answer in one short sentence."),
            [],
        )
        self.assertEqual(select_skill_ids("hello"), [])
        self.assertEqual(
            select_skill_ids("Browse https://zmail.my using the browser and return its title."),
            ["browser-tabs"],
        )

    def test_permission_contract(self):
        skill = get_skill_detail("files-code")
        self.assertEqual(permission_decision(skill, "filesystem.read")["decision"], "allow")
        self.assertEqual(permission_decision(skill, "filesystem.write")["decision"], "confirm")
        self.assertEqual(
            permission_decision(skill, "filesystem.write", task_authorized=True)["decision"],
            "allow",
        )
        self.assertEqual(permission_decision(skill, "destructive.delete", task_authorized=True)["decision"], "confirm")
        self.assertEqual(permission_decision(skill, "external.publish")["decision"], "deny")

    def test_tool_permission_uses_task_scope_and_ssh_risk(self):
        allowed = tool_permission_decision(
            ["server-ops"],
            "ssh_command",
            {"command": "systemctl restart openzero"},
            "deploy the update and restart OpenZero",
        )
        self.assertEqual(allowed["decision"], "allow")
        self.assertEqual(allowed["capability"], "remote.write")
        read_only = tool_permission_decision(
            ["server-ops"],
            "ssh_command",
            {"command": "systemctl status openzero --no-pager"},
            "check the server",
        )
        self.assertEqual(read_only["decision"], "allow")
        self.assertEqual(read_only["capability"], "remote.read")
        copied = tool_permission_decision(
            ["server-ops"],
            "scp_get",
            {"source": "/tmp/report", "destination": "report"},
            "download and copy the report",
        )
        self.assertEqual(copied["decision"], "allow")
        self.assertEqual(copied["capability"], "filesystem.write,remote.read")
        not_selected = tool_permission_decision(
            ["web-research"],
            "write_file",
            {"path": "report.md"},
            "write a report",
        )
        self.assertEqual(not_selected["decision"], "deny")

        browser_click = tool_permission_decision(
            ["browser-tabs"],
            "moltbot_click",
            {"snapshot_id": "snap", "element_id": "e1"},
            "browse the site and click Open my workspace",
        )
        self.assertEqual(browser_click["decision"], "allow")
        self.assertEqual(browser_click["capability"], "browser.interact")

        browser_choose = tool_permission_decision(
            ["browser-tabs"],
            "moltbot_click",
            {"snapshot_id": "snap", "element_id": "e1"},
            "browse the site and choose Open my workspace",
        )
        self.assertEqual(browser_choose["decision"], "allow")
        self.assertEqual(browser_choose["capability"], "browser.interact")

        browser_enter = tool_permission_decision(
            ["browser-tabs"],
            "moltbot_type",
            {"snapshot_id": "snap", "element_id": "e2", "text": "hello"},
            "browse the site and enter hello in the search field",
        )
        self.assertEqual(browser_enter["decision"], "allow")
        self.assertEqual(
            browser_enter["capability"],
            "browser.type_nonsensitive",
        )

        ambiguous_open = tool_permission_decision(
            ["browser-tabs"],
            "moltbot_click",
            {"snapshot_id": "snap", "element_id": "e1"},
            "browse the site and open my workspace",
        )
        self.assertEqual(ambiguous_open["decision"], "confirm")

        browse_only = tool_permission_decision(
            ["browser-tabs"],
            "moltbot_click",
            {"snapshot_id": "snap", "element_id": "e1"},
            "browse zmail.my and only report the title",
        )
        self.assertEqual(browse_only["decision"], "confirm")

        explicitly_forbidden = tool_permission_decision(
            ["browser-tabs"],
            "moltbot_click",
            {"snapshot_id": "snap", "element_id": "e1"},
            "browse the page; do not click or type anything",
        )
        self.assertEqual(explicitly_forbidden["decision"], "confirm")

    def test_budget_stops_at_boundary(self):
        self.assertEqual(
            budget_decision(["web-research"], {"steps": 7, "tool_calls": 4, "elapsed_seconds": 10, "output_chars": 20})[
                "decision"
            ],
            "continue",
        )
        self.assertEqual(
            budget_decision(["web-research"], {"steps": 8, "tool_calls": 4, "elapsed_seconds": 10, "output_chars": 20})[
                "decision"
            ],
            "stop",
        )
        budgets = runtime_skill_budgets(
            ["web-research"],
            {"max_steps": 99, "max_tool_calls": 2, "max_elapsed_seconds": 999},
        )
        self.assertEqual(budgets["max_steps"], 8)
        self.assertEqual(budgets["max_tool_calls"], 2)
        self.assertEqual(budgets["max_elapsed_seconds"], 240)

        ultra = runtime_skill_budgets(
            ["browser-tabs"],
            {"max_steps": 99, "max_tool_calls": 99, "max_elapsed_seconds": 9999},
            profile="ultra",
        )
        self.assertEqual(24, ultra["max_steps"])
        self.assertEqual(24, ultra["max_tool_calls"])
        self.assertEqual(1200, ultra["max_elapsed_seconds"])

    def test_legacy_shape_remains_available(self):
        catalog = legacy_skill_catalog()
        self.assertEqual(len(catalog), 7)
        self.assertEqual(set(catalog[0]), {"id", "name", "triggers", "tool", "notes"})
        rendered = json.dumps(catalog).lower()
        self.assertNotIn('"query":"search terms"', rendered)
        self.assertNotIn("<tool>", rendered)

    def test_validator_detects_invalid_budget(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "skills"
            shutil.copytree(SKILLS_ROOT, copied, ignore=shutil.ignore_patterns("__pycache__"))
            manifest_path = copied / "web-research" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["budgets"]["max_steps"] = 0
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate_catalog(copied)
            self.assertTrue(any("max_steps" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
