"""Programmatic Guardrails and Human-in-the-Loop (HITL) Safety Hooks.

Provides input validation against prompt injections and code-level confirmation gates
for sensitive infrastructure operations.
"""

import re
from typing import Any, Dict, Optional, Tuple


# Programmatic guardrail injection and malicious pattern blacklist
SUSPICIOUS_INJECTION_PATTERNS = [
    r"ignore\s+previous\s+instructions",
    r"disregard\s+all\s+prior\s+prompts",
    r"system\s*override",
    r"you\s+are\s+now\s+dan",
    r"bypass\s+safety\s+filters",
    r"rm\s+-rf\s+/",
    r"drop\s+database",
]


def validate_prompt_guardrails(prompt: str) -> Tuple[bool, Optional[str]]:
    """Evaluates user prompt against programmatic security guardrails.

    Returns:
        (is_safe, error_reason)
    """
    if not prompt or not prompt.strip():
        return False, "Prompt is empty."

    for pattern in SUSPICIOUS_INJECTION_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            return False, f"Prompt blocked by safety guardrails: contains suspicious pattern '{pattern}'."

    return True, None


class HumanInTheLoopGate:
    """Explicit code-level Human-in-the-Loop (HITL) gate for sensitive operations."""

    SENSITIVE_ACTIONS = {
        "deploy_landing_page",
        "delete_cloud_run_service",
        "overwrite_production_files"
    }

    @classmethod
    def check_approval(cls, action_name: str, payload: Dict[str, Any], confirmed: bool = True) -> Tuple[bool, str]:
        """Checks if a sensitive action has received explicit human confirmation."""
        if action_name in cls.SENSITIVE_ACTIONS:
            if not confirmed:
                return False, f"Action '{action_name}' requires explicit Human-in-the-Loop confirmation before proceeding."
        return True, "Approved."
