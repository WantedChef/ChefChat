"""Conversation Memory System for ChefChat.

Provides persistent, intelligent conversation memory with:
- Disk-based persistence (survives restarts)
- Automatic summarization of long conversations
- Memory search and recall
- Token-aware context management
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Constants
MAX_CONTEXT_MESSAGES = 20  # Max messages to keep in active context
SUMMARY_TRIGGER_COUNT = 30  # Summarize when exceeding this count
MEMORY_FILE_VERSION = 1


@dataclass
class MemoryEntry:
    """A single memory entry with metadata."""

    role: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    token_estimate: int = 0
    summary: bool = False  # True if this is a summary message

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "token_estimate": self.token_estimate,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            token_estimate=data.get("token_estimate", 0),
            summary=data.get("summary", False),
        )


@dataclass
class ConversationSummary:
    """Summary of a conversation segment."""

    content: str
    message_count: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    topics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "message_count": self.message_count,
            "timestamp": self.timestamp,
            "topics": self.topics,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationSummary:
        return cls(
            content=data.get("content", ""),
            message_count=data.get("message_count", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            topics=data.get("topics", []),
        )


class ConversationMemory:
    """Manages conversation memory with persistence and summarization."""

    def __init__(
        self,
        chat_id: int | str,
        storage_dir: Path | None = None,
        max_context_messages: int = MAX_CONTEXT_MESSAGES,
    ) -> None:
        self.chat_id = str(chat_id)
        self.storage_dir = storage_dir or Path.home() / ".chefchat" / "memory"
        self.max_context_messages = max_context_messages

        # In-memory state
        self.entries: list[MemoryEntry] = []
        self.summaries: list[ConversationSummary] = []
        self.key_facts: list[str] = []  # Important facts to always include
        self.user_info: dict[
            str, str
        ] = {}  # Extracted user info (name, preferences, etc)

        # Stats
        self.total_messages_ever: int = 0
        self.session_start: str = datetime.now().isoformat()

        # Load from disk if exists
        self._ensure_storage_dir()
        self._load_from_disk()

    @property
    def memory_file(self) -> Path:
        """Get the memory file path for this chat."""
        safe_id = hashlib.md5(self.chat_id.encode()).hexdigest()[:12]
        return self.storage_dir / f"chat_{safe_id}.json"

    def _ensure_storage_dir(self) -> None:
        """Create storage directory if it doesn't exist."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _load_from_disk(self) -> None:
        """Load conversation memory from disk."""
        if not self.memory_file.exists():
            return

        try:
            data = json.loads(self.memory_file.read_text())
            if data.get("version") != MEMORY_FILE_VERSION:
                logger.warning("Memory file version mismatch, starting fresh")
                return

            self.entries = [MemoryEntry.from_dict(e) for e in data.get("entries", [])]
            self.summaries = [
                ConversationSummary.from_dict(s) for s in data.get("summaries", [])
            ]
            self.key_facts = data.get("key_facts", [])
            self.user_info = data.get("user_info", {})
            self.total_messages_ever = data.get(
                "total_messages_ever", len(self.entries)
            )

            logger.info(
                "memory.load: chat=%s entries=%d summaries=%d",
                self.chat_id,
                len(self.entries),
                len(self.summaries),
            )
        except Exception as e:
            logger.warning("Failed to load memory from disk: %s", e)

    def save_to_disk(self) -> None:
        """Persist conversation memory to disk."""
        try:
            data = {
                "version": MEMORY_FILE_VERSION,
                "chat_id": self.chat_id,
                "entries": [e.to_dict() for e in self.entries],
                "summaries": [s.to_dict() for s in self.summaries],
                "key_facts": self.key_facts,
                "user_info": self.user_info,
                "total_messages_ever": self.total_messages_ever,
                "last_saved": datetime.now().isoformat(),
            }
            self.memory_file.write_text(json.dumps(data, indent=2))
            logger.debug(
                "memory.save: chat=%s entries=%d", self.chat_id, len(self.entries)
            )
        except Exception as e:
            logger.error("Failed to save memory to disk: %s", e)

    def add_message(self, role: str, content: str) -> None:
        """Add a message to memory."""
        if not content or not content.strip():
            return

        # Estimate tokens (rough: ~4 chars per token)
        token_estimate = len(content) // 4

        entry = MemoryEntry(
            role=role, content=content.strip(), token_estimate=token_estimate
        )
        self.entries.append(entry)
        self.total_messages_ever += 1

        # Extract user info if this is a user message
        if role == "user":
            self._extract_user_info(content)

        # Auto-save periodically
        if len(self.entries) % 20 == 0:
            self.save_to_disk()

        logger.debug(
            "memory.add: chat=%s role=%s entries=%d",
            self.chat_id,
            role,
            len(self.entries),
        )

    def _extract_user_info(self, content: str) -> None:
        """Extract key user information from messages."""
        content_lower = content.lower()

        # Extract name patterns
        name_patterns = ["my name is ", "i'm ", "i am ", "call me ", "they call me "]
        for pattern in name_patterns:
            if pattern in content_lower:
                idx = content_lower.index(pattern) + len(pattern)
                # Extract first word after pattern
                remaining = content[idx:].strip()
                words = remaining.split()
                if words:
                    name = words[0].strip(".,!?")
                    if len(name) > 1 and name.isalpha():
                        self.user_info["name"] = name.capitalize()
                        self._add_key_fact(f"User's name is {name.capitalize()}")
                        break

    def _add_key_fact(self, fact: str) -> None:
        """Add a key fact if not already present."""
        if fact not in self.key_facts:
            self.key_facts.append(fact)
            # Keep only most recent 20 facts
            if len(self.key_facts) > 20:
                self.key_facts = self.key_facts[-20:]

    def get_context_messages(self) -> list[dict[str, str]]:
        """Get messages formatted for LLM context."""
        messages: list[dict[str, str]] = []

        # Include summaries first if we have any
        if self.summaries:
            latest_summary = self.summaries[-1]
            messages.append({
                "role": "system",
                "content": f"[Conversation Summary]\n{latest_summary.content}",
            })

        # Include key facts about user
        if self.key_facts:
            facts_text = "\n".join(f"• {fact}" for fact in self.key_facts[-5:])
            messages.append({"role": "system", "content": f"[Key Facts]\n{facts_text}"})

        # Include recent messages
        recent = self.entries[-self.max_context_messages :]
        for entry in recent:
            messages.append({"role": entry.role, "content": entry.content})

        return messages

    def get_context_injection(self) -> str | None:
        """Get context to inject into system prompt."""
        parts = []

        if self.user_info.get("name"):
            parts.append(f"The user's name is {self.user_info['name']}.")

        if self.key_facts:
            facts = self.key_facts[-5:]
            parts.append("Key facts from conversation: " + "; ".join(facts))

        if self.summaries:
            parts.append(f"Previous conversation summary: {self.summaries[-1].content}")

        return " ".join(parts) if parts else None

    def needs_summarization(self) -> bool:
        """Check if conversation needs summarization."""
        return len(self.entries) > SUMMARY_TRIGGER_COUNT

    def create_summary_prompt(self) -> str:
        """Create a prompt for summarizing the conversation."""
        messages_text = "\n".join(
            f"{e.role.upper()}: {e.content[:200]}" for e in self.entries[:-5]
        )
        return f"""Summarize this conversation in 2-3 sentences. Focus on:
1. Main topics discussed
2. Key information shared by the user (name, preferences, etc)
3. Important decisions or conclusions

Conversation:
{messages_text}

Summary:"""

    def apply_summary(self, summary_text: str) -> None:
        """Apply a summary and compact the conversation."""
        # Extract topics from summary (simple heuristic)
        topics = []
        for word in summary_text.split():
            if len(word) > 4 and word[0].isupper():
                topics.append(word.strip(".,!?"))

        summary = ConversationSummary(
            content=summary_text, message_count=len(self.entries), topics=topics[:5]
        )
        self.summaries.append(summary)

        # Keep only recent messages after summarizing
        self.entries = self.entries[-10:]
        self.save_to_disk()

        logger.info(
            "memory.summarize: chat=%s kept=%d", self.chat_id, len(self.entries)
        )

    def clear(self) -> None:
        """Clear all memory for this chat."""
        self.entries = []
        self.summaries = []
        self.key_facts = []
        self.user_info = {}
        self.total_messages_ever = 0

        if self.memory_file.exists():
            self.memory_file.unlink()

        logger.info("memory.clear: chat=%s", self.chat_id)

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        role_counts: dict[str, int] = {}
        total_tokens = 0

        for entry in self.entries:
            role_counts[entry.role] = role_counts.get(entry.role, 0) + 1
            total_tokens += entry.token_estimate

        return {
            "total_entries": len(self.entries),
            "total_messages_ever": self.total_messages_ever,
            "summaries": len(self.summaries),
            "key_facts": len(self.key_facts),
            "user_info": self.user_info,
            "role_counts": role_counts,
            "estimated_tokens": total_tokens,
            "session_start": self.session_start,
        }

    def search(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """Search memory for relevant entries."""
        query_lower = query.lower()
        scored: list[tuple[float, MemoryEntry]] = []

        for entry in self.entries:
            content_lower = entry.content.lower()
            # Simple relevance scoring
            score = 0.0
            if query_lower in content_lower:
                score += 1.0
            # Word overlap
            query_words = set(query_lower.split())
            content_words = set(content_lower.split())
            overlap = len(query_words & content_words)
            score += overlap * 0.2

            if score > 0:
                scored.append((score, entry))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:limit]]


class MemoryManager:
    """Manages conversation memories for multiple chats."""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or Path.home() / ".chefchat" / "memory"
        self._memories: dict[str, ConversationMemory] = {}

    def get_memory(self, chat_id: int | str) -> ConversationMemory:
        """Get or create memory for a chat."""
        chat_id_str = str(chat_id)
        if chat_id_str not in self._memories:
            self._memories[chat_id_str] = ConversationMemory(
                chat_id=chat_id_str, storage_dir=self.storage_dir
            )
        return self._memories[chat_id_str]

    def save_all(self) -> None:
        """Save all memories to disk."""
        for memory in self._memories.values():
            memory.save_to_disk()
