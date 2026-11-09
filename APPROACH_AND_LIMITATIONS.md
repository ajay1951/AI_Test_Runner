# Engineering Note: Architectural Approach, LLM Planning, Bounded Retries, and Real-World Limitations

**Author:** Senior AI Automation Architect & SDET Engineer
**Project:** AI Test Runner (Natural Language to Autonomous Browser Automation)
**Target Submission:** CloudQA Practical Technical Assessment (Task 2)
**Date:** November 9, 2026

---

## 1. Architectural Approach & LLM Planning

### The Core Problem in Web Test Automation
Traditional browser automation frameworks (Selenium, Cypress, vanilla Playwright) suffer from **severe locator fragility**. When front-end teams update UI frameworks, switch from styled-components to Tailwind CSS, or restructure DOM wrappers, static selectors (`div.css-19vja8x > button.sc-bdVaJa`) immediately break. Conversely, naive vision-only or unbounded LLM-agent wrappers introduce high token costs, 500-1500ms per-step inference latency, non-deterministic clicking, and the catastrophic SDET failure mode of **false passes**.

### Our Solution: Hybrid Semantic AI-DOM Pipeline with Strict LLM Modes
Our architecture addresses this via a multi-tiered pipeline combining the semantic reasoning of Large Language Models with the speed and reliability of accessibility locators:

```text
[Plain English Step] ──► [Two-Tier Parser] ──► [Live DOM Tagging (data-ai-id)]
                                                          │
   ┌──────────────────────────────────────────────────────┴─────────────────────────────────┐
   ▼                                                                                        ▼
[Deterministic Matcher (0.001s)] ──(Hybrid Fallback)──► [Resolved Ref] ◄──(Strict LLM)── [Groq LLM Planner]
                                                               │                    (openai/gpt-oss-20b)
                                                               ▼
                                                [Pre-Interaction Tag Guard]
                                                               │
                                                               ▼
                                                [Bounded 3-Attempt Executor]
                                                               │
                                                               ▼
                                               [Observable State Verification]
```

1. **Synthetic AI Tagging (`core/dom_extractor.py`)**:
   Instead of overwhelming LLM context windows with noisy, unparsed HTML trees (often >100KB), our lightweight JavaScript extractor selectively queries visible, interactive elements (`<input>`, `<button>`, `<select>`, `<a>`, and ARIA widgets). It injects transient `data-ai-id='ref_X'` attributes and extracts accessible roles, names, associated labels, placeholders, and current states into a compact JSON snapshot (<3KB).

2. **Two-Tier Macro-Goal Decomposition (`core/test_parser.py`)**:
   High-level compound instructions (e.g., *"Log in as a customer"*) are parsed through an abstract two-tier expander. The macro-goal decomposes into generic semantic targets (`"Username"`, `"Password"`, `"login button"`) without hardcoding website-specific IDs or class names, enabling the same prompt to execute seamlessly across completely different websites.

3. **Groq Model Selection (`openai/gpt-oss-20b`) & Gateway Routing**:
   During end-to-end audit on live domains, the legacy model ID (`llama-3.3-70b-versatile`) returned HTTP 404 (`model_not_found`) through the active Groq gateway endpoint. The architecture was remediated to support dynamic model selection via `GROQ_MODEL=openai/gpt-oss-20b` (with verified operational models including `qwen/qwen3.8-27b`, `allam-2-7b`, and `openai/gpt-oss-120b`).

4. **Strict LLM Mode vs. Hybrid Fallback with Full Attribution (`core/llm_planner.py`)**:
   - **Strict LLM Mode (`--strict-llm` / `PLANNER_STRICT=true`)**: Enforces that 100% of action planning and DOM element resolution is executed by the configured LLM. If the Groq API encounters a network timeout, authentication failure, or invalid response, the runner **aborts immediately** with a descriptive `RuntimeError`. Silent heuristic fallback is strictly prohibited.
   - **Hybrid Mode (`PLANNER_MODE=hybrid`)**: Allows fast deterministic resolution or fallback when Groq is unreachable. Crucially, the system tags every action with explicit provenance:
     - `planner_type`: `"llm"` vs. `"deterministic_heuristic"`
     - `model`: e.g., `"openai/gpt-oss-20b"`
     - `fallback_used`: `true` or `false`
   This eliminates heuristic ambiguity and guarantees complete audit transparency.

5. **Groq JSON Schema & Grammar Fallback Handling**:
   Certain Groq models occasionally reject short healthcheck prompts with HTTP 400 (`json_validate_failed`) when strict JSON schema enforcement is active. Our resilient `_create_completion()` method first attempts native JSON mode, and if the grammar validator rejects the payload, cleanly falls back to prompt-guided JSON extraction paired with strict Pydantic model validation. Empty selector structures (`{"name": "", "role": ""}`) emitted for assertions or navigations are safely sanitized before Pydantic parsing.

6. **Automatic Sensitive Credential Masking (`core/models.py`)**:
   Passwords and credentials are protected by an automated Pydantic model validator (`@model_validator(mode="after")`). Any action targeting password fields or labeled with sensitive identifiers has `is_sensitive = True` enforced automatically, guaranteeing that credentials appear only as `********` across all telemetry logs and HTML reports.

---

## 2. Bounded 3-Attempt Retries & Hydration Resilience

In modern Single Page Applications (SPAs) built on React, Angular, or Vue, elements frequently unmount, re-render, or hydrate asynchronously after route changes and network requests.

