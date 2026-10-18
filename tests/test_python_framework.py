import os
import sys
import time
import asyncio

# Setup sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "python"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config.settings import settings
from config.strings import get_string
from shared.cache.ttl_cache import TTLCache
from apps.bot.discord.permissions.permission import Permissions
from apps.bot.discord.permissions.resolver import check_permissions, is_bot_owner, is_blacklist_excluded, parse_duration
from core.security.blacklist import BlacklistManager
from core.security.noprefix import NoPrefixManager
from core.security.antispam import AntiSpamService
from core.security.cooldown import CooldownManager
from core.security.server_commands import ServerCommandManager
from core.events.event_bus import EventBus
from core.logging.error_tracker import ErrorTracker
from core.audit.audit_log import AuditLog
from database.database import database
from plugins.MomentumOneToolkit.tickets.manager import TicketManager
from apps.bot.discord.manager import BotManager

async def run_tests():
    print("=======================================================")
    print("      MomentumOne: Comprehensive Python Engine Tests   ")
    print("=======================================================")

    # 1. Strings.json verification
    print("\n1. Testing Strings.json loading and interpolation...")
    boot_str = get_string("system.booting")
    assert "[MomentumOne]" in boot_str, f"Expected boot string, got {boot_str}"
    
    custom_interp = get_string("security.blacklist_added", target_type="user", target_id="999", expires="1d")
    assert "user" in custom_interp and "999" in custom_interp and "1d" in custom_interp
    print("  ✅ [PASS] Strings.json centralized localization & dot-path lookup works.")

    # 2. TTLCache verification
    print("\n2. Testing TTLCache functionality & expiration...")
    cache = TTLCache(default_ttl_ms=200)
    cache.set("key1", "val1")
    assert cache.get("key1") == "val1", "Key should be present"
    await asyncio.sleep(0.25)
    assert cache.get("key1") is None, "Key should have expired"
    print("  ✅ [PASS] TTLCache fast expiration and pruning works.")

    # 3. Permissions & Durations
    print("\n3. Testing Permissions resolver & duration parser...")
    dur = parse_duration("7d")
    assert dur is not None and dur > time.time() + 6 * 86400
    assert parse_duration("permanent") is None

    class MockMember:
        class GuildPerms:
            administrator = False
            manage_channels = True
            value = Permissions.MANAGE_CHANNELS
        guild_permissions = GuildPerms()

    p_check = check_permissions(
        member=MockMember(),
        bot_member=MockMember(),
        user_perms=[Permissions.MANAGE_CHANNELS],
        bot_perms=[Permissions.ADMINISTRATOR]
    )
    assert not p_check["allowed"]
    assert "Administrator" in p_check["missing_bot_names"]
    print("  ✅ [PASS] Permissions & duration parsing validated.")

    # 4. Security Blacklist & NoPrefix
    print("\n4. Testing BlacklistManager & NoPrefixManager...")
    bl_res = BlacklistManager.blacklist_user("test_user_88", admin_id="owner_1", reason="test spam", duration="1h")
    assert bl_res["success"]
    assert BlacklistManager.is_user_blacklisted("test_user_88")["blacklisted"] is True
    BlacklistManager.unblacklist_user("test_user_88", admin_id="owner_1")
    assert BlacklistManager.is_user_blacklisted("test_user_88")["blacklisted"] is False

    np_res = NoPrefixManager.grant_no_prefix("test_np_1", added_by="admin_1")
    assert np_res["success"]
    assert NoPrefixManager.has_no_prefix("test_np_1") is True
    NoPrefixManager.revoke_no_prefix("test_np_1", removed_by="admin_1")
    assert NoPrefixManager.has_no_prefix("test_np_1") is False
    print("  ✅ [PASS] Blacklist and NoPrefix security layers validated.")

    # 5. AntiSpam sliding window
    print("\n5. Testing AntiSpam sliding window...")
    for _ in range(4):
        AntiSpamService.check("spammer_99")
    spam_warn = AntiSpamService.check("spammer_99")
    # 5th or 6th will trigger rate limit warning
    AntiSpamService.check("spammer_99")
    limit_hit = AntiSpamService.check("spammer_99")
    assert not limit_hit["allowed"], "Spam window should block high-frequency calls"
    print("  ✅ [PASS] AntiSpam sliding window protection validated.")

    # 6. CooldownManager
    print("\n6. Testing CooldownManager...")
    mock_cmd = {"name": "testcmd", "cooldown": 2.0, "cooldownScope": "user"}
    cd1 = CooldownManager.check(mock_cmd, "user_cd_1")
    assert not cd1["on_cooldown"]
    CooldownManager.apply(mock_cmd, "user_cd_1")
    cd2 = CooldownManager.check(mock_cmd, "user_cd_1")
    assert cd2["on_cooldown"] and cd2["remaining_seconds"] > 0
    CooldownManager.reset("testcmd", "user_cd_1")
    assert not CooldownManager.check(mock_cmd, "user_cd_1")["on_cooldown"]
    print("  ✅ [PASS] CooldownManager scopes and timers validated.")

    # 7. ServerCommandManager
    print("\n7. Testing ServerCommandManager...")
    ServerCommandManager.disable_command("guild_1", "ping")
    # 'ping' is essential and cannot be disabled
    assert not ServerCommandManager.is_command_disabled("guild_1", "ping")
    ServerCommandManager.disable_command("guild_1", "announce")
    assert ServerCommandManager.is_command_disabled("guild_1", "announce")
    ServerCommandManager.enable_command("guild_1", "announce")
    assert not ServerCommandManager.is_command_disabled("guild_1", "announce")
    print("  ✅ [PASS] ServerCommandManager validated.")

    # 8. EventBus
    print("\n8. Testing EventBus sync & async event propagation...")
    bus = EventBus()
    received = []
    async def async_handler(payload):
        received.append(payload["msg"])
    bus.subscribe("test:event", async_handler)
    bus.publish("test:event", {"msg": "hello_event_bus"})
    await asyncio.sleep(0.05)
    assert "hello_event_bus" in received
    print("  ✅ [PASS] EventBus publish/subscribe validated.")

    # 9. DatabaseManager & ErrorTracker
    print("\n9. Testing DatabaseManager & ErrorTracker...")
    await database.initialize("test")
    err_rec = await ErrorTracker.record("buggy_cmd", Exception("Simulated division by zero"), {"userId": "tester_1"})
    assert err_rec["error_id"].startswith("ERR-")
    fetched_err = await ErrorTracker.get(err_rec["error_id"])
    assert fetched_err is not None
    assert fetched_err["command_name"] == "buggy_cmd"
    print("  ✅ [PASS] DatabaseManager & ErrorTracker validated.")

    # 10. AuditLog with redaction
    print("\n10. Testing AuditLog with field redaction...")
    audit_rec = await AuditLog.record({
        "actorId": "admin_42",
        "actorType": "dashboard",
        "action": "user.token_update",
        "resourceType": "user",
        "previousState": {"api_key": "secret_old", "name": "Alice"},
        "newState": {"api_key": "secret_new", "name": "Alice Cooper"},
        "success": True
    })
    assert audit_rec["previous_state"]["api_key"] == "[REDACTED]"
    assert audit_rec["new_state"]["api_key"] == "[REDACTED]"
    assert "api_key" in audit_rec["changed_fields"] or "name" in audit_rec["changed_fields"]
    print("  ✅ [PASS] AuditLog sensitive data redaction validated.")

    # 11. BotManager & Plugin registration
    print("\n11. Testing BotManager setup and plugin auto-loading...")
    bot_mgr = BotManager()
    setup_status = await bot_mgr.setup()
    assert setup_status["ready"] is True
    reg = bot_mgr.registry()
    assert len(reg["commands"]) >= 15, f"Expected 15+ commands, found {len(reg['commands'])}"
    assert len(reg["plugins"]) >= 1, "Expected loaded plugins"
    print(f"  ✅ [PASS] BotManager initialized {len(reg['commands'])} commands & {len(reg['plugins'])} plugin(s).")

    # 12. Ensure NO economy commands or references
    cmd_names = [c["name"].lower() for c in reg["commands"]]
    assert "inventory" not in cmd_names, "Inventory/economy must be removed"
    assert "withdraw" not in cmd_names, "Withdraw/economy must be removed"
    assert "balance" not in cmd_names, "Balance/economy must be removed"
    print("  ✅ [PASS] Economy features confirmed completely removed as requested.")

    print("\n=======================================================")
    print("      ALL PYTHON PLATFORM TESTS PASSED SUCCESSFULLY!   ")
    print("=======================================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
