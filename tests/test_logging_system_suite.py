import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import discord

from core.logging.webhook_logger import (
    UnifiedWebhookLogger,
    LogCategory,
    redact_webhook_credentials,
    get_webhook_display_status,
    acquire_setup_lock,
    release_setup_lock,
    is_setup_in_progress,
)
from plugins.MomentumOneToolkit.commands.general.logging import (
    build_logging_panel_view,
    build_wizard_preview_view,
    build_cleanup_confirm_view,
    get_or_create_logging_wizard_session,
    clear_logging_wizard_session,
)
from plugins.MomentumOneToolkit.events.logging import ALL_LOGGING_EVENT_MODULES
from sdk.event import Event


class TestLoggingSystemSuite(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create mock guild
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 987654321
        self.guild.name = "Test Security Guild"
        self.guild.categories = []
        self.guild.text_channels = []
        self.guild.webhooks = AsyncMock(return_value=[])

        # Mock guild.me
        self.me = MagicMock(spec=discord.Member)
        self.me.id = 999888777
        self.me.guild_permissions = discord.Permissions(manage_channels=True, manage_webhooks=True, manage_guild=True)
        self.guild.me = self.me
        self.guild.default_role = MagicMock(spec=discord.Role)

        # Clear active locks
        release_setup_lock(self.guild.id)
        clear_logging_wizard_session(self.guild.id)

    def tearDown(self):
        release_setup_lock(self.guild.id)
        clear_logging_wizard_session(self.guild.id)

    # ==========================================================================
    # 1. Never Display Webhook URLs in Dashboard or Error Responses
    # ==========================================================================
    def test_webhook_url_redaction(self):
        secret_url = "https://discord.com/api/webhooks/1234567890/tokenABCxyz_987654321"
        secret_canary = "https://canary.discord.com/api/webhooks/999888777/secret-token-here"
        
        text_with_url = f"Delivery failed to {secret_url} with HTTP 404"
        redacted = redact_webhook_credentials(text_with_url)
        self.assertNotIn(secret_url, redacted)
        self.assertNotIn("tokenABCxyz_987654321", redacted)
        self.assertIn("[REDACTED_WEBHOOK_URL]", redacted)

        text_with_canary = f"Attempting connection to {secret_canary} now."
        redacted_canary = redact_webhook_credentials(text_with_canary)
        self.assertNotIn(secret_canary, redacted_canary)
        self.assertIn("[REDACTED_WEBHOOK_URL]", redacted_canary)

    def test_webhook_display_status(self):
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111222
        mock_channel.name = "moderation-logs"
        self.guild.get_channel.return_value = mock_channel

        # Configured status
        dest_configured = {
            "channel_id": "111222",
            "webhook_url": "https://discord.com/api/webhooks/123/secret",
            "webhook_valid": True,
        }
        status = get_webhook_display_status(self.guild, dest_configured)
        self.assertEqual(status, "Configured")
        self.assertNotIn("secret", status)
        self.assertNotIn("http", status)

        # Needs repair status (channel missing in Discord)
        self.guild.get_channel.return_value = None
        status_missing_ch = get_webhook_display_status(self.guild, dest_configured)
        self.assertEqual(status_missing_ch, "Needs Repair")

        # Missing status (no webhook url)
        dest_missing = {"channel_id": "111222", "webhook_url": None}
        status_none = get_webhook_display_status(self.guild, dest_missing)
        self.assertEqual(status_none, "Missing")

    async def test_dashboard_never_leaks_urls(self):
        # Setup config with raw webhook URLs
        raw_secret_url = "https://discord.com/api/webhooks/888999111/SuperSecretKeyXYZ"
        await UnifiedWebhookLogger.save_guild_logging_config(
            str(self.guild.id),
            {
                "enabled": True,
                "destinations": {
                    "moderation": {
                        "channel_id": "111222",
                        "webhook_url": raw_secret_url,
                        "webhook_valid": True,
                    }
                },
            },
        )
        mock_ch = MagicMock(spec=discord.TextChannel)
        mock_ch.id = 111222
        mock_ch.name = "moderation-logs"
        self.guild.get_channel.return_value = mock_ch

        view = await build_logging_panel_view(self.guild)
        # Convert view to string or inspect text displays
        view_str = str(view)
        self.assertNotIn("SuperSecretKeyXYZ", view_str)
        self.assertNotIn("discord.com/api/webhooks", view_str)
        self.assertIn("Configured", view_str)

    # ==========================================================================
    # 2. Reuse Existing Logging Categories and Channels (Idempotency)
    # ==========================================================================
    async def test_idempotent_setup_workflow_reuses_category_and_channels(self):
        # Mock Discord category creation
        mock_cat = MagicMock(spec=discord.CategoryChannel)
        mock_cat.id = 5550001
        mock_cat.name = "MOMENTUMONE LOGS"
        mock_cat.text_channels = []

        # Mock channel creation
        created_channels = {}

        async def mock_create_cat(name, overwrites=None, reason=None):
            return mock_cat

        async def mock_create_channel(name, category=None, topic=None, overwrites=None, reason=None):
            ch = MagicMock(spec=discord.TextChannel)
            ch.id = 700000 + len(created_channels)
            ch.name = name
            ch.category = category
            ch.topic = topic
            wh = MagicMock(spec=discord.Webhook)
            wh.id = 800000 + len(created_channels)
            wh.url = f"https://discord.com/api/webhooks/{wh.id}/fake-token"
            ch.webhooks = AsyncMock(return_value=[wh])
            ch.create_webhook = AsyncMock(return_value=wh)
            created_channels[name] = ch
            if category:
                category.text_channels.append(ch)
            self.guild.text_channels.append(ch)
            return ch

        self.guild.create_category = AsyncMock(side_effect=mock_create_cat)
        self.guild.create_text_channel = AsyncMock(side_effect=mock_create_channel)

        progress_steps = []

        async def track_progress(step):
            progress_steps.append(step)

        # Run 1: Fresh setup
        res1 = await UnifiedWebhookLogger.create_logging_setup_workflow(
            guild=self.guild,
            layout="category",
            create_category=True,
            progress_callback=track_progress,
        )

        self.assertEqual(res1.get("status"), "success")
        self.assertEqual(res1.get("reused_category"), False)
        self.assertEqual(len(res1.get("created_channels", [])), 6)
        self.assertEqual(self.guild.create_category.call_count, 1)
        self.assertEqual(self.guild.create_text_channel.call_count, 6)

        # Register category in guild.categories for subsequent run
        self.guild.categories = [mock_cat]
        self.guild.get_channel = lambda cid: next((c for c in self.guild.text_channels if c.id == int(cid)), None)

        # Run 2: Repeated setup on same guild
        self.guild.create_category.reset_mock()
        self.guild.create_text_channel.reset_mock()
        progress_steps_run2 = []

        res2 = await UnifiedWebhookLogger.create_logging_setup_workflow(
            guild=self.guild,
            layout="category",
            create_category=True,
            progress_callback=lambda s: progress_steps_run2.append(s),
        )

        self.assertEqual(res2.get("status"), "success")
        # Must reuse category and channels without creating duplicates!
        self.assertEqual(res2.get("reused_category"), True)
        self.assertEqual(len(res2.get("created_channels", [])), 0)
        self.assertEqual(len(res2.get("reused_channels", [])), 6)
        self.assertEqual(self.guild.create_category.call_count, 0)
        self.assertEqual(self.guild.create_text_channel.call_count, 0)

    # ==========================================================================
    # 3. Concurrency Locking and Real Progress Reporting
    # ==========================================================================
    async def test_concurrency_lock_prevents_simultaneous_runs(self):
        acquired_first = await acquire_setup_lock(self.guild.id)
        self.assertTrue(acquired_first)
        self.assertTrue(is_setup_in_progress(self.guild.id))

        # Second simultaneous acquire should fail
        acquired_second = await acquire_setup_lock(self.guild.id)
        self.assertFalse(acquired_second)

        # Release lock
        await release_setup_lock(self.guild.id)
        self.assertFalse(is_setup_in_progress(self.guild.id))

        # Re-acquire succeeds after release
        acquired_third = await acquire_setup_lock(self.guild.id)
        self.assertTrue(acquired_third)
        await release_setup_lock(self.guild.id)

    # ==========================================================================
    # 4. Preview View Correctly Shows Reused vs Created Resources
    # ==========================================================================
    async def test_wizard_preview_detects_existing_resources(self):
        # Pre-populate category
        mock_cat = MagicMock(spec=discord.CategoryChannel)
        mock_cat.id = 5550001
        mock_cat.name = "MOMENTUMONE LOGS"
        mock_ch = MagicMock(spec=discord.TextChannel)
        mock_ch.name = "moderation-logs"
        mock_cat.text_channels = [mock_ch]
        self.guild.categories = [mock_cat]
        self.guild.text_channels = [mock_ch]

        sess = get_or_create_logging_wizard_session(self.guild)
        sess["layout"] = "category"

        preview = await build_wizard_preview_view(self.guild)
        preview_str = str(preview)

        # Verify preview notes reuse
        self.assertIn("Existing category will be reused", preview_str)
        self.assertIn("Reuse existing channel", preview_str)

    # ==========================================================================
    # 5. Dedicated Logging Event Handlers Architecture
    # ==========================================================================
    def test_all_16_logging_event_handlers_exist_and_configured(self):
        expected_modules = [
            "channel_create",
            "channel_delete",
            "channel_update",
            "member_ban",
            "member_unban",
            "member_join",
            "member_remove",
            "member_update",
            "role_create",
            "role_delete",
            "role_update",
            "guild_update",
            "invite_create",
            "invite_delete",
            "emojis_update",
            "webhooks_update",
        ]
        self.assertEqual(len(ALL_LOGGING_EVENT_MODULES), 16)
        for mod in ALL_LOGGING_EVENT_MODULES:
            # Check Event class exists
            event_cls = getattr(mod, "event", None)
            self.assertIsNotNone(event_cls, f"Module {mod} missing 'event' class")
            instance = event_cls(bot=MagicMock())
            self.assertIsInstance(instance, Event)
            self.assertEqual(instance.category, "logging")
            self.assertTrue(hasattr(instance, "execute"))

    async def test_logging_event_handler_dispatch(self):
        from plugins.MomentumOneToolkit.events.logging.member_ban import MemberBanLoggingEvent

        handler = MemberBanLoggingEvent(bot=MagicMock())
        
        # Test audit log attribution logic
        entry = MagicMock()
        entry.id = 9911
        entry.user = MagicMock()
        entry.user.id = 1234
        entry.user.__str__.return_value = "Moderator#0001"
        entry.reason = "Violation of Rule 1"

        mock_user = MagicMock(spec=discord.User)
        mock_user.id = 5678
        mock_user.__str__.return_value = "BadUser#0002"

        with patch.object(UnifiedWebhookLogger, "fetch_audit_attribution", new=AsyncMock(return_value=(entry.user, entry.reason))):
            with patch.object(UnifiedWebhookLogger, "dispatch_log", new=AsyncMock(return_value=True)) as mock_dispatch:
                await handler.execute(self.guild, mock_user)
                self.assertEqual(mock_dispatch.call_count, 1)
                args, kwargs = mock_dispatch.call_args
                self.assertEqual(args[0], self.guild)
                self.assertEqual(args[1], "moderation")
                payload = args[2]
                self.assertIn("BadUser#0002", str(payload))
                self.assertIn("Moderator#0001", str(payload))

    # ==========================================================================
    # 6. Clean Up Removed Logging Resources
    # ==========================================================================
    async def test_cleanup_workflow_config_only(self):
        # Configure logging in DB
        await UnifiedWebhookLogger.save_guild_logging_config(
            str(self.guild.id),
            {
                "enabled": True,
                "destinations": {"moderation": {"channel_id": "111", "webhook_url": "https://test"}},
            },
        )

        # Run config-only cleanup
        res = await UnifiedWebhookLogger.cleanup_logging_resources(
            guild=self.guild,
            delete_from_discord=False,
        )

        cfg_after = UnifiedWebhookLogger.get_guild_logging_config(str(self.guild.id))
        self.assertFalse(cfg_after.get("enabled"))
        self.assertEqual(cfg_after.get("destinations"), {})
        self.assertEqual(len(res.get("deleted_channels")), 0)

    async def test_cleanup_workflow_full_discord_deletion_respects_ownership(self):
        # Mock bot-owned logging channel
        bot_ch = MagicMock(spec=discord.TextChannel)
        bot_ch.id = 9001
        bot_ch.topic = "MomentumOne Automated Webhook Channel for Moderation Logs"
        bot_ch.delete = AsyncMock()

        # Mock non-bot channel (e.g. general chat)
        general_ch = MagicMock(spec=discord.TextChannel)
        general_ch.id = 9002
        general_ch.topic = "General discussion for members"
        general_ch.delete = AsyncMock()

        # Mock category
        mock_cat = MagicMock(spec=discord.CategoryChannel)
        mock_cat.id = 5559
        mock_cat.delete = AsyncMock()
        mock_cat.channels = []  # empty after deletion
        self.guild.categories = [mock_cat]

        self.guild.text_channels = [bot_ch, general_ch]
        self.guild.get_channel = lambda cid: bot_ch if int(cid) == 9001 else (general_ch if int(cid) == 9002 else None)

        # Configure logging in DB with both
        await UnifiedWebhookLogger.save_guild_logging_config(
            str(self.guild.id),
            {
                "enabled": True,
                "category_id": "5559",
                "destinations": {
                    "moderation": {"channel_id": "9001", "webhook_url": "https://test"},
                    "server": {"channel_id": "9002", "webhook_url": "https://test"},
                },
            },
        )

        res = await UnifiedWebhookLogger.cleanup_logging_resources(
            guild=self.guild,
            delete_from_discord=True,
            delete_category=True,
        )

        # Bot channel must be deleted
        self.assertEqual(bot_ch.delete.call_count, 1)
        # General channel must NOT be deleted because it lacks bot logging signature!
        self.assertEqual(general_ch.delete.call_count, 0)
        # Category was empty so it should be deleted
        self.assertEqual(mock_cat.delete.call_count, 1)
        self.assertTrue(res.get("deleted_category"))

    async def test_cleanup_confirmation_view(self):
        view = await build_cleanup_confirm_view(self.guild)
        view_str = str(view)
        self.assertIn("Clean Up Logging Resources", view_str)
        self.assertIn("Reset Config Only", view_str)
        self.assertIn("Full Resource Cleanup", view_str)
