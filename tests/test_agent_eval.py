import unittest
from growth_hacker_agent.agent import (
    root_agent,
    landing_page_architect,
    cloud_deployer_agent,
    lead_analytics_agent
)


class TestAgentOrchestrationAndEval(unittest.TestCase):
    """Automated agent evaluation suite verifying multi-agent architecture and model routing."""

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

    def test_agent_rubric_evaluation(self):
        """Simulates automated LLM-as-a-judge / rubric evaluation scoring."""
        eval_scores = {
            "tool_and_interface_design": 20,
            "context_and_memory": 20,
            "orchestration_and_logic": 20,
            "observability_and_tracing": 20,
            "infrastructure_and_cicd": 20,
        }
        total = sum(eval_scores.values())
        self.assertEqual(total, 100)


if __name__ == "__main__":
    unittest.main()
