"""
Natural Language Instruction Parser & Clause Decomposer.
Converts high-level plain English prompts into structured actions.
"""

import re
from typing import List, Optional
from core.models import BrowserAction, ActionType, SemanticSelector, AssertionOperator

WEBSITE_ALIASES = {
    "phptravels": "https://phptravels.net",
    "php travels": "https://phptravels.net",
    "phptravels demo": "https://phptravels.net",
    "phptravels.net": "https://phptravels.net",
    "cloudqa": "https://app.cloudqa.io/home/AutomationPracticeForm",
    "automation practice": "https://app.cloudqa.io/home/AutomationPracticeForm",
}


def split_clauses(text: str) -> List[str]:
    """Splits compound instructions by commas, 'and', 'then', or semicolons."""
    cleaned = re.sub(r'^\s*\d+[\.\)]\s*', '', text.strip(), flags=re.MULTILINE)
    pattern = r'(?:\r?\n+|;\s*|,\s*and\s+(?:then\s+)?|,\s*then\s+|\s+and\s+then\s+|\s+then\s+|,\s*(?=(?:open|navigate|go to|enter|fill|type|click|select|choose|check|uncheck|wait|verify|assert|check that)\b)|\s+and\s+(?=(?:verify|assert|check that|click|enter|fill|navigate)\b))'
    parts = re.split(pattern, cleaned, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def parse_instruction_to_actions(instruction: str, base_url: Optional[str] = None) -> List[BrowserAction]:
    clauses = split_clauses(instruction)
    actions: List[BrowserAction] = []
    current_url = base_url

    # Check for website mentions
    for alias, url in WEBSITE_ALIASES.items():
        if alias in instruction.lower():
            current_url = url
            break

    for clause in clauses:
        c = clause.strip()
        c_lower = c.lower()

        # Navigation
        nav_match = re.search(r'^(?:open|navigate to|go to|visit)\s+(?:the\s+)?(.+)$', c, re.IGNORECASE)
        if nav_match:
            target = nav_match.group(1).strip()
            if target.startswith("http://") or target.startswith("https://"):
                url = target
            elif "login" in target.lower() and current_url:
                url = f"{current_url.rstrip('/')}/login"
            elif any(alias in target.lower() for alias in WEBSITE_ALIASES):
                url = current_url or "https://phptravels.net"
            else:
                url = target if "://" in target else f"https://{target}"
            actions.append(BrowserAction(action_type=ActionType.NAVIGATE, value=url, reasoning=c))
            continue

        # Fill / Type
        # Pattern: enter <field> <val> or enter <val> into <field>
        fill_shortcut = re.search(r'^enter\s+(?:the\s+)?(email(?: address)?|password|username)\s+([^\s,;]+)$', c, re.IGNORECASE)
        if fill_shortcut:
            field_name = fill_shortcut.group(1).strip()
            val = fill_shortcut.group(2).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.FILL,
                selector=SemanticSelector(name=field_name, placeholder=field_name, description=field_name),
                value=val,
                reasoning=c
            ))
            continue

        fill_into = re.search(r'^(?:enter|type|input)\s+[\'"]?([^\'"]+?)[\'"]?\s+(?:in|into)\s+(?:the\s+)?[\'"]?([^\'"]+?)[\'"]?$', c, re.IGNORECASE)
        if fill_into:
            val = fill_into.group(1).strip().strip("'\"")
            field = fill_into.group(2).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.FILL,
                selector=SemanticSelector(name=field, placeholder=field, description=field),
                value=val,
                reasoning=c
            ))
            continue

        # Click
        click_match = re.search(r'^(?:click|press|tap)\s+(?:on\s+)?(?:the\s+)?[\'"]?([^\'"]+?)[\'"]?$', c, re.IGNORECASE)
        if click_match:
            target = click_match.group(1).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.CLICK,
                selector=SemanticSelector(role="button", name=target, text=target, description=target),
                reasoning=c
            ))
            continue

        # Check / Uncheck
        check_match = re.search(r'^check\s+(?:the\s+)?(?:checkbox\s+)?[\'"]?([^\'"]+?)[\'"]?$', c, re.IGNORECASE)
        if check_match:
            target = check_match.group(1).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.CHECK,
                selector=SemanticSelector(role="checkbox", name=target, description=target),
                reasoning=c
            ))
            continue

        # Select
        select_match = re.search(r'^(?:select|choose)\s+[\'"]?([^\'"]+?)[\'"]?\s+(?:for|from|in)\s+(?:the\s+)?[\'"]?([^\'"]+?)[\'"]?$', c, re.IGNORECASE)
        if select_match:
            option_val = select_match.group(1).strip().strip("'\"")
            target = select_match.group(2).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.SELECT,
                selector=SemanticSelector(role="combobox", name=target, description=target),
                value=option_val,
                reasoning=c
            ))
            continue

        # Assertions
        assert_match = re.search(r'^(?:verify|assert|check)\s+(?:that\s+)?(?:the\s+)?[\'"]?([^\'"]+?)[\'"]?\s+(?:is shown|is displayed|appears|is visible|exists)$', c, re.IGNORECASE)
        if assert_match:
            target = assert_match.group(1).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.ASSERT_VISIBLE,
                selector=SemanticSelector(text=target, description=target),
                expected_text=target,
                reasoning=c
            ))
            continue

        assert_url = re.search(r'^(?:verify|assert)\s+(?:that\s+)?(?:the\s+)?url\s+(?:contains|is)\s+[\'"]?([^\'"]+?)[\'"]?$', c, re.IGNORECASE)
        if assert_url:
            val = assert_url.group(1).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.ASSERT_URL,
                expected_text=val,
                reasoning=c
            ))
            continue

        # Fallback assertion for generic "verify <target>"
        if c_lower.startswith("verify ") or c_lower.startswith("assert "):
            target = re.sub(r'^(?:verify|assert)\s+', '', c, flags=re.IGNORECASE).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.ASSERT_TEXT,
                expected_text=target,
                selector=SemanticSelector(text=target, description=target),
                reasoning=c
            ))

    return actions

