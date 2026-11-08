# Engineering Note: Approach and Limitations

**Author:** Senior AI Automation Architect & SDET Engineer  
**Project:** AI Test Runner (Natural Language to Browser Automation)  
**Target Submission:** CloudQA Practical Technical Assessment (Task 2)

---

## 1. Architectural Approach

### The Core Challenge in Web Automation
Traditional browser automation frameworks (Selenium, Cypress, vanilla Playwright) suffer from **locator brittleness**: minor changes to CSS class names, DOM hierarchy, or Tailwind utility classes break scripts. Conversely, naive vision-only AI agents suffer from high latency and non-deterministic coordinate clicking.

### Our Solution: Hybrid Semantic AI-DOM Pipeline
We combined the precision of DOM inspection with the semantic reasoning of Large Language Models:

1. **Synthetic AI Tagging (`core/dom_extractor.py`)**:
   Instead of passing raw, noisy HTML (which consumes massive token contexts), our JavaScript extractor filters exclusively for visible, interactable elements (`<input>`, `<button>`, `<select>`, `<a>`, ARIA roles). It injects lightweight transient attributes (`data-ai-id='ref_X'`) and maps associated `<label>` texts, placeholders, and current values into a compact payload (< 3KB).

2. **LLM Schema Enforcement (`core/llm_planner.py`)**:
   Using Groq's high-throughput LLaMA 3.3 engine with JSON schema constraints, the AI evaluates the natural-language step against the live DOM snapshot, returning a structured action referencing the exact element tag without hallucinating selectors.

3. **Multi-Tier Fallback Hierarchy (`core/action_executor.py`)**:
   If dynamic refs encounter race conditions or if running offline without an API key, the executor cascades through accessibility-first fallbacks:
   - **Tier 1:** Accessible ARIA Role + Name (`page.get_by_role()`)
   - **Tier 2:** Associated Label (`page.get_by_label()`)
   - **Tier 3:** Input Placeholder (`page.get_by_placeholder()`)
   - **Tier 4:** Visible Text (`page.get_by_text()`)
   - **Tier 5:** Semantic Heuristics (`input[type='email']`, `#email`)

4. **Hermetic State Verification**:
   Assertions evaluate actual browser state (DOM presence, visibility, URL redirects, inner text) rather than simulated completions. Tests only pass when all required assertions pass.

---

## 2. Generalization Across Diverse Websites

To guarantee the tool does not rely on hardcoded selectors for a single domain:
- **PHPTravels (`https://phptravels.net`)**: Verified against customer login, checkboxes, and dashboard redirection.
- **Second Website (`https://www.saucedemo.com`)**: Validated against standard e-commerce authentication, input forms, dynamic button states, and URL navigation assertions (`/inventory.html`).
- **10 Unseen Cases**: Tested across distinct grammatical structures, varied imperative verbs (*Type, Enter, Select, Check, Verify, Assert*), and compound clauses.

---

## 3. Current Limitations & Edge Cases

| Limitation | Technical Context | Recommended Mitigation in Production |
| :--- | :--- | :--- |
| **Cross-Origin iframes** | Elements nested inside third-party payment gateways or sandboxed iframes are not in the primary document query. | Inject recursive frame traversal into `DOMExtractor.get_interactive_tree`. |
| **Canvas / WebGL Components** | Custom canvas elements (e.g. signature pads, interactive maps) have no DOM representation. | Integrate multimodal vision-based click fallback (VLM coordinate prediction). |
| **Bot Detection & Turnstiles** | Heavy Cloudflare/reCAPTCHA challenges intentionally block automated browsers. | Use Playwright stealth plugins and residential proxy pools for production scraping. |
| **Multi-Tab Contexts** | Popup windows and OAuth redirects that open in separate browser tabs. | Attach event listeners on `context.on('page')` to track child pages automatically. |
| **API Latency** | Live LLM roundtrips introduce ~300-600ms per step. | Cache semantic element matches for identical pages across regression runs. |

---

## 4. Conclusion
This architecture strikes an optimal balance between **zero-maintenance resilience** and **deterministic test execution**, meeting modern enterprise SDET standards.

