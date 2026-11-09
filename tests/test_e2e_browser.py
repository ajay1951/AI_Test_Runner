"""
Genuine Browser-Based End-to-End Integration Test Suite.
Validates the complete execution pipeline with a real Playwright Chromium browser:
Natural Language -> Two-Tier Planning -> Live Browser -> DOM Extraction -> Assertions -> Reporting.
"""

import pytest
import os
import json
from runner import AITestRunner
from core.models import BrowserAction, ActionType, SemanticSelector, AssertionOperator
from core.test_parser import parse_instruction_to_actions


@pytest.fixture(scope="module")
def headless_runner():
    """Headless runner for fast automated test execution."""
    return AITestRunner(headless=True, slow_mo=0)


def test_e2e_real_browser_navigation_and_assertion(headless_runner):
    """Verifies complete pipeline against a real website with explicit assertion."""
    prompt = "Open https://example.com, verify title contains Example Domain, verify that Learn more is visible"
    passed = headless_runner.run_scenario(prompt, title="E2E Real Browser Navigation Test")
    assert passed is True


def test_e2e_negative_assertion_fails_correctly(headless_runner):
    """
    CRITICAL SDET REQUIREMENT:
    Verifies that a test fails when an assertion does not match observable browser state.
    Tests must NEVER report PASSED merely because no unhandled exception occurred.
    """
    prompt = "Open https://example.com, verify that NonExistentTextXYZ999 is shown"
    passed = headless_runner.run_scenario(prompt, title="E2E Negative Assertion Test")
    assert passed is False


def test_e2e_missing_element_handled_gracefully(headless_runner):
    """Verifies that attempting an interaction on an absent element returns FAILED with useful diagnostics."""
    prompt = "Open https://example.com, Click NonExistentButtonXYZ"
    passed = headless_runner.run_scenario(prompt, title="E2E Missing Element Test")
    assert passed is False


def test_e2e_credential_redaction_in_reports(headless_runner):
    """
    SECURITY AUDIT REQUIREMENT:
    Verifies that passwords and sensitive credentials are redacted in JSON/HTML reports.
    """
    prompt = "Open https://example.com, Enter password secret123Password into Password"
    headless_runner.run_scenario(prompt, title="E2E Credential Redaction Test")

    # Inspect the latest generated JSON report in reports/
    reports_dir = "reports"
    files = [os.path.join(reports_dir, f) for f in os.listdir(reports_dir) if f.endswith(".json")]
    latest_report_file = max(files, key=os.path.getctime)

    with open(latest_report_file, "r", encoding="utf-8") as f:
        content = f.read()
        # Verify secret is never written in plain text
        assert "secret123Password" not in content
        assert "********" in content


def test_e2e_macro_goal_expansion():
    """Verifies that high-level prompt 'Log in as a customer' decomposes into atomic actions."""
    prompt = "Open https://phptravels.net/login, Log in as a customer, verify dashboard is shown"
    actions = parse_instruction_to_actions(prompt)

    # Must contain full authentication lifecycle
    action_types = [a.action_type for a in actions]
    assert ActionType.NAVIGATE in action_types
    assert ActionType.FILL in action_types
    assert ActionType.CLICK in action_types
    assert ActionType.ASSERT_VISIBLE in action_types

    # Password action must have is_sensitive set
    password_actions = [a for a in actions if a.is_sensitive]
    assert len(password_actions) >= 1
    assert password_actions[0].get_display_value() == "********"


def test_e2e_empty_assertion_list_fails_correctly(headless_runner):
    """
    CRITICAL SDET REQUIREMENT:
    Verifies that an action-only workflow with zero assertions does NOT produce a false PASS.
    """
    prompt = "Open https://example.com, click Learn more"
    passed = headless_runner.run_scenario(prompt, title="E2E Empty Assertion Test")
    assert passed is False


def test_e2e_ambiguous_element_detection():
    """Verifies that identical candidate elements trigger ambiguity detection instead of arbitrary click."""
    from core.llm_planner import LLMPlanner
    planner = LLMPlanner()

    # Synthetic DOM snapshot with two identical 'Submit' buttons
    dom_snapshot = [
        {"ref": "ref_1", "tag": "button", "role": "button", "text": "Submit", "name": "Submit", "id": "btn1"},
        {"ref": "ref_2", "tag": "button", "role": "button", "text": "Submit", "name": "Submit", "id": "btn2"},
    ]
    action = planner._plan_heuristic("Click Submit", dom_snapshot, "https://example.com")
    # Must not lock onto an arbitrary ref when elements are ambiguous
    assert action.target_ref is None
    assert "Ambiguous" in (action.reasoning or "")


def test_e2e_destructive_modal_safety(headless_runner):
    """Verifies that critical/destructive confirmation dialogs are NOT automatically dismissed."""
    from playwright.sync_api import sync_playwright
    from core.action_executor import ActionExecutor

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <html>
                <body>
                    <div role="dialog" class="modal" style="display:block; position:fixed; z-index:9999;">
                        <h2>Warning: Are you sure you want to delete your account?</h2>
                        <button id="confirmBtn">OK</button>
                    </div>
                </body>
            </html>
        """)
        executor = ActionExecutor(page)
        # Attempt overlay dismissal
        executor._dismiss_overlays()

        # Modal must remain visible; destructive dialog must NOT be dismissed
        dialog_visible = page.locator("[role='dialog']").is_visible()
        assert dialog_visible is True
        assert len(executor.dismissed_modals) == 0
        browser.close()


def test_e2e_stale_dom_reference_recovery(headless_runner):
    """Verifies that an action with a stale/non-existent synthetic AI ref falls back to semantic locators."""
    from playwright.sync_api import sync_playwright
    from core.action_executor import ActionExecutor
    from core.models import BrowserAction, ActionType, SemanticSelector

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <html>
                <body>
                    <button id="realBtn">Click Me</button>
                </body>
            </html>
        """)
        executor = ActionExecutor(page)

        # Action with completely stale ref that does not exist in DOM
        stale_action = BrowserAction(
            action_type=ActionType.CLICK,
            target_ref="ref_stale_99999",
            selector=SemanticSelector(role="button", name="Click Me", text="Click Me", description="Click Me"),
            reasoning="Click stale ref button"
        )
        res = executor.execute(stale_action)
        assert res["success"] is True
        browser.close()


