"""
Robust Hybrid LLM Planner with Deterministic Fallback & Ambiguity Detection.
Uses Groq API (openai/gpt-oss-20b by default) with strict JSON schema validation.
Explicitly records planner provenance (llm vs deterministic_heuristic) and prevents silent fallback in strict mode.
"""

import json
import re
import time
import logging
from typing import Optional, List, Dict, Any
from openai import OpenAI
from core.models import BrowserAction, ActionType, SemanticSelector, AssertionOperator
from core.test_parser import parse_instruction_to_actions
import config

logger = logging.getLogger("llm_planner")


def _extract_json(raw: str) -> dict:
    """Robustly extracts JSON from raw LLM output, handling markdown fences and extraneous text."""
    if not raw or not raw.strip():
        raise ValueError("Empty response received from LLM")
    s = raw.strip()
    code_block = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', s, re.IGNORECASE)
    if code_block:
        s = code_block.group(1).strip()
    json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', s)
    if json_match:
        s = json_match.group(1).strip()
    return json.loads(s)


class LLMPlanner:
    def __init__(self, mode: Optional[str] = None, strict: Optional[bool] = None, model: Optional[str] = None):
        self.mode = (mode or config.PLANNER_MODE).lower()
        self.strict = strict if strict is not None else config.PLANNER_STRICT
        self.model = model or config.GROQ_MODEL
        self.client = None

        if config.GROQ_API_KEY and config.GROQ_API_KEY.strip():
            try:
                self.client = OpenAI(
                    api_key=config.GROQ_API_KEY,
                    base_url=config.GROQ_BASE_URL
                )
            except Exception as e:
                logger.warning(f"Could not initialize OpenAI/Groq client: {e}")

    def _create_completion(self, messages: list, max_tokens: int = 1200, timeout: float = 12.0) -> str:
        """
        Attempts JSON mode completion first; if the model rejects JSON schema enforcement
        with json_validate_failed, cleanly falls back to prompt-guided JSON output.
        """
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
                timeout=timeout
            )
            content = (resp.choices[0].message.content or "").strip()
            if content:
                return content
        except Exception as e:
            err_str = str(e).lower()
            if "json_validate_failed" in err_str or "failed to validate json" in err_str:
                logger.info(f"JSON mode validation failed on {self.model}; retrying with prompt-guided JSON extraction.")
            else:
                raise

        # Safe alternative: Request JSON directly without response_format constraint
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            max_tokens=max_tokens,
            timeout=timeout
        )
        return (resp.choices[0].message.content or "").strip()

    def check_connectivity(self) -> Dict[str, Any]:
        """
        Tests API key configuration and model accessibility without exposing keys.
        Distinguishes authentication, model_not_found, rate_limit, network, and invalid requests.
        """
        if not config.GROQ_API_KEY or not config.GROQ_API_KEY.strip():
            return {
                "api_key_configured": False,
                "model": self.model,
                "accessible": False,
                "status": "FAIL",
                "error_type": "missing_api_key",
                "message": "GROQ_API_KEY is not set or empty in environment.",
                "latency_ms": 0.0
            }

        t0 = time.time()
        try:
            raw = self._create_completion(
                messages=[
                    {"role": "system", "content": "You are a test assistant. Output valid JSON: {\"status\": \"ok\"}"},
                    {"role": "user", "content": "Ping"}
                ],
                max_tokens=50,
                timeout=6.0
            )
            latency = round((time.time() - t0) * 1000, 2)
            data = _extract_json(raw)
            return {
                "api_key_configured": True,
                "model": self.model,
                "accessible": True,
                "status": "PASS",
                "error_type": None,
                "message": f"Successfully connected to {self.model}",
                "raw_response": raw,
                "latency_ms": latency
            }
        except Exception as e:
            latency = round((time.time() - t0) * 1000, 2)
            err_str = str(e).lower()
            if "401" in err_str or "auth" in err_str or "api_key" in err_str:
                err_type = "authentication_error"
            elif "404" in err_str or "not found" in err_str:
                err_type = "model_not_found"
            elif "429" in err_str or "rate" in err_str or "quota" in err_str:
                err_type = "rate_limit"
            elif "connect" in err_str or "timeout" in err_str or "network" in err_str:
                err_type = "network_error"
            else:
                err_type = "invalid_request"

            return {
                "api_key_configured": True,
                "model": self.model,
                "accessible": False,
                "status": "FAIL",
                "error_type": err_type,
                "message": str(e),
                "latency_ms": latency
            }

    def plan_instruction_sequence(self, instruction: str, base_url: Optional[str] = None) -> List[BrowserAction]:
        """
        Converts a compound natural language instruction into an array of validated BrowserAction schemas.
        Uses LLM planning in strict/LLM mode; falls back to deterministic parsing only when allowed.
        """
        # Strict or LLM mode requires LLM planning
        if (self.strict or self.mode == "llm") and self.client:
            try:
                actions = self._plan_sequence_with_groq(instruction, base_url)
                if actions:
                    return actions
            except Exception as e:
                if self.strict:
                    raise RuntimeError(f"Strict LLM Mode: Action sequence planning failed ({e}) and fallback is disabled.") from e
                logger.warning(f"Groq sequence planning failed ({e}). Falling back to deterministic parser.")

        # Hybrid mode: try LLM first if client available, otherwise deterministic
        if self.mode == "hybrid" and self.client and not self.strict:
            try:
                actions = self._plan_sequence_with_groq(instruction, base_url)
                if actions:
                    return actions
            except Exception as e:
                logger.warning(f"Groq sequence planning call failed ({e}). Using deterministic fallback.")

        # Fallback path
        fallback_actions = parse_instruction_to_actions(instruction, base_url=base_url)
        for a in fallback_actions:
            a.planner_type = "deterministic_heuristic"
            a.model = None
            a.fallback_used = True
        return fallback_actions

    def _plan_sequence_with_groq(self, instruction: str, base_url: Optional[str] = None) -> List[BrowserAction]:
        """Calls Groq API to decompose natural language instruction into a sequence of BrowserAction schemas."""
        system_prompt = (
            "You are a Senior Browser Automation Architect and SDET. "
            "Convert natural language test instructions into a sequence of structured browser actions. "
            "Allowed action_type values: navigate, click, fill, check, uncheck, select_option, hover, scroll, wait, assert_visible, assert_text, assert_url, assert_title. "
            "For navigate actions, put the target URL into 'value'. "
            "For fill actions, put the input text into 'value'. "
            "For assertions, put the expected substring or visible landmark into 'expected_text'. "
            "Never generate code, python, or javascript. "
            "Output ONLY a valid JSON object matching this structure: "
            '{"actions": [{"action_type": "<action>", "target_ref": null, "selector": {"name": "<name>", "role": "<role>", "description": "<desc>"}, "value": "<val>", "expected_text": "<text>", "is_sensitive": false, "reasoning": "<why>"}]}'
        )

        user_content = {
            "instruction": instruction,
            "base_url": base_url or ""
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_content)}
        ]

        raw_output = self._create_completion(messages, max_tokens=1500, timeout=12.0)
        data = _extract_json(raw_output)
        raw_actions = data.get("actions", [])
        if not raw_actions and isinstance(data, list):
            raw_actions = data

        validated_actions: List[BrowserAction] = []
        for ra in raw_actions:
            # Clean empty selector dicts
            sel = ra.get("selector")
            if isinstance(sel, dict):
                if not any(v and str(v).strip() for v in sel.values()):
                    ra["selector"] = None
            elif sel is not None and not isinstance(sel, dict):
                ra["selector"] = None

            # Enforce password sensitivity
            desc = (ra.get("selector", {}).get("description") if isinstance(ra.get("selector"), dict) else "") or ""
            reason = ra.get("reasoning") or ""
            val = str(ra.get("value") or "")
            if "password" in desc.lower() or "password" in reason.lower() or "password" in val.lower():
                ra["is_sensitive"] = True

            action = BrowserAction(**ra)
            action.planner_type = "llm"
            action.model = self.model
            action.fallback_used = False

            # Post-parse sanitation for navigation and assertion values
            if action.action_type == ActionType.NAVIGATE and (not action.value or not action.value.startswith("http")):
                if action.selector and action.selector.name and "://" in action.selector.name:
                    action.value = action.selector.name
                elif base_url:
                    action.value = base_url
                else:
                    m = re.search(r'https?://[^\s,;]+', instruction)
                    if m:
                        action.value = m.group(0)

            if action.action_type == ActionType.ASSERT_VISIBLE and not action.expected_text and action.selector:
                action.expected_text = action.selector.name or action.selector.description

            validated_actions.append(action)

        return validated_actions

    def plan_step(self, instruction: str, dom_snapshot: List[dict], current_url: str) -> BrowserAction:
        """
        Plans or resolves an atomic interaction against a live DOM snapshot.
        In strict mode, exclusively uses the LLM; fails fast without fallback.
        In hybrid mode, executes LLM when available and attributes provenance accurately.
        """
        # Strict LLM Mode: Must use LLM, zero fallback allowed
        if self.strict or self.mode == "llm":
            if not self.client:
                raise RuntimeError("Strict LLM Mode enabled but no Groq client/API key is configured.")
            try:
                llm_action = self._plan_with_groq(instruction, dom_snapshot, current_url)
                if llm_action:
                    llm_action.planner_type = "llm"
                    llm_action.model = self.model
                    llm_action.fallback_used = False
                    return llm_action
                raise ValueError("LLM returned empty plan in strict mode.")
            except Exception as e:
                raise RuntimeError(f"Strict LLM Mode: Groq planning failed ({e}) and fallback is disabled.") from e

        # Hybrid Mode: Try LLM first if client available
        if self.client:
            try:
                llm_action = self._plan_with_groq(instruction, dom_snapshot, current_url)
                if llm_action and llm_action.target_ref:
                    llm_action.planner_type = "llm"
                    llm_action.model = self.model
                    llm_action.fallback_used = False
                    return llm_action
            except Exception as e:
                logger.warning(f"Groq step planning failed ({e}). Falling back to deterministic heuristic.")

        # Deterministic Heuristic Fallback
        fast_action = self._plan_heuristic(instruction, dom_snapshot, current_url)
        fast_action.planner_type = "deterministic_heuristic"
        fast_action.model = None
        fast_action.fallback_used = True
        return fast_action

    def _plan_with_groq(self, instruction: str, dom_snapshot: List[dict], current_url: str) -> Optional[BrowserAction]:
        """Queries Groq with live DOM elements and returns validated BrowserAction."""
        system_prompt = (
            "You are a Senior Browser Automation Architect and SDET. "
            "Given a live list of interactive elements on the page and a natural-language step, "
            "choose the exact action type and the element ref tag (e.g. 'ref_1'). "
            "Allowed action_type values: navigate, click, fill, check, uncheck, select_option, hover, scroll, wait, assert_visible, assert_text, assert_url, assert_title. "
            "Never generate code, python, or javascript. "
            "Output ONLY a valid JSON object matching this structure: "
            '{"action_type": "<action>", "target_ref": "<ref_id or null>", "value": "<input value or null>", "reasoning": "<explanation>"}'
        )

        user_content = {
            "current_url": current_url,
            "instruction": instruction,
            "interactive_elements": dom_snapshot[:80]
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_content)}
        ]

        raw_output = self._create_completion(messages, max_tokens=300, timeout=8.0)
        data = _extract_json(raw_output)

        inst_lower = instruction.lower()
        reason_lower = (data.get("reasoning") or "").lower()
        if "password" in inst_lower or "password" in reason_lower:
            data["is_sensitive"] = True

        action = BrowserAction(**data)
        action.planner_type = "llm"
        action.model = self.model
        action.fallback_used = False
        return action

    def _plan_heuristic(self, instruction: str, dom_snapshot: List[dict], current_url: str) -> BrowserAction:
        """Deterministic matcher against live DOM snapshot attributes with ambiguity detection."""
        inst_lower = instruction.lower()

        # 1. Navigation
        if inst_lower.startswith("go to ") or inst_lower.startswith("open ") or inst_lower.startswith("navigate to "):
            url = instruction.split(" ")[-1]
            return BrowserAction(action_type=ActionType.NAVIGATE, value=url, reasoning="Deterministic navigation")

        # 2. Hover
        if inst_lower.startswith("hover ") or "hover over " in inst_lower:
            target = re.sub(r'^(?:hover|hover over)\s+(?:the\s+)?', '', instruction, flags=re.IGNORECASE).strip().lower()
            return BrowserAction(
                action_type=ActionType.HOVER,
                selector=SemanticSelector(text=target, description=target),
                reasoning=f"Hover over '{target}'"
            )

        # 3. Scroll
        if inst_lower.startswith("scroll "):
            direction = "down" if "down" in inst_lower else "up"
            return BrowserAction(
                action_type=ActionType.SCROLL,
                value=direction,
                reasoning=f"Scroll {direction}"
            )

        # 4. Assertions
        if "verify" in inst_lower or "assert" in inst_lower:
            if "url" in inst_lower:
                val = re.sub(r'.*?(?:contains|is|equals)\s+', '', instruction, flags=re.IGNORECASE).strip().strip("'\"")
                return BrowserAction(
                    action_type=ActionType.ASSERT_URL,
                    expected_text=val,
                    reasoning=f"Assert URL contains '{val}'"
                )
            if "title" in inst_lower:
                val = re.sub(r'.*?(?:contains|is|equals)\s+', '', instruction, flags=re.IGNORECASE).strip().strip("'\"")
                return BrowserAction(
                    action_type=ActionType.ASSERT_TITLE,
                    expected_text=val,
                    reasoning=f"Assert title contains '{val}'"
                )

            target = instruction
            for prefix in ["verify that ", "verify ", "assert that ", "assert "]:
                if inst_lower.startswith(prefix):
                    target = instruction[len(prefix):].strip()
                    break
            target_clean = re.sub(r'\s+(?:is shown|is displayed|appears|is visible|exists)$', '', target, flags=re.IGNORECASE).strip()
            return BrowserAction(
                action_type=ActionType.ASSERT_VISIBLE,
                expected_text=target_clean,
                selector=SemanticSelector(text=target_clean, description=target_clean),
                reasoning=f"Assertion for visibility of '{target_clean}'"
            )

        # 5. DOM Matching with Strict Priority Scoring & Ambiguity Resolution
        is_fill = any(w in inst_lower for w in ["type ", "enter ", "fill "])
        is_click = any(w in inst_lower for w in ["click ", "press ", "tap "])
        is_check = "check " in inst_lower and "uncheck " not in inst_lower
        is_uncheck = "uncheck " in inst_lower
        is_select = any(w in inst_lower for w in ["select ", "choose "])

        if is_fill and " into " in inst_lower:
            target_clean = inst_lower.split(" into ")[-1].strip()
        elif is_fill and " in " in inst_lower:
            target_clean = inst_lower.split(" in ")[-1].strip()
        elif is_select and " for " in inst_lower:
            target_clean = inst_lower.split(" for ")[-1].strip()
        elif is_select and " in " in inst_lower:
            target_clean = inst_lower.split(" in ")[-1].strip()
        else:
            target_clean = re.sub(r'^(?:click|press|tap|type|enter|fill|select|choose|check|uncheck)\s+(?:on\s+)?(?:the\s+)?', '', instruction, flags=re.IGNORECASE).strip().lower()

        target_words = set(re.findall(r'\w+', target_clean))
        candidate_scores: List[tuple[int, dict]] = []

        for el in dom_snapshot:
            tag = (el.get("tag") or "").lower()
            role = (el.get("role") or "").lower()
            type_attr = (el.get("type") or "").lower()

            name = (el.get("name") or "").lower()
            ph = (el.get("placeholder") or "").lower()
            label = (el.get("associatedLabel") or "").lower()
            aria = (el.get("ariaLabel") or "").lower()
            el_id = (el.get("id") or "").lower()
            text = (el.get("text") or "").lower()

            if is_fill and tag not in ["input", "textarea"] and role not in ["textbox", "searchbox"]:
                continue
            if is_check and type_attr != "checkbox" and role != "checkbox":
                continue
            if is_uncheck and type_attr != "checkbox" and role != "checkbox":
                continue

            score = 0
            clues = [name, label, el_id, ph, text, aria]

            if any(c and c == target_clean for c in [name, label, el_id]):
                score = 100
            elif any(c and c == target_clean for c in [ph, text, aria]):
                score = 90
            elif any(c and (target_clean in c or c in target_clean) and len(c) > 3 for c in [name, label, el_id]):
                score = 75
            elif any(c and (target_clean in c or c in target_clean) and len(c) > 3 for c in [ph, text, aria]):
                score = 65
            else:
                for c in clues:
                    if not c:
                        continue
                    clue_words = set(re.findall(r'\w+', c))
                    overlap = len(target_words.intersection(clue_words))
                    if overlap >= 2:
                        score = max(score, 50)
                    elif overlap == 1 and len(target_words) == 1:
                        score = max(score, 30)

            if score > 0:
                candidate_scores.append((score, el))

        best_ref = None
        best_candidate = None
        is_ambiguous = False
        if candidate_scores:
            candidate_scores.sort(key=lambda x: x[0], reverse=True)
            best_score, best_candidate = candidate_scores[0]

            if len(candidate_scores) > 1:
                second_score, second_candidate = candidate_scores[1]
                if best_score == second_score and best_score >= 50:
                    is_ambiguous = True
                    logger.warning(
                        f"Ambiguous target detected for '{target_clean}': '{best_candidate.get('ref')}' and '{second_candidate.get('ref')}' have identical score {best_score}."
                    )

            if not is_ambiguous:
                best_ref = best_candidate.get("ref")

        ambiguity_suffix = " (Ambiguous target)" if is_ambiguous else ""

        if is_fill:
            parts = instruction.split(" into ")
            if len(parts) == 2:
                val = parts[0].replace("Type ", "").replace("type ", "").replace("Enter ", "").replace("enter ", "").strip()
            else:
                words = instruction.split()
                val = words[1] if len(words) > 1 else ""
            is_pass = "password" in target_clean or "password" in inst_lower
            return BrowserAction(
                action_type=ActionType.FILL,
                target_ref=best_ref,
                selector=SemanticSelector(description=target_clean, role="textbox", placeholder=target_clean),
                value=val,
                is_sensitive=is_pass,
                reasoning=f"Type '{val}' into {target_clean}{ambiguity_suffix}"
            )

        if is_select:
            if best_candidate and best_candidate.get("type") == "radio":
                return BrowserAction(
                    action_type=ActionType.RADIO,
                    target_ref=best_ref,
                    selector=SemanticSelector(description=target_clean, role="radio"),
                    reasoning=f"Select radio button '{best_candidate.get('id') or target_clean}'{ambiguity_suffix}"
                )
            words = instruction.split()
            val = words[1] if len(words) > 1 else ""
            return BrowserAction(
                action_type=ActionType.SELECT,
                target_ref=best_ref,
                selector=SemanticSelector(description=target_clean, role="combobox"),
                value=val,
                reasoning=f"Select '{val}' in dropdown{ambiguity_suffix}"
            )

        if is_check:
            return BrowserAction(
                action_type=ActionType.CHECK,
                target_ref=best_ref,
                selector=SemanticSelector(description=target_clean, role="checkbox"),
                reasoning=f"Check box '{target_clean}'{ambiguity_suffix}"
            )

        if is_uncheck:
            return BrowserAction(
                action_type=ActionType.UNCHECK,
                target_ref=best_ref,
                selector=SemanticSelector(description=target_clean, role="checkbox"),
                reasoning=f"Uncheck box '{target_clean}'{ambiguity_suffix}"
            )

        return BrowserAction(
            action_type=ActionType.CLICK,
            target_ref=best_ref,
            selector=SemanticSelector(
                description=target_clean,
                role="button",
                name=target_clean,
                text=target_clean
            ),
            reasoning=f"Click element '{target_clean}'{ambiguity_suffix}"
        )
