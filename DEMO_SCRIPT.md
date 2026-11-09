# 5-Minute Video Recording Demonstration Script

**Project:** Autonomous AI Test Runner (Task 2)
**Author:** Senior AI Automation Architect & SDET Engineer
**Target Submission:** CloudQA Practical Technical Assessment (Task 2)
**Total Video Duration:** Exactly ~5 minutes (300 seconds)

---

## ⏱️ Video Walkthrough Breakdown

| Timestamp | Presentation Phase | On-Screen Visuals | Spoken Narrative & Actions |
|:---|:---|:---|:---|
| **0:00 - 0:40** | **1. Introduction & The SDET Challenge** | Open VS Code displaying the root `AI_Test_Runner` repository structure. | *"Hello CloudQA team! I am pleased to present Task 2: Turning unscripted plain-English test instructions into autonomous, verifiable browser automation. Traditional automation breaks because CSS classes and XPaths are brittle. Naive LLM approaches fail because they hallucinate selectors, click arbitrarily, or produce false passes when no assertion occurred. Our system solves these problems with a hybrid AI-DOM architecture, strict observable-state assertions, and bounded retry resilience."* |
| **0:40 - 1:20** | **2. Architecture, Strict LLM Mode & Security Guardrails** | Highlight `core/` modules: `dom_extractor.py`, `llm_planner.py`, `action_executor.py`, `models.py`. | *"Here in `core/`, our pipeline works in discrete stages. `dom_extractor.py` injects lightweight synthetic tags `data-ai-id='ref_X'` into visible interactive elements and extracts labels, roles, and placeholders into a compact JSON snapshot under 3 kilobytes. In `llm_planner.py`, we integrate Groq with `openai/gpt-oss-20b`, featuring a strict LLM mode that guarantees zero silent fallback. Crucially, every action is validated by our tag compatibility guard—preventing invalid operations like typing into buttons. Plus, sensitive credentials like passwords are automatically masked with asterisks across all logs and reports."* |
| **1:20 - 1:50** | **3. Pre-flight LLM Healthcheck** | Execute `python runner.py --check-llm` in terminal and display output. | *"Before test execution, let's verify our LLM gateway using our built-in healthcheck command: `python runner.py --check-llm`. In just two seconds, it confirms Groq API connectivity, validates model accessibility for `openai/gpt-oss-20b`, records roundtrip latency, and saves structured diagnostics to `reports/llm_connectivity.json`."* |
| **1:50 - 2:45** | **4. Automated Test Suite Execution (29/29 Tests)** | Open terminal and execute: `python -m pytest -v`. Let tests run. | *"Now let's run our comprehensive automated test suite. Watch the terminal as all 29 automated tests execute across LLM planner mocks, error handling, prompt parsing, schema protection, negative assertion integrity, stale reference recovery, and real headless Chromium browser navigation. Notice tests specifically verifying that workflows without assertions strictly fail—preventing false passes. All 29 tests pass with 100% compliance in under 130 seconds."* |
| **2:45 - 3:55** | **5. Live Multi-Site Demonstration & Strict LLM Execution** | Terminal execution of live sites: (1) PHPTravels Strict LLM, (2) SauceDemo, (3) The Internet Herokuapp. | *"A core requirement of this assessment is proving the engine operates autonomously across multiple real-world domains. Let's run a full customer authentication workflow on PHPTravels in strict LLM mode: `python runner.py --site phptravels --strict-llm`. Notice that 100% of actions are planned by `openai/gpt-oss-20b` with zero fallback. The browser navigates, locates email and password fields, redacts the password, signs in, and verifies the redirect to `/dashboard`, the page Title, and the visible 'Account Summary' heading. We also have live cross-site workflows on SauceDemo and The Internet Herokuapp demonstrating generalizability without hardcoded site selectors."* |
| **3:55 - 4:35** | **6. Executive HTML & JSON Telemetry** | Open generated report in browser: `reports/phptravels_llm_e2e.html` and inspect JSON. | *"After every run, the runner compiles an executive HTML and structured machine JSON report. Notice the key SDET metrics: step-by-step elapsed milliseconds, captured screenshots, clear badges showing planner attribution—distinguishing whether the LLM or our deterministic heuristic planned the action—the specific model name, `fallback_used: false`, retry attempt counts, and strict masking of passwords."* |
| **4:35 - 5:00** | **7. Limitations & Wrap-Up** | Display `APPROACH_AND_LIMITATIONS.md` and `FINAL_AUDIT_REPORT.md`. | *"In our engineering documentation, we detail our multi-tier fallback hierarchy and discuss real-world constraints such as cross-origin iframes, HTML5 canvas components, and anti-bot turnstiles, along with enterprise production mitigations. All deliverables are complete and verified. Thank you for your time and consideration!"* |

---

## ⌨️ Exact CLI Commands to Execute During Recording

Keep these exact commands ready to paste into your terminal during the video recording:

```powershell
# Step 1: Run pre-flight LLM connectivity check:
python runner.py --check-llm

# Step 2: Run the full 29-test automated verification suite:
python -m pytest -v

# Step 3: Run live PHPTravels customer authentication flow in Strict LLM mode:
python runner.py --site phptravels --strict-llm

# Step 4: Run live SauceDemo E-Commerce authentication flow:
python runner.py --site saucedemo

# Step 5: Run live custom workflow against The Internet Herokuapp:
python runner.py "Go to https://the-internet.herokuapp.com/login, Type tomsmith into Username, Type SuperSecretPassword! into Password, Click Login, Verify that Secure Area is visible"

# Step 6: Open the generated executive HTML reports in your browser:
# Open reports/phptravels_llm_e2e.html in Chrome or Edge
```