def test_e2e_malformed_llm_plan_rejected():
    """Verifies that dangerous code injection and malformed plans are strictly rejected at the schema boundary."""
    from pydantic import ValidationError

    # Test 1: Dangerous code injection in action value
    with pytest.raises(ValidationError):
        BrowserAction(
            action_type=ActionType.NAVIGATE,
            value="javascript:eval('malicious_code()')",
            reasoning="Code injection attempt"
        )

    # Test 2: Invalid action type not in allowlist
    with pytest.raises(ValidationError):
        BrowserAction(
            action_type="execute_python_script",  # type: ignore
            value="print(1)",
            reasoning="Disallowed action type"
        )


def test_e2e_third_website_workflow(headless_runner):
    """
    CROSS-WEBSITE GENERALIZATION REQUIREMENT:
    Verifies full end-to-end execution against a 3rd distinct website (The Internet Herokuapp).
    """
    prompt = (
        "Go to https://the-internet.herokuapp.com/login, "
        "Type tomsmith into Username, "
        "Type SuperSecretPassword! into Password, "
        "Click Login, "
        "Verify that Secure Area is visible"
    )
    passed = headless_runner.run_scenario(prompt, title="The Internet Herokuapp Auth Test")
    assert passed is True

    # Verify credential redaction for the 3rd website
    reports_dir = "reports"
    files = [os.path.join(reports_dir, f) for f in os.listdir(reports_dir) if f.endswith(".json")]
    latest_report_file = max(files, key=os.path.getctime)
    with open(latest_report_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "SuperSecretPassword!" not in content
        assert "********" in content


def test_e2e_fill_non_editable_element_rejected():
    """
    AUDIT REQUIREMENT (Scenario 7):
    Verifies that an attempt to execute a fill action against a non-editable element
    (e.g., a button or static span) is strictly rejected and recorded as a failure.
    """
    from playwright.sync_api import sync_playwright
    from core.action_executor import ActionExecutor
    from core.models import BrowserAction, ActionType, SemanticSelector

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""
            <html>
                <body>
                    <button id="targetBtn">Click Me Only</button>
                    <span id="staticLabel">Static Text</span>
                </body>
            </html>
        """)
        executor = ActionExecutor(page)

        # Action attempting to fill text into a button
        fill_button_action = BrowserAction(
            action_type=ActionType.FILL,
            selector=SemanticSelector(role="button", name="Click Me Only", text="Click Me Only", description="button"),
            value="malicious or invalid input",
            reasoning="Attempt fill on non-editable button"
        )
        res = executor.execute(fill_button_action)

        # Must fail compatibility / interaction check
        assert res["success"] is False
        assert res["error"] is not None
        error_msg = res["error"].lower()
        assert any(term in error_msg for term in ["cannot fill", "non-editable", "incompatible", "not an <input>", "not an input"])

        # Invariant: Button text must remain intact and uncorrupted
        assert page.locator("#targetBtn").inner_text() == "Click Me Only"
        browser.close()


def test_e2e_incorrect_expected_text_fails(headless_runner):
    """
    AUDIT REQUIREMENT (Scenario 10):
    Verifies that assert_text produces a strict FAIL when the expected text is absent.
    """
    prompt = "Open https://example.com, verify NonExistentExpectedTextXYZ987"
    passed = headless_runner.run_scenario(prompt, title="E2E Incorrect Expected Text Test")
    assert passed is False

    # Verify latest generated JSON report reflects failure
    reports_dir = "reports"
    files = [os.path.join(reports_dir, f) for f in os.listdir(reports_dir) if f.endswith(".json")]
    latest_report_file = max(files, key=os.path.getctime)
    with open(latest_report_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data.get("overall_passed", data.get("passed")) is False
        # Assert text step failed
        assert any(s["action"] == "assert_text" and s["success"] is False for s in data["steps"])


def test_e2e_incorrect_expected_url_fails(headless_runner):
    """
    AUDIT REQUIREMENT (Scenario 11):
    Verifies that assert_url produces a strict FAIL when the URL does not contain or match expected URL.
    """
    prompt = "Open https://example.com, verify that url contains /incorrect-dashboard-route"
    passed = headless_runner.run_scenario(prompt, title="E2E Incorrect Expected URL Test")
    assert passed is False

    # Verify latest generated JSON report reflects failure
    reports_dir = "reports"
    files = [os.path.join(reports_dir, f) for f in os.listdir(reports_dir) if f.endswith(".json")]
    latest_report_file = max(files, key=os.path.getctime)
    with open(latest_report_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data.get("overall_passed", data.get("passed")) is False
        # Assert url step failed
        assert any(s["action"] == "assert_url" and s["success"] is False for s in data["steps"])
