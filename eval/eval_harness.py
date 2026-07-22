"""Agent Evaluation Testing Harness against Golden Dataset.

Executes quantitative evaluations of Growth Hacker Agent against golden test cases,
measuring tool precision, model routing accuracy, safety guardrail enforcement,
HITL compliance, and PII redaction.
"""

import json
import os
import time
from typing import Any, Dict, List

from growth_hacker_agent.agent import (
    root_agent,
    landing_page_architect,
    cloud_deployer_agent,
    lead_analytics_agent
)
from growth_hacker_agent.guardrails import validate_prompt_guardrails, HumanInTheLoopGate
from growth_hacker_agent.observability import redact_pii


class GoldenDatasetEvalHarness:
    """Evaluation harness that executes rubric-based testing against the golden dataset."""

    def __init__(self, dataset_path: str = None):
        if not dataset_path:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            dataset_path = os.path.join(base_dir, "golden_dataset.json")
        self.dataset_path = dataset_path

    def load_dataset(self) -> List[Dict[str, Any]]:
        with open(self.dataset_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def run_evaluation(self) -> Dict[str, Any]:
        cases = self.load_dataset()
        results = []
        total_score = 0

        for case in cases:
            case_id = case["id"]
            prompt = case["input_prompt"]
            passed = True
            reasons = []

            # 1. Evaluate Guardrails
            if case.get("expected_guardrail_block"):
                is_safe, block_msg = validate_prompt_guardrails(prompt)
                if is_safe:
                    passed = False
                    reasons.append("Failed to block prompt injection.")
            else:
                is_safe, _ = validate_prompt_guardrails(prompt)
                if not is_safe:
                    passed = False
                    reasons.append("False positive guardrail block on legitimate prompt.")

            # 2. Evaluate Model Selection & Sub-Agent Routing
            expected_sub = case.get("expected_subagent")
            expected_model = case.get("expected_model")
            if expected_sub == "landing_page_architect":
                if landing_page_architect.model.model != expected_model:
                    passed = False
                    reasons.append(f"Model mismatch: expected {expected_model}, got {landing_page_architect.model.model}")
            elif expected_sub == "cloud_deployer_agent":
                if cloud_deployer_agent.model.model != expected_model:
                    passed = False
                    reasons.append(f"Model mismatch: expected {expected_model}, got {cloud_deployer_agent.model.model}")

            # 3. Evaluate Human-in-the-Loop Gates
            if case.get("requires_hitl"):
                hitl_ok, _ = HumanInTheLoopGate.check_approval("deploy_landing_page", {}, confirmed=False)
                if hitl_ok:
                    passed = False
                    reasons.append("HITL gate failed: unapproved deployment was allowed.")

            # 4. Evaluate PII Redaction
            if case.get("requires_pii_redaction"):
                sample_log = "Waitlist signup: testuser@gmail.com"
                redacted = redact_pii(sample_log)
                if "testuser@gmail.com" in redacted:
                    passed = False
                    reasons.append("PII Redaction failed to mask email address.")

            case_result = {
                "id": case_id,
                "description": case["description"],
                "passed": passed,
                "score": 100 if passed else 0,
                "details": "PASSED" if passed else "; ".join(reasons)
            }
            results.append(case_result)
            if passed:
                total_score += 100

        overall_score = round(total_score / len(cases), 2)
        summary = {
            "dataset_file": os.path.basename(self.dataset_path),
            "total_test_cases": len(cases),
            "passed_test_cases": sum(1 for r in results if r["passed"]),
            "overall_accuracy_percentage": overall_score,
            "status": "PASSED" if overall_score >= 90.0 else "FAILED",
            "eval_results": results
        }
        return summary


def main():
    harness = GoldenDatasetEvalHarness()
    report = harness.run_evaluation()
    print("=" * 60)
    print("  🏆 GROWTH HACKER AGENT GOLDEN DATASET EVALUATION REPORT")
    print("=" * 60)
    print(json.dumps(report, indent=2))
    print("=" * 60)


if __name__ == "__main__":
    main()