### The Failure of Naive Retries
- **Unbounded retries** risk masking critical performance regressions and cause test suites to hang indefinitely on absent elements.
- **Immediate retries without backoff** hammer the DOM before microtasks or asynchronous fetches complete, exhausting retry budgets in milliseconds.

### Our Bounded Hydration Engine (`core/action_executor.py`)
1. **Bounded Iteration Loop:** Every action is capped at exactly `max_attempts = 3`.
2. **Progressive Backoff:** Between transient failures, the executor introduces linear backoff:
   $$\text{sleep\_time} = 0.4 \times \text{attempt}$$
   (0.4s after Attempt 1, 0.8s after Attempt 2), allowing the browser render thread and virtual DOM hydration to settle.
3. **Fail-Fast Type Guardrails:** Not all errors warrant a retry. When an interaction targets an incompatible element (e.g., attempting a `fill` on a `<button>`), the engine raises `TypeError` and terminates immediately on Attempt 1. Retries are strictly reserved for transient DOM attachment errors, timeout waits, and hydration delays.
4. **Observable Attempt Badging:** The attempt count (`attempts: 1`, `2`, or `3`) is preserved in execution telemetry and rendered in HTML reports, highlighting unstable or slow-hydrating UI components before they cause production regressions.

---

## 3. Element Tag Compatibility Validation

A common failure mode in LLM-driven browser automation is **element mis-targeting**: the model correctly identifies the semantic purpose (e.g., "Search") but selects a static label wrapper, a submit button, or an enclosing SVG instead of the actual `<input>` tag.

To eliminate this class of defects, `core/action_executor.py` implements pre-interaction runtime validation:

```python
def _validate_element_compatibility(self, loc, act_type: str):
    tag = loc.evaluate("el => (el.tagName || '').toLowerCase()")
    if act_type == "fill":
        is_editable = loc.evaluate(
            "el => el.isContentEditable === true || ['input', 'textarea'].includes((el.tagName || '').toLowerCase())"
        )
        if not is_editable:
            raise TypeError(f"Incompatible target: Cannot fill non-editable element <{tag}>")
    elif act_type == "click":
        is_disabled = loc.evaluate(
            "el => el.disabled === true || el.getAttribute('aria-disabled') === 'true'"
        )
        if is_disabled:
            raise ValueError(f"Incompatible target: Cannot click disabled element <{tag}>")
```

### Key Invariants Enforced:
1. **Editable Tag Enforcement:** `fill` actions are strictly confined to `<input>`, `<textarea>`, and elements with `contenteditable="true"`.
2. **State Protection:** Attempts to fill a button or static container fail fast, guaranteeing that button text and UI state remain uncorrupted (verified by `test_e2e_fill_non_editable_element_rejected`).
3. **Disabled Control Guard:** Clicks on controls with `disabled` or `aria-disabled="true"` are rejected before Playwright force-clicks or hangs on actionability checks.

---

## 4. Real-World Environment Boundaries & Production Mitigations

In enterprise SDET environments, automated runners interact with complex external infrastructure. The table below outlines our technical boundaries and recommended production mitigations:

| Real-World Boundary | Root Technical Constraint | Engineering Behavior | Recommended Enterprise Mitigation |
|:---|:---|:---|:---|
| **Cross-Origin iframes** | Browser Same-Origin Policy isolates third-party iframes (e.g., Stripe payment forms, PayPal, reCAPTCHA). | Primary DOM extraction traverses the top-level window document; nested cross-origin iframes are not indexed. | Implement recursive frame traversal in `DOMExtractor`: iterate through `page.frames`, injecting synthetic IDs into each accessible frame context. |
| **Canvas / WebGL Components** | `<canvas>` elements render pixel bitmaps without backing DOM nodes or accessibility tree representations. | DOM inspection cannot identify buttons or fields rendered inside custom canvas widgets. | Integrate a multimodal Vision-Language Model (VLM coordinate predictor) that computes normalized $(x, y)$ click coordinates from viewport screenshots. |
| **Bot Defenses & Turnstiles** | Cloudflare Turnstile, Akamai Bot Manager, and Datadome challenge automated browser processes. | Standard Chromium launch flags can be fingerprinted by advanced bot-detection algorithms. | Deploy `playwright-stealth` patches, utilize residential IP proxy pools, and persist authenticated session storage states across runs. |
| **Public Demo Ephemerality** | Shared public demo environments (e.g., `phptravels.net`) have unpinned state and periodic DB resets. | If external credentials expire or sessions are terminated by other global users, post-login assertions fail. | The runner handles this gracefully without crashing (as demonstrated on PHPTravels), but production CI pipelines should always target dedicated, ephemeral Docker test containers with deterministic seed fixtures. |
| **LLM Concurrency & Rate Limits** | High-throughput regression suites (hundreds of tests) can saturate cloud LLM rate limits (TPM/RPM). | Uncached external inference adds latency per step and risks HTTP 429 rate-limiting. | Our hybrid architecture allows deterministic matching for standard patterns while reserving LLM inference for ambiguous steps; offline mock suites ensure full CI verification without external API cost. |

---

## 5. Conclusion

By enforcing **strict element compatibility guards**, **bounded 3-attempt retries with progressive backoff**, **strict observable state assertions**, and **transparent LLM planner provenance**, the AI Test Runner bridges the gap between natural language flexibility and enterprise-grade test execution determinism.
