import os
import sys
import time
import asyncio
from typing import Any, List, Dict, Optional
from unittest.mock import MagicMock, AsyncMock

# Add python directory to sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "python"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import pytest
from core.security.antinuke import (
    AntiNukeManager,
    AntiNukeConstants,
    get_default_thresholds,
    get_default_punishments,
)
from core.security.antinuke_service import AntiNukeService
from core.security.server_commands import ServerCommandManager
from config.strings import get_string
from database.database import database


class MockRole:
    def __init__(self, id: int, name: str, position: int, permissions: Any = None):
        self.id = id
        self.name = name
        self.position = position
        self.permissions = permissions or MagicMock()
        self.is_default = lambda: id == 0
        self.managed = False

    def __lt__(self, other):
        return self.position < getattr(other, "position", 0)

    def __ge__(self, other):
        return self.position >= getattr(other, "position", 0)


class MockMember:
    def __init__(self, id: int, name: str, roles: list, is_bot: bool = False, guild: Any = None):
        self.id = id
        self.name = name
        self.roles = sorted(roles, key=lambda r: r.position)
        self.top_role = self.roles[-1] if self.roles else MockRole(0, "@everyone", 0)
        self.bot = is_bot
        self.guild = guild
        self.guild_permissions = MagicMock()
        self.guild_permissions.administrator = False
        self.guild_permissions.ban_members = True
        self.guild_permissions.kick_members = True
        self.guild_permissions.manage_roles = True
        self.guild_permissions.manage_channels = True
        self.guild_permissions.view_audit_log = True

    def __str__(self):
        return f"{self.name}#{self.id}"


class MockChannel:
    def __init__(self, id: int, name: str, category_name: str = "", topic: str = ""):
        self.id = id
        self.name = name
        self.topic = topic
        self.category = MagicMock()
        self.category.name = category_name


class MockGuild:
    def __init__(self, id: int, name: str, owner_id: int):
        self.id = id
        self.name = name
        self.owner_id = owner_id
        self.roles = []
        self.me = None
        self.members = {}

    def get_role(self, role_id: int):
        for r in self.roles:
            if r.id == role_id:
                return r
        return None

    def get_member(self, member_id: int):
        return self.members.get(member_id)

    async def fetch_member(self, member_id: int):
        return self.members.get(member_id)

    async def ban(self, user, reason=None, delete_message_days=0):
        return True

    async def kick(self, user, reason=None):
        return True


@pytest.mark.asyncio
async def test_antinuke_defaults_and_modes():
    """Verify operating configurations: Hard, Ultimate Defence Wall, Hybrid."""
    await database.initialize("test")
    await AntiNukeManager.initialize()

    guild_id = "test_guild_modes"
    cfg = AntiNukeManager.get_guild_config(guild_id)
    assert cfg["guild_id"] == guild_id
    assert cfg["enabled"] is False

    # Check Ultimate mode defaults
    ultimate_thresholds = get_default_thresholds(AntiNukeConstants.MODE_ULTIMATE)
    assert ultimate_thresholds[AntiNukeConstants.EVENT_CHANNEL_DELETE]["count"] == 2
    assert ultimate_thresholds[AntiNukeConstants.EVENT_CHANNEL_DELETE]["window"] == 10

    ultimate_name = AntiNukeManager.get_mode_display_name(AntiNukeConstants.MODE_ULTIMATE)
    assert "Ultimate Defence Wall" in ultimate_name

    # Check Hard mode defaults: 1 action zero-tolerance
    hard_thresholds = get_default_thresholds(AntiNukeConstants.MODE_HARD)
    for ev in AntiNukeConstants.ALL_EVENTS:
        assert hard_thresholds[ev]["count"] == 1
        assert hard_thresholds[ev]["window"] == 60

    hard_punishments = get_default_punishments(AntiNukeConstants.MODE_HARD)
    for ev in AntiNukeConstants.ALL_EVENTS:
        assert hard_punishments[ev] == AntiNukeConstants.PUNISH_BAN

    # Check Hybrid mode defaults: 1 action for bot_add/permissions, sliding burst on channels
    hybrid_thresholds = get_default_thresholds(AntiNukeConstants.MODE_HYBRID)
    assert hybrid_thresholds[AntiNukeConstants.EVENT_BOT_ADD]["count"] == 1
    assert hybrid_thresholds[AntiNukeConstants.EVENT_CHANNEL_CREATE]["count"] == 3


