"""
Main AI Test Runner.
Executes natural language test cases against real browser instances using Playwright,
two-tier macro-goal planning, dynamic AI DOM inspection, and automated report generation.
Supports genuine LLM planning with Groq, explicit planner provenance, and strict LLM mode.
"""

import os
import sys
import time
import json
import argparse
from typing import Union, List, Optional
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
    def __init__(
        self,
        headless: bool = config.HEADLESS,
        slow_mo: int = 50,
        strict_llm: bool = config.PLANNER_STRICT,
        model: Optional[str] = None
    ):
        self.strict_llm = strict_llm
        self.model = model or config.GROQ_MODEL
        self.planner = LLMPlanner(strict=strict_llm, model=self.model)
        self.reporter = TestReporter(output_dir="reports")
        self.headless = headless
        self.slow_mo = slow_mo
        os.makedirs("screenshots", exist_ok=True)
        os.makedirs("reports", exist_ok=True)

    def check_llm(self) -> dict:
        """Runs model connectivity and accessibility test."""
        res = self.planner.check_connectivity()
        status_color = "green" if res.get("accessible") else "red"
        console.print(Panel.fit(
            f"[bold {status_color}]LLM Connectivity Check: {res.get('status')}[/bold {status_color}]\n"
            f"[cyan]Model:[/cyan] {res.get('model')}\n"
            f"[cyan]Accessible:[/cyan] {res.get('accessible')}\n"
            f"[cyan]Latency:[/cyan] {res.get('latency_ms')}ms\n"
            f"[dim]{res.get('message')}[/dim]",
            border_style=status_color
        ))

        # Save JSON artifact
        json_path = os.path.join("reports", "llm_connectivity.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)
        console.print(f"Saved connectivity report: [cyan]{json_path}[/cyan]")
        return res

    def run_scenario(self, instructions: Union[str, List[str]], title: str = "Natural Language Test Scenario") -> bool:
        """
        Runs a test scenario given either a single high-level plain English instruction
        or a list of atomic test steps.
        """
        start_time = time.time()
        combined_text = instructions if isinstance(instructions, str) else " ".join(instructions)
        target_url = extract_url_from_text(combined_text)

        # Plan actions: in strict LLM mode or when PLANNER_MODE='llm', query LLM
        if self.strict_llm or config.PLANNER_MODE == "llm":
            console.print(f"[bold cyan]🤖 Using Genuine LLM Sequence Planner ({self.planner.model})...[/bold cyan]")
            planned_actions = self.planner.plan_instruction_sequence(combined_text, base_url=target_url)
        else:
            # Two-tier expansion: decompose macro-goals into validated actions
            if isinstance(instructions, str):
                planned_actions = parse_instruction_to_actions(instructions, base_url=target_url)
            else:
                planned_actions = []
                for item in instructions:
                    planned_actions.extend(parse_instruction_to_actions(item, base_url=target_url))

        planner_label = f"LLM ({self.planner.model})" if (self.strict_llm or config.PLANNER_MODE == "llm") else "Hybrid (LLM / Heuristic Engine)"
        console.print(Panel.fit(
            f"[bold green]AI Natural Language Test Runner[/bold green]\n"
            f"[cyan]Scenario:[/cyan] {title}\n"
            f"[cyan]Actions Planned:[/cyan] {len(planned_actions)}\n"
            f"[dim]Planner Engine: {planner_label} | Strict LLM: {self.strict_llm}[/dim]",
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
                    # Resolve step via planner (LLM in strict mode, or hybrid)
                    resolved_action = self.planner.plan_step(step_desc, dom, page.url)
                    action.planner_type = getattr(resolved_action, "planner_type", "deterministic_heuristic")
                    action.model = getattr(resolved_action, "model", None)
                    action.fallback_used = getattr(resolved_action, "fallback_used", False)
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
                    "planner_type": getattr(action, "planner_type", "deterministic_heuristic"),
                    "model": getattr(action, "model", None),
                    "fallback_used": getattr(action, "fallback_used", False),
                    "attempts": exec_result.get("attempts", 1),
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

            # Record any auto-dismissed informational modals into telemetry for complete observability
            for m in executor.dismissed_modals:
                steps_log.insert(0, {
                    "instruction": f"Auto-dismissed informational modal via '{m['button_text']}'",
                    "action": "dismiss_overlay",
                    "planner_type": "deterministic_heuristic",
                    "model": None,
                    "fallback_used": False,
                    "attempts": 1,
                    "rationale": "Safety dismissal of non-intrusive demo disclaimer/cookie notice",
                    "success": True,
                    "assertion_result": None,
                    "error": None,
                    "screenshot": None,
                    "duration_ms": 300.0
                })

            # Strict SDET Verification: Action execution vs Expected Outcome
            assertion_steps = [s for s in steps_log if s.get("assertion_result") is not None]
            if overall_passed and len(assertion_steps) == 0:
                console.print(
                    "[bold yellow]⚠️ Verification Warning: Scenario executed actions successfully, but contains ZERO assertions. "
                    "Cannot mark test as PASSED without observable state verification.[/bold yellow]"
                )
                overall_passed = False
                status_text = "[bold yellow]FAILED (NO ASSERTIONS)[/bold yellow]"
            elif overall_passed:
                status_text = "[bold green]PASSED[/bold green]"
            else:
                status_text = "[bold red]FAILED[/bold red]"

            # Final screenshot
            try:
                page.screenshot(path="final_result.png")
            except Exception:
                pass

            browser.close()

        total_duration = (time.time() - start_time) * 1000
        report_path = self.reporter.generate(title, steps_log, overall_passed, total_duration)

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
        "--check-llm",
        action="store_true",
        help="Verify Groq API connectivity and model accessibility"
    )
    parser.add_argument(
        "--strict-llm",
        action="store_true",
        help="Enforce strict LLM planning mode with zero silent fallback"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override Groq model ID (default from config: openai/gpt-oss-20b)"
    )
    parser.add_argument(
        "instruction",
        nargs="?",
        default=None,
        help="Optional custom natural language test instruction to execute against any website"
    )
    args = parser.parse_args()

    runner = AITestRunner(strict_llm=args.strict_llm, model=args.model)

    if args.check_llm:
        res = runner.check_llm()
        sys.exit(0 if res.get("accessible") else 1)

    elif args.instruction:
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
