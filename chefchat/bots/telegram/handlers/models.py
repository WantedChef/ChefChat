from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import time
from typing import TYPE_CHECKING

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, constants
from telegram.ext import ContextTypes

from chefchat.core.config import VibeConfig
from chefchat.interface.services import ModelService

if TYPE_CHECKING:
    from chefchat.bots.telegram.telegram_bot import TelegramBotService

logger = logging.getLogger(__name__)


class ModelHandlers:
    """Model selection and status flows."""

    def __init__(
        self,
        svc: TelegramBotService,
        menu_buttons_per_row: int,
        cheap_model_price_threshold: float,
        min_command_args_model_select: int,
        model_service: ModelService | None = None,
    ) -> None:
        self.svc = svc
        self.menu_buttons_per_row = menu_buttons_per_row
        self.cheap_model_price_threshold = cheap_model_price_threshold
        self.min_command_args_model_select = min_command_args_model_select
        self.model_service = model_service or ModelService(self.svc.config)
        home = Path(os.getenv("CHEFCHAT_HOME", Path.home() / ".chefchat"))
        self.model_cache_path = home / "telegram_provider_models.json"
        self.model_cache_ttl = 10 * 60  # 10 minutes

    async def send_model_status_card(self, chat_id: int) -> None:
        """Send current model status with quick actions."""
        info = self.model_service.get_active_model_info()
        if info:
            features = ", ".join(sorted(info.features)) or "n/a"
            active_line = (
                f"🧠 Actief: {info.alias} ({info.provider})\n"
                f"ID: {info.name}\n"
                f"Features: `{features}`"
            )
        else:
            active_line = "⚠️ Geen actief model gevonden."

        bot_policy = self.svc.policy.get_current(chat_id)
        policy_line = f"🔧 Bot-modus: {bot_policy}"

        buttons = [
            [InlineKeyboardButton("🔀 Wissel model", callback_data="mmain")],
            [
                InlineKeyboardButton("Dev", callback_data="botmode:dev"),
                InlineKeyboardButton("Chat", callback_data="botmode:chat"),
                InlineKeyboardButton("Combi", callback_data="botmode:combo"),
            ],
        ]

        if self.svc.application:
            await self.svc.application.bot.send_message(
                chat_id=chat_id,
                text=f"{active_line}\n{policy_line}",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=constants.ParseMode.MARKDOWN,
            )

    async def model_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        try:
            user = update.effective_user
            if not user or not update.message:
                return

            user_id_str = str(user.id)
            allowed = self.svc.bot_manager.get_allowed_users("telegram")
            if user_id_str not in allowed:
                await update.message.reply_text("Access denied.")
                return

            args = [a.strip() for a in (context.args or []) if a.strip()]
            action = args[0].lower() if args else ""

            if action in {"list", "select", "status"}:
                await self._legacy_model_handler(update, context, action, args[1:])
                return

            active_model = self.model_service.get_active_model_info()

            categories = [
                ("👨‍💻 Coding", "coding"),
                ("🧠 Reasoning", "reasoning"),
                ("⚡ Speed", "speed"),
                ("👁️ Vision", "vision"),
                ("💰 Free/Cheap", "cost_effective"),
                ("📦 All Models", "all"),
            ]

            buttons = []
            row = []
            for label, tag in categories:
                row.append(InlineKeyboardButton(label, callback_data=f"mcat:{tag}"))
                if len(row) == self.menu_buttons_per_row:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)

            if active_model:
                text = (
                    f"🧠 **Model Control Strategy**\n\n"
                    f"Current Active Model:\n"
                    f"🌟 **{active_model.alias}**\n"
                    f"Testing: {active_model.name}\n"
                    f"Provider: {active_model.provider}\n\n"
                    f"👇 **Select a specialized fleet:**"
                )
            else:
                text = (
                    "🧠 **Model Control Strategy**\n\n"
                    "⚠️ No active model configured.\n\n"
                    "👇 **Select a specialized fleet:**"
                )

            reply_markup = InlineKeyboardMarkup(buttons)
            await update.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except Exception as exc:
            logger.exception("telegram.model.command failed: %s", exc)
            if update.message:
                await update.message.reply_text(f"❌ Model command failed: {exc}")

    async def _legacy_model_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        action: str,
        args: list[str],
    ) -> None:
        try:
            if action == "list":
                await self._perform_model_list(update)
            elif action == "select":
                full_args = ["select"] + args
                await self._perform_model_select(update, full_args)
            elif action == "status":
                await self.send_model_status_card(update.effective_chat.id)
        except Exception as exc:
            logger.exception("telegram.model.legacy failed: %s", exc)
            if update.message:
                await update.message.reply_text(f"❌ Model command failed: {exc}")

    async def _perform_model_list(self, update: Update) -> None:
        refresh_msg = self._refresh_models_from_disk()
        lines = ["🧠 Beschikbare modellen:"]
        active = (self.svc.config.active_model or "").lower()
        models = sorted(self.model_service.list_all_models(), key=lambda x: x.alias)
        for m in models:
            is_active = m.alias.lower() == active or m.model_id.lower() == active
            marker = "✅" if is_active else "•"
            price = ""
            if m.input_price or m.output_price:
                price = f" | ${m.input_price:.2f}/{m.output_price:.2f} per MT"
            features = f" [{', '.join(sorted(m.features))}]" if m.features else ""
            lines.append(f"{marker} {m.alias} ({m.provider}{price}){features}")
        if refresh_msg:
            lines.append(f"\n{refresh_msg}")
        await update.message.reply_text("\n".join(lines))

    async def _perform_model_select(self, update: Update, args: list[str]) -> None:
        if len(args) < self.min_command_args_model_select:
            await update.message.reply_text("Usage: /model select <alias>")
            return

        target = args[1].lower()
        success, message = self.model_service.switch_model(target)
        if not success:
            await update.message.reply_text(message)
            return

        self._propagate_active_model(self.svc.config.active_model)
        await update.message.reply_text(
            f"✅ Switched model to: {self.svc.config.active_model}"
        )

    async def _handle_model_list(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        try:
            _ = self._refresh_models_from_disk()
            lines = ["Available models:"]
            active = (self.svc.config.active_model or "").lower()
            for m in sorted(
                self.model_service.list_all_models(), key=lambda x: x.alias
            ):
                is_active = m.alias.lower() == active or m.model_id.lower() == active
                marker = "✅" if is_active else "•"
                lines.append(f"{marker} {m.alias} ({m.provider})")
            await update.message.reply_text("\n".join(lines))
        except Exception as exc:
            logger.exception("telegram.model.list failed: %s", exc)
            await update.message.reply_text(f"❌ Model list failed: {exc}")

    async def _handle_model_select_prompt(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        if not user or not update.message:
            return

        user_id_str = str(user.id)
        allowed = self.svc.bot_manager.get_allowed_users("telegram")
        if user_id_str not in allowed:
            await update.message.reply_text("Access denied.")
            return

        await update.message.reply_text(
            "Please use: `/model select <alias>`\n\n"
            "Or type `modellist` to see available models.",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    def _propagate_active_model(self, alias: str) -> None:
        """Sync active model to all sessions and agents."""
        if not alias:
            return
        self.svc.config.active_model = alias
        for session in self.svc.sessions.values():
            session.config.active_model = alias
            session.agent.config.active_model = alias

    def _refresh_models_from_disk(self) -> str:
        try:
            latest = VibeConfig.load()
        except Exception as exc:
            return f"❌ Fout bij herladen: {exc}"

        self.svc.config.models = latest.models
        self.svc.config.providers = latest.providers
        self.svc.config.active_model = latest.active_model
        # Refresh model service with new config snapshot
        self.model_service = ModelService(self.svc.config)

        for session in self.svc.sessions.values():
            session.config.models = latest.models
            session.config.providers = latest.providers
            session.config.active_model = latest.active_model
            session.agent.config.models = latest.models
            session.agent.config.providers = latest.providers
            session.agent.config.active_model = latest.active_model

        return "✅ Modellen herladen vanaf config."

    def _load_cached_provider_models(self) -> tuple[dict[str, list[str]], float]:
        if not self.model_cache_path.exists():
            return {}, 0.0
        try:
            data = json.loads(self.model_cache_path.read_text())
            return data.get("models", {}), float(data.get("ts", 0.0))
        except Exception:
            return {}, 0.0

    def _save_cached_provider_models(self, models: dict[str, list[str]]) -> None:
        payload = {"ts": time.time(), "models": models}
        self.model_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.model_cache_path.write_text(json.dumps(payload, indent=2))

    async def _fetch_provider_models_live(self) -> dict[str, list[str]]:
        results: dict[str, list[str]] = {}
        async with httpx.AsyncClient(timeout=10) as client:
            for provider in self.svc.config.providers:
                if not provider.api_base:
                    continue
                url = provider.api_base.rstrip("/") + "/models"
                headers = {"Content-Type": "application/json"}
                if provider.api_key_env_var:
                    key = os.getenv(provider.api_key_env_var, "")
                    if key:
                        headers["Authorization"] = f"Bearer {key}"
                try:
                    resp = await client.get(url, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    names: list[str] = []
                    if isinstance(data, dict) and "data" in data:
                        for item in data["data"]:
                            if isinstance(item, dict):
                                ident = item.get("id") or item.get("name")
                                if ident:
                                    names.append(str(ident))
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                ident = item.get("id") or item.get("name")
                                if ident:
                                    names.append(str(ident))
                            elif isinstance(item, str):
                                names.append(item)
                    results[provider.name] = sorted(set(names))
                except Exception as exc:
                    results.setdefault(provider.name, [])
                    logger.debug(
                        "modelrefresh: provider list failed for %s: %s",
                        provider.name,
                        exc,
                    )
        return results

    async def _fetch_provider_models(
        self, force: bool = False
    ) -> tuple[dict[str, list[str]], bool]:
        cached, ts = self._load_cached_provider_models()
        if cached and not force and (time.time() - ts) < self.model_cache_ttl:
            return cached, True

        live = await self._fetch_provider_models_live()
        if live:
            self._save_cached_provider_models(live)
            return live, False

        if cached:
            return cached, True
        return {}, False

    async def model_refresh_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat_id = update.effective_chat.id
        refresh_msg = self._refresh_models_from_disk()

        provider_models, from_cache = await self._fetch_provider_models()
        lines = [refresh_msg]
        if provider_models:
            lines.append("🔄 Provider model scan" + (" (cache)" if from_cache else ""))
            for name, models in sorted(provider_models.items()):
                if models:
                    lines.append(f"• {name}: {len(models)} models available")
                else:
                    lines.append(f"• {name}: (no list or auth missing)")
        else:
            lines.append("ℹ️ Geen providers gevonden voor modelverversing.")

        await self.svc._send_message(chat_id, "\n".join(lines))
        await self.send_model_status_card(chat_id)

    async def _handle_model_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        data = query.data

        if data == "mmain":
            await self._show_model_root_menu(update)
            return

        if data.startswith("mcat:"):
            category = data.split(":", 1)[1]
            await self._show_model_category(update, category)
            return

        if data.startswith("mod:"):
            alias = data.split(":", 1)[1]
            await self._select_model_and_confirm(update, alias)
            return

    async def _show_model_root_menu(self, update: Update) -> None:
        active_model = self.model_service.get_active_model_info()

        categories = [
            ("👨‍💻 Coding", "coding"),
            ("🧠 Reasoning", "reasoning"),
            ("⚡ Speed", "speed"),
            ("👁️ Vision", "vision"),
            ("💰 Free/Cheap", "cost_effective"),
            ("📦 All Models", "all"),
        ]

        buttons = []
        row = []
        for label, tag in categories:
            row.append(InlineKeyboardButton(label, callback_data=f"mcat:{tag}"))
            if len(row) == self.menu_buttons_per_row:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        if active_model:
            text = (
                f"🧠 **Model Control Strategy**\n\n"
                f"Current Active Model:\n"
                f"🌟 **{active_model.alias}**\n"
                f"Testing: {active_model.name}\n"
                f"Provider: {active_model.provider}\n\n"
                f"👇 **Select a specialized fleet:**"
            )
        else:
            text = (
                "🧠 **Model Control Strategy**\n\n"
                "⚠️ No active model configured.\n\n"
                "👇 **Select a specialized fleet:**"
            )

        reply_markup = InlineKeyboardMarkup(buttons)
        try:
            await update.callback_query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except Exception:
            pass

    async def _show_model_category(self, update: Update, category: str) -> None:
        active = (self.svc.config.active_model or "").lower()
        models = []
        for m in self.model_service.list_all_models():
            if category == "all":
                models.append(m)
                continue

            if category == "vision" and m.supports_vision:
                models.append(m)
                continue

            if category == "cost_effective":
                if (m.input_price or 0) < self.cheap_model_price_threshold:
                    models.append(m)
                continue

            if category in m.features:
                models.append(m)

        models.sort(key=lambda x: (x.alias != active, x.alias))

        buttons = []
        for m in models:
            marker = "✅" if m.alias == active else ""
            label = f"{marker} {m.alias} [{m.provider}]"
            buttons.append([
                InlineKeyboardButton(label, callback_data=f"mod:{m.alias}")
            ])

        buttons.append([
            InlineKeyboardButton("🔙 Back to Fleets", callback_data="mmain")
        ])

        reply_markup = InlineKeyboardMarkup(buttons)

        cat_names = {
            "coding": "👨‍💻 Coding Specialists",
            "reasoning": "🧠 Reasoning Engines",
            "speed": "⚡ High Speed Models",
            "vision": "👁️ Multimodal/Vision",
            "cost_effective": "💰 High Efficiency",
            "all": "📦 All Available Models",
        }
        cat_title = cat_names.get(category, "Models")

        text = f"**{cat_title}**\nSelect a model to deploy:"

        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    async def _select_model_and_confirm(self, update: Update, alias: str) -> None:
        model = self.model_service.find_model_by_alias(alias)
        if not model:
            await update.callback_query.answer("Model not found!", show_alert=True)
            return
        logger.info(
            "telegram.model.switch",
            extra={
                "chat_id": update.effective_chat.id,
                "model": model.alias,
                "provider": model.provider,
            },
        )

        success, message = self.model_service.switch_model(model.alias)
        if not success:
            await update.callback_query.answer(message, show_alert=True)
            return

        self._propagate_active_model(model.alias)

        await update.callback_query.answer(f"Switched to {model.alias}")
        await self._show_model_root_menu(update)
