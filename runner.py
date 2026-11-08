"""
Main AI Test Runner.
Executes natural language test cases against real browser instances using Playwright,
LLM-driven dynamic DOM inspection, semantic locators, and automated report generation.
"""

import os
import sys
import time
from typing import Union, List
from playwright.sync_api import sync_playwright
from core.dom_extractor import DOMExtractor
from core.llm_planner import LLMPlanner
from core.action_executor import ActionExecutor
from core.test_parser import split_clauses, parse_instruction_to_actions
from core.reporter import TestReporter
from core.models import ActionType
import config
from rich.console import Console
from rich.panel import Panel

console = Console()


class AITestRunner:
    def __init__(self, headless: bool = config.HEADLESS, slow_mo: int = 50):
        self.planner = LLMPlanner()
        self.reporter = TestReporter(output_dir="reports")
        self.headless = headless
        self.slow_mo = slow_mo
        os.makedirs("screenshots", exist_ok=True)

    def run_scenario(self, instructions: Union[str, List[str]], title: str = "Natural Language Test Scenario") -> bool:
        """
        Runs a test scenario given either a single high-level plain English instruction
        or a list of atomic test steps.
        """
        start_time = time.time()

        # Normalize instructions into step list
        if isinstance(instructions, str):
            steps = split_clauses(instructions)
            if not steps:
                steps = [instructions]
        else:
            steps = instructions

        console.print(Panel.fit(
            f"[bold green]AI Natural Language Test Runner[/bold green]\n"
            f"[cyan]Scenario:[/cyan] {title}\n"
            f"[cyan]Steps Count:[/cyan] {len(steps)}\n"
            f"[dim]Provider: Groq LLaMA 3.3 (with Deterministic Fallback)[/dim]",
            border_style="blue"
        ))

        steps_log = []
        overall_passed = True

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
                args=["--disable-dev-shm-usage", "--no-sandbox"]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.set_default_timeout(config.TIMEOUT_MS)
            executor = ActionExecutor(page)

            for idx, step in enumerate(steps, 1):
                console.print(f"\n[bold yellow]─── Step {idx}/{len(steps)}: '{step}' ───[/bold yellow]")
                step_start = time.time()
                step_screenshot = None
                action = None
                success = False

                step_lower = step.lower().strip()
                # 1. Navigation handling
                if step_lower.startswith("open ") or step_lower.startswith("go to ") or step_lower.startswith("navigate to "):
                    target = step.split(" ")[-1].strip()
                    if "phptravels" in target.lower():
                        url = "https://phptravels.net/login" if "login" in step_lower else "https://phptravels.net"
                    elif "cloudqa" in target.lower():
                        url = "https://app.cloudqa.io/home/AutomationPracticeForm"
                    else:
                        url = target if "://" in target else f"https://{target}"

                    success = executor.execute(from_nav_url(url, step))
                    action_name = "navigate"
                    rationale = f"Navigated to {url}"
                    # Dismiss modal immediately after navigation
                    executor._dismiss_overlays()

                else:
                    # Dismiss any popup before capturing DOM and acting
                    executor._dismiss_overlays()
                    # 2. Extract interactive DOM snapshot
                    dom = DOMExtractor.get_interactive_tree(page)
                    # 3. Plan step
                    action = self.planner.plan_step(step, dom, page.url)
                    action_name = action.action_type.value if hasattr(action.action_type, "value") else str(action.action_type)
                    rationale = action.reasoning or ""
                    # 4. Execute action
                    success = executor.execute(action)

                # Capture step screenshot
                screenshot_filename = f"screenshots/step_{idx}_{int(time.time())}.png"
                try:
                    page.screenshot(path=screenshot_filename)
                    step_screenshot = screenshot_filename
                except Exception:
                    pass

                steps_log.append({
                    "instruction": step,
                    "action": action_name,
                    "rationale": rationale,
                    "success": success,
                    "screenshot": step_screenshot,
                    "duration_ms": round((time.time() - step_start) * 1000, 2)
                })

                if not success:
                    overall_passed = False
                    console.print(f"[bold red]❌ Step failed:[/bold red] '{step}'")
                    break

            # Final screenshot
            try:
                page.screenshot(path="final_result.png")
            except Exception:
                pass

            browser.close()

        total_duration = (time.time() - start_time) * 1000
        report_path = self.reporter.generate(title, steps_log, overall_passed, total_duration)

        status_text = "[bold green]PASSED[/bold green]" if overall_passed else "[bold red]FAILED[/bold red]"
        console.print(Panel.fit(
            f"Test Result: {status_text}\n"
            f"HTML Report: [cyan]{report_path}[/cyan]\n"
            f"Total Duration: {round(total_duration / 1000, 2)}s",
            border_style="green" if overall_passed else "red"
        ))

        return overall_passed


def from_nav_url(url: str, reasoning: str):
    from core.models import BrowserAction, ActionType
    return BrowserAction(action_type=ActionType.NAVIGATE, value=url, reasoning=reasoning)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI Natural Language Browser Test Runner")
    parser.add_argument(
        "--site",
        choices=["phptravels", "cloudqa", "saucedemo"],
        default="phptravels",
        help="Predefined test scenario to run (default: phptravels)"
    )
    parser.add_argument(
        "instruction",
        nargs="?",
        default=None,
        help="Optional custom natural language test instruction to execute against any website"
    )
    args = parser.parse_args()

    runner = AITestRunner()

    if args.instruction:
        # Custom plain English instruction entered by the user
        runner.run_scenario(args.instruction, title="Custom Website Scenario")

    elif args.site == "cloudqa":
        cloudqa_instruction = (
            "Go to https://app.cloudqa.io/home/AutomationPracticeForm, "
            "Type Ajay into First Name, "
            "Type Gollapudi into Last Name, "
            "Select Male for gender, "
            "Choose India in State dropdown, "
            "Type test@example.com into Email"
        )
        runner.run_scenario(cloudqa_instruction, title="CloudQA Practice Form Automation")

    elif args.site == "saucedemo":
        saucedemo_instruction = (
            "Go to https://www.saucedemo.com, "
            "Type standard_user into Username, "
            "Type secret_sauce into Password, "
            "Click Login, "
            "Verify URL contains /inventory.html"
        )
        runner.run_scenario(saucedemo_instruction, title="SauceDemo E-Commerce Flow")

    else:
        # Default: PHPTravels Customer Authentication
        phptravels_instruction = (
            "Go to https://phptravels.net/login, "
            "Type user@phptravels.com into Email Address, "
            "Type demouser into Password, "
            "Check Remember Me, "
            "Click Sign In to your account"
        )
        runner.run_scenario(phptravels_instruction, title="PHPTravels Customer Authentication")
