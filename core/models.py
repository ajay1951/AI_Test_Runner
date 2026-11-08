"""
Strict Pydantic models for Browser Automation Test Plans, Actions, and Selectors.
Enforces typed schemas, action allowlists, security redaction, and bounded timeouts.
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
    RADIO = "radio_select"
    HOVER = "hover"
    SCROLL = "scroll"
    PRESS = "press"
    WAIT = "wait"
    WAIT_FOR_URL = "wait_for_url"
    ASSERT_VISIBLE = "assert_visible"
    ASSERT_TEXT = "assert_text"
    ASSERT_URL = "assert_url"
    ASSERT_VALUE = "assert_value"
    ASSERT_TITLE = "assert_title"
    ASSERT_ELEMENT_STATE = "assert_element_state"
    EXTRACT_TEXT = "extract_text"
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
    role: Optional[str] = Field(None, description="Accessible role: button, textbox, link, checkbox, combobox, heading, main")
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


DANGEROUS_PATTERNS = [
    re.compile(r"javascript:", re.I),
    re.compile(r"data:text/html", re.I),
    re.compile(r"eval\(", re.I),
    re.compile(r"exec\(", re.I),
    re.compile(r"__import__", re.I),
    re.compile(r"os\.system", re.I),
    re.compile(r"subprocess\.", re.I),
]


class BrowserAction(BaseModel):
    action_type: ActionType
    target_ref: Optional[str] = Field(None, description="Synthetic AI DOM ref (e.g. 'ref_1')")
    selector: Optional[SemanticSelector] = Field(None, description="Semantic fallback selector")
    value: Optional[str] = Field(None, description="Input value, URL, key, or scroll parameter")
    expected_text: Optional[str] = Field(None, description="Expected text, URL, or state for assertions")
    operator: AssertionOperator = Field(default=AssertionOperator.CONTAINS)
    timeout_ms: int = Field(default=10000, ge=100, le=60000)
    is_sensitive: bool = Field(default=False, description="Flag indicating value contains passwords or credentials")
    reasoning: Optional[str] = Field(default=None, description="AI rationale for this action")

    @field_validator("value", "expected_text")
    @classmethod
    def validate_safe_payloads(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        for pat in DANGEROUS_PATTERNS:
            if pat.search(v):
                raise ValueError(f"Unsafe expression detected in action value: {v}")
        return v

    def get_display_value(self) -> str:
        """Returns masked string if action contains sensitive credentials."""
        if not self.value:
            return ""
        if self.is_sensitive:
            return "********"
        # Auto-detect password field names
        desc = (self.selector.description if self.selector and self.selector.description else "").lower()
        reason = (self.reasoning or "").lower()
        if "password" in desc or "password" in reason:
            return "********"
        return self.value


class TestPlan(BaseModel):
    __test__ = False
    name: str = "Natural Language Browser Test"
    description: str = ""
    target_url: str = "https://phptravels.net"
    browser: BrowserType = BrowserType.CHROMIUM
    headless: bool = True
    actions: List[BrowserAction] = Field(..., min_length=1, max_length=100)
