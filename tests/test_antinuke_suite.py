import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
import discord

from core.security.antinuke import AntiNukeManager, AntiNukeConstants
from plugins.MomentumOneToolkit.commands.security.setup import (
    build_wizard_step1_view,
    build_wizard_step2_view,
    build_wizard_step3_view,
    build_wizard_step4_view,
    build_wizard_step5_view,
    build_wizard_step6_view,
    build_wizard_step7_view,
    build_wizard_step8_view,
    build_wizard_step9_view,
    build_wizard_step10_view,
    build_wizard_step11_view,
    get_or_create_wizard_session,
)
from plugins.MomentumOneToolkit.commands.security.antinuke import (
    build_dashboard_view,
    build_overview_panel,
    build_security_panel,
    build_event_manager_panel,
    build_channels_panel,
    build_ticket_bots_panel,
    build_extra_owners_panel,
    build_access_panel,
    build_permission_manager_panel,
)
from plugins.MomentumOneToolkit.commands.security.punishment import build_punishment_panel_view
from plugins.MomentumOneToolkit.commands.security.thresholds import (
    build_threshold_overview_view,
    build_thresholds_dashboard_view,
)
from plugins.MomentumOneToolkit.commands.security.extraowner import (
    build_extraowner_main_view,
    build_extraowner_set_view,
    build_extraowner_remove_view,
)
from plugins.MomentumOneToolkit.events import component_handler


