"""Context Compaction and Asynchronous Background Memory Consolidation.

Implements token-aware sliding window conversation history compaction, automatic
turn summarization, and non-blocking asynchronous background memory extraction.
"""

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class HistoryCompactor:
    """Sliding-window token and turn compactor for LLM conversational context."""

    def __init__(self, max_tokens: int = 4000, max_turns: int = 10, keep_recent_turns: int = 4):
        self.max_tokens = max_tokens
        self.max_turns = max_turns
        self.keep_recent_turns = keep_recent_turns

    def estimate_tokens(self, text: str) -> int:
        """Estimates token count using standard 4 characters per token heuristic."""
        return max(1, len(text) // 4)

    def compact_history(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Compacts conversation history if turn count or token estimate exceeds bounds."""
        if len(messages) <= self.keep_recent_turns:
            return messages

        total_tokens = sum(self.estimate_tokens(m.get("content", "")) for m in messages)
        if total_tokens <= self.max_tokens and len(messages) <= self.max_turns:
            return messages

        # Separate system messages, older turns to compact, and recent turns to preserve
        system_msgs = [m for m in messages if m.get("role") == "system"]
        chat_msgs = [m for m in messages if m.get("role") != "system"]

        if len(chat_msgs) <= self.keep_recent_turns:
            return messages

        older_turns = chat_msgs[:-self.keep_recent_turns]
        recent_turns = chat_msgs[-self.keep_recent_turns:]

        # Compact older turns into a structured high-density summary
        summary_lines = []
        for m in older_turns:
            role = m.get("role", "unknown")
            snippet = m.get("content", "").strip()
            # Truncate long snippets in summary
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            summary_lines.append(f"- {role.capitalize()}: {snippet}")

        compacted_summary = (
            "[CONVERSATION SUMMARY OF EARLIER TURNS]\n" + "\n".join(summary_lines)
        )

        compacted_messages = list(system_msgs)
        compacted_messages.append({"role": "system", "content": compacted_summary})
        compacted_messages.extend(recent_turns)

        return compacted_messages


class MemoryConsolidator:
    """Asynchronous background memory consolidator that extracts structured project metadata."""

    def __init__(self, memory_file_path: Optional[str] = None):
        if not memory_file_path:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            memory_file_path = os.path.join(base_dir, "long_term_memory.json")
        self.memory_file_path = memory_file_path
        self._lock = asyncio.Lock()

    async def extract_and_consolidate(self, session_id: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Analyzes messages asynchronously and persists extracted project facts."""
        consolidated = {
            "session_id": session_id,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "extracted_facts": {}
        }

        full_text = " ".join([m.get("content", "") for m in messages])

        # Extract product name or slug if present
        proj_match = re.search(r'(?:product|proyecto|slug|name)\s*[:=]\s*([a-zA-Z0-9-_]+)', full_text, re.IGNORECASE)
        if proj_match:
            consolidated["extracted_facts"]["product_name"] = proj_match.group(1)

        # Extract live Cloud Run URLs if present
        url_match = re.findall(r'https://[a-zA-Z0-9-]+\.run\.app', full_text)
        if url_match:
            consolidated["extracted_facts"]["cloud_run_urls"] = list(set(url_match))

        # Save to persistent file
        async with self._lock:
            try:
                data = {}
                if os.path.exists(self.memory_file_path):
                    with open(self.memory_file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                data[session_id] = consolidated
                with open(self.memory_file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

        return consolidated

    def trigger_async_consolidation(self, session_id: str, messages: List[Dict[str, str]]):
        """Dispatches consolidation to a non-blocking background async task."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.extract_and_consolidate(session_id, messages))
        except RuntimeError:
            pass
