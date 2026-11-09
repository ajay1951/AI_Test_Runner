# 🤖 AI Test Runner: Natural Language to Browser Automation

An intelligent, autonomous test automation system that converts plain-English test instructions into validated, executable browser automation using **Playwright**, **Groq LLM Planner (`openai/gpt-oss-20b`)**, dynamic semantic DOM tagging, accessibility locators, and strict observable-state assertions.

Built for the **CloudQA Senior AI Automation Architect & SDET** technical assessment (Task 2).

---

## 🏗️ Architecture & Pipeline

```text
[Plain English Natural Language Prompt]
                  │
                  ▼
   [Two-Tier Macro-Goal Decomposer] ──► Decomposes compound intents into atomic actions
                  │
                  ▼
        [Live Playwright Browser] ──► Navigates & Injects Synthetic AI IDs ([data-ai-id='ref_X'])
                  │
                  ▼
       [Semantic DOM Extractor] ──► Extracts compact JSON snapshot (roles, labels, aria, bounds)
                  │
                  ▼
      [Hybrid AI / Strict LLM Planner] ──► Groq API (openai/gpt-oss-20b default)
                  │                         Strict Mode (--strict-llm / PLANNER_STRICT=true)
                  │                         Zero silent fallback in strict mode
                  │                         Records planner_type ("llm" vs "deterministic_heuristic"),
                  │                         model ("openai/gpt-oss-20b"), and fallback_used (bool)
                  ▼
     [Compatibility & Guardrails Engine] ──► Validates tag compatibility (rejects fill on non-editable)
                  │                         Scans for destructive modals (prevents auto-deletion)
                  │                         Pydantic schema validation & injection protection
                  ▼
       [Bounded 3-Attempt Executor] ──► Progressive backoff (0.4s * attempt) for transient hydration
                  │                     Multi-tier semantic locators (Role -> Label -> Placeholder)
                  ▼
     [Observable-State Assertions] ──► Decouples action success from state verification
                  │                     Zero-assertion workflows strictly rejected (FAILED NO ASSERTIONS)
                  ▼
      [Executive Reporting Engine] ──► Credential masking (********), HTML timeline, machine JSON
```

---

## 🌟 Key Engineering Capabilities

1. **Two-Tier Natural Language Decomposition**: Decomposes high-level compound macro-goals (e.g., *"Open PHPTravels, log in as customer, and verify the dashboard appears"*) into generic, site-agnostic semantic actions without hardcoding domain-specific selectors.
2. **Dynamic Semantic DOM Tagging**: Injects lightweight, transient `data-ai-id='ref_X'` attributes into visible, interactable elements (`<input>`, `<button>`, `<select>`, `<a>`), extracting associated labels, placeholders, ARIA roles, and bounding boxes into a compact payload (<3KB).
3. **Groq LLM Integration with Strict / Hybrid Modes**: Powered by `openai/gpt-oss-20b` (configurable via `GROQ_MODEL`). Supports both **hybrid mode** (graceful heuristic tie-breaker) and **strict LLM mode** (`--strict-llm` / `PLANNER_STRICT=true`) where silent heuristic fallback is completely forbidden.
4. **Transparent Planner Attribution**: Every single executed step tracks `planner_type` (`"llm"` vs `"deterministic_heuristic"`), `model`, and `fallback_used: bool` across CLI telemetry, JSON logs, and executive HTML dashboards.
5. **Pre-flight LLM Healthcheck CLI**: Built-in `python runner.py --check-llm` command tests Groq API authentication, model accessibility, and latency within ~2 seconds, writing diagnostics to `reports/llm_connectivity.json`.
6. **Action-Element Tag Compatibility Guard**: Validates element types prior to interaction. Rejects attempts to `fill` non-editable tags (`<button>`, `<span>`) with fast-failing `TypeError` without futile retries.
7. **Bounded 3-Attempt Hydration Retries**: Employs controlled 3-attempt retries with progressive backoff (`0.4s * attempt`) to handle asynchronous DOM re-rendering and network hydration.
8. **Strict Observable-State Assertions**: Interaction success is decoupled from test status. Tests pass only when actual DOM visibility, container text, or URL redirects match expectations. Workflows with 0 assertions fail with `FAILED (NO ASSERTIONS)`.
9. **Universal Credential Sanitization**: Passwords and sensitive tokens are automatically masked (`********`) across console logs, JSON reports, and HTML report dashboards via Pydantic model validators.
10. **Multi-Site Generalization**: Verified across 3 distinct public production domains: **SauceDemo**, **The Internet Herokuapp**, and **PHPTravels** (strict LLM customer auth).

