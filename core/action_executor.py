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
from typing import Optional, Dict, Any

console = Console()


class ActionExecutor:
    def __init__(self, page: Page):
        self.page = page

    def _dismiss_overlays(self):
        """
        Generic, multi-strategy dialog & overlay dismissal.
        Handles ARIA modals, cookie consents, and demo disclaimers without hardcoding website IDs.
        """
        try:
            # 1. Directly check and click visible affirmative/dismiss buttons on overlays/modals
            dismiss_buttons = self.page.locator(
                'button:has-text("Understand"), button:has-text("Continue"), '
                'button:has-text("Accept"), button:has-text("Agree"), '
                'button:has-text("Close"), button:has-text("Got it"), '
                'button:has-text("Dismiss"), button:has-text("OK"), '
                '#acknowledgeDemoWarning, [aria-label*="close" i], .modal-close'
            )
            for idx in range(dismiss_buttons.count()):
                btn = dismiss_buttons.nth(idx)
                if btn.is_visible():
                    btn.click(force=True, timeout=1000)
                    self.page.wait_for_timeout(300)
                    break

            # 2. Check if any dialog or modal is visible and try Escape key
            dialog = self.page.locator('[role="dialog"], [aria-modal="true"], .modal, .modal-overlay, #demoWarningModal')
            for i in range(dialog.count()):
                d = dialog.nth(i)
                if d.is_visible():
                    self.page.keyboard.press("Escape")
                    self.page.wait_for_timeout(200)
                    break

            # 3. Generic DOM backdrop cleanup if pointer events remain blocked
            self.page.evaluate("""() => {
                const overlays = document.querySelectorAll(
                    '.modal-overlay, .modal-backdrop, #demoWarningModal, [data-modal-backdrop]'
                );
                overlays.forEach(el => {
                    if (el && (window.getComputedStyle(el).position === 'fixed' || el.id === 'demoWarningModal')) {
                        el.remove();
                    }
                });
                document.body.style.overflow = 'auto';
            }""")
        except Exception:
            pass

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
                # If fill action, ensure target is an editable input or textarea (not a button/link)
                if action.action_type == ActionType.FILL:
                    try:
                        tag = loc.first.evaluate("el => el.tagName.toLowerCase()")
                        if tag in ["input", "textarea"]:
                            return loc.first
                    except Exception:
                        pass
                else:
                    return loc.first

        # Tier 2 - 5: Semantic selector
        if action.selector:
            sel = action.selector
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
                    loc = self.page.get_by_text(txt, exact=False)
                    if loc.count() > 0:
                        return loc.first
                except Exception:
                    pass

            # Tier 6: Scoped Heuristic Fallback
            if sel.description:
                d = sel.description.lower()
                if "email" in d:
                    loc = self.page.locator("input[type='email'], input[name='email'], #email")
                    if loc.count() > 0:
                        return loc.first
                elif "password" in d:
                    loc = self.page.locator("input[type='password'], input[name='password'], #password")
                    if loc.count() > 0:
                        return loc.first
                elif "checkbox" in d or "remember" in d:
                    loc = self.page.locator("input[type='checkbox']")
                    if loc.count() > 0:
                        return loc.first

        # Direct heuristic fallback from reasoning
        reasoning = (action.reasoning or "").lower()
        if "sign in" in reasoning or "login" in reasoning:
            loc = self.page.locator("button:has-text('Sign In'), button:has-text('Login'), button[type='submit']")
            if loc.count() > 0:
                return loc.first
        elif "submit" in reasoning:
            loc = self.page.locator("button[type='submit'], input[type='submit']")
            if loc.count() > 0:
                return loc.first

        return None

    def execute(self, action: BrowserAction) -> Dict[str, Any]:
        """
        Executes a single action and returns a structured execution telemetry result.
        """
        act_type = action.action_type.value if hasattr(action.action_type, "value") else str(action.action_type)
        display_val = action.get_display_value()

        console.print(f"[bold cyan]Action:[/bold cyan] {act_type} | [yellow]Ref:[/yellow] {action.target_ref or 'Semantic'} | [green]Value:[/green] {display_val}")
        if action.reasoning:
            console.print(f"[dim]Rationale: {action.reasoning}[/dim]")

        # Dismiss any intrusive dialogs before interaction
        self._dismiss_overlays()

        result = {
            "success": False,
            "error": None,
            "assertion_result": None,
            "action_type": act_type
        }

        try:
            if act_type == "navigate":
                self.page.goto(action.value, wait_until="domcontentloaded", timeout=action.timeout_ms)
                self._dismiss_overlays()
                result["success"] = True
                return result

            elif act_type == "fill":
                loc = self._resolve_locator(action)
                if not loc:
                    raise ValueError(f"Could not locate input field for target: {action.selector}")
                loc.scroll_into_view_if_needed()
                try:
                    loc.fill(action.value or "", timeout=action.timeout_ms)
                except Exception:
                    loc.click(force=True)
                    loc.fill(action.value or "")
                result["success"] = True
                return result

            elif act_type == "click":
                loc = self._resolve_locator(action)
                if not loc:
                    raise ValueError(f"Could not locate element to click for target: {action.selector}")
                loc.scroll_into_view_if_needed()
                try:
                    loc.click(timeout=action.timeout_ms)
                except Exception:
                    loc.click(force=True, timeout=3000)
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
                    heading_loc.wait_for(state="visible", timeout=min(action.timeout_ms, 3000))
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
                        loc.wait_for(state="visible", timeout=min(action.timeout_ms, 3000))
                        console.print(f"[bold green]✓ Assertion Passed:[/bold green] Element '{target}' is visible")
                        result["assertion_result"] = {"type": "Visibility", "target": target, "passed": True}
                        result["success"] = True
                        return result
                    except Exception:
                        pass

                # 3. Bounded visible text check with wait
                text_loc = self.page.get_by_text(target, exact=False).first
                try:
                    text_loc.wait_for(state="visible", timeout=action.timeout_ms)
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

        except Exception as e:
            console.print(f"[bold red]Execution error:[/bold red] {e}")
            result["success"] = False
            result["error"] = str(e)
            return result
