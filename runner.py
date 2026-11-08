"""
Main AI Test Runner.
Executes natural language test cases against real browser instances using Playwright,
two-tier macro-goal planning, dynamic AI DOM inspection, and automated report generation.
"""

import os
import sys
import time
import argparse
from typing import Union, List
from playwright.sync_api import sync_playwright
from core.dom_extractor import DOMExtractor
from core.llm_planner import LLMPlanner
from core.action_executor import ActionExecutor
from core.test_parser import split_clauses, parse_instruction_to_actions, extract_url_from_text
from core.reporter import TestReporter
from core.models import ActionType, BrowserAction
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

        # Parse and decompose into structured action sequence
        target_url = extract_url_from_text(instructions if isinstance(instructions, str) else " ".join(instructions))
        
        # Two-tier expansion: decompose macro-goals (e.g. "log in as customer") into validated actions
        if isinstance(instructions, str):
            planned_actions = parse_instruction_to_actions(instructions, base_url=target_url)
        else:
            planned_actions = []
            for item in instructions:
                planned_actions.extend(parse_instruction_to_actions(item, base_url=target_url))

        console.print(Panel.fit(
            f"[bold green]AI Natural Language Test Runner[/bold green]\n"
            f"[cyan]Scenario:[/cyan] {title}\n"
            f"[cyan]Actions Planned:[/cyan] {len(planned_actions)}\n"
            f"[dim]Provider: Hybrid LLaMA 3.3 / Deterministic Multi-Tier Engine[/dim]",
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

            for idx, action in enumerate(planned_actions, 1):
                step_desc = action.reasoning or f"Step {idx}"
                console.print(f"\n[bold yellow]─── Step {idx}/{len(planned_actions)}: '{step_desc}' ───[/bold yellow]")
                step_start = time.time()
                step_screenshot = None

                # If action requires DOM element and has no ref yet, inspect live DOM
                if action.action_type in (ActionType.FILL, ActionType.CLICK, ActionType.CHECK, ActionType.SELECT, ActionType.RADIO, ActionType.HOVER):
                    executor._dismiss_overlays()
                    dom = DOMExtractor.get_interactive_tree(page)
                    # Re-plan with live DOM snapshot if needed
                    resolved_action = self.planner.plan_step(step_desc, dom, page.url)
                    if resolved_action.target_ref:
                        action.target_ref = resolved_action.target_ref

                # Execute action
                exec_result = executor.execute(action)
                success = exec_result.get("success", False)

                # Capture step screenshot
                screenshot_filename = f"screenshots/step_{idx}_{int(time.time())}.png"
                try:
                    page.screenshot(path=screenshot_filename)
                    step_screenshot = screenshot_filename
                except Exception:
                    pass

                steps_log.append({
                    "instruction": step_desc,
                    "action": action.action_type.value,
                    "rationale": action.reasoning or "",
                    "success": success,
                    "assertion_result": exec_result.get("assertion_result"),
                    "error": exec_result.get("error"),
                    "screenshot": step_screenshot,
                    "duration_ms": round((time.time() - step_start) * 1000, 2)
                })

                if not success:
                    overall_passed = False
                    console.print(f"[bold red]❌ Step failed:[/bold red] '{step_desc}'")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Natural Language Browser Test Runner")
    parser.add_argument(
        "--site",
        choices=["phptravels", "saucedemo"],
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
        runner.run_scenario(args.instruction, title="Custom Website Scenario")

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
        # Canonical high-level objective on PHPTravels
        phptravels_instruction = (
            "Open https://phptravels.net/login, "
            "Log in as a customer, "
            "Verify that customer dashboard is shown"
        )
        runner.run_scenario(phptravels_instruction, title="PHPTravels Customer Authentication")
