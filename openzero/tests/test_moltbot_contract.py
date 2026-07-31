import pathlib
import unittest


OPENZERO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MOLTBOT_SOURCE = (OPENZERO_ROOT / "moltbot" / "moltbot.js").read_text(encoding="utf-8")
APP_SOURCE = (OPENZERO_ROOT / "brain" / "app.py").read_text(encoding="utf-8")


def source_slice(start, end):
    start_index = MOLTBOT_SOURCE.index(start)
    return MOLTBOT_SOURCE[start_index:MOLTBOT_SOURCE.index(end, start_index)]


def app_source_slice(start, end):
    start_index = APP_SOURCE.index(start)
    return APP_SOURCE[start_index:APP_SOURCE.index(end, start_index)]


class MoltbotContractTests(unittest.TestCase):
    def test_moltbot_binds_to_loopback_and_uses_ephemeral_elements(self):
        self.assertIn("app.listen(3000, '127.0.0.1'", MOLTBOT_SOURCE)
        self.assertIn("snapshotId = crypto.randomUUID()", MOLTBOT_SOURCE)
        self.assertIn("requireInspectedElement", MOLTBOT_SOURCE)
        self.assertIn("Page snapshot is stale", MOLTBOT_SOURCE)
        self.assertNotIn("waitForSelector(selector", MOLTBOT_SOURCE)
        self.assertNotIn("activePage.click(selector", MOLTBOT_SOURCE)
        self.assertNotIn("element.value", MOLTBOT_SOURCE)

    def test_sensitive_controls_and_unconfirmed_risky_clicks_are_blocked(self):
        self.assertIn("blocked_sensitive", MOLTBOT_SOURCE)
        self.assertIn("Moltbot blocks", MOLTBOT_SOURCE)
        self.assertIn("requires fresh confirmation", MOLTBOT_SOURCE)
        self.assertIn("Text is limited to 4,000 characters", MOLTBOT_SOURCE)
        self.assertIn("element.type || element.getAttribute('type')", MOLTBOT_SOURCE)
        self.assertIn("form_associated", MOLTBOT_SOURCE)
        self.assertIn("isSubmitControl", MOLTBOT_SOURCE)
        self.assertIn("app.post('/release'", MOLTBOT_SOURCE)
        self.assertIn("livePolicyDescriptor", MOLTBOT_SOURCE)
        self.assertIn("enforceLiveElementPolicy", MOLTBOT_SOURCE)

    def test_every_verified_action_returns_a_post_action_inspection(self):
        self.assertGreaterEqual(MOLTBOT_SOURCE.count("const next = await inspectPage"), 2)
        self.assertIn("POST-ACTION INSPECTION", APP_SOURCE)
        self.assertIn('"moltbot_click"', APP_SOURCE)
        self.assertIn('"moltbot_type"', APP_SOURCE)
        self.assertIn("moltbot_element_descriptor", APP_SOURCE)

    def test_browser_routes_require_one_32_hex_run_owner(self):
        self.assertIn("let ownerRunId = ''", MOLTBOT_SOURCE)
        self.assertIn("const RUN_ID_RE = /^[a-f0-9]{32}$/i", MOLTBOT_SOURCE)
        self.assertIn("A valid 32-character hexadecimal run_id is required.", MOLTBOT_SOURCE)

        goto_route = source_slice("app.post('/goto'", "app.get('/text'")
        self.assertIn("requestRunId(req)", goto_route)
        self.assertIn("claimBrowserOwner(runId)", goto_route)

        protected_routes = [
            source_slice("app.post('/inspect'", "app.get('/element"),
            source_slice("app.get('/element", "app.get('/links'"),
            source_slice("app.post('/click'", "app.post('/type'"),
            source_slice("app.post('/type'", "app.listen("),
        ]
        for route in protected_routes:
            self.assertIn("requireBrowserOwner(req)", route)

    def test_release_detaches_owner_and_snapshot_before_async_disposal(self):
        self.assertIn("let ownerGeneration = 0", MOLTBOT_SOURCE)
        self.assertIn("owner_generation: ownerGeneration", MOLTBOT_SOURCE)
        detach = source_slice("function detachBrowserOwner", "function classifyElement")
        self.assertIn("const runId = requireBrowserOwner(req)", detach)
        self.assertIn("const handles = detachElementRegistry()", detach)
        self.assertIn("ownerRunId = ''", detach)
        self.assertIn("ownerGeneration += 1", detach)
        self.assertNotIn("await ", detach)

        release_route = source_slice("app.post('/release'", "app.post('/goto'")
        detach_index = release_route.index("const release = detachBrowserOwner(req)")
        await_index = release_route.index("await disposeElementHandles(release.handles)")
        self.assertLess(detach_index, await_index)
        self.assertNotIn("ownerRunId = ''", release_route)
        self.assertIn("released_generation: release.released_generation", release_route)
        self.assertIn("owner_reassigned: Boolean(ownerRunId)", release_route)

    def test_status_exposes_current_browser_owner(self):
        status_route = source_slice("app.get('/status'", "app.post('/release'")
        self.assertIn("owner_run_id: ownerRunId", status_route)
        self.assertIn("owner_generation: ownerGeneration", status_route)

    def test_confirmed_actions_reject_material_descriptor_drift(self):
        material_fields = [
            "tag",
            "role",
            "type",
            "name",
            "form_associated",
            "label",
            "text",
            "href",
            "disabled",
            "risk",
            "sensitive_kind",
        ]
        fields_source = source_slice(
            "const MATERIAL_DESCRIPTOR_FIELDS",
            "function publicPolicyDescriptor",
        )
        for field in material_fields:
            self.assertIn(f"'{field}'", fields_source)

        self.assertIn("function requireStableDescriptor", MOLTBOT_SOURCE)
        self.assertIn("inspected[field] !== live[field]", MOLTBOT_SOURCE)
        self.assertIn("changed materially; inspect the page again", MOLTBOT_SOURCE)
        self.assertIn("name: cleanText(descriptor.name, 120)", MOLTBOT_SOURCE)
        self.assertGreaterEqual(
            MOLTBOT_SOURCE.count(
                "const stableDescriptor = requireStableDescriptor(descriptor, liveDescriptor)"
            ),
            2,
        )
        self.assertGreaterEqual(MOLTBOT_SOURCE.count("acted_element: actedElement"), 2)

    def test_post_dispatch_failures_are_explicitly_ambiguous_and_not_replay_safe(self):
        helper = source_slice("async function ambiguousActionError", "async function pageLinks")
        detach_index = helper.index("const handles = detachElementRegistry()")
        await_index = helper.index("await disposeElementHandles(handles)")
        self.assertLess(detach_index, await_index)
        for marker in [
            "dispatched: true",
            "outcome_ambiguous: true",
            "retry_safe: false",
            "requires_reinspection: true",
            "acted_element:",
            "before_hash:",
            "initial_after_hash:",
            "after_hash:",
            "verification_signals:",
            "state_changed: false",
        ]:
            self.assertIn(marker, helper)
        self.assertIn("proof_error: true", helper)
        self.assertGreaterEqual(MOLTBOT_SOURCE.count("return ambiguousActionError(res"), 2)
        self.assertGreaterEqual(MOLTBOT_SOURCE.count("outcome_ambiguous: !stateChanged"), 2)
        self.assertGreaterEqual(MOLTBOT_SOURCE.count("dispatched: false"), 3)

    def test_click_proof_requires_a_target_scoped_causal_signal(self):
        click_route = source_slice("app.post('/click'", "app.post('/type'")
        self.assertIn("event.isTrusted === true", MOLTBOT_SOURCE)
        self.assertIn("startTrustedClickObservation(handle)", click_route)
        self.assertIn(
            "trustedTargetClick && pageProof.stable_page_change",
            click_route,
        )
        self.assertIn("click_event_page_change: targetScopedPageChange", click_route)

        state_start = click_route.index("const stateChanged = Boolean(")
        state_end = click_route.index(");", state_start) + 2
        state_expression = click_route[state_start:state_end]
        self.assertIn("targetScopedPageChange", state_expression)
        self.assertIn("targetStateChanged", state_expression)
        self.assertIn("navigation_observed", state_expression)
        self.assertNotIn("stable_page_change", state_expression)
        self.assertNotIn("Object.values", state_expression)

    def test_type_proof_baselines_after_focus_and_detects_same_length_replacement(self):
        type_route = source_slice("app.post('/type'", "app.listen(")
        dispatch_index = type_route.index("dispatched = true")
        focus_index = type_route.index("await handle.focus()")
        url_baseline_index = type_route.index("const beforeUrl = activePage.url()")
        page_hash_baseline_index = type_route.index(
            "beforeHash = pageStateHash(await pageStateDigest(activePage))"
        )
        target_baseline_index = type_route.index(
            "const beforeTargetState = await targetStateDigest(handle)"
        )
        value_baseline_index = type_route.index(
            "beforeValueState = await captureFieldValueState(handle)"
        )
        typing_index = type_route.index("await activePage.keyboard.type")
        self.assertLess(dispatch_index, focus_index)
        self.assertLess(focus_index, url_baseline_index)
        self.assertLess(url_baseline_index, page_hash_baseline_index)
        self.assertLess(page_hash_baseline_index, target_baseline_index)
        self.assertLess(target_baseline_index, value_baseline_index)
        self.assertLess(value_baseline_index, typing_index)

        capture = source_slice("async function captureFieldValueState", "async function safeFieldValueChanged")
        compare = source_slice("async function safeFieldValueChanged", "function inputSha256")
        self.assertIn("evaluateHandle", capture)
        self.assertIn("return {", capture)
        self.assertIn("current !== beforeState.value", compare)
        self.assertIn("value_changed: valueChanged", type_route)
        self.assertIn("value_length_changed: valueLengthChanged", type_route)

        state_start = type_route.index("const stateChanged = Boolean(")
        state_end = type_route.index(");", state_start) + 2
        state_expression = type_route[state_start:state_end]
        self.assertIn("valueChanged", state_expression)
        self.assertNotIn("valueLengthChanged", state_expression)
        self.assertNotIn("stable_page_change", state_expression)

    def test_action_responses_keep_structured_privacy_safe_proof(self):
        self.assertIn("pageStateDigest", MOLTBOT_SOURCE)
        self.assertIn("targetStateDigest", MOLTBOT_SOURCE)
        self.assertIn("class_name: classTokens.join(' ')", MOLTBOT_SOURCE)
        self.assertIn("checked:", MOLTBOT_SOURCE)
        self.assertIn("selected_index:", MOLTBOT_SOURCE)
        self.assertIn("aria_checked:", MOLTBOT_SOURCE)
        self.assertGreaterEqual(MOLTBOT_SOURCE.count("before_hash: beforeHash"), 2)
        self.assertGreaterEqual(MOLTBOT_SOURCE.count("after_hash: pageProof.after_hash"), 2)
        self.assertGreaterEqual(
            MOLTBOT_SOURCE.count("verification_signals: verificationSignals"),
            2,
        )
        self.assertGreaterEqual(MOLTBOT_SOURCE.count("state_changed: stateChanged"), 2)
        self.assertIn("input_length: inputLength", MOLTBOT_SOURCE)
        self.assertIn("input_sha256: inputDigest", MOLTBOT_SOURCE)
        self.assertIn(".createHash('sha256')", MOLTBOT_SOURCE)
        self.assertIn("Reflect.get(element, 'value')", MOLTBOT_SOURCE)
        self.assertNotIn("element.value", MOLTBOT_SOURCE)
        self.assertNotIn("input_value", MOLTBOT_SOURCE)
        self.assertNotIn("before_value", MOLTBOT_SOURCE)
        self.assertNotIn("after_value", MOLTBOT_SOURCE)

    def test_app_halts_ambiguous_dispatch_without_clearing_inflight_state(self):
        result_helper = app_source_slice(
            "def moltbot_action_result(",
            "def action_confirmation_consumed",
        )
        self.assertIn("MOLTBOT ACTION OUTCOME UNKNOWN", result_helper)
        self.assertIn("data.get(\"dispatched\") is True", result_helper)
        self.assertIn("data.get(\"outcome_ambiguous\") is True", result_helper)
        self.assertIn("ambiguous=True", result_helper)
        self.assertIn("dispatched=True", result_helper)

        run_loop = app_source_slice(
            "def execute_autonomous_run(",
            "def _autonomous_worker_entry",
        )
        self.assertIn("checkpoint_action_result(", run_loop)
        self.assertIn(
            'clear_inflight=not bool(action.get("ambiguous_action"))', run_loop
        )
        self.assertIn("browser_action_outcome_unverified", run_loop)
        self.assertLess(
            run_loop.index('if action.get("ambiguous_action"):'),
            run_loop.index('if action.get("approval_required"):'),
        )

    def test_app_persists_structured_run_bound_action_ledger(self):
        result_helper = app_source_slice(
            "def moltbot_action_result(",
            "def action_confirmation_consumed",
        )
        for marker in [
            "hashes_valid",
            "causal_signal",
            "element_bound",
            "inspection_bound",
            '"verification_signals": verification_signals',
            '"before_hash": before_hash',
            '"initial_after_hash": initial_after_hash',
            '"after_hash": after_hash',
            'evidence["typed_text_length"]',
            'evidence["typed_text_digest"]',
        ]:
            self.assertIn(marker, result_helper)

        run_loop = app_source_slice(
            "def execute_autonomous_run(",
            "def _autonomous_worker_entry",
        )
        self.assertIn('evidence["browser_actions"] = action_ledger[-16:]', run_loop)
        self.assertIn('ledger_entry["owner_run_id"] = str(run_id)', run_loop)
        self.assertIn('"typed_text_length"', run_loop)
        self.assertIn('"typed_text_digest"', run_loop)

    def test_app_uses_atomic_run_routes_and_nonblocking_browser_dispatch(self):
        approve_route = app_source_slice(
            "def approve_autonomous_run(",
            '@app.route("/api/agent/runs/<run_id>/resume"',
        )
        self.assertIn("AUTONOMOUS_RUN_STORE.approve_and_queue(", approve_route)
        self.assertNotIn("AUTONOMOUS_RUN_STORE.approve(", approve_route)

        resume_route = app_source_slice(
            "def resume_autonomous_run(",
            '@socketio.on("user_message")',
        )
        self.assertIn("AUTONOMOUS_RUN_STORE.queue_for_resume(", resume_route)

        worker_start = app_source_slice(
            "def start_autonomous_worker(",
            "def start_next_queued_run",
        )
        self.assertIn("needs_browser_lane", worker_start)
        self.assertIn("not acquire_moltbot_run(run_id)", worker_start)
        dispatcher = app_source_slice(
            "def start_next_queued_run",
            "def recover_autonomous_runs",
        )
        self.assertIn("and not state.get(\"revoked\")", dispatcher)
        self.assertIn("and not state.get(\"stop_requested\")", dispatcher)
        self.assertNotIn("break", dispatcher)


if __name__ == "__main__":
    unittest.main()
