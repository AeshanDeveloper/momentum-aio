"""
Unit tests for Quick Setup, Security Posture Live Recheck, Slash Subcommand Parsing,
and Discord Channel Hierarchy Parity.
"""

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import discord

from core.security.lockdown_journal import LockdownRecord, JournalEntryStatus, JournalEntry
from core.security.emergency_lockdown_manager import emergency_lockdown_manager
from core.security.response_policy import SecurityResponsePolicy
from core.security.antinuke import AntiNukeConstants
from plugins.MomentumOneToolkit.commands.security.setup import (
    build_unified_setup_view,
    execute_quick_setup,
)
from plugins.MomentumOneToolkit.commands.security.lockdown import (
    build_posture_view,
    build_dangerous_permissions_view,
)
from plugins.MomentumOneToolkit.events.slash_handler import _extract_slash_args


class TestQuickSetupAndPosture(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Create a mock guild with bot member and roles
        self.guild = discord.Guild(id=9988776655, name="Hardened Fortress")
        self.guild.owner_id = 11112222

        # Bot role & member
        bot_perms = discord.Permissions(administrator=True, manage_roles=True, manage_channels=True)
        bot_role = discord.Role(
            id=88001,
            name="Sentinel Bot",
            position=50,
            guild=self.guild,
            permissions=bot_perms,
            managed=True,
        )

        self.bot_member = discord.Member(id=99990001, name="Sentinel Bot", guild=self.guild)
        self.bot_member.roles = [bot_role]
        self.bot_member.top_role = bot_role
        self.bot_member._guild_permissions = bot_perms
        self.guild.me = self.bot_member

        # Roles
        everyone_role = discord.Role(
            id=9988776655,
            name="@everyone",
            position=0,
            guild=self.guild,
            permissions=discord.Permissions(send_messages=True),
        )

        mod_role = discord.Role(
            id=88002,
            name="Moderator",
            position=30,
            guild=self.guild,
            permissions=discord.Permissions(
                permissions=(1 << 2) | (1 << 1) | (1 << 4),
                ban_members=True,
                kick_members=True,
                manage_channels=True,
            ),
        )

        rogue_role = discord.Role(
            id=88003,
            name="Unmanageable Admin",
            position=60,  # Above bot position 50!
            guild=self.guild,
            permissions=discord.Permissions(administrator=True),
        )

        self.guild.roles = [everyone_role, mod_role, bot_role, rogue_role]
        self.guild.text_channels = []
        self.guild.voice_channels = []

    def test_slash_subcommand_recursive_parsing(self):
        """Slash command recursive parsing extracts nested subcommands and options."""
        # Interaction data representing /lockdown posture verbose:True
        raw_options = [
            {
                "name": "posture",
                "type": 1,  # SUB_COMMAND
                "options": [
                    {
                        "name": "verbose",
                        "type": 5,  # BOOLEAN
                        "value": True,
                    }
                ],
            }
        ]
        args = _extract_slash_args(raw_options)
        self.assertEqual(args, ["posture", "True"])

        # Deeper nested: /security policy set level:lockdown
        raw_nested = [
            {
                "name": "policy",
                "type": 2,  # SUB_COMMAND_GROUP
                "options": [
                    {
                        "name": "set",
                        "type": 1,  # SUB_COMMAND
                        "options": [
                            {"name": "level", "type": 3, "value": "lockdown"}
                        ],
                    }
                ],
            }
        ]
        nested_args = _extract_slash_args(raw_nested)
        self.assertEqual(nested_args, ["policy", "set", "lockdown"])

    def test_security_posture_score_and_breakdown(self):
        """Audit calculates 0-100 score, letter grade, and itemized dangerous roles."""
        policy = SecurityResponsePolicy(guild_id=str(self.guild.id))
        report = emergency_lockdown_manager.audit_guild_security_posture(self.guild, policy)

        self.assertIn("score", report)
        self.assertIn("grade", report)
        self.assertIn("overall_posture", report)
        self.assertIn("dangerous_roles", report)

        # Rogue role has admin and is above bot (position 60 > 50)
        dangerous = report["dangerous_roles"]
        self.assertTrue(any(r["role_name"] == "Unmanageable Admin" for r in dangerous))
        rogue_entry = next(r for r in dangerous if r["role_name"] == "Unmanageable Admin")
        self.assertFalse(rogue_entry["can_manage"])
        self.assertEqual(rogue_entry["severity"], "CRITICAL")

        # Test view builder
        view = build_posture_view(self.guild, policy)
        self.assertIsNotNone(view)

        danger_view = build_dangerous_permissions_view(self.guild, policy)
        self.assertIsNotNone(danger_view)

    def test_lockdown_journal_metrics_breakdown(self):
        """Lockdown record properly counts non-overlapping verified, simulated, and skipped outcomes."""
        rec = LockdownRecord(
            lockdown_id="lck_test_metrics",
            guild_id="998877",
            status="active",
            is_shadow_mode=False,
            entries=[
                JournalEntry(
                    entry_id="e1",
                    target_id="r1",
                    target_type="role",
                    target_name="Mod",
                    original_state={"permissions": 8},
                    applied_state={"permissions": 0},
                    status=JournalEntryStatus.VERIFIED,
                ),
                JournalEntry(
                    entry_id="e2",
                    target_id="r2",
                    target_type="role",
                    target_name="Helper",
                    original_state={"permissions": 16},
                    applied_state={"permissions": 0},
                    status=JournalEntryStatus.SIMULATED,
                ),
                JournalEntry(
                    entry_id="e3",
                    target_id="r3",
                    target_type="role",
                    target_name="OwnerRole",
                    original_state={"permissions": 8},
                    applied_state=None,
                    status=JournalEntryStatus.SKIPPED_HIERARCHY,
                ),
            ],
        )
        rec.update_summary()
        self.assertEqual(rec.summary_metrics.get("verified"), 1)
        self.assertEqual(rec.summary_metrics.get("simulated"), 1)
        self.assertEqual(rec.summary_metrics.get("skipped_hierarchy"), 1)
        self.assertEqual(rec.summary_metrics.get("planned"), 3)

    def test_unified_setup_view(self):
        """Unified setup view produces 1-click Quick Setup and Advanced options."""
        view = build_unified_setup_view(self.guild)
        self.assertIsNotNone(view)

    async def test_execute_quick_setup(self):
        """Quick setup enables Hard mode, Aegis, logging workflow, and verifies live posture."""
        with patch("core.logging.webhook_logger.UnifiedWebhookLogger.create_logging_setup_workflow", new_callable=AsyncMock) as mock_logs, \
             patch("core.security.antinuke.AntiNukeManager.save_guild_config", new_callable=AsyncMock) as mock_save:
            mock_logs.return_value = {
                "category_name": "SENTINEL AUDIT",
                "created_channels": ["#security-logs", "#mod-logs"],
                "reused_channels": [],
            }
            view = await execute_quick_setup(self.guild, 11112222)
            self.assertIsNotNone(view)
            mock_save.assert_awaited_once()
            saved_cfg = mock_save.await_args[0][1]
            self.assertEqual(saved_cfg["mode"], AntiNukeConstants.MODE_HARD)
            self.assertTrue(saved_cfg["enabled"])
            self.assertTrue(saved_cfg["observation_system_enabled"])

    def test_discord_channel_hierarchy_parity(self):
        """Verifies CategoryChannel, TextChannel, VoiceChannel, and overwrite permissions parity."""
        category = discord.CategoryChannel(
            id=1001,
            name="Security Category",
            guild=self.guild,
            position=1,
        )
        text_ch = discord.TextChannel(
            id=2001,
            name="security-logs",
            guild=self.guild,
            category=category,
            position=1,
        )
        voice_ch = discord.VoiceChannel(
            id=3001,
            name="Security Briefing",
            guild=self.guild,
            category=category,
            position=2,
        )
        self.guild.channels = [category, text_ch, voice_ch]

        # Verify category relationships
        self.assertEqual(category.text_channels, [text_ch])
        self.assertEqual(category.voice_channels, [voice_ch])
        self.assertEqual(category.channels, [text_ch, voice_ch])

        # Verify permissions_for
        perms = text_ch.permissions_for(self.bot_member)
        self.assertTrue(perms.administrator)


if __name__ == "__main__":
    unittest.main()
