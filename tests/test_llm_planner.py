"""
Unit Tests for Groq LLM Planner & Strict Mode Provenance Engine.
Covers:
1. Successful Groq completion
2. Model-not-found error
3. Invalid API key error
4. Rate-limit response
5. Invalid JSON response handling
6. Pydantic validation failure
7. Unsupported action rejection
8. Strict mode preventing fallback
9. Normal mode allowing explicitly recorded fallback
10. LLM planner provenance tracking
11. Successful structured action generation
12. PHPTravels LLM workflow schema validation
"""

import pytest
import json
from unittest.mock import MagicMock, patch
from openai import AuthenticationError, NotFoundError, RateLimitError, APIConnectionError
from core.models import BrowserAction, ActionType
from core.llm_planner import LLMPlanner, _extract_json


def test_groq_completion_success():
    planner = LLMPlanner(model="openai/gpt-oss-20b")
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"status": "ok"}'
    mock_resp = MagicMock(choices=[mock_choice])
    mock_client.chat.completions.create.return_value = mock_resp
    planner.client = mock_client

    res = planner.check_connectivity()
    assert res["status"] == "PASS"
    assert res["accessible"] is True
    assert res["error_type"] is None
    assert "Successfully connected" in res["message"]


def test_model_not_found_error():
    planner = LLMPlanner(model="nonexistent-model")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("Error code: 404 - {'message': 'model not found'}")
    planner.client = mock_client

    res = planner.check_connectivity()
    assert res["status"] == "FAIL"
    assert res["accessible"] is False
    assert res["error_type"] == "model_not_found"


def test_invalid_api_key_error():
    planner = LLMPlanner()
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("Error code: 401 - {'message': 'invalid api key'}")
    planner.client = mock_client

    res = planner.check_connectivity()
    assert res["status"] == "FAIL"
    assert res["accessible"] is False
    assert res["error_type"] == "authentication_error"


def test_rate_limit_error():
    planner = LLMPlanner()
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("Error code: 429 - {'message': 'rate limit exceeded'}")
    planner.client = mock_client

    res = planner.check_connectivity()
    assert res["status"] == "FAIL"
    assert res["accessible"] is False
    assert res["error_type"] == "rate_limit"


def test_invalid_json_response_handling():
    with pytest.raises(Exception):
        _extract_json("This is pure prose without any valid JSON")

    # Handles markdown fenced JSON cleanly
    valid_fenced = "```json\n{\"action_type\": \"click\"}\n```"
    parsed = _extract_json(valid_fenced)
    assert parsed["action_type"] == "click"


def test_pydantic_validation_failure():
    # Invalid timeout bounds (< 100ms)
    invalid_data = {
        "action_type": "click",
        "timeout_ms": 10  # Schema requires ge=100
    }
    with pytest.raises(Exception):
        BrowserAction(**invalid_data)


def test_unsupported_action_rejection():
    # Unsupported action type
    with pytest.raises(Exception):
        BrowserAction(action_type="execute_bash_script")

    # Injection payload rejection
    with pytest.raises(ValueError):
        BrowserAction(action_type=ActionType.NAVIGATE, value="javascript:alert(1)")


def test_strict_mode_prevents_fallback():
    planner = LLMPlanner(strict=True, model="openai/gpt-oss-20b")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("API Offline")
    planner.client = mock_client

    # Strict mode MUST raise RuntimeError and NEVER silently use deterministic heuristic
    with pytest.raises(RuntimeError) as exc_info:
        planner.plan_step("Click Login", [{"ref": "ref_1", "text": "Login"}], "https://example.com")
    assert "Strict LLM Mode" in str(exc_info.value)

    with pytest.raises(RuntimeError) as exc_info2:
        planner.plan_instruction_sequence("Open https://example.com and click Login")
    assert "Strict LLM Mode" in str(exc_info2.value)


def test_normal_mode_allows_recorded_fallback():
    planner = LLMPlanner(strict=False, mode="hybrid")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("API Offline")
    planner.client = mock_client

    # In hybrid mode without strict flag, fallback is permitted but MUST be explicitly attributed
    action = planner.plan_step("Click Login", [{"ref": "ref_1", "text": "Login", "role": "button"}], "https://example.com")
    assert action.planner_type == "deterministic_heuristic"
    assert action.fallback_used is True
    assert action.model is None


def test_llm_planner_provenance_recording():
    planner = LLMPlanner(strict=True, model="openai/gpt-oss-20b")
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "action_type": "fill",
        "target_ref": "ref_10",
        "value": "user@phptravels.com",
        "reasoning": "Enter customer email into ref_10"
    })
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    planner.client = mock_client

    action = planner.plan_step("Enter email", [{"ref": "ref_10", "text": "Email", "role": "textbox"}], "https://phptravels.net/login")
    assert action.planner_type == "llm"
    assert action.model == "openai/gpt-oss-20b"
    assert action.fallback_used is False
    assert action.target_ref == "ref_10"
    assert action.value == "user@phptravels.com"


def test_successful_structured_action_generation():
    planner = LLMPlanner(strict=True, model="openai/gpt-oss-20b")
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "actions": [
            {"action_type": "navigate", "value": "https://phptravels.net/login", "reasoning": "Open login page"},
            {"action_type": "fill", "value": "user@phptravels.com", "selector": {"name": "email", "description": "email input"}, "reasoning": "Fill email"},
            {"action_type": "click", "selector": {"name": "Sign In", "role": "button", "description": "Sign In button"}, "reasoning": "Submit"}
        ]
    })
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    planner.client = mock_client

    actions = planner.plan_instruction_sequence("Open login, enter email, click sign in")
    assert len(actions) == 3
    assert actions[0].action_type == ActionType.NAVIGATE
    assert actions[1].action_type == ActionType.FILL
    assert actions[2].action_type == ActionType.CLICK
    for a in actions:
        assert a.planner_type == "llm"
        assert a.model == "openai/gpt-oss-20b"
        assert a.fallback_used is False


def test_phptravels_llm_workflow_simulation():
    # Tests complete structured schema output matching the live PHPTravels verification contract
    raw_payload = {
        "actions": [
            {"action_type": "navigate", "value": "https://phptravels.net/login", "reasoning": "Open login"},
            {"action_type": "fill", "value": "user@phptravels.com", "selector": {"description": "email field"}, "reasoning": "Enter email"},
            {"action_type": "fill", "value": "demouser", "selector": {"description": "password field"}, "reasoning": "Enter password"},
            {"action_type": "click", "selector": {"name": "Sign In", "role": "button", "description": "Submit"}, "reasoning": "Submit"},
            {"action_type": "assert_url", "expected_text": "/dashboard", "reasoning": "Assert dashboard url"},
            {"action_type": "assert_title", "expected_text": "Dashboard", "reasoning": "Assert dashboard title"},
            {"action_type": "assert_visible", "expected_text": "Account Summary", "reasoning": "Assert heading"}
        ]
    }
    validated = [BrowserAction(**a) for a in raw_payload["actions"]]
    assert len(validated) == 7
    assert validated[2].is_sensitive is True  # Password auto-detected as sensitive
    assert validated[4].action_type == ActionType.ASSERT_URL
    assert validated[5].action_type == ActionType.ASSERT_TITLE
    assert validated[6].action_type == ActionType.ASSERT_VISIBLE
