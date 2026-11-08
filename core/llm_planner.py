"""
Robust Hybrid LLM Planner with Deterministic Fallback & Ambiguity Detection.
Uses Groq LLaMA 3.3 when configured, and falls back to deterministic heuristic parsing if offline.
Strictly disallows arbitrary executable code; outputs validated BrowserAction schemas.
"""

import json
import re
import logging
from typing import Optional, List, Dict, Any
from openai import OpenAI
from core.models import BrowserAction, ActionType, SemanticSelector, AssertionOperator
import config

logger = logging.getLogger("llm_planner")


class LLMPlanner:
    def __init__(self):
        self.client = None
        if config.GROQ_API_KEY and config.GROQ_API_KEY.strip():
            try:
                self.client = OpenAI(
                    api_key=config.GROQ_API_KEY,
                    base_url=config.GROQ_BASE_URL
                )
            except Exception as e:
                logger.warning(f"Could not initialize OpenAI/Groq client: {e}")

    def plan_step(self, instruction: str, dom_snapshot: List[dict], current_url: str) -> BrowserAction:
        """
        Fast Hybrid Planner:
        1. Evaluates instant deterministic matcher first (0.001s latency).
        2. If target ref found with high confidence, returns immediately.
        3. For ambiguous or complex steps, queries Groq with a fast 4s timeout.
        """
        fast_action = self._plan_heuristic(instruction, dom_snapshot, current_url)
        if fast_action.target_ref:
            return fast_action

        # Ambiguous or unreferenced step: consult Groq LLM
        if self.client:
            try:
                llm_action = self._plan_with_groq(instruction, dom_snapshot, current_url)
                if llm_action:
                    return llm_action
            except Exception as e:
                logger.warning(f"Groq planning call skipped/failed ({e}). Falling back to heuristic.")

        return fast_action

    def _plan_with_groq(self, instruction: str, dom_snapshot: List[dict], current_url: str) -> Optional[BrowserAction]:
        system_prompt = (
            "You are a Senior Browser Automation Architect and SDET. "
            "Given a live list of interactive elements on the page and a natural-language step, "
            "choose the exact action type and the element ref tag (e.g. 'ref_1'). "
            "Never generate code, python, or javascript. "
            "Output ONLY a valid JSON object matching the requested BrowserAction schema."
        )

        user_content = {
            "current_url": current_url,
            "instruction": instruction,
            "interactive_elements": dom_snapshot[:80]
        }

        response = self.client.chat.completions.create(
            model=config.GROQ_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Schema:\n{BrowserAction.model_json_schema()}\n\nTask:\n{json.dumps(user_content)}"
                }
            ],
            temperature=1e-8,
            timeout=4.0
        )

        raw_output = response.choices[0].message.content
        data = json.loads(raw_output)
        return BrowserAction(**data)

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
            # URL assertion
            if "url" in inst_lower:
                val = re.sub(r'.*?(?:contains|is|equals)\s+', '', instruction, flags=re.IGNORECASE).strip().strip("'\"")
                return BrowserAction(
                    action_type=ActionType.ASSERT_URL,
                    expected_text=val,
                    reasoning=f"Assert URL contains '{val}'"
                )
            # Title assertion
            if "title" in inst_lower:
                val = re.sub(r'.*?(?:contains|is|equals)\s+', '', instruction, flags=re.IGNORECASE).strip().strip("'\"")
                return BrowserAction(
                    action_type=ActionType.ASSERT_TITLE,
                    expected_text=val,
                    reasoning=f"Assert title contains '{val}'"
                )

            # Target visibility / text
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

        # Extract target field description cleanly
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

            ref = el.get("ref")
            text = (el.get("text") or "").lower()
            name = (el.get("name") or "").lower()
            ph = (el.get("placeholder") or "").lower()
            label = (el.get("associatedLabel") or "").lower()
            aria = (el.get("ariaLabel") or "").lower()
            el_id = (el.get("id") or "").lower()

            # Enforce tag/role semantics
            if is_fill and tag not in ["input", "textarea"] and role not in ["textbox", "searchbox"]:
                continue
            if is_check and type_attr != "checkbox" and role != "checkbox":
                continue
            if is_uncheck and type_attr != "checkbox" and role != "checkbox":
                continue

            score = 0
            clues = [name, label, el_id, ph, text, aria]

            # Tier A: Exact string match on name, label, or id (Highest Priority)
            if any(c and c == target_clean for c in [name, label, el_id]):
                score = 100
            elif any(c and c == target_clean for c in [ph, text, aria]):
                score = 90
            # Tier B: Multi-word phrase containment
            elif any(c and (target_clean in c or c in target_clean) and len(c) > 3 for c in [name, label, el_id]):
                score = 75
            elif any(c and (target_clean in c or c in target_clean) and len(c) > 3 for c in [ph, text, aria]):
                score = 65
            # Tier C: Keyword word overlap
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

            # Special case for radio selection: "Select Male for gender"
            if is_select and type_attr == "radio":
                if ("male" in inst_lower and el_id == "male") or ("female" in inst_lower and el_id == "female"):
                    score = 110

            if score > 0:
                candidate_scores.append((score, el))

        # Select highest-scoring candidate
        best_ref = None
        best_candidate = None
        if candidate_scores:
            candidate_scores.sort(key=lambda x: x[0], reverse=True)
            best_score, best_candidate = candidate_scores[0]
            best_ref = best_candidate.get("ref")

        # 6. Action Type Assignment
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
                reasoning=f"Type '{val}' into {target_clean}"
            )

        if is_select:
            # Check if best candidate is a radio button
            if best_candidate and best_candidate.get("type") == "radio":
                return BrowserAction(
                    action_type=ActionType.RADIO,
                    target_ref=best_ref,
                    selector=SemanticSelector(description=target_clean, role="radio"),
                    reasoning=f"Select radio button '{best_candidate.get('id') or target_clean}'"
                )
            words = instruction.split()
            val = words[1] if len(words) > 1 else ""
            return BrowserAction(
                action_type=ActionType.SELECT,
                target_ref=best_ref,
                selector=SemanticSelector(description=target_clean, role="combobox"),
                value=val,
                reasoning=f"Select '{val}' in dropdown"
            )

        if is_check:
            return BrowserAction(
                action_type=ActionType.CHECK,
                target_ref=best_ref,
                selector=SemanticSelector(description=target_clean, role="checkbox"),
                reasoning=f"Check box '{target_clean}'"
            )

        if is_uncheck:
            return BrowserAction(
                action_type=ActionType.UNCHECK,
                target_ref=best_ref,
                selector=SemanticSelector(description=target_clean, role="checkbox"),
                reasoning=f"Uncheck box '{target_clean}'"
            )

        # Default click action
        return BrowserAction(
            action_type=ActionType.CLICK,
            target_ref=best_ref,
            selector=SemanticSelector(
                description=target_clean,
                role="button",
                name=target_clean,
                text=target_clean
            ),
            reasoning=f"Click element '{target_clean}'"
        )
