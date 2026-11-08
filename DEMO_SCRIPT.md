# 5-Minute Video Recording Demo Script

Use this script to guide your 5-minute screen recording for the CloudQA submission.

---

### Timing Breakdown (Total: ~5 minutes)

| Timestamp | Topic / Section | Visual on Screen | What to Say / Demonstrate |
| :--- | :--- | :--- | :--- |
| **0:00 - 0:45** | **Introduction & Problem Statement** | Open VS Code / IDE showing `AI_Test_Runner` folder structure. | *"Hello CloudQA team! I'm presenting Task 2: Turning plain-English test cases into autonomous browser automation. Our goal is to accept unscripted natural language, parse actions, locate elements without hardcoded selectors, and report PASS/FAIL results."* |
| **0:45 - 1:45** | **Architecture Overview** | Show `core/` folder: `dom_extractor.py`, `llm_planner.py`, `action_executor.py`. | *"Instead of fragile CSS selectors, we use a hybrid AI-DOM approach. `dom_extractor.py` injects synthetic tags `data-ai-id='ref_X'` into visible interactive elements and extracts labels, roles, and placeholders. `llm_planner.py` uses Groq LLaMA 3.3 to select the right element, backed by a deterministic semantic fallback so tests never crash even without API keys."* |
| **1:45 - 2:45** | **PHPTravels Execution (Live Browser)** | Run `python runner.py` in the terminal. Watch Chromium launch and execute live. | *"Now let's run the primary requirement: the PHPTravels demo site. In `runner.py`, we supply the instruction: 'Go to phptravels.net/login, type email, type password, check remember me, and click Sign In'. Notice Playwright launching, identifying the inputs dynamically via AI tags, clicking the login button, and capturing step screenshots."* |
| **2:45 - 3:30** | **Second Website & Unseen Generalization** | Run `pytest tests/test_scenarios.py -v`. | *"A key assessment requirement is proving that nothing is hardcoded to PHPTravels. Here, our pytest suite tests 10 diverse unseen natural-language cases and a second target website (CloudQA Automation Practice Form). All 3 test suites pass cleanly in seconds."* |
| **3:30 - 4:15** | **Reports & Failure Diagnostics** | Open generated `reports/report_*.html` in the browser. | *"After execution, the system generates an executive HTML and JSON report. It displays overall PASS status, step-by-step breakdown, execution latency in milliseconds, rationale, and captured screenshots."* |
| **4:15 - 5:00** | **Approach, Limitations & Wrap-Up** | Show `APPROACH_AND_LIMITATIONS.md`. | *"In our engineering notes, we documented our multi-tier fallback hierarchy and known constraints such as cross-origin iframes and anti-bot turnstiles, along with enterprise mitigations. Thank you for your time, and I look forward to discussing this in the next round!"* |

---

### Commands to Run During the Video:
```powershell
# 1. Run the PHPTravels automation flow:
python runner.py

# 2. Run the automated pytest suite:
pytest tests/test_scenarios.py -v

# 3. View the generated HTML report:
# Double click the latest report in the reports/ folder in your browser
```