@pytest.mark.asyncio
async def test_extra_owners_and_authorization():
    """Verify Root Owner, Extra Owners, and authorization boundary."""
    guild = MockGuild(1001, "Security Test Guild", owner_id=99999)
    bot_role = MockRole(10, "MomentumOne", 10)
    guild.me = MockMember(88888, "MomentumOne", [bot_role], is_bot=True, guild=guild)

    # 1. Server Owner is root authority
    assert AntiNukeManager.is_owner_or_extra_owner(guild, 99999) is True
    # Regular user is not
    assert AntiNukeManager.is_owner_or_extra_owner(guild, 11111) is False

    # 2. Add Extra Owner
    await AntiNukeManager.save_guild_config(str(guild.id), {"extra_owners": ["11111"]})
    assert AntiNukeManager.is_owner_or_extra_owner(guild, 11111) is True

    # 3. Remove Extra Owner
    await AntiNukeManager.save_guild_config(str(guild.id), {"extra_owners": []})
    assert AntiNukeManager.is_owner_or_extra_owner(guild, 11111) is False


@pytest.mark.asyncio
async def test_whitelists_granular_and_wildcard():
    """Verify granular per-event whitelisting and wildcard bypass."""
    gid = "guild_wl_test"

    # Whitelist user 2001 for channel_create only
    await AntiNukeManager.save_guild_config(gid, {
        "whitelists": {
            "2001": [AntiNukeConstants.EVENT_CHANNEL_CREATE],
            "2002": ["*"],  # wildcard
        }
    })

    assert AntiNukeManager.is_whitelisted(gid, 2001, AntiNukeConstants.EVENT_CHANNEL_CREATE) is True
    assert AntiNukeManager.is_whitelisted(gid, 2001, AntiNukeConstants.EVENT_CHANNEL_DELETE) is False
    assert AntiNukeManager.is_whitelisted(gid, 2001, AntiNukeConstants.EVENT_BAN) is False

    # User 2002 has wildcard
    assert AntiNukeManager.is_whitelisted(gid, 2002, AntiNukeConstants.EVENT_BAN) is True
    assert AntiNukeManager.is_whitelisted(gid, 2002, AntiNukeConstants.EVENT_CHANNEL_DELETE) is True


@pytest.mark.asyncio
async def test_ticket_bot_exemptions():
    """
    Verify ticket bot exemptions:
    Approved ticket bots can create/delete ticket channels without false positives.
    Non-ticket destructive actions (bans, kicks, role deletes) are strictly blocked!
    """
    guild = MockGuild(1002, "Ticket Guild", owner_id=99999)
    bot_role = MockRole(10, "MomentumOne", 10)
    guild.me = MockMember(88888, "MomentumOne", [bot_role], is_bot=True, guild=guild)

    ticket_bot_id = "50001"
    await AntiNukeManager.save_guild_config(str(guild.id), {
        "enabled": True,
        "ticket_bots": [ticket_bot_id],
    })

    ticket_channel = MockChannel(101, "ticket-0042", category_name="Support Tickets")
    regular_channel = MockChannel(102, "general-chat", category_name="Community")

    # 1. Ticket Bot on Ticket Channel -> Exempt!
    assert AntiNukeManager.is_ticket_bot_exempt(
        guild, ticket_bot_id, AntiNukeConstants.EVENT_CHANNEL_CREATE, ticket_channel
    ) is True
    assert AntiNukeManager.is_ticket_bot_exempt(
        guild, ticket_bot_id, AntiNukeConstants.EVENT_CHANNEL_DELETE, ticket_channel
    ) is True

    # 2. Ticket Bot on Non-Ticket Channel -> NOT exempt!
    assert AntiNukeManager.is_ticket_bot_exempt(
        guild, ticket_bot_id, AntiNukeConstants.EVENT_CHANNEL_DELETE, regular_channel
    ) is False

    # 3. Ticket Bot attempting BAN or ROLE_DELETE -> NOT exempt!
    assert AntiNukeManager.is_ticket_bot_exempt(
        guild, ticket_bot_id, AntiNukeConstants.EVENT_BAN, ticket_channel
    ) is False
    assert AntiNukeManager.is_ticket_bot_exempt(
        guild, ticket_bot_id, AntiNukeConstants.EVENT_ROLE_DELETE, ticket_channel
    ) is False

    # 4. Unregistered Bot attempting ticket channel -> NOT exempt!
    assert AntiNukeManager.is_ticket_bot_exempt(
        guild, "999999", AntiNukeConstants.EVENT_CHANNEL_CREATE, ticket_channel
    ) is False