---

## 🚀 Quickstart & Setup

### 1. Prerequisites
- Python 3.12+ installed
- Chromium browser binaries for Playwright

### 2. Installation
```powershell
# Navigate to repository root
cd AI_Test_Runner

# Activate virtual environment (if using venv)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser binaries
playwright install chromium
```

### 3. Environment Configuration
Create or configure `.env` (see `.env.example`):
```ini
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-20b
PLANNER_MODE=hybrid
PLANNER_STRICT=false
HEADLESS=true
TIMEOUT_MS=15000
```
> **Note:** The default model is `openai/gpt-oss-20b`. Additional verified models include `qwen/qwen3.8-27b`, `allam-2-7b`, and `openai/gpt-oss-120b`. If `GROQ_API_KEY` is omitted, the system falls back gracefully to the multi-tier deterministic heuristic engine unless `--strict-llm` is asserted.

### 4. Verify LLM Connectivity
```powershell
python runner.py --check-llm
```
*Outputs structured JSON diagnostic to `reports/llm_connectivity.json`, validating authentication and model accessibility.*

---

## 🧪 Automated Test Suite (29 Tests)

Run the complete 29-test automated verification suite (covering LLM planner unit/mock tests, parsing, schema validation, negative assertions, and live headless browser tests):

```powershell
# Run all 29 automated tests with verbose output:
python -m pytest -v
```

### Verified Test Breakdown:
- **`tests/test_llm_planner.py` (12 tests):**
  - `test_check_connectivity_success`: Successful Groq healthcheck with latency.
  - `test_check_connectivity_model_not_found`: Graceful HTTP 404 detection.
  - `test_check_connectivity_auth_failure`: HTTP 401 handling without secret leakage.
  - `test_check_connectivity_rate_limit`: HTTP 429 rate limit diagnostics.
  - `test_plan_instruction_sequence_invalid_json_fallback_hybrid`: Hybrid recovery from invalid JSON.
  - `test_plan_instruction_sequence_invalid_json_strict_mode`: Strict mode raises `RuntimeError` immediately.
  - `test_plan_instruction_sequence_pydantic_validation_failure`: Rejects malformed action schemas.
  - `test_plan_instruction_sequence_unsupported_action`: Rejects unapproved action types.
  - `test_plan_step_strict_mode_no_fallback`: Strict mode DOM step planning aborts on LLM failure.
  - `test_plan_step_hybrid_fallback_attribution`: Proper provenance attribution when falling back.
  - `test_plan_instruction_sequence_success_with_groq`: Full sequence generation with provenance.
  - `test_phptravels_llm_workflow_simulation`: End-to-end simulated PHPTravels flow with password masking.
- **`tests/test_scenarios.py` (3 tests):**
  - `test_parser_clause_splitting`: Multi-clause prompt parsing.
  - `test_unseen_instructions_suite`: 10 diverse unseen sentence structures.
  - `test_phptravels_scenario_parsing`: Full authentication workflow sequencing.
- **`tests/test_e2e_browser.py` (14 tests):**
  - `test_e2e_real_browser_navigation_and_assertion`: Chromium navigation & title/visibility check.
  - `test_e2e_negative_assertion_fails_correctly`: Strict failure on missing state.
  - `test_e2e_missing_element_handled_gracefully`: Absent target diagnostic handling.
  - `test_e2e_credential_redaction_in_reports`: Plaintext password masking (`********`).
  - `test_e2e_macro_goal_expansion`: Macro-goal decomposition into sensitive actions.
  - `test_e2e_empty_assertion_list_fails_correctly`: Zero-assertion false pass guard.
  - `test_e2e_ambiguous_element_detection`: Candidate tie-breaking and ambiguity detection.
  - `test_e2e_destructive_modal_safety`: Prevents auto-dismissal of destructive dialogs.
  - `test_e2e_stale_dom_reference_recovery`: Resilient recovery via accessibility locators.
  - `test_e2e_malformed_llm_plan_rejected`: Rejection of script/injection payloads.
  - `test_e2e_third_website_workflow`: Live execution on The Internet Herokuapp.
  - `test_e2e_fill_non_editable_element_rejected`: Compatibility rejection of non-editable fill.
  - `test_e2e_incorrect_expected_text_fails`: Text assertion mismatch strict failure.
  - `test_e2e_incorrect_expected_url_fails`: URL assertion mismatch strict failure.

---

