from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from chefchat.interface.services import ModelService

if TYPE_CHECKING:
    from chefchat.bots.discord.bot import DiscordBotService

logger = logging.getLogger(__name__)


class ModelSelectView(discord.ui.View):
    def __init__(self, svc: DiscordBotService, model_handlers: ModelHandlers) -> None:
        super().__init__(timeout=None)
        self.svc = svc
        self.handlers = model_handlers

    @discord.ui.select(
        placeholder="Select a category...",
        options=[
            discord.SelectOption(
                label="👨‍💻 Coding",
                value="coding",
                description="Specialized coding models",
            ),
            discord.SelectOption(
                label="🧠 Reasoning",
                value="reasoning",
                description="High intelligence models",
            ),
            discord.SelectOption(
                label="⚡ Speed", value="speed", description="Fast and cheap models"
            ),
            discord.SelectOption(
                label="👁️ Vision", value="vision", description="Multimodal models"
            ),
            discord.SelectOption(
                label="📦 All Models", value="all", description="List everything"
            ),
        ],
        custom_id="model_category_select",
    )
    async def select_category(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        category = select.values[0]
        await self.handlers.show_category(interaction, category)


class ModelCategoryView(discord.ui.View):
    def __init__(
        self, svc: DiscordBotService, models: list, model_handlers: ModelHandlers
    ) -> None:
        super().__init__(timeout=None)
        self.svc = svc
        self.models = models
        self.handlers = model_handlers

        # Create a select menu for models in this category
        options = []
        for m in models:
            label = m.alias
            desc = f"{m.provider} - {m.name}"[:100]
            options.append(
                discord.SelectOption(label=label, value=m.alias, description=desc)
            )

        # Discord allows max 25 options.
        MAX_SELECT_OPTIONS = 25
        if len(options) > MAX_SELECT_OPTIONS:
            options = options[:MAX_SELECT_OPTIONS]

        self.select_menu = discord.ui.Select(
            placeholder="Choose a model...",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="model_select_final",
        )
        self.select_menu.callback = self.select_model_callback
        self.add_item(self.select_menu)

    @discord.ui.button(label="🔙 Back", style=discord.ButtonStyle.secondary)
    async def back(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.handlers.show_root_menu(interaction)

    async def select_model_callback(self, interaction: discord.Interaction) -> None:
        alias = self.select_menu.values[0]
        success, message = self.svc.model.model_service.switch_model(alias)

        if success:
            # Propagate change (simplified)
            self.svc.config.active_model = alias
            for session in self.svc.sessions.values():
                session.config.active_model = alias
                session.agent.config.active_model = alias

            await interaction.response.send_message(
                f"✅ Switched to **{alias}**", ephemeral=True
            )
            # Refresh menu with new active state if we were fancy, but simple ack is fine
            await self.handlers.show_root_menu(interaction, edit_original=True)
        else:
            await interaction.response.send_message(
                f"❌ Failed: {message}", ephemeral=True
            )


class ModelHandlers:
    def __init__(self, svc: DiscordBotService) -> None:
        self.svc = svc
        self.model_service = ModelService(svc.config)

    async def handle_message(self, message: discord.Message) -> bool:
        if message.content.strip() == "/model":
            await self.send_model_root(message.channel)
            return True
        return False

    async def send_model_root(self, channel: discord.abc.Messageable) -> None:
        active = self.model_service.get_active_model_info()
        active_text = f"🌟 **{active.alias}** ({active.provider})" if active else "None"

        embed = discord.Embed(
            title="🧠 Model Control",
            description=f"Current Active Model: {active_text}\n\nSelect a category below to browse available models.",
            color=discord.Color.blue(),
        )
        view = ModelSelectView(self.svc, self)
        await channel.send(embed=embed, view=view)

    async def show_root_menu(
        self, interaction: discord.Interaction, edit_original: bool = False
    ) -> None:
        active = self.model_service.get_active_model_info()
        active_text = f"🌟 **{active.alias}** ({active.provider})" if active else "None"

        embed = discord.Embed(
            title="🧠 Model Control",
            description=f"Current Active Model: {active_text}\n\nSelect a category below.",
            color=discord.Color.blue(),
        )
        view = ModelSelectView(self.svc, self)

        if edit_original:
            await interaction.message.edit(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)

    async def show_category(
        self, interaction: discord.Interaction, category: str
    ) -> None:
        models = []
        for m in self.model_service.list_all_models():
            if category == "all":
                models.append(m)
            elif category == "vision" and m.supports_vision:
                models.append(m)
            elif category == "coding" and "coding" in m.features:
                models.append(m)
            elif category == "reasoning" and "reasoning" in m.features:
                models.append(m)
            elif category == "speed" and "speed" in m.features:
                models.append(m)

        # Sort by alias
        models.sort(key=lambda x: x.alias)

        if not models:
            await interaction.response.send_message(
                f"No models found in {category}", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"Category: {category.title()}",
            description="Select a model from the dropdown below.",
            color=discord.Color.green(),
        )
        view = ModelCategoryView(self.svc, models, self)
        await interaction.response.edit_message(embed=embed, view=view)
