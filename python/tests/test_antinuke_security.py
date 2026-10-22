import asyncio
import os
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock
# Add python directory to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import discord

from config.settings import settings, COLORS, EMOJIS
from core.security.antinuke import AntiNukeManager, AntiNukeConstants, get_default_thresholds, get_default_punishments
from core.security.antinuke_service import AntiNukeService
from apps.bot.discord.commands.registry import commands_registry
from plugins.MomentumOneToolkit import Plugin as ToolkitPlugin
from core.plugins.context import PluginContext
from core.events.event_bus import EventBus
from database.database import database
from shared.types.command_record import CommandType


class TestAntiNukeSecurity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Clear command registry and register toolkit
        commands_registry.clear()
        mock_client = MagicMock()
        mock_ctx = PluginContext(
            event_bus=EventBus(),
            client=mock_client,
            logger=MagicMock(),
            cache=MagicMock(),
            database_manager=database,
        )
        plugin = ToolkitPlugin(mock_ctx)
        await plugin.on_load()

    def test_security_commands_registered(self):
        """Validates all security commands are registered independently under Security category."""
        expected_cmds = ["antinuke", "setup", "whitelist", "unwhitelist", "punishment"]
        for cmd_name in expected_cmds:
            cmd = commands_registry.get(cmd_name)
            self.assertIsNotNone(cmd, f"Command '{cmd_name}' should be registered in commands_registry.")
            self.assertEqual(cmd.category, "Security", f"Command '{cmd_name}' must belong to 'Security' category.")
            self.assertTrue(len(cmd.description) > 0, f"Command '{cmd_name}' must have a description.")
            self.assertTrue(len(cmd.usage) > 0, f"Command '{cmd_name}' must have usage instructions.")

    def test_all_23_events_mapped_and_friendly(self):
        """Validates all 23 Discord event keys have human-readable display names and no raw keys."""
        self.assertEqual(len(AntiNukeConstants.ALL_EVENTS), 24)  # 23 Discord.js mapped + bot_add
        for ev in AntiNukeConstants.ALL_EVENTS:
            display_name = AntiNukeConstants.get_event_display_name(ev)
            self.assertNotEqual(display_name, ev, f"Display name for '{ev}' should not be raw key.")
            self.assertTrue(len(display_name) > 3, f"Display name for '{ev}' should be human-readable.")
            desc = AntiNukeConstants.get_event_description(ev)
            self.assertTrue(len(desc) > 5, f"Description for '{ev}' should be provided.")

    def test_setup_enforcement_prevents_unconfigured_management(self):
        """Validates no anti-nuke management commands operate before setup is complete."""
        guild_id = "test_guild_99999"
        cfg = AntiNukeManager.get_guild_config(guild_id)
        cfg["setup_completed"] = False
        self.assertFalse(AntiNukeManager.is_setup_completed(guild_id))

        mock_guild = MagicMock()
        mock_guild.id = 99999
        mock_guild.name = "Test Security Guild"

        view = AntiNukeManager.build_setup_required_view(mock_guild)
        self.assertIsNotNone(view)

    def test_scoped_whitelists(self):
        """Validates whitelists by user, role, channel, and category."""
        guild_id = "test_guild_12345"
        cfg = AntiNukeManager.get_guild_config(guild_id)

        # 1. User whitelist
        cfg["whitelists"]["1111"] = {"type": "user", "name": "TrustedUser", "events": ["guildBanAdd"]}
        user_mock = MagicMock()
        user_mock.id = 1111
        user_mock.roles = []
        self.assertTrue(AntiNukeManager.is_whitelisted(guild_id, user_mock, "guildBanAdd"))
        self.assertFalse(AntiNukeManager.is_whitelisted(guild_id, user_mock, "channelDelete"))

        # 2. Role whitelist
        cfg["whitelists"]["2222"] = {"type": "role", "name": "SeniorMod", "events": ["channelDelete"]}
        role_mock = MagicMock()
        role_mock.id = 2222
        user_with_role = MagicMock()
        user_with_role.id = 3333
        user_with_role.roles = [role_mock]
        self.assertTrue(AntiNukeManager.is_whitelisted(guild_id, user_with_role, "channelDelete"))
        self.assertFalse(AntiNukeManager.is_whitelisted(guild_id, user_with_role, "guildBanAdd"))

        # 3. Channel whitelist
        cfg["whitelists"]["4444"] = {"type": "channel", "name": "testing-ch", "events": ["channelDelete"]}
        ch_mock = MagicMock()
        ch_mock.id = 4444
        ch_mock.category = None
        other_user = MagicMock()
        other_user.id = 5555
        other_user.roles = []
        self.assertTrue(AntiNukeManager.is_whitelisted(guild_id, other_user, "channelDelete", channel=ch_mock))

    def test_ticket_bot_exemptions(self):
        """Validates ticket bots are exempt for ticket channel operations, but protected against bans/kicks."""
        guild_id = "987654321"
        cfg = AntiNukeManager.get_guild_config(guild_id)
        cfg["ticket_bots"] = ["98765"]

        mock_guild = MagicMock()
        mock_guild.id = int(guild_id)

        ticket_ch = MagicMock()
        ticket_ch.name = "ticket-0042"
        ticket_ch.topic = "User Ticket"
        ticket_ch.category = None

        general_ch = MagicMock()
        general_ch.name = "general-chat"
        general_ch.topic = None
        general_ch.category = None

        # Ticket channel operations -> EXEMPT
        self.assertTrue(AntiNukeManager.is_ticket_bot_exempt(mock_guild, "98765", AntiNukeConstants.EVENT_CHANNEL_CREATE, ticket_ch))
        self.assertTrue(AntiNukeManager.is_ticket_bot_exempt(mock_guild, "98765", AntiNukeConstants.EVENT_CHANNEL_DELETE, ticket_ch))

        # Non-ticket channel operations -> NOT exempt
        self.assertFalse(AntiNukeManager.is_ticket_bot_exempt(mock_guild, "98765", AntiNukeConstants.EVENT_CHANNEL_DELETE, general_ch))

        # Destructive actions (bans, kicks, role deletes) -> NEVER exempt for ticket bot!
        self.assertFalse(AntiNukeManager.is_ticket_bot_exempt(mock_guild, "98765", AntiNukeConstants.EVENT_BAN_ADD, ticket_ch))
        self.assertFalse(AntiNukeManager.is_ticket_bot_exempt(mock_guild, "98765", AntiNukeConstants.EVENT_ROLE_DELETE, ticket_ch))

    async def test_antinuke_command_dispatch(self):
        """Validates execution of antinuke and security commands through real dispatch."""
        from plugins.MomentumOneToolkit.commands.security import antinuke, setup as sec_setup, whitelist, unwhitelist, punishment

        mock_guild = MagicMock()
        mock_guild.id = 77777
        mock_guild.name = "MomentumOne HQ"
        mock_guild.owner_id = 12345
        mock_guild.roles = []
        mock_me = MagicMock()
        mock_me.id = 99999
        mock_me.top_role = MagicMock()
        mock_me.top_role.position = 100
        mock_me.guild_permissions.administrator = True
        mock_guild.me = mock_me

        mock_author = MagicMock()
        mock_author.id = 12345  # Server Owner
        mock_author.name = "ServerOwner"

        mock_msg = AsyncMock(spec=discord.Message)
        mock_msg.guild = mock_guild
        mock_msg.author = mock_author
        mock_msg.channel = MagicMock()
        mock_msg.channel.id = 88888

        # 1. Antinuke dashboard
        res = await antinuke.execute(None, "prefix", mock_msg, [])
        mock_msg.reply.assert_called()

        # 2. Setup command
        mock_msg.reply.reset_mock()
        await sec_setup.execute(None, "prefix", mock_msg, [])
        mock_msg.reply.assert_called()

        # 3. Whitelist command before setup -> returns setup required
        mock_msg.reply.reset_mock()
        await whitelist.execute(None, "prefix", mock_msg, [])
        mock_msg.reply.assert_called()

        # 4. Complete setup wizard
        from plugins.MomentumOneToolkit.commands.security.setup import get_or_create_wizard_session
        sess = get_or_create_wizard_session(mock_guild)
        sess["mode"] = "ultimate"
        sess["warning_channel_id"] = "88888"

        # Complete setup
        await AntiNukeManager.save_guild_config(str(mock_guild.id), {
            "setup_completed": True,
            "enabled": True,
            "mode": "ultimate",
            "warning_channel_id": "88888",
        })
        self.assertTrue(AntiNukeManager.is_setup_completed(str(mock_guild.id)))

        # 5. Whitelist command after setup -> manages whitelist
        mock_msg.reply.reset_mock()
        await whitelist.execute(None, "prefix", mock_msg, ["<@12345>", "channelDelete,guildBanAdd"])
        mock_msg.reply.assert_called()

        cfg = AntiNukeManager.get_guild_config(str(mock_guild.id))
        self.assertIn("12345", cfg["whitelists"])
        self.assertIn("channelDelete", cfg["whitelists"]["12345"]["events"])

        # 6. Punishment command after setup -> updates punishment
        mock_msg.reply.reset_mock()
        await punishment.execute(None, "prefix", mock_msg, ["channel", "quarantine"])
        mock_msg.reply.assert_called()

        cfg = AntiNukeManager.get_guild_config(str(mock_guild.id))
        self.assertEqual(cfg["punishments"].get("channelDelete"), "quarantine")

        # 7. Unwhitelist command -> revokes whitelist
        mock_msg.reply.reset_mock()
        await unwhitelist.execute(None, "prefix", mock_msg, ["<@12345>"])
        mock_msg.reply.assert_called()

        cfg = AntiNukeManager.get_guild_config(str(mock_guild.id))
        self.assertNotIn("12345", cfg["whitelists"])

    async def test_component_handler_interactions(self):
        """Validates button and interaction acknowledgements in component_handler."""
        from plugins.MomentumOneToolkit.events.component_handler import execute as handle_component

        mock_guild = MagicMock()
        mock_guild.id = 55555
        mock_guild.name = "Test Interactive Guild"
        mock_guild.owner_id = 11111

        mock_user = MagicMock()
        mock_user.id = 11111  # Root owner

        mock_interaction = AsyncMock(spec=discord.Interaction)
        mock_interaction.type = discord.InteractionType.component
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_user
        mock_interaction.channel = MagicMock()
        mock_interaction.channel.id = 44444
        mock_interaction.response = MagicMock()
        mock_interaction.response.is_done = MagicMock(return_value=False)
        mock_interaction.response.edit_message = AsyncMock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.response.defer = AsyncMock()

        # Wizard Step 1
        mock_interaction.data = {"custom_id": f"an_wiz:step1:{mock_guild.id}"}
        await handle_component(None, mock_interaction)
        mock_interaction.response.edit_message.assert_called()

        # Wizard Set Mode
        mock_interaction.response.edit_message.reset_mock()
        mock_interaction.data = {"custom_id": f"an_wiz:set_mode:hard:{mock_guild.id}"}
        await handle_component(None, mock_interaction)
        mock_interaction.response.edit_message.assert_called()

        # Wizard Complete
        mock_interaction.response.edit_message.reset_mock()
        mock_interaction.data = {"custom_id": f"an_wiz:complete:{mock_guild.id}"}
        await handle_component(None, mock_interaction)
        mock_interaction.response.edit_message.assert_called()

        self.assertTrue(AntiNukeManager.is_setup_completed(mock_guild.id))

    async def test_no_duplicate_custom_ids(self):
        """Verifies that all views and dashboards generate strictly unique custom IDs across all components."""
        from plugins.MomentumOneToolkit.commands.security.antinuke import build_dashboard_view
        from plugins.MomentumOneToolkit.commands.security.setup import (
            build_wizard_step1_view,
            build_wizard_step2_view,
            build_wizard_step3_view,
            build_wizard_step4_view,
            build_wizard_step5_view,
            build_wizard_step6_view,
        )
        from plugins.MomentumOneToolkit.commands.security.whitelist import build_whitelist_type_picker_view
        from plugins.MomentumOneToolkit.commands.security.punishment import build_punishment_overview_view

        mock_guild = MagicMock()
        mock_guild.id = 77777
        mock_guild.name = "ID Uniqueness Test Guild"
        mock_guild.owner_id = 99999
        mock_guild.me = MagicMock()
        mock_guild.me.top_role.position = 50
        mock_guild.roles = []

        views_to_test = []

        # 1. Dashboard when setup is incomplete
        await AntiNukeManager.save_guild_config(str(mock_guild.id), {"setup_completed": False, "enabled": False})
        dash_unconfigured = await build_dashboard_view(mock_guild)
        views_to_test.append(("Dashboard (unconfigured)", dash_unconfigured))

        # 2. Dashboard when setup is complete and enabled
        await AntiNukeManager.save_guild_config(str(mock_guild.id), {"setup_completed": True, "enabled": True})
        dash_configured = await build_dashboard_view(mock_guild)
        views_to_test.append(("Dashboard (configured)", dash_configured))

        # 3. Wizard steps
        views_to_test.append(("Wizard Step 1", await build_wizard_step1_view(mock_guild)))
        views_to_test.append(("Wizard Step 2", await build_wizard_step2_view(mock_guild)))
        views_to_test.append(("Wizard Step 3", await build_wizard_step3_view(mock_guild)))
        views_to_test.append(("Wizard Step 4", await build_wizard_step4_view(mock_guild)))
        views_to_test.append(("Wizard Step 5", await build_wizard_step5_view(mock_guild, current_ch_id=12345)))
        views_to_test.append(("Wizard Step 6", await build_wizard_step6_view(mock_guild)))

        # 4. Whitelist & Punishment views
        views_to_test.append(("Whitelist Type Picker", await build_whitelist_type_picker_view(mock_guild)))
        views_to_test.append(("Punishment Overview", await build_punishment_overview_view(mock_guild)))

        for label, view in views_to_test:
            interactive = view.get_interactive_components()
            custom_ids = [getattr(c, "custom_id", None) for c in interactive if getattr(c, "custom_id", None)]
            duplicate_ids = [cid for cid in custom_ids if custom_ids.count(cid) > 1]
            self.assertEqual(
                len(custom_ids),
                len(set(custom_ids)),
                f"Duplicate custom_id found in {label}: {set(duplicate_ids)}"
            )


if __name__ == "__main__":
    unittest.main()