class TestAntiNukeSuite(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create mock guild
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 987654321
        self.guild.name = "Test Security Guild"
        self.guild.owner_id = 111222333

        # Mock guild.me
        me = MagicMock(spec=discord.Member)
        me.id = 999888777
        top_role = MagicMock(spec=discord.Role)
        top_role.name = "MomentumOne Security Bot"
        top_role.position = 50
        top_role.is_default.return_value = False
        me.top_role = top_role

        me_perms = MagicMock()
        me_perms.administrator = True
        me_perms.ban_members = True
        me_perms.kick_members = True
        me_perms.manage_roles = True
        me_perms.manage_channels = True
        me_perms.view_audit_log = True
        me.guild_permissions = me_perms
        self.guild.me = me

        # Mock roles
        self.guild.roles = [top_role]

        # Reset guild config
        AntiNukeManager._guild_configs[str(self.guild.id)] = {
            "guild_id": str(self.guild.id),
            "setup_completed": True,
            "enabled": True,
            "mode": AntiNukeConstants.MODE_HARD,
            "monitored_events": list(AntiNukeConstants.ALL_EVENTS),
            "extra_owners": [],
            "whitelists": {},
            "ticket_bots": [],
            "warning_channel_id": "123456",
            "log_channel_id": "654321",
            "thresholds": {},
            "punishments": {},
        }

    async def test_setup_wizard_all_11_steps(self):
        """Validates that all 11 steps of the setup wizard render without coroutine or component errors."""
        sess = get_or_create_wizard_session(self.guild)
        sess["warning_channel_id"] = "123456"
        sess["log_channel_id"] = "654321"

        v1 = await build_wizard_step1_view(self.guild)
        self.assertIsNotNone(v1)

        v2 = await build_wizard_step2_view(self.guild)
        self.assertIsNotNone(v2)

        v3 = await build_wizard_step3_view(self.guild)
        self.assertIsNotNone(v3)

        v4 = await build_wizard_step4_view(self.guild)
        self.assertIsNotNone(v4)

        v5 = await build_wizard_step5_view(self.guild)
        self.assertIsNotNone(v5)

        v6 = await build_wizard_step6_view(self.guild)
        self.assertIsNotNone(v6)

        v7 = await build_wizard_step7_view(self.guild)
        self.assertIsNotNone(v7)

        v8 = await build_wizard_step8_view(self.guild)
        self.assertIsNotNone(v8)

        v9 = await build_wizard_step9_view(self.guild)
        self.assertIsNotNone(v9)

        v10 = await build_wizard_step10_view(self.guild)
        self.assertIsNotNone(v10)

        v11 = await build_wizard_step11_view(self.guild)
        self.assertIsNotNone(v11)

    async def test_compact_dashboard_and_panels(self):
        """Validates that compact dashboard and all sub-panels render successfully."""
        dash = await build_dashboard_view(self.guild)
        self.assertIsNotNone(dash)

        overview = await build_overview_panel(self.guild)
        self.assertIsNotNone(overview)

        sec = await build_security_panel(self.guild)
        self.assertIsNotNone(sec)

        ev_panel = await build_event_manager_panel(self.guild)
        self.assertIsNotNone(ev_panel)

        channels = await build_channels_panel(self.guild)
        self.assertIsNotNone(channels)

        tb = await build_ticket_bots_panel(self.guild)
        self.assertIsNotNone(tb)

        eo = await build_extra_owners_panel(self.guild)
        self.assertIsNotNone(eo)

        acc = await build_access_panel(self.guild)
        self.assertIsNotNone(acc)

        perm = await build_permission_manager_panel(self.guild)
        self.assertIsNotNone(perm)

    async def test_punishment_and_threshold_views(self):
        """Validates punishment and threshold views render properly."""
        pn_view = await build_punishment_panel_view(self.guild)
        self.assertIsNotNone(pn_view)

        th_view = await build_threshold_overview_view(self.guild, user_id=111222333)
        self.assertIsNotNone(th_view)

        th_alias = await build_thresholds_dashboard_view(self.guild, user_id=111222333)
        self.assertIsNotNone(th_alias)

    async def test_extraowner_views(self):
        """Validates extraowner views render properly."""
        eo_main = await build_extraowner_main_view(self.guild)
        self.assertIsNotNone(eo_main)

        eo_set = await build_extraowner_set_view(self.guild)
        self.assertIsNotNone(eo_set)

        eo_remove = await build_extraowner_remove_view(self.guild)
        self.assertIsNotNone(eo_remove)

    async def test_component_handler_dispatch(self):
        """Simulates Discord interaction callbacks across all components."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.guild = self.guild
        interaction.user = MagicMock()
        interaction.user.id = self.guild.owner_id  # Authorized as server owner

        response = MagicMock()
        response.is_done.return_value = False
        response.edit_message = AsyncMock()
        interaction.response = response

        # Test dashboard panel select
        interaction.data = {"custom_id": f"an:panel_select:{self.guild.id}", "values": ["events"]}
        await component_handler.execute(None, interaction)
        response.edit_message.assert_called()

        # Test threshold button callback
        response.edit_message.reset_mock()
        interaction.data = {"custom_id": f"an_th:set_count:channelDelete:2:{self.guild.id}", "values": []}
        await component_handler.execute(None, interaction)
        response.edit_message.assert_called()

        # Test punishment set callback
        response.edit_message.reset_mock()
        interaction.data = {"custom_id": f"an_pn:set:channelDelete:kick:{self.guild.id}", "values": []}
        await component_handler.execute(None, interaction)
        response.edit_message.assert_called()

        # Test wizard event multi-selection callback
        response.edit_message.reset_mock()
        interaction.data = {
            "custom_id": f"an_wiz:select_events:{self.guild.id}",
            "values": [AntiNukeConstants.EVENT_CHANNEL_DELETE, AntiNukeConstants.EVENT_ROLE_DELETE],
        }
        await component_handler.execute(None, interaction)
        response.edit_message.assert_called()

    async def test_complete_wizard_lifecycle(self):
        """Simulates all 11 wizard steps sequentially and tests final database persistence."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.guild = self.guild
        interaction.user = MagicMock()
        interaction.user.id = self.guild.owner_id
        response = MagicMock()
        response.is_done.return_value = False
        response.edit_message = AsyncMock()
        interaction.response = response

        # Step 2: Mode selection
        interaction.data = {"custom_id": f"an_wiz:select_mode:{self.guild.id}", "values": ["hard"]}
        await component_handler.execute(None, interaction)

        # Step 3: Event selection
        interaction.data = {
            "custom_id": f"an_wiz:select_events:{self.guild.id}",
            "values": [AntiNukeConstants.EVENT_CHANNEL_DELETE, AntiNukeConstants.EVENT_GUILD_UPDATE],
        }
        await component_handler.execute(None, interaction)

        # Step 4: Thresholds
        interaction.data = {"custom_id": f"an_wiz:th_set_count:channelDelete:3:{self.guild.id}", "values": []}
        await component_handler.execute(None, interaction)
        interaction.data = {"custom_id": f"an_wiz:th_set_window:channelDelete:30:{self.guild.id}", "values": []}
        await component_handler.execute(None, interaction)

        # Step 5: Punishments
        interaction.data = {"custom_id": f"an_wiz:pn_set:channelDelete:kick:{self.guild.id}", "values": []}
        await component_handler.execute(None, interaction)

        # Step 6: Warning channel
        interaction.data = {"custom_id": f"an_wiz:set_warning_ch:{self.guild.id}", "values": ["555111"]}
        await component_handler.execute(None, interaction)

        # Step 7: Log channel
        interaction.data = {"custom_id": f"an_wiz:set_log_ch:{self.guild.id}", "values": ["555222"]}
        await component_handler.execute(None, interaction)

        # Step 8: Ticket bot
        interaction.data = {"custom_id": f"an_wiz:pick_ticket_bot:{self.guild.id}", "values": ["999111"]}
        await component_handler.execute(None, interaction)

        # Step 9: Extra owner
        interaction.data = {"custom_id": f"an_wiz:pick_extra_owner:{self.guild.id}", "values": ["888111"]}
        await component_handler.execute(None, interaction)

        # Step 10: Whitelist
        interaction.data = {"custom_id": f"an_wiz:pick_wl_user:{self.guild.id}", "values": ["777111"]}
        await component_handler.execute(None, interaction)

        # Step 11: Complete setup!
        interaction.data = {"custom_id": f"an_wiz:complete:{self.guild.id}", "values": []}
        await component_handler.execute(None, interaction)

        # Verify configuration in AntiNukeManager
        cfg = AntiNukeManager.get_guild_config(str(self.guild.id))
        self.assertTrue(cfg.get("setup_completed"))
        self.assertTrue(cfg.get("enabled"))
        self.assertEqual(cfg.get("mode"), "hard")
        self.assertEqual(cfg.get("warning_channel_id"), "555111")
        self.assertEqual(cfg.get("log_channel_id"), "555222")
        self.assertIn("999111", cfg.get("ticket_bots", []))
        self.assertIn("888111", cfg.get("extra_owners", []))
        self.assertIn("777111", cfg.get("whitelists", {}))
        self.assertEqual(cfg.get("thresholds", {}).get("channelDelete", {}).get("count"), 3)
        self.assertEqual(cfg.get("punishments", {}).get("channelDelete"), "kick")

    async def test_extraowner_command_and_enforcement(self):
        """Tests extraowner add, remove, and privilege checks."""
        from plugins.MomentumOneToolkit.commands.security.extraowner import execute as eo_execute

        message = MagicMock(spec=discord.Message)
        message.guild = self.guild
        message.author = MagicMock()
        message.author.id = self.guild.owner_id  # Owner invoking
        message.channel = MagicMock()
        message.channel.send = AsyncMock()
        message.reply = AsyncMock()

        # Test extraowner set command
        await eo_execute(None, "prefix", message, ["set"])

        # Test callback confirm_set
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.guild = self.guild
        interaction.user = MagicMock()
        interaction.user.id = self.guild.owner_id
        response = MagicMock()
        response.is_done.return_value = False
        response.edit_message = AsyncMock()
        interaction.response = response

        interaction.data = {"custom_id": f"an_eo:confirm_set:444333:{self.guild.id}", "values": []}
        await component_handler.execute(None, interaction)

        cfg = AntiNukeManager.get_guild_config(str(self.guild.id))
        self.assertIn("444333", cfg.get("extra_owners", []))
        self.assertTrue(AntiNukeManager.is_owner_or_extra_owner(self.guild, "444333"))

        # Test callback confirm_remove
        interaction.data = {"custom_id": f"an_eo:confirm_remove:444333:{self.guild.id}", "values": []}
        await component_handler.execute(None, interaction)

        cfg = AntiNukeManager.get_guild_config(str(self.guild.id))
        self.assertNotIn("444333", cfg.get("extra_owners", []))
        self.assertFalse(AntiNukeManager.is_owner_or_extra_owner(self.guild, "444333"))

    async def test_event_manager_disabled_event_enforcement(self):
        """Verifies that disabled events are ignored by Anti-Nuke enforcement."""
        # Only monitor channelDelete
        await AntiNukeManager.save_guild_config(str(self.guild.id), {
            "monitored_events": [AntiNukeConstants.EVENT_CHANNEL_DELETE],
            "enabled": True,
        })

        rogue_user = MagicMock(spec=discord.Member)
        rogue_user.id = 123999
        rogue_user.bot = False
        top_role = MagicMock()
        top_role.position = 10
        rogue_user.top_role = top_role

        # An event that is NOT monitored (e.g. roleDelete)
        result = await AntiNukeManager.record_and_evaluate_infraction(
            self.guild, rogue_user, AntiNukeConstants.EVENT_ROLE_DELETE
        )
        self.assertIsNone(result.get("action_taken"))
        self.assertIn("not in monitored events", result.get("reason", ""))


if __name__ == "__main__":
    unittest.main()
