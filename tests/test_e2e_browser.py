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

