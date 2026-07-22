import unittest
import os
from growth_hacker_agent.agent import (
    root_agent,
    landing_page_architect,
    cloud_deployer_agent,
    lead_analytics_agent
)
from eval.eval_harness import GoldenDatasetEvalHarness


class TestAgentOrchestrationAndEval(unittest.TestCase):
    """Automated agent evaluation suite verifying multi-agent architecture and golden dataset benchmarks."""

    def test_multi_agent_subagent_registry(self):
        self.assertIsNotNone(root_agent.sub_agents)
        self.assertEqual(len(root_agent.sub_agents), 3)
        sub_names = [a.name for a in root_agent.sub_agents]
        self.assertIn("landing_page_architect", sub_names)
        self.assertIn("cloud_deployer_agent", sub_names)
        self.assertIn("lead_analytics_agent", sub_names)

    def test_strategic_model_routing(self):
        # Architect agent uses gemini-2.5-pro for deep reasoning and code generation
        self.assertEqual(landing_page_architect.model.model, "gemini-2.5-pro")
        # Operational sub-agents use gemini-2.5-flash for rapid execution
        self.assertEqual(cloud_deployer_agent.model.model, "gemini-2.5-flash")
        self.assertEqual(lead_analytics_agent.model.model, "gemini-2.5-flash")

    def test_golden_dataset_eval_harness(self):
        """Executes full evaluation harness against the golden dataset and asserts 100% pass rate."""
        harness = GoldenDatasetEvalHarness()
        report = harness.run_evaluation()
        self.assertEqual(report["status"], "PASSED")
        self.assertGreaterEqual(report["overall_accuracy_percentage"], 90.0)
        self.assertEqual(report["passed_test_cases"], report["total_test_cases"])


if __name__ == "__main__":
    unittest.main()
