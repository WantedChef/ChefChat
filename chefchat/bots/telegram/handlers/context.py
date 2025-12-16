from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import Update, constants
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from chefchat.bots.telegram.telegram_bot import TelegramBotService

logger = logging.getLogger(__name__)


class ContextHandlers:
    """Handlers for context management commands."""

    def __init__(self, svc: TelegramBotService) -> None:
        self.svc = svc

    async def context_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Manage conversation context."""
        if not update.message:
            return
        args = [a.strip() for a in (context.args or []) if a.strip()]
        sub = args[0].lower() if args else "status"
        user = update.effective_user
        if not user:
            return

        session = self.svc._get_session(update.effective_chat.id, str(user.id))
        if not session:
            await self.svc.start(update, context)
            return

        if sub == "clear":
            await self._handle_clear(update, session)
            return

        if sub == "facts":
            await self._handle_facts(update, session)
            return

        if sub == "forget":
            await self._handle_forget(update, session)
            return

        if sub == "search" and len(args) > 1:
            await self._handle_search(update, session, " ".join(args[1:]))
            return

        if sub in {"show", "history"}:
            await self._handle_status(update, session, show_history=True)
            return

        # Default: Status
        await self._handle_status(update, session, show_history=False)

    async def _handle_clear(self, update: Update, session) -> None:
        await session.clear_history()
        await update.message.reply_text(
            "🧹 Context and memory cleared!\n"
            "Bot will no longer remember this conversation."
        )

    async def _handle_facts(self, update: Update, session) -> None:
        stats = session.get_memory_stats()
        user_info = stats.get("user_info", {})
        key_facts = stats.get("key_facts", [])

        lines = ["🧠 **What I Remember About You**"]
        if user_info.get("name"):
            lines.append(f"👤 Name: {user_info['name']}")

        if key_facts:
            lines.append("\n📝 **Key Facts:**")
            for fact in key_facts[-10:]:
                lines.append(f"• {fact}")
        else:
            lines.append("\n_No facts remembered yet._")

        lines.append("\nUse `/context forget` to clear my memory of you.")
        await update.message.reply_text(
            "\n".join(lines), parse_mode=constants.ParseMode.MARKDOWN
        )

    async def _handle_forget(self, update: Update, session) -> None:
        session.memory.key_facts = []
        session.memory.user_info = {}
        session.memory.save_to_disk()
        await update.message.reply_text(
            "🧹 Forgotten all personal information about you."
        )

    async def _handle_search(self, update: Update, session, query: str) -> None:
        results = session.memory.search(query, limit=5)

        if results:
            lines = [f"🔍 **Search Results for:** `{query}`"]
            for i, entry in enumerate(results, 1):
                preview = entry.content[:80].replace("\n", " ")
                if len(entry.content) > 80:
                    preview += "..."
                lines.append(f"{i}. [{entry.role}] {preview}")
            await update.message.reply_text(
                "\n".join(lines), parse_mode=constants.ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(f"No results found for: {query}")

    async def _handle_status(self, update: Update, session, show_history: bool) -> None:
        try:
            messages = session.agent.message_manager.messages
            agent_msg_count = len(messages)
            stats = session.get_memory_stats()

            lines = [
                "🧠 **Conversation Memory Status**",
                "",
                f"📊 **Agent Context:** {agent_msg_count} messages",
                f"💾 **Persistent Memory:** {stats['total_entries']} entries",
                f"📚 **Total Ever:** {stats['total_messages_ever']} messages",
            ]

            if stats["summaries"]:
                lines.append(f"📝 **Summaries:** {stats['summaries']}")

            role_counts = stats.get("role_counts", {})
            if role_counts:
                lines.append("\n**Message Breakdown:**")
                role_emojis = {
                    "system": "🔧",
                    "user": "👤",
                    "assistant": "🤖",
                    "tool": "🛠️",
                }
                for role, count in role_counts.items():
                    emoji = role_emojis.get(role, "❓")
                    lines.append(f"  {emoji} {role}: {count}")

            user_info = stats.get("user_info", {})
            if user_info:
                lines.append(
                    f"\n👤 **I know you as:** {user_info.get('name', 'Unknown')}"
                )

            key_facts = stats.get("key_facts", [])
            if key_facts:
                lines.append(f"📝 **Key Facts:** {len(key_facts)} remembered")

            if show_history:
                lines.append("\n**Recent Messages:**")
                for i, msg in enumerate(
                    messages[-5:], start=max(1, agent_msg_count - 4)
                ):
                    role = (
                        msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                    )
                    content = msg.content or "(no content)"
                    preview = content[:60].replace("\n", " ")
                    if len(content) > 60:
                        preview += "..."
                    lines.append(f"`{i}. {role}`: {preview}")

            lines.append(
                "\n**Commands:**\n"
                "`/context` - Show status\n"
                "`/context show` - View recent messages\n"
                "`/context facts` - Show what I remember\n"
                "`/context search <query>` - Search history\n"
                "`/context clear` - Clear all memory"
            )

            await update.message.reply_text(
                "\n".join(lines), parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.exception("context_command failed")
            await update.message.reply_text(f"❌ Error: {e}")
