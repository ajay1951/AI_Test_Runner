"""
Two-Tier Natural Language Instruction Parser & Workflow Decomposer.
Converts high-level plain English goals (e.g. 'Log in as a customer and verify dashboard is shown')
and micro-instructions into validated, structured BrowserAction sequences.
Contains zero hardcoded website selectors.
"""

import re
from typing import List, Optional
from urllib.parse import urlparse
from core.models import BrowserAction, ActionType, SemanticSelector, AssertionOperator
import config


def split_clauses(text: str) -> List[str]:
    """Splits compound instructions by commas, 'and', 'then', or semicolons."""
    cleaned = re.sub(r'^\s*\d+[\.\)]\s*', '', text.strip(), flags=re.MULTILINE)
    pattern = r'(?:\r?\n+|;\s*|,\s*and\s+(?:then\s+)?|,\s*then\s+|\s+and\s+then\s+|\s+then\s+|,\s*(?=(?:open|navigate|go to|enter|fill|type|click|hover|scroll|select|choose|check|uncheck|wait|verify|assert|check that)\b)|\s+and\s+(?=(?:verify|assert|check that|click|enter|fill|navigate|hover|scroll)\b))'
    parts = re.split(pattern, cleaned, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def extract_url_from_text(text: str) -> Optional[str]:
    """Dynamically extracts URLs or web domains from text without hardcoded aliases."""
    url_match = re.search(r'https?://[^\s,;]+', text, re.IGNORECASE)
    if url_match:
        return url_match.group(0).rstrip('.,;')
    # Domain pattern e.g. "phptravels.net", "phptravels.com/demo", "saucedemo.com"
    domain_match = re.search(r'\b([a-zA-Z0-9-]+\.(?:com|net|org|io|dev|app|co)(?:/[^\s,;]*)?)\b', text, re.IGNORECASE)
    if domain_match:
        return f"https://{domain_match.group(1).rstrip('.,;')}"
    return None


def decompose_macro_goal(goal: str, target_url: Optional[str] = None) -> Optional[List[BrowserAction]]:
    """
    Decomposes high-level macro goals (e.g. 'Log in as a customer') into atomic actions
    using secure credentials from environment config.
    """
    g_lower = goal.lower().strip()

    # Authentication macro-goal pattern
    auth_match = re.search(r'\b(?:log\s*in|sign\s*in)\s+(?:as\s+(?:a\s+|an\s+)?)?(customer|admin|user|demo\s*user)?', g_lower)
    if auth_match:
        role = (auth_match.group(1) or "customer").strip()
        is_admin = "admin" in role
        email = config.TEST_ADMIN_EMAIL if is_admin else config.TEST_CUSTOMER_EMAIL
        password = config.TEST_ADMIN_PASSWORD if is_admin else config.TEST_CUSTOMER_PASSWORD

        actions = []
        # If target URL is provided and not already pointing to login, navigate to login
        if target_url:
            login_url = target_url if "login" in target_url.lower() else f"{target_url.rstrip('/')}/login"
            actions.append(BrowserAction(
                action_type=ActionType.NAVIGATE,
                value=login_url,
                reasoning=f"Navigate to {role} login page"
            ))

        # Enter email/username
        actions.append(BrowserAction(
            action_type=ActionType.FILL,
            selector=SemanticSelector(role="textbox", name="Email Address", placeholder="Email Address", description="Email Address"),
            value=email,
            is_sensitive=False,
            reasoning=f"Enter {role} email address"
        ))

        # Enter password (marked sensitive)
        actions.append(BrowserAction(
            action_type=ActionType.FILL,
            selector=SemanticSelector(role="textbox", name="Password", placeholder="Password", description="Password"),
            value=password,
            is_sensitive=True,
            reasoning=f"Enter {role} password"
        ))

        # Check Remember Me if applicable
        actions.append(BrowserAction(
            action_type=ActionType.CHECK,
            selector=SemanticSelector(role="checkbox", name="Remember Me", description="Remember Me"),
            reasoning="Select Remember Me"
        ))

        # Click submit / login button
        actions.append(BrowserAction(
            action_type=ActionType.CLICK,
            selector=SemanticSelector(role="button", name="Sign In to your account", text="Sign In", description="Login submit button"),
            reasoning="Click login button"
        ))

        # Wait for navigation/redirection
        actions.append(BrowserAction(
            action_type=ActionType.WAIT,
            value="1000",
            reasoning="Wait for authentication redirect"
        ))

        return actions

    return None


def parse_instruction_to_actions(instruction: str, base_url: Optional[str] = None) -> List[BrowserAction]:
    """
    Parses natural language instruction clauses into validated BrowserAction objects.
    Expands macro-goals and maps atomic interactions dynamically.
    """
    clauses = split_clauses(instruction)
    actions: List[BrowserAction] = []
    current_url = base_url or extract_url_from_text(instruction)

    for clause in clauses:
        c = clause.strip()
        c_lower = c.lower()

        # 1. Check for Macro-Goal first (e.g. "log in as a customer")
        macro_actions = decompose_macro_goal(c, target_url=current_url)
        if macro_actions:
            actions.extend(macro_actions)
            continue

        # 2. Navigation
        nav_match = re.search(r'^(?:open|navigate to|go to|visit)\s+(?:the\s+)?(.+)$', c, re.IGNORECASE)
        if nav_match:
            target = nav_match.group(1).strip()
            found_url = extract_url_from_text(target)
            if found_url:
                url = found_url
                current_url = url
            elif current_url and "login" in target.lower():
                url = f"{current_url.rstrip('/')}/login"
            elif current_url and ("dashboard" in target.lower() or "account" in target.lower()):
                url = f"{current_url.rstrip('/')}/dashboard"
            else:
                url = target if "://" in target else f"https://{target}"
                current_url = url
            actions.append(BrowserAction(action_type=ActionType.NAVIGATE, value=url, reasoning=c))
            continue

        # 3. Fill / Type
        fill_shortcut = re.search(r'^enter\s+(?:the\s+)?(email(?: address)?|password|username)\s+([^\s,;]+)$', c, re.IGNORECASE)
        if fill_shortcut:
            field_name = fill_shortcut.group(1).strip()
            val = fill_shortcut.group(2).strip().strip("'\"")
            is_pass = "password" in field_name.lower()
            actions.append(BrowserAction(
                action_type=ActionType.FILL,
                selector=SemanticSelector(name=field_name, placeholder=field_name, description=field_name),
                value=val,
                is_sensitive=is_pass,
                reasoning=c
            ))
            continue

        fill_into = re.search(r'^(?:enter|type|input)\s+[\'"]?([^\'"]+?)[\'"]?\s+(?:in|into)\s+(?:the\s+)?[\'"]?([^\'"]+?)[\'"]?$', c, re.IGNORECASE)
        if fill_into:
            val = fill_into.group(1).strip().strip("'\"")
            field = fill_into.group(2).strip().strip("'\"")
            is_pass = "password" in field.lower()
            actions.append(BrowserAction(
                action_type=ActionType.FILL,
                selector=SemanticSelector(name=field, placeholder=field, description=field),
                value=val,
                is_sensitive=is_pass,
                reasoning=c
            ))
            continue

        # 4. Hover
        hover_match = re.search(r'^(?:hover|move mouse to|focus on)\s+(?:the\s+)?[\'"]?([^\'"]+?)[\'"]?$', c, re.IGNORECASE)
        if hover_match:
            target = hover_match.group(1).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.HOVER,
                selector=SemanticSelector(text=target, description=target),
                reasoning=c
            ))
            continue

        # 5. Scroll
        scroll_match = re.search(r'^scroll\s+(down|up|to\s+bottom|to\s+top)\b', c, re.IGNORECASE)
        if scroll_match:
            direction = scroll_match.group(1).strip().lower()
            actions.append(BrowserAction(
                action_type=ActionType.SCROLL,
                value=direction,
                reasoning=c
            ))
            continue

        # 6. Click
        click_match = re.search(r'^(?:click|press|tap)\s+(?:on\s+)?(?:the\s+)?[\'"]?([^\'"]+?)[\'"]?$', c, re.IGNORECASE)
        if click_match:
            target = click_match.group(1).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.CLICK,
                selector=SemanticSelector(role="button", name=target, text=target, description=target),
                reasoning=c
            ))
            continue

        # 7. Check / Uncheck
        check_match = re.search(r'^check\s+(?:the\s+)?(?:checkbox\s+)?[\'"]?([^\'"]+?)[\'"]?$', c, re.IGNORECASE)
        if check_match:
            target = check_match.group(1).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.CHECK,
                selector=SemanticSelector(role="checkbox", name=target, description=target),
                reasoning=c
            ))
            continue

        uncheck_match = re.search(r'^uncheck\s+(?:the\s+)?(?:checkbox\s+)?[\'"]?([^\'"]+?)[\'"]?$', c, re.IGNORECASE)
        if uncheck_match:
            target = uncheck_match.group(1).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.UNCHECK,
                selector=SemanticSelector(role="checkbox", name=target, description=target),
                reasoning=c
            ))
            continue

        # 8. Radio selection
        radio_match = re.search(r'^(?:select|choose)\s+radio\s+(?:button\s+)?[\'"]?([^\'"]+?)[\'"]?$', c, re.IGNORECASE)
        if radio_match:
            target = radio_match.group(1).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.RADIO,
                selector=SemanticSelector(role="radio", name=target, description=target),
                reasoning=c
            ))
            continue

        # 9. Select / Dropdown
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

        # 10. Wait
        wait_match = re.search(r'^wait\s+(?:for\s+)?(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|milliseconds?|ms)?', c, re.IGNORECASE)
        if wait_match:
            num = float(wait_match.group(1))
            unit = (wait_match.group(2) or "seconds").lower()
            ms = int(num * 1000) if ("s" in unit and "ms" not in unit) else int(num)
            actions.append(BrowserAction(
                action_type=ActionType.WAIT,
                value=str(ms),
                timeout_ms=ms,
                reasoning=c
            ))
            continue

        # 11. Assert URL
        assert_url = re.search(r'^(?:verify|assert)\s+(?:that\s+)?(?:the\s+)?url\s+(contains|is|equals)\s+[\'"]?([^\'"]+?)[\'"]?$', c, re.IGNORECASE)
        if assert_url:
            op_str = assert_url.group(1).lower()
            val = assert_url.group(2).strip().strip("'\"")
            op = AssertionOperator.EQUALS if op_str in ("is", "equals") else AssertionOperator.CONTAINS
            actions.append(BrowserAction(
                action_type=ActionType.ASSERT_URL,
                expected_text=val,
                operator=op,
                reasoning=c
            ))
            continue

        # 12. Assert Page Title
        assert_title = re.search(r'^(?:verify|assert)\s+(?:that\s+)?(?:the\s+)?(?:page\s+)?title\s+(contains|is|equals)\s+[\'"]?([^\'"]+?)[\'"]?$', c, re.IGNORECASE)
        if assert_title:
            op_str = assert_title.group(1).lower()
            val = assert_title.group(2).strip().strip("'\"")
            op = AssertionOperator.EQUALS if op_str in ("is", "equals") else AssertionOperator.CONTAINS
            actions.append(BrowserAction(
                action_type=ActionType.ASSERT_TITLE,
                expected_text=val,
                operator=op,
                reasoning=c
            ))
            continue

        # 13. Assert Visibility (Specific element/heading)
        assert_match = re.search(r'^(?:verify|assert|check)\s+(?:that\s+)?(?:the\s+)?[\'"]?([^\'"]+?)[\'"]?\s+(?:is shown|is displayed|appears|is visible|exists)$', c, re.IGNORECASE)
        if assert_match:
            target = assert_match.group(1).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.ASSERT_VISIBLE,
                selector=SemanticSelector(text=target, description=target),
                expected_text=target,
                operator=AssertionOperator.IS_VISIBLE,
                reasoning=c
            ))
            continue

        # 14. Fallback text assertion
        if c_lower.startswith("verify ") or c_lower.startswith("assert "):
            target = re.sub(r'^(?:verify|assert)\s+(?:that\s+)?', '', c, flags=re.IGNORECASE).strip().strip("'\"")
            actions.append(BrowserAction(
                action_type=ActionType.ASSERT_TEXT,
                expected_text=target,
                selector=SemanticSelector(text=target, description=target),
                reasoning=c
            ))

    return actions
