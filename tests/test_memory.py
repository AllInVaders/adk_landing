import unittest
import asyncio
import os
from growth_hacker_agent.memory import HistoryCompactor, MemoryConsolidator


class TestMemory(unittest.TestCase):
    """Verifies token-aware history compaction and asynchronous memory consolidation."""

    def test_history_compactor_preserves_short_dialogue(self):
        compactor = HistoryCompactor(max_tokens=4000, max_turns=10)
        messages = [
            {"role": "system", "content": "System instruction."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        compacted = compactor.compact_history(messages)
        self.assertEqual(len(compacted), 3)

    def test_history_compactor_summarizes_long_dialogue(self):
        compactor = HistoryCompactor(max_tokens=100, max_turns=4, keep_recent_turns=2)
        messages = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Turn 1: Here is a long paragraph explaining the product idea in detail."},
            {"role": "assistant", "content": "Turn 2: Understood, here is the conversion strategy brief for you."},
            {"role": "user", "content": "Turn 3: Great, please generate the landing page files."},
            {"role": "assistant", "content": "Turn 4: Done! Files are ready."},
            {"role": "user", "content": "Turn 5: Let's deploy to Cloud Run."},
            {"role": "assistant", "content": "Turn 6: Ready to deploy."}
        ]
        compacted = compactor.compact_history(messages)
        # Should contain system message, compacted summary, and recent turns
        has_summary = any("[CONVERSATION SUMMARY" in m.get("content", "") for m in compacted)
        self.assertTrue(has_summary)

    def test_async_memory_consolidation(self):
        test_file = os.path.join(os.path.dirname(__file__), "test_long_term_memory.json")
        consolidator = MemoryConsolidator(memory_file_path=test_file)
        messages = [
            {"role": "user", "content": "Product: SmartBrew Kettle. URL: https://lp-smartbrew-xyz.run.app"}
        ]
        res = asyncio.run(consolidator.extract_and_consolidate("session-123", messages))
        self.assertEqual(res["extracted_facts"].get("product_name"), "SmartBrew")
        if os.path.exists(test_file):
            os.remove(test_file)


if __name__ == "__main__":
    unittest.main()