## 🌐 Running Live Multi-Site Workflows

Execute live autonomous workflows across multiple production demo sites:

### 1. PHPTravels Live Strict LLM Authentication Workflow
```powershell
# Run using strict LLM mode with openai/gpt-oss-20b:
python runner.py --strict-llm "Go to https://phptravels.net/login, Type user@phptravels.com into email, Type demouser into password, Click Login, Verify that URL contains /dashboard, Verify that title is Dashboard, Verify that Account Summary is visible"
```
*Or run pre-configured site:*
```powershell
python runner.py --site phptravels --strict-llm
```
*Navigates live `phptravels.net`, generates 100% of actions via `openai/gpt-oss-20b` (`fallback_used: False`), fills credentials, submits login, verifies URL contains `/dashboard`, title equals `'Dashboard'`, and observable landmark `'Account Summary'` heading is visible.*
*Evidence generated: `reports/phptravels_llm_e2e.json` and `reports/phptravels_llm_e2e.html`.*

### 2. SauceDemo E-Commerce Site
```powershell
python runner.py --site saucedemo
```
*Navigates, authenticates `standard_user`, verifies URL contains `/inventory.html`, redacts password, and outputs report.*

### 3. The Internet Herokuapp Login
```powershell
python runner.py "Go to https://the-internet.herokuapp.com/login, Type tomsmith into Username, Type SuperSecretPassword! into Password, Click Login, Verify that Secure Area is visible"
```
*Navigates, fills credentials, clicks login, verifies Secure Area heading visibility, and redacts password.*

### 4. Custom Unseen Prompt
```powershell
python runner.py "Go to https://example.com, Verify that Example Domain is visible, Verify title contains Example Domain"
```

---

## 📊 Sample Machine JSON Report Schema

Every run generates structured JSON metrics under `reports/report_<timestamp>.json` (or designated report file) with full planner provenance, retry count, and password masking:

```json
{
  "title": "PHPTravels Customer Authentication - Strict LLM Mode",
  "timestamp": "2026-11-09 13:05:42",
  "passed": true,
  "duration_sec": 58.34,
  "passed_count": 7,
  "failed_count": 0,
  "steps": [
    {
      "instruction": "Go to https://phptravels.net/login",
      "action": "navigate",
      "planner_type": "llm",
      "model": "openai/gpt-oss-20b",
      "fallback_used": false,
      "attempts": 1,
      "rationale": "Navigate to the PHPTravels login page",
      "success": true,
      "assertion_result": null,
      "error": null,
      "screenshot": "screenshots/phptravels_llm_step_1_navigate.png",
      "duration_ms": 11420.30
    },
    {
      "instruction": "Type ******** into password",
      "action": "fill",
      "planner_type": "llm",
      "model": "openai/gpt-oss-20b",
      "fallback_used": false,
      "attempts": 1,
      "rationale": "Fill password credential",
      "success": true,
      "assertion_result": null,
      "error": null,
      "screenshot": "screenshots/phptravels_llm_step_3_fill_password.png",
      "duration_ms": 612.45
    },
    {
      "instruction": "Verify that URL contains /dashboard",
      "action": "assert_url",
      "planner_type": "llm",
      "model": "openai/gpt-oss-20b",
      "fallback_used": false,
      "attempts": 1,
      "rationale": "Verify user redirected to dashboard",
      "success": true,
      "assertion_result": {
        "type": "URL",
        "expected": "/dashboard",
        "actual": "https://phptravels.net/dashboard",
        "passed": true
      },
      "error": null,
      "screenshot": "screenshots/phptravels_llm_step_5_assert_url.png",
      "duration_ms": 48.20
    }
  ]
}
```

---

## 📂 Deliverables Included
- **[FINAL_AUDIT_REPORT.md](FINAL_AUDIT_REPORT.md)**: Forensic engineering audit report, severity-classified findings taxonomy (C1-C3, H1-H2, M1-M3, L1-L2), strict LLM validation evidence, and 14-scenario compliance scorecard.
- **[APPROACH_AND_LIMITATIONS.md](APPROACH_AND_LIMITATIONS.md)**: Deep dive on LLM planning vs deterministic fallback, strict mode provenance, multi-tier locators, bounded 3-attempt retries, element compatibility validation, and real-world environment boundaries.
- **[DEMO_SCRIPT.md](DEMO_SCRIPT.md)**: 5-minute video recording walkthrough script covering setup, 29/29 test execution, LLM healthcheck, strict LLM planning, and live multi-site runs.
