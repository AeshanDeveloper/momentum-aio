import time
import asyncio
from typing import Optional, Any
import discord

from core.logging.logger import logger
from .antinuke import AntiNukeManager, AntiNukeConstants


class AntiNukeService:
    """
    Discord Gateway Event Listener and Audit-Log Processor for Anti-Nuke.
    Inspects audit logs, resolves culprits, validates permissions/hierarchy,
    and applies instant enforcement.
    """

    @classmethod
    async def _fetch_audit_entry(
        cls,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: Optional[int] = None,
        max_age_seconds: float = 6.0,
    ) -> Optional[discord.AuditLogEntry]:
        """Fetches the most recent audit log entry matching the action and target within a time window."""
        if not guild.me.guild_permissions.view_audit_log:
            return None

        try:
            async for entry in guild.audit_logs(limit=3, action=action):
                entry_age = time.time() - entry.created_at.timestamp()
                if entry_age > max_age_seconds:
                    continue
                if target_id is not None and entry.target and entry.target.id != target_id:
                    continue
                return entry
        except Exception as err:
            logger.debug(f"[AntiNukeService] Audit log fetch error on guild {guild.id}: {err}")
        return None

    # 1. BANS
    @classmethod
    async def on_member_ban(cls, guild: discord.Guild, user: discord.User | discord.Member) -> None:
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        if not cfg.get("enabled", False):
            return

        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.ban, target_id=user.id)
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_BAN,
            audit_entry_id=entry.id,
            details={"target_user": str(user), "target_id": str(user.id), "reason": entry.reason},
        )

    # 2. KICKS (Detected via member_remove + audit log)
    @classmethod
    async def on_member_remove(cls, member: discord.Member) -> None:
        guild = member.guild
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        if not cfg.get("enabled", False):
            return

        # Check if removal was a kick
        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.kick, target_id=member.id)
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_KICK,
            audit_entry_id=entry.id,
            details={"target_member": str(member), "target_id": str(member.id), "reason": entry.reason},
        )

    # 3. BOT ADDITIONS
    @classmethod
    async def on_member_join(cls, member: discord.Member) -> None:
        if not member.bot:
            return

        guild = member.guild
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        if not cfg.get("enabled", False):
            return

        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.bot_add, target_id=member.id, max_age_seconds=10.0)
        executor = entry.user if entry else None

        if executor:
            # Check if executor is exempt or whitelisted
            is_exempt = (
                AntiNukeManager.is_owner_or_extra_owner(guild, executor.id)
                or AntiNukeManager.is_whitelisted(str(guild.id), executor.id, AntiNukeConstants.EVENT_BOT_ADD)
            )
            if not is_exempt:
                # Ban the rogue bot immediately!
                try:
                    await guild.ban(member, reason=f"Anti-Nuke: Unauthorized bot added by {executor} ({executor.id})")
                except Exception as b_err:
                    logger.warning(f"[AntiNukeService] Failed to auto-ban unauthorized bot {member.id}: {b_err}")

                # Punish the executor
                await AntiNukeManager.record_and_evaluate_infraction(
                    guild=guild,
                    executor=executor,
                    event_type=AntiNukeConstants.EVENT_BOT_ADD,
                    audit_entry_id=entry.id if entry else None,
                    details={"added_bot_id": str(member.id), "added_bot_name": str(member)},
                )

    # 4. MEMBER UPDATES (Mutes / Timeouts & Dangerous Role Grants)
    @classmethod
    async def on_member_update(cls, before: discord.Member, after: discord.Member) -> None:
        guild = after.guild
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        if not cfg.get("enabled", False):
            return

        # 4a. Timeout / Mute check
        before_timeout = getattr(before, "timed_out_until", None)
        after_timeout = getattr(after, "timed_out_until", None)
        if after_timeout and after_timeout != before_timeout:
            entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.member_update, target_id=after.id)
            if entry and entry.user:
                await AntiNukeManager.record_and_evaluate_infraction(
                    guild=guild,
                    executor=entry.user,
                    event_type=AntiNukeConstants.EVENT_TIMEOUT,
                    audit_entry_id=entry.id,
                    details={"target_member": str(after), "timeout_until": str(after_timeout)},
                )

        # 4b. Dangerous Role Assignment check
        before_roles = set(before.roles)
        after_roles = set(after.roles)
        added_roles = after_roles - before_roles
        if added_roles:
            dangerous_added = []
            for r in added_roles:
                for perm_key in AntiNukeConstants.DANGEROUS_PERMISSIONS.keys():
                    if getattr(r.permissions, perm_key, False):
                        dangerous_added.append((r, perm_key))

            if dangerous_added:
                entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.member_role_update, target_id=after.id)
                if entry and entry.user:
                    # Strip dangerous roles back from target if executor is not owner/whitelisted
                    if not (AntiNukeManager.is_owner_or_extra_owner(guild, entry.user.id) or AntiNukeManager.is_whitelisted(str(guild.id), entry.user.id, AntiNukeConstants.EVENT_MEMBER_UPDATE)):
                        try:
                            strip_targets = [r[0] for r in dangerous_added if r[0] < guild.me.top_role]
                            if strip_targets:
                                await after.remove_roles(*strip_targets, reason="Anti-Nuke: Reverting unauthorized dangerous role grant.")
                        except Exception:
                            pass

                    await AntiNukeManager.record_and_evaluate_infraction(
                        guild=guild,
                        executor=entry.user,
                        event_type=AntiNukeConstants.EVENT_MEMBER_UPDATE,
                        audit_entry_id=entry.id,
                        details={
                            "target_member": str(after),
                            "dangerous_roles": [f"{r[0].name} ({r[1]})" for r in dangerous_added]
                        },
                    )

    # 5. ROLE CREATION
    @classmethod
    async def on_guild_role_create(cls, role: discord.Role) -> None:
        guild = role.guild
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        if not cfg.get("enabled", False):
            return

        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.role_create, target_id=role.id)
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_ROLE_CREATE,
            audit_entry_id=entry.id,
            details={"role_name": role.name, "role_id": str(role.id)},
        )

    # 6. ROLE DELETION
    @classmethod
    async def on_guild_role_delete(cls, role: discord.Role) -> None:
        guild = role.guild
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        if not cfg.get("enabled", False):
            return

        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.role_delete, target_id=role.id)
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_ROLE_DELETE,
            audit_entry_id=entry.id,
            details={"role_name": role.name, "role_id": str(role.id)},
        )

    # 7. ROLE UPDATE (Dangerous permission changes)
    @classmethod
    async def on_guild_role_update(cls, before: discord.Role, after: discord.Role) -> None:
        guild = after.guild
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        if not cfg.get("enabled", False):
            return

        escalated_perms = []
        for p in AntiNukeConstants.DANGEROUS_PERMISSIONS.keys():
            if not getattr(before.permissions, p, False) and getattr(after.permissions, p, False):
                escalated_perms.append(p)

        if not escalated_perms:
            return

        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.role_update, target_id=after.id)
        if not entry or not entry.user:
            return

        # Attempt to roll back permissions if possible
        if not (AntiNukeManager.is_owner_or_extra_owner(guild, entry.user.id) or AntiNukeManager.is_whitelisted(str(guild.id), entry.user.id, AntiNukeConstants.EVENT_ROLE_UPDATE)):
            if after < guild.me.top_role and guild.me.guild_permissions.manage_roles:
                try:
                    await after.edit(permissions=before.permissions, reason="Anti-Nuke: Reverting dangerous permission escalation.")
                except Exception:
                    pass

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_ROLE_UPDATE,
            audit_entry_id=entry.id,
            details={"role_name": after.name, "escalated_permissions": escalated_perms},
        )

    # 8. CHANNEL CREATION
    @classmethod
    async def on_guild_channel_create(cls, channel: discord.abc.GuildChannel) -> None:
        guild = channel.guild
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        if not cfg.get("enabled", False):
            return

        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.channel_create, target_id=channel.id)
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_CHANNEL_CREATE,
            audit_entry_id=entry.id,
            details={"channel_name": channel.name, "channel_id": str(channel.id)},
            channel=channel,
        )

    # 9. CHANNEL DELETION
    @classmethod
    async def on_guild_channel_delete(cls, channel: discord.abc.GuildChannel) -> None:
        guild = channel.guild
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        if not cfg.get("enabled", False):
            return

        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.channel_delete, target_id=channel.id)
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_CHANNEL_DELETE,
            audit_entry_id=entry.id,
            details={"channel_name": channel.name, "channel_id": str(channel.id)},
            channel=channel,
        )

    # 10. CHANNEL UPDATE
    @classmethod
    async def on_guild_channel_update(cls, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
        guild = after.guild
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        if not cfg.get("enabled", False):
            return

        # Check if overwrites or critical properties changed
        if before.overwrites == after.overwrites and before.name == after.name:
            return

        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.channel_update, target_id=after.id)
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_CHANNEL_UPDATE,
            audit_entry_id=entry.id,
            details={"channel_name": after.name, "channel_id": str(after.id)},
            channel=after,
        )

    # 11. WEBHOOKS UPDATE
    @classmethod
    async def on_webhooks_update(cls, channel: discord.abc.GuildChannel) -> None:
        guild = channel.guild
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        if not cfg.get("enabled", False):
            return

        # Inspect webhook audit log (create, delete, update)
        for action, ev_type in [
            (discord.AuditLogAction.webhook_create, AntiNukeConstants.EVENT_WEBHOOK_CREATE),
            (discord.AuditLogAction.webhook_delete, AntiNukeConstants.EVENT_WEBHOOK_DELETE),
            (discord.AuditLogAction.webhook_update, AntiNukeConstants.EVENT_WEBHOOK_UPDATE),
        ]:
            entry = await cls._fetch_audit_entry(guild, action, max_age_seconds=4.0)
            if entry and entry.user:
                await AntiNukeManager.record_and_evaluate_infraction(
                    guild=guild,
                    executor=entry.user,
                    event_type=ev_type,
                    audit_entry_id=entry.id,
                    details={"channel_name": channel.name, "channel_id": str(channel.id)},
                )
                break
