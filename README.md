# 🤖 AI Test Runner: Natural Language to Browser Automation

An intelligent, autonomous test automation system that converts plain-English test instructions into validated, executable browser automation using **Playwright**, **Groq (LLaMA 3.3)**, dynamic AI DOM tagging, and semantic accessibility locators.

Built for the **CloudQA Senior AI Automation Architect & SDET** technical assessment.

---

## 🏗️ Architecture & Pipeline

```text
[Plain English Test Case]
          │
          ▼
 [Clause Decomposer] ──► Splits compound sentences into sequential actions
          │
          ▼
 [Playwright Browser] ──► Navigates & Injects Synthetic AI IDs ([data-ai-id])
          │
          ▼
   [Live DOM Tree] ──► Captures interactive element snapshot (tag, text, labels, aria)
          │
          ▼
  [Hybrid AI Planner] ──► Groq LLaMA 3.3 (with zero-delay deterministic fallback)
          │
          ▼
 [Action Executor] ──► Multi-tier semantic locator & state verification
          │
          ▼
[Diagnostics & Reports] ──► Screenshots, JSON metrics, and standalone HTML reports
```

---

## 🌟 Key Features

1. **Natural Language Decomposition**: Takes high-level compound instructions (e.g., *"Open PHPTravels, log in as customer, and verify the dashboard is shown"*) and automatically sequences them into browser actions.
2. **Synthetic AI DOM Tagging**: Dynamically annotates interactive elements (`<input>`, `<button>`, `<select>`, `<a>`) with `data-ai-id='ref_X'`, extracting associated labels, placeholders, and roles into a compact JSON snapshot.
3. **Multi-Tier Semantic Locators**: Prioritizes accessible roles, associated labels, placeholders, and text over brittle dynamic CSS classes or fixed XPaths.
4. **Zero-Lockout Fallback**: Uses Groq LLaMA 3.3 for high-speed reasoning, with a deterministic offline heuristic parser so tests never crash even if an API key is absent.
5. **Multi-Site Generalization**: Validated against both **PHPTravels demo** (`https://phptravels.net`) and a completely distinct second website (**SauceDemo E-Commerce** `https://www.saucedemo.com`).
6. **Executive Reporting**: Generates interactive HTML reports with step timelines, elapsed milliseconds, and step screenshots.

---

## 🚀 Quickstart & Setup

### 1. Prerequisites
- Python 3.12+ installed
- Chromium browser binaries for Playwright

### 2. Installation
```powershell
# Clone or navigate to the repository
cd AI_Test_Runner

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser binaries (if not already installed)
playwright install chromium
```

### 3. Environment Configuration
Create a `.env` file (or edit the existing one):
```ini
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
HEADLESS=false
TIMEOUT_MS=15000
```
> **Note:** If `GROQ_API_KEY` is not provided, the system automatically runs using the deterministic semantic fallback engine.

---

## 🧪 Running Tests Across Different Demo Sites

### 1. PHPTravels Demo Site (Default)
```powershell
python runner.py
# or explicitly:
python runner.py --site phptravels
```

### 2. SauceDemo E-Commerce Site (Second Demo Site)
```powershell
python runner.py --site saucedemo
```

### 3. Any Custom Unseen Website on the Fly
You can pass any plain-English instruction directly as a parameter:
```powershell
python runner.py "Go to https://www.saucedemo.com, Type standard_user into Username, Click Login"
```

### 5. Automated PyTest Suite
```powershell
pytest tests/test_scenarios.py -v
```

---

## 📊 Report Artifacts
After every test execution:
- **Screenshots:** Saved under `screenshots/step_*.png` and `final_result.png`.
- **HTML Report:** Generated under `reports/report_*.html` with interactive pass/fail metrics.
- **JSON Metrics:** Structured machine-readable results saved in `reports/report_*.json`.

---

## 📂 Deliverables Included
- **[APPROACH_AND_LIMITATIONS.md](APPROACH_AND_LIMITATIONS.md)**: Engineering analysis of design decisions, locator hierarchy, and current constraints.
- **[DEMO_SCRIPT.md](DEMO_SCRIPT.md)**: 5-minute recording walkthrough script for video submission.

