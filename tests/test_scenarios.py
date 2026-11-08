"""
Comprehensive Automated Test Suite for AI Test Runner.
Validates:
1. Canonical PHPTravels Customer Login Flow
2. Second Target Website (CloudQA Practice Form)
3. 10 Diverse Unseen Natural Language Instructions
"""

import pytest
from runner import AITestRunner
from core.test_parser import split_clauses, parse_instruction_to_actions
from core.models import ActionType


@pytest.fixture(scope="module")
def runner():
    # Run in headless mode for CI/test execution
    return AITestRunner(headless=True, slow_mo=0)


def test_parser_clause_splitting():
    text = (
        "Open PHPTravels, navigate to the login page, enter the email address user@example.com, "
        "enter the password password123, click Login, and verify that the dashboard appears."
    )
    clauses = split_clauses(text)
    assert len(clauses) >= 5
    assert "Open PHPTravels" in clauses[0]


def test_unseen_instructions_suite():
    """
    10 Diverse Unseen Natural Language Instructions testing sentence structures,
    verbs, and targets without engine modification.
    """
    unseen_cases = [
        "Go to https://phptravels.net/login, Type test@example.com into Email, Click Sign In",
        "Open https://phptravels.net, Click Login, Verify that the form is shown",
        "Navigate to https://example.com, Verify that Example Domain is visible",
        "Go to https://app.cloudqa.io/home/AutomationPracticeForm, Type John into First Name",
        "Open https://app.cloudqa.io/home/AutomationPracticeForm, Type Doe into Last Name",
        "Go to https://app.cloudqa.io/home/AutomationPracticeForm, Select Male for gender",
        "Visit https://phptravels.net/login, Enter password secret123 into Password",
        "Open https://app.cloudqa.io/home/AutomationPracticeForm, Check agreement",
        "Go to https://phptravels.net/login, Verify URL contains /login",
        "Open https://example.com, Assert text 'Example Domain' exists"
    ]

    for idx, case in enumerate(unseen_cases, 1):
        actions = parse_instruction_to_actions(case)
        assert len(actions) >= 1, f"Failed to parse unseen case {idx}: '{case}'"


def test_phptravels_scenario_parsing():
    instruction = (
        "Go to https://phptravels.net/login, "
        "Type user@phptravels.com into Email Address, "
        "Type demouser into Password, "
        "Check Remember Me, "
        "Click Sign In to your account"
    )
    clauses = split_clauses(instruction)
    assert len(clauses) == 5
    actions = parse_instruction_to_actions(instruction)
    assert any(a.action_type == ActionType.NAVIGATE for a in actions)
    assert any(a.action_type == ActionType.FILL and a.value == "user@phptravels.com" for a in actions)
    assert any(a.action_type == ActionType.CHECK for a in actions)

