"""
Strict Pydantic models for Browser Automation Test Plans, Actions, and Selectors.
"""

from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator, model_validator
import re


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select_option"
    CHECK = "check"
    UNCHECK = "uncheck"
    PRESS = "press"
    WAIT = "wait"
    ASSERT_VISIBLE = "assert_visible"
    ASSERT_TEXT = "assert_text"
    ASSERT_URL = "assert_url"
    ASSERT_VALUE = "assert_value"
    ASSERT_ELEMENT_STATE = "assert_element_state"
    FINISH = "finish"


class AssertionOperator(str, Enum):
    EQUALS = "equals"
    CONTAINS = "contains"
    MATCHES = "matches"
    NOT_CONTAINS = "not_contains"
    IS_VISIBLE = "is_visible"
    IS_HIDDEN = "is_hidden"
    IS_ENABLED = "is_enabled"
    IS_DISABLED = "is_disabled"
    IS_CHECKED = "is_checked"


class BrowserType(str, Enum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class SemanticSelector(BaseModel):
    role: Optional[str] = Field(None, description="Accessible role: button, textbox, link, checkbox, combobox")
    name: Optional[str] = Field(None, description="Accessible name or label text")
    placeholder: Optional[str] = Field(None, description="Input placeholder text")
    text: Optional[str] = Field(None, description="Exact or partial visible text")
    test_id: Optional[str] = Field(None, description="Test ID attribute (data-testid, id)")
    css_fallback: Optional[str] = Field(None, description="Scoped CSS selector fallback")
    description: Optional[str] = Field(None, description="Human readable description")

    @model_validator(mode="after")
    def validate_selector_has_target(self) -> "SemanticSelector":
        has_identifier = any([
            self.role, self.name, self.placeholder, 
            self.text, self.test_id, self.css_fallback, self.description
        ])
        if not has_identifier:
            raise ValueError("SemanticSelector must contain at least one locator clue or description.")
        return self


class BrowserAction(BaseModel):
    action_type: ActionType
    target_ref: Optional[str] = Field(None, description="Synthetic AI DOM ref (e.g. 'ref_1')")
    selector: Optional[SemanticSelector] = Field(None, description="Semantic fallback selector")
    value: Optional[str] = Field(None, description="Input value, URL, or key name")
    expected_text: Optional[str] = Field(None, description="Expected text or URL for assertions")
    operator: AssertionOperator = Field(default=AssertionOperator.CONTAINS)
    timeout_ms: int = Field(default=10000, ge=100, le=60000)
    reasoning: Optional[str] = Field(default=None, description="AI rationale for this action")


class TestPlan(BaseModel):
    __test__ = False
    name: str = "Natural Language Browser Test"
    description: str = ""
    target_url: str = "https://phptravels.net"
    browser: BrowserType = BrowserType.CHROMIUM
    headless: bool = True
    actions: List[BrowserAction] = Field(..., min_length=1, max_length=100)

