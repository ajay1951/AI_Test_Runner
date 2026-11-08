"""
Robust Hybrid LLM Planner with Deterministic Fallback.
Uses Groq LLaMA 3.3 when configured, and falls back to deterministic heuristic parsing if offline.
"""

import json
import re
import logging
from typing import Optional, List
from openai import OpenAI
from core.models import BrowserAction, ActionType, SemanticSelector
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

        # Ambiguous step: consult Groq LLM
        if self.client:
            try:
                return self._plan_with_groq(instruction, dom_snapshot, current_url)
            except Exception as e:
                logger.warning(f"Groq planning call skipped/failed ({e}).")

        return fast_action

    def _plan_with_groq(self, instruction: str, dom_snapshot: List[dict], current_url: str) -> BrowserAction:
        system_prompt = (
            "You are an expert browser automation planner. "
            "Given interactive elements on the page and a natural-language step, "
            "choose the exact action and element ref tag. "
            "Always return a valid JSON object matching the requested schema."
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
        """Deterministic fallback matcher matching instruction text against live DOM attributes."""
        inst_lower = instruction.lower()

        # Check navigation
        if inst_lower.startswith("go to ") or inst_lower.startswith("open ") or inst_lower.startswith("navigate to "):
            url = instruction.split(" ")[-1]
            return BrowserAction(action_type=ActionType.NAVIGATE, value=url, reasoning="Deterministic navigation")

        # Check assertion
        if "verify" in inst_lower or "assert" in inst_lower:
            target = instruction
            for prefix in ["verify that ", "verify ", "assert that ", "assert "]:
                if inst_lower.startswith(prefix):
                    target = instruction[len(prefix):].strip()
                    break
            return BrowserAction(
                action_type=ActionType.ASSERT_TEXT,
                expected_text=target,
                reasoning=f"Assertion for '{target}'"
            )

        # Match against DOM elements
        best_ref = None
        best_tag = None

        # Clean target text (e.g. from "Click Sign In to your account" -> "sign in to your account")
        target_clean = re.sub(r'^(?:click|press|tap|type|enter|fill)\s+(?:on\s+)?(?:the\s+)?', '', instruction, flags=re.IGNORECASE).strip().lower()
        target_words = set(re.findall(r'\w+', target_clean))

        for el in dom_snapshot:
            ref = el.get("ref")
            text = (el.get("text") or "").lower()
            name = (el.get("name") or "").lower()
            ph = (el.get("placeholder") or "").lower()
            label = (el.get("associatedLabel") or "").lower()
            tag = el.get("tag")

            # Check direct substring matching
            clues = [text, name, ph, label]
            matched = False
            for clue in clues:
                if not clue:
                    continue
                # Bidirectional containment
                if clue in inst_lower or target_clean in clue:
                    matched = True
                    break
                # Word overlap (e.g. "sign in" matches "login \n sign in to your account")
                clue_words = set(re.findall(r'\w+', clue))
                if target_words and len(target_words.intersection(clue_words)) >= 2:
                    matched = True
                    break

            if matched:
                best_ref = ref
                best_tag = tag
                break

        # Decide action type
        if "type " in inst_lower or "enter " in inst_lower or "fill " in inst_lower:
            parts = instruction.split(" into ")
            if len(parts) == 2:
                val = parts[0].replace("Type ", "").replace("type ", "").replace("Enter ", "").replace("enter ", "").strip()
            else:
                words = instruction.split()
                val = words[1] if len(words) > 1 else ""
            return BrowserAction(
                action_type=ActionType.FILL,
                target_ref=best_ref,
                selector=SemanticSelector(description=target_clean, role="textbox", placeholder=target_clean),
                value=val,
                reasoning=f"Type '{val}' into element {best_ref or target_clean}"
            )

        if "select " in inst_lower or "choose " in inst_lower:
            words = instruction.split()
            val = words[1] if len(words) > 1 else ""
            return BrowserAction(
                action_type=ActionType.SELECT,
                target_ref=best_ref,
                selector=SemanticSelector(description=target_clean, role="combobox"),
                value=val,
                reasoning=f"Select '{val}' in dropdown"
            )

        if "check " in inst_lower:
            return BrowserAction(
                action_type=ActionType.CHECK,
                target_ref=best_ref,
                selector=SemanticSelector(description=target_clean, role="checkbox"),
                reasoning="Check box"
            )

        # Default to click with rich semantic fallback
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