@pytest.mark.asyncio
async def test_sliding_window_and_duplicate_suppression():
    """Verify sliding-window rate limits, threshold triggers, and audit-entry deduplication."""
    guild = MockGuild(1003, "Threshold Guild", owner_id=99999)
    bot_role = MockRole(10, "MomentumOne", 10)
    guild.me = MockMember(88888, "MomentumOne", [bot_role], is_bot=True, guild=guild)
    guild.ban = AsyncMock(return_value=True)

    attacker_role = MockRole(5, "Member", 5)
    attacker = MockMember(77777, "Attacker", [attacker_role], is_bot=False, guild=guild)
    guild.members[attacker.id] = attacker

    # Configure Anti-Nuke: Threshold 2 actions in 10s
    await AntiNukeManager.save_guild_config(str(guild.id), {
        "enabled": True,
        "mode": AntiNukeConstants.MODE_ULTIMATE,
        "thresholds": {
            AntiNukeConstants.EVENT_CHANNEL_DELETE: {"count": 2, "window": 10}
        },
        "punishments": {
            AntiNukeConstants.EVENT_CHANNEL_DELETE: AntiNukeConstants.PUNISH_BAN
        }
    })

    # Action 1: Count = 1 (under threshold)
    res1 = await AntiNukeManager.record_and_evaluate_infraction(
        guild=guild,
        executor=attacker,
        event_type=AntiNukeConstants.EVENT_CHANNEL_DELETE,
        audit_entry_id=12345,
    )
    assert res1["action_taken"] is None
    assert res1["current_count"] == 1

    # Duplicate check: Action 1 again with same audit_entry_id -> suppressed
    res1_dup = await AntiNukeManager.record_and_evaluate_infraction(
        guild=guild,
        executor=attacker,
        event_type=AntiNukeConstants.EVENT_CHANNEL_DELETE,
        audit_entry_id=12345,
    )
    assert res1_dup["action_taken"] is None
    assert "Duplicate audit entry" in res1_dup["reason"]

    # Action 2: Count = 2 (threshold reached -> punishment executed!)
    res2 = await AntiNukeManager.record_and_evaluate_infraction(
        guild=guild,
        executor=attacker,
        event_type=AntiNukeConstants.EVENT_CHANNEL_DELETE,
        audit_entry_id=12346,
    )
    assert res2["action_taken"] == AntiNukeConstants.PUNISH_BAN
    assert guild.ban.called


@pytest.mark.asyncio
async def test_role_hierarchy_safety():
    """Verify the bot NEVER claims protection against roles higher than its own role."""
    guild = MockGuild(1004, "Hierarchy Guild", owner_id=99999)
    bot_role = MockRole(10, "MomentumOne", 10)
    guild.me = MockMember(88888, "MomentumOne", [bot_role], is_bot=True, guild=guild)

    # 1. Target with lower role -> can act
    low_role = MockRole(5, "Mod", 5)
    low_target = MockMember(33333, "LowMod", [low_role], guild=guild)
    check_low = AntiNukeManager.check_hierarchy_and_permissions(guild, low_target)
    assert check_low["can_act"] is True

    # 2. Target with higher role -> cannot act
    high_role = MockRole(20, "Co-Owner", 20)
    high_target = MockMember(44444, "HighMod", [high_role], guild=guild)
    check_high = AntiNukeManager.check_hierarchy_and_permissions(guild, high_target)
    assert check_high["can_act"] is False
    assert "higher than or equal to MomentumOne's role" in check_high["reason"]

    # 3. Target is server owner -> cannot act
    owner_target = MockMember(99999, "ServerOwner", [high_role], guild=guild)
    check_owner = AntiNukeManager.check_hierarchy_and_permissions(guild, owner_target)
    assert check_owner["can_act"] is False


@pytest.mark.asyncio
async def test_moderation_virtualization():
    """Verify virtualized moderator authorization (Requirement 7)."""
    gid = "guild_virt_test"
    mod_role = MockRole(15, "Server Moderator", 15)
    mod_member = MockMember(66666, "Moderator", [mod_role])

    # Initially not authorized
    assert ServerCommandManager.is_authorized_moderator(gid, mod_member, "channel") is False

    # Authorize role in MomentumOne virtual system
    ServerCommandManager.authorize_moderator_role(gid, str(mod_role.id))
    assert str(mod_role.id) in ServerCommandManager.get_authorized_roles(gid)

    # Now authorized without native Discord dangerous permissions!
    assert ServerCommandManager.is_authorized_moderator(gid, mod_member, "channel") is True

    # Deauthorize role
    ServerCommandManager.deauthorize_moderator_role(gid, str(mod_role.id))
    assert ServerCommandManager.is_authorized_moderator(gid, mod_member, "channel") is False


if __name__ == "__main__":
    asyncio.run(test_antinuke_defaults_and_modes())
    asyncio.run(test_extra_owners_and_authorization())
    asyncio.run(test_whitelists_granular_and_wildcard())
    asyncio.run(test_ticket_bot_exemptions())
    asyncio.run(test_sliding_window_and_duplicate_suppression())
    asyncio.run(test_role_hierarchy_safety())
    asyncio.run(test_moderation_virtualization())
    print("\n🎉 ALL 7 ANTINUKE TEST SUITES PASSED SUCCESSFULLY!")
