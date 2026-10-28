import time
import asyncio
from typing import Optional, Any, Sequence, Union, Dict
import discord


from core.logging.logger import logger
from .antinuke import AntiNukeManager, AntiNukeConstants


class AntiNukeService:
    """
    Discord Gateway Event Listener and Audit-Log Processor for Anti-Nuke.
    Inspects audit logs, resolves culprits, validates permissions/hierarchy,
    and applies instant enforcement across all 23 critical Discord event vectors.
    """

    @classmethod
    async def _fetch_audit_entry(
        cls,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: Optional[int] = None,
        max_age_seconds: float = 8.0,
    ) -> Optional[discord.AuditLogEntry]:
        """Fetches the most recent audit log entry matching action and target within a time window."""
        if not guild or not getattr(guild, "me", None):
            return None
        if not guild.me.guild_permissions.view_audit_log:
            return None

        try:
            async for entry in guild.audit_logs(limit=4, action=action):
                entry_age = time.time() - entry.created_at.timestamp()
                if entry_age > max_age_seconds:
                    continue
                if target_id is not None and entry.target and getattr(entry.target, "id", None) != target_id:
                    continue
                return entry
        except Exception as err:
            logger.debug(f"[AntiNukeService] Audit log query error on guild {guild.id}: {err}")
        return None

    @classmethod
    def _observe_security_event(
        cls,
        event_type: str,
        *args: Any,
        guild: Optional[discord.Guild] = None,
        actor: Optional[Union[discord.Member, discord.User]] = None,
        audit_entry_id: Optional[Union[int, str]] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Dispatches normalized gateway events to Sentinel's unified observation pipeline."""
        try:
            from core.security.pipeline import sentinel_pipeline
            sentinel_pipeline.process_gateway_event(
                event_type,
                *args,
                guild=guild,
                actor=actor,
                audit_entry_id=audit_entry_id,
                details=details,
                **kwargs,
            )
        except Exception as err:
            logger.debug(f"[AntiNukeService] Pipeline event observation error: {err}")



    # 1. GUILD UPDATE (Server changes: vanity, name, icon)
    @classmethod
    async def on_guild_update(cls, before: discord.Guild, after: discord.Guild) -> None:
        entry = await cls._fetch_audit_entry(after, discord.AuditLogAction.guild_update)
        cls._observe_security_event(
            AntiNukeConstants.EVENT_GUILD_UPDATE,
            before,
            after,
            guild=after,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"before_name": before.name, "after_name": after.name},
        )
        if not AntiNukeManager.is_setup_completed(after.id):
            return
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=after,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_GUILD_UPDATE,
            audit_entry_id=entry.id,
            details={"before_name": before.name, "after_name": after.name},
        )

    # 2. CHANNEL CREATION
    @classmethod
    async def on_guild_channel_create(cls, channel: discord.abc.GuildChannel) -> None:
        guild = getattr(channel, "guild", None)
        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.channel_create, target_id=channel.id) if guild else None
        cls._observe_security_event(
            AntiNukeConstants.EVENT_CHANNEL_CREATE,
            channel,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"channel_name": getattr(channel, "name", ""), "channel_id": str(getattr(channel, "id", ""))},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return
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

    # 3. CHANNEL UPDATE
    @classmethod
    async def on_guild_channel_update(cls, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
        guild = getattr(after, "guild", None)
        # Filter out minor voice channel member movements or non-permission updates
        if getattr(before, "overwrites", None) == getattr(after, "overwrites", None) and before.name == after.name:
            return

        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.channel_update, target_id=after.id) if guild else None
        cls._observe_security_event(
            AntiNukeConstants.EVENT_CHANNEL_UPDATE,
            before,
            after,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"channel_name": after.name, "channel_id": str(after.id)},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return
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

    # 4. CHANNEL DELETION
    @classmethod
    async def on_guild_channel_delete(cls, channel: discord.abc.GuildChannel) -> None:
        guild = getattr(channel, "guild", None)
        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.channel_delete, target_id=channel.id) if guild else None
        cls._observe_security_event(
            AntiNukeConstants.EVENT_CHANNEL_DELETE,
            channel,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"channel_name": getattr(channel, "name", ""), "channel_id": str(getattr(channel, "id", ""))},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return
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

    # 5. ROLE CREATION
    @classmethod
    async def on_guild_role_create(cls, role: discord.Role) -> None:
        guild = role.guild
        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.role_create, target_id=role.id) if guild else None
        cls._observe_security_event(
            AntiNukeConstants.EVENT_ROLE_CREATE,
            role,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"role_name": role.name, "role_id": str(role.id)},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_ROLE_CREATE,
            audit_entry_id=entry.id,
            details={"role_name": role.name, "role_id": str(role.id)},
        )

    # 6. ROLE UPDATE (Permission escalation)
    @classmethod
    async def on_guild_role_update(cls, before: discord.Role, after: discord.Role) -> None:
        guild = after.guild
        escalated_perms = []
        for p in AntiNukeConstants.DANGEROUS_PERMISSIONS.keys():
            if not getattr(before.permissions, p, False) and getattr(after.permissions, p, False):
                escalated_perms.append(p)

        if not escalated_perms:
            return

        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.role_update, target_id=after.id) if guild else None
        cls._observe_security_event(
            AntiNukeConstants.EVENT_ROLE_UPDATE,
            before,
            after,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"role_name": after.name, "escalated_permissions": escalated_perms},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return
        if not entry or not entry.user:
            return

        # Attempt to roll back dangerous permissions if bot has permissions
        if not AntiNukeManager.is_owner_or_extra_owner(guild, entry.user.id):
            if after < guild.me.top_role and guild.me.guild_permissions.manage_roles:
                try:
                    await after.edit(permissions=before.permissions, reason="Anti-Nuke: Reverting unauthorized dangerous permission grant.")
                except Exception:
                    pass

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_ROLE_UPDATE,
            audit_entry_id=entry.id,
            details={"role_name": after.name, "escalated_permissions": escalated_perms},
        )

    # 7. ROLE DELETION
    @classmethod
    async def on_guild_role_delete(cls, role: discord.Role, guild: Optional[discord.Guild] = None) -> None:
        resolved_guild = guild or getattr(role, "guild", None)
        if not resolved_guild:
            client = getattr(role, "_client", None) or getattr(discord, "Client", None)._default_instance
            if client and hasattr(client, "guilds"):
                for g in client.guilds:
                    if any(getattr(r, "id", None) == getattr(role, "id", None) for r in getattr(g, "roles", [])):
                        resolved_guild = g
                        break

        entry = await cls._fetch_audit_entry(resolved_guild, discord.AuditLogAction.role_delete, target_id=role.id) if resolved_guild else None
        cls._observe_security_event(
            AntiNukeConstants.EVENT_ROLE_DELETE,
            role,
            guild=resolved_guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"role_name": getattr(role, "name", f"Role {role.id}"), "role_id": str(role.id)},
        )
        if not resolved_guild:
            logger.warning(f"[AntiNukeService] Unable to obtain guild context for deleted role {getattr(role, 'id', 'unknown')}.")
            return
        if not AntiNukeManager.is_setup_completed(resolved_guild.id):
            return
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=resolved_guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_ROLE_DELETE,
            audit_entry_id=entry.id,
            details={"role_name": getattr(role, "name", f"Role {role.id}"), "role_id": str(role.id)},
        )

    # 8. MEMBER UPDATE (Dangerous roles or timeouts)

    @classmethod
    async def on_member_update(cls, before: discord.Member, after: discord.Member) -> None:
        guild = after.guild
        if not AntiNukeManager.is_setup_completed(guild.id):
            return

        # 8a. Timeout check
        before_timeout = getattr(before, "timed_out_until", None)
        after_timeout = getattr(after, "timed_out_until", None)
        if after_timeout and after_timeout != before_timeout:
            entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.member_update, target_id=after.id)
            if entry and entry.user:
                await AntiNukeManager.record_and_evaluate_infraction(
                    guild=guild,
                    executor=entry.user,
                    event_type=AntiNukeConstants.EVENT_MEMBER_UPDATE,
                    audit_entry_id=entry.id,
                    details={"target_member": str(after), "timeout_until": str(after_timeout)},
                )

        # 8b. Dangerous Role Assignment check
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
                    if not AntiNukeManager.is_owner_or_extra_owner(guild, entry.user.id):
                        try:
                            strip_targets = [r[0] for r in dangerous_added if r[0] < guild.me.top_role]
                            if strip_targets and guild.me.guild_permissions.manage_roles:
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

    # 9. MEMBER REMOVAL (Kicks)
    @classmethod
    async def on_member_remove(cls, member: discord.Member) -> None:
        guild = member.guild
        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.kick, target_id=member.id) if guild else None
        executor = entry.user if (entry and entry.user) else None
        reason = entry.reason if entry else "No reason specified"

        cls._observe_security_event(
            AntiNukeConstants.EVENT_MEMBER_REMOVE,
            member,
            guild=guild,
            actor=executor,
            audit_entry_id=entry.id if entry else None,
            is_kick=bool(entry and entry.action == discord.AuditLogAction.kick),
            details={"target_member": str(member), "target_id": str(member.id), "reason": reason},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return

        # Log moderation kick via unified webhook logger
        if entry:
            from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
            await UnifiedWebhookLogger.dispatch_log(
                guild=guild,
                category=LogCategory.MODERATION,
                title="Member Kicked",
                description=f"Member {member.mention} was removed from the server.",
                actor=executor,
                target=member,
                reason=reason,
                severity=LogSeverity.LOW,
            )

        if executor:
            await AntiNukeManager.record_and_evaluate_infraction(
                guild=guild,
                executor=executor,
                event_type=AntiNukeConstants.EVENT_MEMBER_REMOVE,
                audit_entry_id=entry.id if entry else None,
                details={"target_member": str(member), "target_id": str(member.id), "reason": reason},
            )

    # 10. MEMBER BAN
    @classmethod
    async def on_member_ban(cls, guild: discord.Guild, user: discord.User | discord.Member) -> None:
        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.ban, target_id=user.id)
        executor = entry.user if (entry and entry.user) else None
        reason = entry.reason if entry else "No reason specified"
        audit_id = entry.id if entry else None

        cls._observe_security_event(
            AntiNukeConstants.EVENT_BAN_ADD,
            guild,
            user,
            guild=guild,
            actor=executor,
            audit_entry_id=audit_id,
            details={"target_user": str(user), "target_id": str(user.id), "reason": reason},
        )
        if not AntiNukeManager.is_setup_completed(guild.id):
            return

        from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.MODERATION,
            title="Member Banned",
            description=f"Member {user.mention} was banned from the server.",
            actor=executor,
            target=user,
            reason=reason,
            severity=LogSeverity.MEDIUM,
        )

        if executor:
            await AntiNukeManager.record_and_evaluate_infraction(
                guild=guild,
                executor=executor,
                event_type=AntiNukeConstants.EVENT_BAN_ADD,
                audit_entry_id=audit_id,
                details={"target_user": str(user), "target_id": str(user.id), "reason": reason},
            )

    # 11. MEMBER UNBAN
    @classmethod
    async def on_member_unban(cls, guild: discord.Guild, user: discord.User | discord.Member) -> None:
        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.unban, target_id=user.id)
        executor = entry.user if (entry and entry.user) else None
        reason = entry.reason if entry else "No reason specified"

        cls._observe_security_event(
            AntiNukeConstants.EVENT_BAN_REMOVE,
            guild,
            user,
            guild=guild,
            actor=executor,
            audit_entry_id=entry.id if entry else None,
            details={"target_user": str(user), "target_id": str(user.id)},
        )
        if not AntiNukeManager.is_setup_completed(guild.id):
            return

        from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.MODERATION,
            title="Member Unbanned",
            description=f"Ban revoked for {user.mention}.",
            actor=executor,
            target=user,
            reason=reason,
            severity=LogSeverity.LOW,
        )

        if executor:
            await AntiNukeManager.record_and_evaluate_infraction(
                guild=guild,
                executor=executor,
                event_type=AntiNukeConstants.EVENT_BAN_REMOVE,
                audit_entry_id=entry.id if entry else None,
                details={"target_user": str(user), "target_id": str(user.id)},
            )

    # 12. EMOJIS UPDATE
    @classmethod
    async def on_guild_emojis_update(cls, guild: discord.Guild, before: Sequence[discord.Emoji], after: Sequence[discord.Emoji]) -> None:
        action = discord.AuditLogAction.emoji_delete if len(after) < len(before) else discord.AuditLogAction.emoji_create
        entry = await cls._fetch_audit_entry(guild, action)
        cls._observe_security_event(
            AntiNukeConstants.EVENT_EMOJIS_UPDATE,
            guild,
            before,
            after,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"before_count": len(before), "after_count": len(after)},
        )
        if not AntiNukeManager.is_setup_completed(guild.id):
            return
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_EMOJIS_UPDATE,
            audit_entry_id=entry.id,
            details={"before_count": len(before), "after_count": len(after)},
        )

    # 13. STICKERS UPDATE
    @classmethod
    async def on_guild_stickers_update(cls, guild: discord.Guild, before: Sequence[discord.GuildSticker], after: Sequence[discord.GuildSticker]) -> None:
        action = discord.AuditLogAction.sticker_delete if len(after) < len(before) else discord.AuditLogAction.sticker_create
        entry = await cls._fetch_audit_entry(guild, action)
        cls._observe_security_event(
            AntiNukeConstants.EVENT_STICKERS_UPDATE,
            guild,
            before,
            after,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"before_count": len(before), "after_count": len(after)},
        )
        if not AntiNukeManager.is_setup_completed(guild.id):
            return
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_STICKERS_UPDATE,
            audit_entry_id=entry.id,
            details={"before_count": len(before), "after_count": len(after)},
        )

    # 14. WEBHOOKS UPDATE
    @classmethod
    async def on_webhooks_update(cls, channel: discord.abc.GuildChannel) -> None:
        guild = getattr(channel, "guild", None)
        entry = None
        for action in [
            discord.AuditLogAction.webhook_create,
            discord.AuditLogAction.webhook_delete,
            discord.AuditLogAction.webhook_update,
        ]:
            if guild:
                entry = await cls._fetch_audit_entry(guild, action, max_age_seconds=6.0)
                if entry and entry.user:
                    break

        cls._observe_security_event(
            AntiNukeConstants.EVENT_WEBHOOKS_UPDATE,
            channel,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"channel_name": getattr(channel, "name", ""), "channel_id": str(getattr(channel, "id", ""))},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return
        if entry and entry.user:
            await AntiNukeManager.record_and_evaluate_infraction(
                guild=guild,
                executor=entry.user,
                event_type=AntiNukeConstants.EVENT_WEBHOOKS_UPDATE,
                audit_entry_id=entry.id,
                details={"channel_name": channel.name, "channel_id": str(channel.id)},
            )


    # 15. INVITE CREATE
    @classmethod
    async def on_invite_create(cls, invite: discord.Invite) -> None:
        guild = getattr(invite, "guild", None)
        inviter = getattr(invite, "inviter", None)
        if not inviter and guild:
            entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.invite_create)
            inviter = entry.user if entry else None

        cls._observe_security_event(
            AntiNukeConstants.EVENT_INVITE_CREATE,
            invite,
            guild=guild,
            actor=inviter,
            details={"invite_code": getattr(invite, "code", ""), "channel_id": str(getattr(getattr(invite, "channel", None), "id", ""))},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return

        if inviter:
            await AntiNukeManager.record_and_evaluate_infraction(
                guild=guild,
                executor=inviter,
                event_type=AntiNukeConstants.EVENT_INVITE_CREATE,
                details={"invite_code": invite.code, "channel_id": str(invite.channel.id) if invite.channel else ""},
            )

    # 16. INVITE DELETE
    @classmethod
    async def on_invite_delete(cls, invite: discord.Invite) -> None:
        guild = getattr(invite, "guild", None)
        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.invite_delete) if guild else None
        cls._observe_security_event(
            AntiNukeConstants.EVENT_INVITE_DELETE,
            invite,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"invite_code": getattr(invite, "code", "")},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_INVITE_DELETE,
            audit_entry_id=entry.id,
            details={"invite_code": invite.code},
        )

    # 17. INTEGRATIONS UPDATE
    @classmethod
    async def on_guild_integrations_update(cls, guild: discord.Guild) -> None:
        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.integration_create)
        if not entry or not entry.user:
            entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.integration_delete)

        cls._observe_security_event(
            AntiNukeConstants.EVENT_INTEGRATIONS_UPDATE,
            guild,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"integration_action": str(entry.action) if entry else "unknown"},
        )
        if not AntiNukeManager.is_setup_completed(guild.id):
            return
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_INTEGRATIONS_UPDATE,
            audit_entry_id=entry.id,
            details={"integration_action": str(entry.action)},
        )

    # 18. AUTOMOD RULE CREATE
    @classmethod
    async def on_auto_moderation_rule_create(cls, rule: Any) -> None:
        guild = getattr(rule, "guild", None)
        entry = await cls._fetch_audit_entry(guild, getattr(discord.AuditLogAction, "automod_rule_create", discord.AuditLogAction.guild_update)) if guild else None
        cls._observe_security_event(
            AntiNukeConstants.EVENT_AUTOMOD_CREATE,
            rule,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"rule_name": getattr(rule, "name", "AutoMod Rule")},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_AUTOMOD_CREATE,
            audit_entry_id=entry.id,
            details={"rule_name": getattr(rule, "name", "AutoMod Rule")},
        )

    # 19. AUTOMOD RULE UPDATE
    @classmethod
    async def on_auto_moderation_rule_update(cls, rule: Any) -> None:
        guild = getattr(rule, "guild", None)
        entry = await cls._fetch_audit_entry(guild, getattr(discord.AuditLogAction, "automod_rule_update", discord.AuditLogAction.guild_update)) if guild else None
        cls._observe_security_event(
            AntiNukeConstants.EVENT_AUTOMOD_UPDATE,
            None,
            rule,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"rule_name": getattr(rule, "name", "AutoMod Rule")},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_AUTOMOD_UPDATE,
            audit_entry_id=entry.id,
            details={"rule_name": getattr(rule, "name", "AutoMod Rule")},
        )

    # 20. AUTOMOD RULE DELETE
    @classmethod
    async def on_auto_moderation_rule_delete(cls, rule: Any) -> None:
        guild = getattr(rule, "guild", None)
        entry = await cls._fetch_audit_entry(guild, getattr(discord.AuditLogAction, "automod_rule_delete", discord.AuditLogAction.guild_update)) if guild else None
        cls._observe_security_event(
            AntiNukeConstants.EVENT_AUTOMOD_DELETE,
            rule,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"rule_name": getattr(rule, "name", "AutoMod Rule")},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_AUTOMOD_DELETE,
            audit_entry_id=entry.id,
            details={"rule_name": getattr(rule, "name", "AutoMod Rule")},
        )

    # 21. AUDIT LOG ENTRY PROCESSING (Internal Attribution & Evidence)
    @classmethod
    async def on_audit_log_entry_create(cls, entry: discord.AuditLogEntry) -> None:
        guild = getattr(entry, "guild", None)
        cls._observe_security_event(
            AntiNukeConstants.EVENT_AUDIT_LOG_CREATE,
            entry,
            guild=guild,
            actor=getattr(entry, "user", None),
            audit_entry_id=entry.id,
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return

        if not entry.user or (guild.me and entry.user.id == guild.me.id):
            return

        # Deduplicate audit log entries to prevent duplicate processing
        if entry.id in AntiNukeManager._processed_audit_entries:
            return
        AntiNukeManager._processed_audit_entries.append(entry.id)

    # 22. SCHEDULED EVENT DELETE
    @classmethod
    async def on_scheduled_event_delete(cls, event: Any) -> None:
        guild = getattr(event, "guild", None)
        entry = await cls._fetch_audit_entry(guild, getattr(discord.AuditLogAction, "scheduled_event_delete", discord.AuditLogAction.guild_update)) if guild else None
        cls._observe_security_event(
            AntiNukeConstants.EVENT_SCHEDULED_EVENT_DELETE,
            event,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"event_name": getattr(event, "name", "Scheduled Event")},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_SCHEDULED_EVENT_DELETE,
            audit_entry_id=entry.id,
            details={"event_name": getattr(event, "name", "Scheduled Event")},
        )

    # 23. THREAD DELETE
    @classmethod
    async def on_thread_delete(cls, thread: discord.Thread) -> None:
        guild = getattr(thread, "guild", None)
        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.thread_delete, target_id=thread.id) if guild else None
        cls._observe_security_event(
            AntiNukeConstants.EVENT_THREAD_DELETE,
            thread,
            guild=guild,
            actor=entry.user if entry else None,
            audit_entry_id=entry.id if entry else None,
            details={"thread_name": getattr(thread, "name", ""), "thread_id": str(getattr(thread, "id", ""))},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return
        if not entry or not entry.user:
            return

        await AntiNukeManager.record_and_evaluate_infraction(
            guild=guild,
            executor=entry.user,
            event_type=AntiNukeConstants.EVENT_THREAD_DELETE,
            audit_entry_id=entry.id,
            details={"thread_name": thread.name, "thread_id": str(thread.id)},
        )

    # 24. ROGUE BOT ADDITIONS
    @classmethod
    async def on_member_join(cls, member: discord.Member) -> None:
        if not member.bot:
            return

        guild = member.guild
        entry = await cls._fetch_audit_entry(guild, discord.AuditLogAction.bot_add, target_id=member.id, max_age_seconds=12.0) if guild else None
        executor = entry.user if entry else None

        cls._observe_security_event(
            AntiNukeConstants.EVENT_BOT_ADD,
            member,
            guild=guild,
            actor=executor,
            audit_entry_id=entry.id if entry else None,
            details={"added_bot_id": str(member.id), "added_bot_name": str(member)},
        )
        if not guild or not AntiNukeManager.is_setup_completed(guild.id):
            return

        if executor:
            is_exempt = (
                AntiNukeManager.is_owner_or_extra_owner(guild, executor.id)
                or AntiNukeManager.is_whitelisted(str(guild.id), executor, AntiNukeConstants.EVENT_BOT_ADD)
            )
            if not is_exempt:
                # Ban the rogue bot immediately!
                try:
                    await guild.ban(member, reason=f"{settings.BOT_NAME} Anti-Nuke: Unauthorized bot added by {executor} ({executor.id})")
                except Exception as b_err:
                    logger.warning(f"[AntiNukeService] Failed to auto-ban rogue bot {member.id}: {b_err}")

                await AntiNukeManager.record_and_evaluate_infraction(
                    guild=guild,
                    executor=executor,
                    event_type=AntiNukeConstants.EVENT_BOT_ADD,
                    audit_entry_id=entry.id if entry else None,
                    details={"added_bot_id": str(member.id), "added_bot_name": str(member)},
                )

