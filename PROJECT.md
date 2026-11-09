# Project: AI_Test_Runner Task 2 Remediation & Submission Readiness

## Architecture
- Two-Tier Parser & Macro-Goal Decomposition (`core/test_parser.py`)
- Live Browser Automation & DOM Extraction (`core/dom_extractor.py`, `core/action_executor.py`)
- Planner Attribution (`core/models.py`, `core/llm_planner.py`): tracks `groq_llama_3.3` vs `deterministic_heuristic`
- Compatibility & Retry Engine (`core/action_executor.py`): element tag validation + bounded 3x retries
- Executive Reporter (`core/reporter.py`): credential redaction, observable assertions, structured logs/HTML/JSON
- CLI & Multi-Site Runner (`runner.py`)
- Automated Test Suite (`tests/test_e2e_browser.py`, `tests/test_scenarios.py`)

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Planner Attribution in Models | Add `planner_type` to `BrowserAction` and plan step outputs | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Planner Attribution in LLM/Heuristic | Explicitly set `groq_llama_3.3` vs `deterministic_heuristic` in `core/llm_planner.py`, `runner.py`, and logs | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Action Compatibility Validation | Validate FILL targets editable tags (`<input>`, `<textarea>`, `contenteditable`) and CLICK targets interactive elements before interaction | M1 | ORIGINAL_REQUEST §R2 |
| 4 | Controlled 3-Attempt Retries | Implement bounded 3-attempt retry loop with backoff for transient DOM hydration in `core/action_executor.py` | M1 | ORIGINAL_REQUEST §R2 |
| 5 | Test Fill Non-Editable Element | `test_e2e_fill_non_editable_element_rejected` in `tests/test_e2e_browser.py` | M2 | ORIGINAL_REQUEST §R3 |
| 6 | Test Incorrect Expected Text Fails | `test_e2e_incorrect_expected_text_fails` in `tests/test_e2e_browser.py` | M2 | ORIGINAL_REQUEST §R3 |
| 7 | Test Incorrect Expected URL Fails | `test_e2e_incorrect_expected_url_fails` in `tests/test_e2e_browser.py` | M2 | ORIGINAL_REQUEST §R3 |
| 8 | 100% Automated Test Pass Rate | Ensure all 17 automated tests pass via `py -m pytest -v` (0 failures, 0 errors) | M2 | ORIGINAL_REQUEST §R3 |
| 9 | SauceDemo Live Execution | Run `py runner.py --site saucedemo`, verify auth and pass report | M3 | ORIGINAL_REQUEST §R4 |
| 10 | The Internet Herokuapp Live Execution | Run `py runner.py "..."` on Herokuapp login, verify auth and pass report | M3 | ORIGINAL_REQUEST §R4 |
| 11 | PHPTravels Live Execution | Run `py runner.py --site phptravels`, verify modal handling & demo expiration report | M3 | ORIGINAL_REQUEST §R4 |
| 12 | Final Audit Report Deliverable | Create `FINAL_AUDIT_REPORT.md` at root with severity-classified findings (Critical, High, Medium, Low) | M4 | ORIGINAL_REQUEST §R5 |
| 13 | Documentation Deliverables | Update `README.md`, `APPROACH_AND_LIMITATIONS.md`, `DEMO_SCRIPT.md`, `walkthrough.md` | M4 | ORIGINAL_REQUEST §R5 |
| 14 | Git Submission Cleanliness | Verify `git status` and `git diff`, ensure no leaked secrets/scratch files, wait for explicit approval before commit/push | M5 | ORIGINAL_REQUEST §R6 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M0 | Survey & Codebase Baseline | Survey existing implementation, tests, and configuration | none | DONE |
| M1 | Planner Attribution & Action Compatibility/Retry | `core/models.py`, `core/llm_planner.py`, `core/action_executor.py`, `core/reporter.py`, `runner.py` | M0 | DONE |
| M2 | Automated Test Suite Expansion (17 tests) | `tests/test_e2e_browser.py`, run `pytest -v` to ensure 17/17 pass | M1 | IN_PROGRESS |
| M3 | Live Multi-Site Workflow Execution | Run live workflows for SauceDemo, Herokuapp, PHPTravels; capture artifacts | M2 | PLANNED |
| M4 | Documentation & Audit Deliverables | Create `FINAL_AUDIT_REPORT.md`, update `README.md`, `APPROACH_AND_LIMITATIONS.md`, etc. | M3 | PLANNED |
| M5 | Git Submission Hygiene & Verification | Verify git status, diff, prepare clean summary report | M4 | PLANNED |

## Interface Contracts
### `core.models.BrowserAction`
- Fields:
  - `action_type`: `ActionType`
  - `target_ref`: Optional[str]
  - `selector`: Optional[SemanticSelector]
  - `value`: Optional[str]
  - `expected_text`: Optional[str]
  - `operator`: AssertionOperator
  - `timeout_ms`: int
  - `is_sensitive`: bool
  - `planner_type`: str (`"groq_llama_3.3"` or `"deterministic_heuristic"`, default `"deterministic_heuristic"`)
  - `reasoning`: Optional[str]

### `core.action_executor.ActionExecutor`
- `_validate_element_compatibility(loc, act_type: str)`:
  - If `act_type == "fill"`: verifies element is `input`, `textarea`, or `contenteditable`. Raises `TypeError(f"Incompatible target: Cannot fill non-editable element <{tag}>")`.
  - If `act_type == "click"`: verifies element is not disabled (`disabled` or `aria-disabled="true"`). Raises `ValueError`.
- `execute(action: BrowserAction, max_attempts: int = 3) -> Dict[str, Any]`:
  - Implements bounded 3-attempt loop with linear/exponential backoff for transient DOM hydration.
  - Fails fast on `TypeError` (compatibility violations).
  - Returns dict with `success`, `error`, `assertion_result`, `action_type`, `attempts`.

### `runner.py` & `core.reporter.TestReporter`
- `runner.py`: Copies `planner_type` from `resolved_action` to `action`. Logs `planner_type` and `attempts` into `steps_log`.
- `reporter.py`: Displays `planner_type` and attempts count badge in HTML report and records them in JSON report.

## Code Layout
- `core/`
  - `models.py`: Pydantic data schemas (`BrowserAction`, `ExecutionReport`, etc.)
  - `test_parser.py`: Two-tier natural language instruction parser
  - `dom_extractor.py`: Semantic DOM extractor and ARIA tree generator
  - `llm_planner.py`: Groq LLM + Deterministic Heuristic Planner
  - `action_executor.py`: Playwright interaction executor with compatibility guard and retry loop
  - `reporter.py`: Executive reporting, credential redaction, HTML/JSON output
- `tests/`
  - `test_scenarios.py`: Parser and scenario unit tests (3 tests)
  - `test_e2e_browser.py`: End-to-end browser tests (target: 14 tests, total 17)
- `runner.py`: CLI entry point for test execution
- Root docs: `README.md`, `APPROACH_AND_LIMITATIONS.md`, `DEMO_SCRIPT.md`, `FINAL_AUDIT_REPORT.md`
