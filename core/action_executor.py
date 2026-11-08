"""
Action Executor with Multi-Tier Semantic Locators & Robust Assertions.
Includes automatic modal dismissal, force-click fallbacks, and custom checkbox handling.
"""

from playwright.sync_api import Page, expect
from core.models import BrowserAction, ActionType
from rich.console import Console
import time
import re

console = Console()


class ActionExecutor:
    def __init__(self, page: Page):
        self.page = page

    def _dismiss_overlays(self):
        """Automatically dismisses demo warning popups, 'I Understand & Continue', cookie consent, or modals."""
        try:
            # 1. Click 'I Understand & Continue' button if present
            btn = self.page.locator("button:has-text('Understand'), button:has-text('Continue'), #demoWarningModal button, .modal-overlay button")
            if btn.count() > 0:
                for i in range(btn.count()):
                    b = btn.nth(i)
                    if b.is_visible():
                        b.click(force=True, timeout=1500)
                        self.page.wait_for_timeout(300)
                        return

            # 2. Press Escape
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(200)

            # 3. If overlay still exists in DOM, remove it cleanly so it never intercepts pointer events
            self.page.evaluate("""() => {
                const overlay = document.querySelector('#demoWarningModal') || document.querySelector('.modal-overlay');
                if (overlay) overlay.remove();
                // Also restore document scroll if locked by modal
                document.body.style.overflow = 'auto';
            }""")
        except Exception:
            pass

    def _resolve_locator(self, action: BrowserAction):
        # 1. First priority: Target ref from LLM DOM Extractor
        if action.target_ref:
            loc = self.page.locator(f"[data-ai-id='{action.target_ref}']")
            if loc.count() > 0:
                return loc.first

        # 2. Multi-tier semantic discovery fallback
        if action.selector:
            sel = action.selector
            # Tier 1: Role and Name
            if sel.role:
                name_q = sel.name or sel.text or sel.description
                if name_q:
                    try:
                        loc = self.page.get_by_role(sel.role, name=name_q, exact=False)
                        if loc.count() > 0:
                            return loc.first
                    except Exception:
                        pass

            # Tier 2: Label
            lbl = sel.name or sel.description
            if lbl:
                try:
                    loc = self.page.get_by_label(lbl, exact=False)
                    if loc.count() > 0:
                        return loc.first
                except Exception:
                    pass

            # Tier 3: Placeholder
            ph = sel.placeholder or sel.description
            if ph:
                try:
                    loc = self.page.get_by_placeholder(ph, exact=False)
                    if loc.count() > 0:
                        return loc.first
                except Exception:
                    pass

            # Tier 4: Visible Text
            txt = sel.text or sel.name or sel.description
            if txt:
                try:
                    loc = self.page.get_by_text(txt, exact=False)
                    if loc.count() > 0:
                        return loc.first
                except Exception:
                    pass

            # Tier 5: Scoped Heuristics
            if sel.description:
                d = sel.description.lower()
                if "email" in d:
                    loc = self.page.locator("input[type='email'], #email, input[name='email']")
                    if loc.count() > 0:
                        return loc.first
                elif "password" in d:
                    loc = self.page.locator("input[type='password'], #password, input[name='password']")
                    if loc.count() > 0:
                        return loc.first
                elif "remember" in d:
                    loc = self.page.locator("#remember_me, input[name='remember_me'], input[type='checkbox']")
                    if loc.count() > 0:
                        return loc.first
                elif "login" in d or "sign in" in d:
                    loc = self.page.locator("button:has-text('Sign In'), button:has-text('Login'), input[value*='Login' i]")
                    if loc.count() > 0:
                        return loc.first

        # 3. Direct heuristic fallback from reasoning or action type
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

    def execute(self, action: BrowserAction) -> bool:
        act_type = action.action_type.value if hasattr(action.action_type, "value") else str(action.action_type)
        console.print(f"[bold cyan]Action:[/bold cyan] {act_type} | [yellow]Ref:[/yellow] {action.target_ref or 'Semantic'} | [green]Value:[/green] {action.value or action.expected_text or ''}")
        if action.reasoning:
            console.print(f"[dim]Rationale: {action.reasoning}[/dim]")

        # Dismiss any intrusive demo warning modal or banner before action
        self._dismiss_overlays()

        try:
            if act_type == "navigate":
                self.page.goto(action.value, wait_until="domcontentloaded", timeout=action.timeout_ms)
                self._dismiss_overlays()
                return True

            elif act_type == "fill":
                loc = self._resolve_locator(action)
                if not loc:
                    raise ValueError(f"Could not locate input element for {action}")
                loc.scroll_into_view_if_needed()
                try:
                    loc.fill(action.value or "", timeout=action.timeout_ms)
                except Exception:
                    loc.click(force=True)
                    loc.fill(action.value or "")
                return True

            elif act_type == "click":
                loc = self._resolve_locator(action)
                if not loc:
                    raise ValueError(f"Could not locate element to click for {action}")
                loc.scroll_into_view_if_needed()
                try:
                    loc.click(timeout=action.timeout_ms)
                except Exception:
                    loc.click(force=True, timeout=3000)
                return True

            elif act_type == "check":
                loc = self._resolve_locator(action)
                if not loc:
                    raise ValueError(f"Could not locate checkbox for {action}")
                try:
                    loc.check(timeout=2500)
                except Exception:
                    # Custom styled checkbox wrapper (.checkbox-custom or label) intercepts click
                    try:
                        loc.check(force=True, timeout=2500)
                    except Exception:
                        try:
                            # Click the wrapper / parent label
                            loc.locator("xpath=..").click(force=True)
                        except Exception:
                            loc.dispatch_event("click")
                return True

            elif act_type == "uncheck":
                loc = self._resolve_locator(action)
                if not loc:
                    raise ValueError(f"Could not locate checkbox for {action}")
                try:
                    loc.uncheck(timeout=2500)
                except Exception:
                    loc.uncheck(force=True, timeout=2500)
                return True

            elif act_type == "select_option":
                loc = self._resolve_locator(action)
                if not loc:
                    raise ValueError(f"Could not locate select for {action}")
                try:
                    loc.select_option(label=action.value)
                except Exception:
                    loc.select_option(value=action.value)
                return True

            elif act_type == "press":
                self.page.keyboard.press(action.value or "Enter")
                return True

            elif act_type == "wait":
                ms = int(action.value) if (action.value and str(action.value).isdigit()) else 1000
                self.page.wait_for_timeout(ms)
                return True

            # ---------------- ASSERTIONS ----------------
            elif act_type == "assert_text":
                expected = action.expected_text or action.value or ""
                expect(self.page.locator("body")).to_contain_text(expected, timeout=action.timeout_ms)
                console.print(f"[bold green]✓ Assertion Passed:[/bold green] Found text '{expected}'")
                return True

            elif act_type == "assert_visible":
                loc = self._resolve_locator(action)
                if loc and loc.is_visible():
                    console.print(f"[bold green]✓ Assertion Passed:[/bold green] Element is visible")
                    return True
                # Fallback: check if text is visible on page
                expected = action.expected_text or (action.selector.description if action.selector else "")
                expect(self.page.get_by_text(expected, exact=False).first).to_be_visible(timeout=action.timeout_ms)
                console.print(f"[bold green]✓ Assertion Passed:[/bold green] '{expected}' is visible")
                return True

            elif act_type == "assert_url":
                expected = action.expected_text or action.value or ""
                time.sleep(0.5)
                current_url = self.page.url
                if expected in current_url:
                    console.print(f"[bold green]✓ URL Assertion Passed:[/bold green] '{expected}' in '{current_url}'")
                    return True
                raise AssertionError(f"Expected URL to contain '{expected}', got '{current_url}'")

            elif act_type == "finish":
                return True

            return True

        except Exception as e:
            console.print(f"[bold red]Execution error:[/bold red] {e}")
            return False
