import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import discord

from sdk.discord.builders import (
    ContainerBuilder,
    SectionBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
)
from plugins.MomentumOneToolkit.events.guild_join import (
    select_announcement_channel,
    can_bot_send,
    can_everyone_send,
    find_inviter,
    build_welcome_container,
    build_inviter_dm_container,
    execute as execute_guild_join,
    _processed_guilds,
)


class TestGuildJoinSuite(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _processed_guilds.clear()

        # Mock Bot Member
        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_member.id = 1563628961379123302
        self.bot_member.bot = True
        self.bot_member.name = "Sentinel™"
        self.bot_member.guild_permissions = discord.Permissions(
            administrator=True,
            view_channel=True,
            send_messages=True,
        )

        # Mock Guild
        self.guild = discord.Guild(id=1122334455, name="Fortress Citadel")
        self.guild.me = self.bot_member
        self.guild.system_channel = None
        self.guild.public_updates_channel = None
        self.guild.channels = []
        self.guild.text_channels = []

    def test_components_v2_serialization_never_produces_embeds(self):
        """Verifies that Containers serialize strictly as Components V2 and NEVER produce embeds."""
        builder = ContainerBuilder()
        builder.set_accent_color(0x0844C5)

        sec = SectionBuilder()
        sec.add_text_display("-# Sentinel™\n### Test Header\nTest copy")
        sec.set_thumbnail_accessory("https://example.com/avatar.png")
        builder.add_section(sec)

        row = ActionRowBuilder()
        row.add_button(ButtonBuilder().set_label("Invite Sentinel").set_url("https://discord.com/invite"))
        row.add_button(ButtonBuilder().set_label("Support Server").set_url("https://discord.gg/momentumone"))
        builder.add_action_row(row)

        builder.add_media_gallery("https://example.com/banner.png")
        builder.add_text_display("-# A MomentumOne product")

        view = builder.build()
        payload = discord.serialize_discord_payload(view=view)

        # 1. embeds MUST NOT be in payload
        self.assertNotIn("embeds", payload, "Containers must NEVER be converted into embeds!")
        # 2. flags must contain 32768 (Components V2 flag)
        self.assertIn("flags", payload)
        self.assertEqual(payload["flags"] & 32768, 32768, "Payload flags must have Components V2 flag (32768)")
        # 3. components must have Container (type 17)
        self.assertIn("components", payload)
        self.assertEqual(len(payload["components"]), 1)
        container_dict = payload["components"][0]
        self.assertEqual(container_dict["type"], 17, "Top-level item must be Container (type 17)")
        self.assertEqual(container_dict["accent_color"], 0x0844C5)

        # Check container children
        children = container_dict["components"]
        # Order 2: Section (type 9)
        self.assertEqual(children[0]["type"], 9, "First item inside container must be Section (type 9)")
        self.assertIn("accessory", children[0])
        self.assertEqual(children[0]["accessory"]["type"], 11, "Section accessory must be Thumbnail (type 11)")
        # Section text display
        self.assertEqual(children[0]["components"][0]["type"], 10)
        self.assertTrue(children[0]["components"][0]["content"].startswith("-# Sentinel™"))

        # Order 3: ActionRow (type 1) with 2 buttons
        self.assertEqual(children[1]["type"], 1, "Second item inside container must be ActionRow (type 1)")
        self.assertEqual(len(children[1]["components"]), 2, "ActionRow must contain exactly 2 buttons")
        self.assertEqual(children[1]["components"][0]["label"], "Invite Sentinel")
        self.assertEqual(children[1]["components"][1]["label"], "Support Server")

        # Order 4: MediaGallery (type 12)
        self.assertEqual(children[2]["type"], 12, "Third item inside container must be MediaGallery (type 12)")

        # Order 5: TextDisplay footer
        self.assertEqual(children[3]["type"], 10)
        self.assertEqual(children[3]["content"], "-# A MomentumOne product")

    def test_channel_hierarchy_priority_1_system_channel(self):
        """Priority 1: Community Announcement Channel / system_channel is selected when accessible."""
        sys_ch = discord.TextChannel(id=101, name="system-announcements")
        sys_ch.guild = self.guild
        self.guild.system_channel = sys_ch

        gen_ch = discord.TextChannel(id=102, name="general")
        gen_ch.guild = self.guild

        self.guild.text_channels = [gen_ch, sys_ch]
        self.guild.channels = [gen_ch, sys_ch]

        selected = select_announcement_channel(self.guild)
        self.assertEqual(selected, sys_ch, "Priority 1 must select system_channel over general")

    def test_channel_hierarchy_priority_2_everyone_permission_prefers_general(self):
        """Priority 2: When system_channel is absent, select text channel where @everyone can send, preferring #general."""
        announcements_ch = discord.TextChannel(id=201, name="staff-announcements")
        announcements_ch.guild = self.guild
        # Make @everyone unable to send in announcements
        everyone_role = self.guild.default_role
        announcements_ch.overwrites[everyone_role] = discord.PermissionOverwrite(send_messages=False)

        general_ch = discord.TextChannel(id=202, name="general")
        general_ch.guild = self.guild
        # @everyone can send in general
        general_ch.overwrites[everyone_role] = discord.PermissionOverwrite(send_messages=True, view_channel=True)

        random_ch = discord.TextChannel(id=203, name="random")
        random_ch.guild = self.guild

        self.guild.text_channels = [announcements_ch, random_ch, general_ch]
        self.guild.channels = [announcements_ch, random_ch, general_ch]

        selected = select_announcement_channel(self.guild)
        self.assertEqual(selected, general_ch, "Priority 2 must select #general when @everyone can send")

    def test_channel_hierarchy_priority_2_without_general_name(self):
        """Priority 2: When no #general exists, select another channel where @everyone can send (do not hardcode)."""
        chat_ch = discord.TextChannel(id=205, name="community-chat")
        chat_ch.guild = self.guild

        bot_spam_ch = discord.TextChannel(id=206, name="bot-commands")
        bot_spam_ch.guild = self.guild

        self.guild.text_channels = [chat_ch, bot_spam_ch]
        self.guild.channels = [chat_ch, bot_spam_ch]

        selected = select_announcement_channel(self.guild)
        self.assertIsNotNone(selected)
        self.assertIn(selected, [chat_ch, bot_spam_ch])

    def test_channel_hierarchy_priority_3_fallback_accessible_channel(self):
        """Priority 3: When @everyone has send_messages=False in all channels, falls back to first channel bot can send to."""
        everyone_role = self.guild.default_role

        read_only_1 = discord.TextChannel(id=301, name="rules")
        read_only_1.guild = self.guild
        read_only_1.overwrites[everyone_role] = discord.PermissionOverwrite(send_messages=False)

        read_only_2 = discord.TextChannel(id=302, name="announcements")
        read_only_2.guild = self.guild
        read_only_2.overwrites[everyone_role] = discord.PermissionOverwrite(send_messages=False)

        self.guild.text_channels = [read_only_1, read_only_2]
        self.guild.channels = [read_only_1, read_only_2]

        selected = select_announcement_channel(self.guild)
        self.assertEqual(selected, read_only_1, "Priority 3 must fallback to first text channel bot can send to")

    def test_channel_hierarchy_failure_handling_no_permissions(self):
        """Failure Handling: When bot has no permission to send anywhere, returns None cleanly without crashing."""
        self.bot_member.guild_permissions = discord.Permissions(administrator=False, view_channel=False, send_messages=False)
        restricted_ch = discord.TextChannel(id=401, name="secret-vault")
        restricted_ch.guild = self.guild
        restricted_ch.overwrites[self.bot_member] = discord.PermissionOverwrite(send_messages=False, view_channel=False)

        self.guild.text_channels = [restricted_ch]
        self.guild.channels = [restricted_ch]

        selected = select_announcement_channel(self.guild)
        self.assertIsNone(selected, "Must return None when no channel has send permissions")

    async def test_deduplication_prevents_duplicate_processing(self):
        """Verifies in-memory deduplication set prevents duplicate welcomes for the same guild."""
        channel = discord.TextChannel(id=501, name="general")
        channel.guild = self.guild
        channel.send = AsyncMock()
        self.guild.text_channels = [channel]

        # First run
        await execute_guild_join(self.guild)
        self.assertEqual(channel.send.call_count, 1)

        # Duplicate run
        await execute_guild_join(self.guild)
        self.assertEqual(channel.send.call_count, 1, "Duplicate execution must be dropped by deduplication set")

    async def test_inviter_discovery_and_direct_message(self):
        """Verifies inviter is discovered via audit log and thanked via direct message."""
        inviter_user = MagicMock(spec=discord.User)
        inviter_user.id = 999888777
        inviter_user.name = "SecAdmin"
        inviter_user.bot = False
        inviter_user.send = AsyncMock()

        audit_entry = discord.AuditLogEntry(
            id=1,
            action=discord.AuditLogAction.bot_add,
            user=inviter_user,
            target=self.bot_member,
        )
        self.guild._audit_logs = [audit_entry]

        channel = discord.TextChannel(id=601, name="general")
        channel.guild = self.guild
        channel.send = AsyncMock()
        self.guild.text_channels = [channel]

        await execute_guild_join(self.guild)

        # Inviter DM must have been sent
        self.assertEqual(inviter_user.send.call_count, 1)
        # Server announcement must also have been sent
        self.assertEqual(channel.send.call_count, 1)

    async def test_inviter_dm_failure_does_not_abort_server_announcement(self):
        """Verifies that if inviter's DMs are closed/fail, server announcement still completes."""
        inviter_user = MagicMock(spec=discord.User)
        inviter_user.id = 999888777
        inviter_user.name = "ClosedDMsUser"
        inviter_user.bot = False
        inviter_user.send = AsyncMock(side_effect=discord.Forbidden("Cannot send messages to this user"))

        audit_entry = discord.AuditLogEntry(
            id=2,
            action=discord.AuditLogAction.bot_add,
            user=inviter_user,
            target=self.bot_member,
        )
        self.guild._audit_logs = [audit_entry]

        channel = discord.TextChannel(id=602, name="general")
        channel.guild = self.guild
        channel.send = AsyncMock()
        self.guild.text_channels = [channel]

        # Should not raise exception
        await execute_guild_join(self.guild)

        # Channel announcement must succeed despite DM error
        self.assertEqual(channel.send.call_count, 1)

    async def test_inviter_unknown_never_dms_random_admin(self):
        """Verifies that if inviter is not identified, no DM is dispatched."""
        # No audit logs
        self.guild._audit_logs = []

        channel = discord.TextChannel(id=603, name="general")
        channel.guild = self.guild
        channel.send = AsyncMock()
        self.guild.text_channels = [channel]

        with patch("plugins.MomentumOneToolkit.events.guild_join.build_inviter_dm_container") as mock_dm_builder:
            await execute_guild_join(self.guild)
            mock_dm_builder.assert_not_called()

        self.assertEqual(channel.send.call_count, 1)


if __name__ == "__main__":
    unittest.main()
