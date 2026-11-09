"""
Generic Browser Action Executor & Strict State Assertion Engine.
Supports accessibility locators, synthetic AI tags, generic dialog dismissal,
and explicit observable state verification with credential masking.
"""

from playwright.sync_api import Page, expect
from core.models import BrowserAction, ActionType, AssertionOperator
from rich.console import Console
import time
import re
from typing import Optional, Dict, Any, List

console = Console()


class ActionExecutor:
    def __init__(self, page: Page):
        self.page = page
        self.dismissed_modals: List[Dict[str, Any]] = []

    def _dismiss_overlays(self):
        """
        Generic, multi-strategy dialog & overlay dismissal with strict safety boundaries.
        Only dismisses informational disclaimers, cookie notices, and demo banners.
        Never auto-dismisses destructive confirmations or alters DOM with forced removal.
        """
        try:
            # 1. Identify dialog containers
            dialogs = self.page.locator('[role="dialog"], [aria-modal="true"], .modal, .modal-overlay')
            for i in range(dialogs.count()):
                d = dialogs.nth(i)
                if not d.is_visible():
                    continue

                # Safety Check: Never dismiss destructive confirmation dialogs
                try:
                    dialog_text = (d.inner_text() or "").lower()
                    destructive_patterns = ["delete", "destroy", "remove item", "cancel subscription", "irreversible", "are you sure"]
                    if any(dp in dialog_text for dp in destructive_patterns):
                        # Destructive or critical confirmation - do NOT auto-dismiss
                        return
                except Exception:
                    pass

            # 2. Safely find and click informational or consent dismissal buttons
            dismiss_buttons = self.page.locator(
                'button:has-text("Understand"), button:has-text("Continue"), '
                'button:has-text("Accept All"), button:has-text("Accept Cookies"), '
                'button:has-text("Got it"), button:has-text("Dismiss"), '
                '[aria-label*="close" i], .modal-close'
            )
            for idx in range(dismiss_buttons.count()):
                btn = dismiss_buttons.nth(idx)
                if btn.is_visible():
                    btn_text = (btn.inner_text() or "Close").strip()
                    btn.click(force=True, timeout=1000)
                    self.page.wait_for_timeout(300)
                    self.dismissed_modals.append({
                        "timestamp": time.time(),
                        "button_text": btn_text,
                        "type": "informational_overlay"
                    })
                    console.print(f"[dim yellow]ℹ Auto-dismissed informational overlay via '{btn_text}'[/dim yellow]")
                    return

            # 3. For generic modals without recognized buttons, attempt gentle Escape key
            for i in range(dialogs.count()):
                d = dialogs.nth(i)
                if d.is_visible():
                    self.page.keyboard.press("Escape")
                    self.page.wait_for_timeout(200)
                    break
        except Exception:
            pass

    def _validate_element_compatibility(self, loc, act_type: str):
        """
        Validates element tag and state compatibility before interaction.
        Raises TypeError for non-editable fill targets.
        Raises ValueError for disabled click targets.
        """
        tag = loc.evaluate("el => (el.tagName || '').toLowerCase()")
        if act_type == "fill":
            is_editable = loc.evaluate(
                "el => el.isContentEditable === true || ['input', 'textarea'].includes((el.tagName || '').toLowerCase())"
            )
            if not is_editable:
                raise TypeError(f"Incompatible target: Cannot fill non-editable element <{tag}>")
        elif act_type == "click":
            is_disabled = loc.evaluate(
                "el => el.disabled === true || el.getAttribute('aria-disabled') === 'true'"
            )
            if is_disabled:
                raise ValueError(f"Incompatible target: Cannot click disabled element <{tag}>")

    def _resolve_locator(self, action: BrowserAction):
        """
        Multi-tier locator resolution:
        Tier 1: Synthetic AI tag [data-ai-id]
        Tier 2: Accessible Role + Name
        Tier 3: Associated Label
        Tier 4: Input Placeholder
        Tier 5: Visible Text
        Tier 6: Scoped semantic heuristics
        """
        # Tier 1: Target ref from dynamic DOM Extractor
        if action.target_ref:
            loc = self.page.locator(f"[data-ai-id='{action.target_ref}']")
            if loc.count() > 0:
                # Sanity guard: if clicking login/submit, do not click a reset/forgot password link
                if action.action_type == ActionType.CLICK:
                    r_text = (action.reasoning or "").lower()
                    if any(k in r_text for k in ["login", "sign in", "submit"]):
                        try:
                            txt = (loc.first.inner_text() or "").lower()
                            href = (loc.first.get_attribute("href") or "").lower()
                            if any(bad in txt or bad in href for bad in ["forgot", "reset", "signup", "register"]):
                                loc = None
                        except Exception:
                            pass
                if loc and loc.count() > 0:
                    return loc.first

        # Tier 2 - 5: Semantic selector
        if action.selector:
            sel = action.selector

            # Test ID or direct ID fallback
            if sel.test_id:
                try:
                    loc = self.page.locator(f"[data-testid='{sel.test_id}'], #{sel.test_id}")
                    if loc.count() > 0:
                        return loc.first
                except Exception:
                    pass

            # CSS fallback
            if sel.css_fallback:
                try:
                    loc = self.page.locator(sel.css_fallback)
                    if loc.count() > 0:
                        return loc.first
                except Exception:
                    pass

            # Tier 2: Role and Name
            if sel.role:
                name_q = sel.name or sel.text or sel.description
                if name_q:
                    try:
                        loc = self.page.get_by_role(sel.role, name=name_q, exact=False)
                        if loc.count() > 0:
                            return loc.first
                    except Exception:
                        pass
                # Role only
                try:
                    loc = self.page.get_by_role(sel.role)
                    if loc.count() > 0:
                        return loc.first
                except Exception:
                    pass

            # Direct element ID or Name attribute
            ident = sel.name or sel.description
            if ident:
                try:
                    loc = self.page.locator(f"#{ident}, [name='{ident}']")
                    if loc.count() > 0:
                        return loc.first
                except Exception:
                    pass

            # Tier 3: Label
            lbl = sel.name or sel.description
            if lbl:
                try:
                    loc = self.page.get_by_label(lbl, exact=False)
                    if loc.count() > 0:
                        return loc.first
                except Exception:
                    pass

            # Tier 4: Placeholder
            ph = sel.placeholder or sel.description
            if ph:
                try:
                    loc = self.page.get_by_placeholder(ph, exact=False)
                    if loc.count() > 0:
                        return loc.first
                except Exception:
                    pass

            # Tier 5: Visible Text
            txt = sel.text or sel.name or sel.description
            if txt:
                try:
                    if action.action_type == ActionType.FILL:
                        # For fill actions, text should match associated label or placeholder, not arbitrary text
                        loc = self.page.locator("input, textarea").filter(has_text=txt)
                        if loc.count() == 0:
                            loc = self.page.get_by_label(txt, exact=False)
                    elif action.action_type == ActionType.CLICK:
                        loc = self.page.locator("button, a, [role='button'], input[type='submit'], input[type='button']").filter(has_text=txt)
                        if loc.count() == 0:
                            # Support common authentication/submission synonyms
                            txt_lower = txt.lower()
                            if any(k in txt_lower for k in ["login", "sign in", "log in", "signin", "submit"]):
                                loc = self.page.locator("button:visible:has-text('Sign In'), button:visible:has-text('Login'), button:visible:has-text('Log In'), form button[type='submit']:visible, button[type='submit']:visible, input[type='submit']:visible")
                        if loc.count() == 0:
                            loc = self.page.get_by_text(txt, exact=False)
                    else:
                        loc = self.page.get_by_text(txt, exact=False)

                    if loc.count() > 0:
                        return loc.first
                except Exception:
                    pass

            # Tier 6: Scoped Heuristic Fallback
            if sel.description:
                d = sel.description.lower()
                if "email" in d or "username" in d or "user" in d:
                    loc = self.page.locator("input[type='email'], input[name='username'], input[name='user-name'], input[name='email'], input[id*='user'], input[id*='email'], #username, #user-name, #email, [placeholder*='user' i], [placeholder*='email' i]")
                    if loc.count() > 0:
                        return loc.first
                elif "password" in d:
                    loc = self.page.locator("input[type='password'], input[name='password'], #password, [placeholder*='password' i]")
                    if loc.count() > 0:
                        return loc.first
                elif "checkbox" in d or "remember" in d:
                    loc = self.page.locator("input[type='checkbox']")
                    if loc.count() > 0:
                        return loc.first

        # Direct heuristic fallback from reasoning
        reasoning = (action.reasoning or "").lower()
        if "sign in" in reasoning or "login" in reasoning:
            loc = self.page.locator("button:visible:has-text('Sign In'), button:visible:has-text('Login'), button:visible:has-text('Log In'), form button[type='submit']:visible, button[type='submit']:visible")
            if loc.count() > 0:
                return loc.first
        elif "submit" in reasoning:
            loc = self.page.locator("form button[type='submit']:visible, button[type='submit']:visible, input[type='submit']:visible")
            if loc.count() > 0:
                return loc.first

        return None

    def execute(self, action: BrowserAction, max_attempts: int = 3) -> Dict[str, Any]:
        """
        Executes a single action with pre-interaction compatibility check
        and a bounded 3-attempt retry loop for transient DOM hydration.
        """
        act_type = action.action_type.value if hasattr(action.action_type, "value") else str(action.action_type)
        display_val = action.get_display_value()

        console.print(f"[bold cyan]Action:[/bold cyan] {act_type} | [yellow]Ref:[/yellow] {action.target_ref or 'Semantic'} | [green]Value:[/green] {display_val}")
        if action.reasoning:
            console.print(f"[dim]Rationale: {action.reasoning}[/dim]")

        result = {
            "success": False,
            "error": None,
            "assertion_result": None,
            "action_type": act_type,
            "attempts": 0
        }

        for attempt in range(1, max_attempts + 1):
            result["attempts"] = attempt
            try:
                # Dismiss any intrusive dialogs before interaction
                self._dismiss_overlays()

                if act_type == "navigate":
                    self.page.goto(action.value, wait_until="domcontentloaded", timeout=action.timeout_ms)
                    self._dismiss_overlays()
                    result["success"] = True
                    return result

                elif act_type == "fill":
                    loc = self._resolve_locator(action)
                    if not loc:
                        raise ValueError(f"Could not locate input field for target: {action.selector}")
                    self._validate_element_compatibility(loc, act_type)
                    try:
                        loc.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                    try:
                        loc.fill(action.value or "", timeout=min(action.timeout_ms, 3000))
                    except Exception:
                        self._dismiss_overlays()
                        loc.click(force=True, timeout=2000)
                        loc.fill(action.value or "", timeout=3000)
                    result["success"] = True
                    return result

                elif act_type == "click":
                    loc = self._resolve_locator(action)
                    if not loc:
                        raise ValueError(f"Could not locate element to click for target: {action.selector}")
                    self._validate_element_compatibility(loc, act_type)
                    try:
                        loc.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                    try:
                        loc.click(timeout=min(action.timeout_ms, 3000))
                    except Exception:
                        self._dismiss_overlays()
                        loc.click(force=True, timeout=2000)
                    result["success"] = True
                    return result

                elif act_type == "hover":
                    loc = self._resolve_locator(action)
                    if not loc:
                        raise ValueError(f"Could not locate element to hover for target: {action.selector}")
                    loc.scroll_into_view_if_needed()
                    loc.hover(timeout=action.timeout_ms)
                    result["success"] = True
                    return result

                elif act_type == "scroll":
                    direction = (action.value or "down").lower()
                    delta_y = 600 if "down" in direction else -600
                    self.page.mouse.wheel(0, delta_y)
                    self.page.wait_for_timeout(300)
                    result["success"] = True
                    return result

                elif act_type == "check":
                    loc = self._resolve_locator(action)
                    if not loc:
                        raise ValueError(f"Could not locate checkbox for target: {action.selector}")
                    try:
                        loc.check(timeout=2000)
                    except Exception:
                        try:
                            loc.check(force=True, timeout=2000)
                        except Exception:
                            loc.locator("xpath=..").click(force=True)
                    result["success"] = True
                    return result

                elif act_type == "uncheck":
                    loc = self._resolve_locator(action)
                    if not loc:
                        raise ValueError(f"Could not locate checkbox for target: {action.selector}")
                    try:
                        loc.uncheck(timeout=2000)
                    except Exception:
                        loc.uncheck(force=True, timeout=2000)
                    result["success"] = True
                    return result

                elif act_type == "radio_select":
                    loc = self._resolve_locator(action)
                    if not loc:
                        raise ValueError(f"Could not locate radio button for target: {action.selector}")
                    try:
                        loc.check(force=True, timeout=2500)
                    except Exception:
                        loc.click(force=True)
                    result["success"] = True
                    return result

                elif act_type == "select_option":
                    loc = self._resolve_locator(action)
                    if not loc:
                        raise ValueError(f"Could not locate dropdown for target: {action.selector}")
                    try:
                        loc.select_option(label=action.value, timeout=action.timeout_ms)
                    except Exception:
                        loc.select_option(value=action.value, timeout=action.timeout_ms)
                    result["success"] = True
                    return result

                elif act_type == "press":
                    self.page.keyboard.press(action.value or "Enter")
                    result["success"] = True
                    return result

                elif act_type == "wait":
                    ms = int(action.value) if (action.value and str(action.value).isdigit()) else 1000
                    self.page.wait_for_timeout(ms)
                    result["success"] = True
                    return result

                elif act_type == "wait_for_url":
                    expected = action.expected_text or action.value or ""
                    self.page.wait_for_url(f"**{expected}**", timeout=action.timeout_ms)
                    result["success"] = True
                    return result

                # ---------------- STRICT ASSERTIONS ----------------
                elif act_type == "assert_url":
                    expected = action.expected_text or action.value or ""
                    time.sleep(0.3)
                    current_url = self.page.url
                    passed = (expected in current_url) if action.operator == AssertionOperator.CONTAINS else (expected == current_url)
                    result["assertion_result"] = {
                        "type": "URL",
                        "expected": expected,
                        "actual": current_url,
                        "passed": passed
                    }
                    if passed:
                        console.print(f"[bold green]✓ Assertion Passed:[/bold green] URL '{current_url}' contains '{expected}'")
                        result["success"] = True
                        return result
                    raise AssertionError(f"Expected URL to contain '{expected}', actual was '{current_url}'")

                elif act_type == "assert_title":
                    expected = action.expected_text or action.value or ""
                    current_title = self.page.title()
                    passed = expected.lower() in current_title.lower()
                    result["assertion_result"] = {
                        "type": "Title",
                        "expected": expected,
                        "actual": current_title,
                        "passed": passed
                    }
                    if passed:
                        console.print(f"[bold green]✓ Assertion Passed:[/bold green] Title '{current_title}' matches '{expected}'")
                        result["success"] = True
                        return result
                    raise AssertionError(f"Expected page title to match '{expected}', actual was '{current_title}'")

                elif act_type == "assert_visible":
                    target = action.expected_text or (action.selector.description if action.selector else "")
                    # 1. Prioritize heading / landmark / primary container with wait
                    heading_loc = self.page.locator(f"h1:has-text('{target}'), h2:has-text('{target}'), [role='heading']:has-text('{target}')").first
                    try:
                        heading_loc.wait_for(state="visible", timeout=min(action.timeout_ms, 2000))
                        console.print(f"[bold green]✓ Assertion Passed:[/bold green] Landmark '{target}' is visible in viewport")
                        result["assertion_result"] = {"type": "Visibility", "target": target, "passed": True}
                        result["success"] = True
                        return result
                    except Exception:
                        pass

                    # 2. Semantic locator resolution with wait
                    loc = self._resolve_locator(action)
                    if loc:
                        try:
                            loc.wait_for(state="visible", timeout=min(action.timeout_ms, 2000))
                            console.print(f"[bold green]✓ Assertion Passed:[/bold green] Element '{target}' is visible")
                            result["assertion_result"] = {"type": "Visibility", "target": target, "passed": True}
                            result["success"] = True
                            return result
                        except Exception:
                            pass

                    # 3. Bounded visible text check with wait
                    text_loc = self.page.get_by_text(target, exact=False).first
                    try:
                        per_attempt_timeout = max(2000, action.timeout_ms // max_attempts)
                        text_loc.wait_for(state="visible", timeout=per_attempt_timeout)
                        console.print(f"[bold green]✓ Assertion Passed:[/bold green] '{target}' is visible")
                        result["assertion_result"] = {"type": "Visibility", "target": target, "passed": True}
                        result["success"] = True
                        return result
                    except Exception:
                        pass

                    raise AssertionError(f"Expected element or landmark '{target}' to be visible on page.")

                elif act_type == "assert_text":
                    expected = action.expected_text or action.value or ""
                    # Search within <main>, <article>, or form containers rather than unconstrained body text
                    container = self.page.locator("main, [role='main'], article, form, .container, #app, #root").first
                    scope = container if container.count() > 0 else self.page.locator("body")
                    expect(scope).to_contain_text(expected, timeout=action.timeout_ms)
                    console.print(f"[bold green]✓ Assertion Passed:[/bold green] Verified text '{expected}' in primary container")
                    result["assertion_result"] = {"type": "Text", "expected": expected, "passed": True}
                    result["success"] = True
                    return result

                elif act_type == "finish":
                    result["success"] = True
                    return result

                result["success"] = True
                return result

            except TypeError as te:
                # Incompatible element error: fail immediately without futile retries
                console.print(f"[bold red]Element Compatibility Error:[/bold red] {te}")
                result["success"] = False
                result["error"] = str(te)
                return result

            except Exception as e:
                result["error"] = str(e)
                if attempt < max_attempts:
                    console.print(f"[yellow]Transient failure on attempt {attempt}/{max_attempts} ({e}). Retrying in {round(0.4 * attempt, 2)}s...[/yellow]")
                    time.sleep(0.4 * attempt)
                else:
                    console.print(f"[bold red]Execution error after {max_attempts} attempts:[/bold red] {e}")
                    result["success"] = False
                    return result

        return result
