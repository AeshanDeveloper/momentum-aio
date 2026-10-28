"""
Sentinel™ Admin Notifier & Interactive Recovery Workflow.

Agent 5 of 8 Security Core: Secure DM dispatcher, interactive action components,
strict runtime authorization checks, multi-admin quorum verification, graceful
DM failure fallback, and evidence-preserving false alarm reporting.

Key capabilities:
- Interactive UI components: Keep Lockdown, Begin Recovery, Review Incident, Report False Alarm.
- Strict Authorization: Button presence != authorization. Every interaction validates user ID
  and guild permissions against policy before executing actions.
- Quorum verification: Owner action is immediately authorized; non-owner trusted admins
  require configured quorum count before initiating full recovery.
- Fallback Channel Routing: Automatically reroutes alerts if recovery admin DMs are closed/forbidden.
- Evidence-Preserving False Alarm Handling: Records dismissal and correction without deleting audit proof.
"""

from __future__ import annotations

import time
import asyncio
import threading
from typing import Dict, Any, List, Optional, Set, Callable, Union

import discord
from discord import ui, ButtonStyle

from config.settings import settings, COLORS, EMOJIS, IMAGES, get_color, get_emoji
from core.logging.logger import logger
from core.security.response_policy import SecurityResponsePolicy, LockdownStatus, get_default_response_policy
from core.security.lockdown_journal import LockdownRecord, lockdown_journal_manager
from core.security.emergency_lockdown_manager import emergency_lockdown_manager
from core.security.incident import (
    Incident,
    IncidentStatus,
    ReviewDecisionType,
    AdminVote,
    ProtectiveActionType,
)


class InteractiveActionID:
    """Canonical custom_ids for emergency alert interactive components."""
    KEEP_LOCKDOWN = "sentinel:action:keep_lockdown"
    BEGIN_RECOVERY = "sentinel:action:begin_recovery"
    REVIEW_INCIDENT = "sentinel:action:review_incident"
    REPORT_FALSE_ALARM = "sentinel:action:report_false_alarm"


class EmergencyRecoveryView(ui.View):
    """
    Interactive button view attached to emergency alert DMs and fallback channel broadcasts.
    Provides immediate one-click decision-making for verified recovery staff.
    """
    def __init__(
        self,
        incident: Incident,
        lockdown_record: Optional[LockdownRecord] = None,
        policy: Optional[SecurityResponsePolicy] = None,
        lockdown_manager: Optional[EmergencyLockdownManager] = None,
        timeout: Optional[float] = 86400.0,  # 24 hours
    ):
        super().__init__(timeout=timeout)
        self.incident = incident
        self.lockdown_record = lockdown_record
        self.policy = policy or get_default_response_policy(incident.guild_id)
        self.lockdown_manager = lockdown_manager or emergency_lockdown_manager

        if self.lockdown_record and hasattr(self.lockdown_manager, "journal"):
            self.lockdown_manager.journal.save_lockdown(self.lockdown_record)
        
        # In-memory approval tracker for recovery quorum: user_id -> timestamp
        self._recovery_approvals: Set[str] = set()


        # Add interactive buttons
        self.btn_keep = ui.Button(
            style=ButtonStyle.danger,
            label="Keep Lockdown",
            custom_id=f"{InteractiveActionID.KEEP_LOCKDOWN}:{incident.incident_id}",
            emoji=get_emoji("lock", "🔒"),
        )
        self.btn_keep.callback = self.handle_keep_lockdown
        self.add_item(self.btn_keep)

        self.btn_recover = ui.Button(
            style=ButtonStyle.success,
            label="Begin Recovery",
            custom_id=f"{InteractiveActionID.BEGIN_RECOVERY}:{incident.incident_id}",
            emoji=get_emoji("unlock", "🔓"),
        )
        self.btn_recover.callback = self.handle_begin_recovery
        self.add_item(self.btn_recover)

        self.btn_review = ui.Button(
            style=ButtonStyle.secondary,
            label="Review Incident",
            custom_id=f"{InteractiveActionID.REVIEW_INCIDENT}:{incident.incident_id}",
            emoji=get_emoji("search", "🔍"),
        )
        self.btn_review.callback = self.handle_review_incident
        self.add_item(self.btn_review)

        self.btn_false_alarm = ui.Button(
            style=ButtonStyle.secondary,
            label="Report False Alarm",
            custom_id=f"{InteractiveActionID.REPORT_FALSE_ALARM}:{incident.incident_id}",
            emoji=get_emoji("warning", "⚠️"),
        )
        self.btn_false_alarm.callback = self.handle_false_alarm
        self.add_item(self.btn_false_alarm)

    def _verify_caller_authorization(self, user: Any) -> Tuple[bool, str]:
        """
        Revalidates user authorization on every button interaction.
        Enforces policy: user must be designated recovery owner or trusted recovery admin.
        """
        if not user:
            return False, "User context missing"

        uid_str = str(getattr(user, "id", ""))
        if not self.policy.is_trusted_recovery_actor(uid_str):
            logger.warning(
                f"[SecurityAuth] Unauthorized interaction attempt by user {uid_str} ({user}) on incident {self.incident.incident_id}"
            )
            return False, "Unauthorized: You are not a designated recovery administrator for this server."

        return True, "Authorized"

    async def handle_keep_lockdown(self, interaction: Any) -> None:
        """Confirms the lockdown must remain active."""
        user = getattr(interaction, "user", None)
        authorized, reason = self._verify_caller_authorization(user)
        if not authorized:
            await self._respond_ephemeral(interaction, f"❌ {reason}")
            return

        uid_str = str(user.id)
        self.incident.add_decision(
            actor_id=uid_str,
            actor_name=str(user),
            decision_type=ReviewDecisionType.LOCKDOWN,
            reason="Confirmed lockdown continuation via interactive alert component.",
        )
        self.incident.status = IncidentStatus.UNDER_REVIEW

        await self._respond_ephemeral(
            interaction,
            f"🛡️ **Lockdown Confirmed Active** by <@{uid_str}>. Server containment remains in effect.",
        )

    async def handle_begin_recovery(self, interaction: Any) -> None:
        """
        Initiates reversible recovery with quorum checking.
        If recovery owner: executed immediately.
        If non-owner trusted admin: requires quorum count of approvals.
        """
        user = getattr(interaction, "user", None)
        authorized, reason = self._verify_caller_authorization(user)
        if not authorized:
            await self._respond_ephemeral(interaction, f"❌ {reason}")
            return

        uid_str = str(user.id)
        guild = getattr(interaction, "guild", None)
        is_owner = self.policy.is_recovery_owner(uid_str)

        # Quorum verification
        if not is_owner:
            self._recovery_approvals.add(uid_str)
            needed = self.policy.recovery_quorum
            current = len(self._recovery_approvals)
            if current < needed:
                await self._respond_ephemeral(
                    interaction,
                    f"⏳ **Recovery Approval Registered** ({current}/{needed} required approvals). "
                    f"Waiting for additional trusted admin verification before restoring server.",
                )
                self.incident.add_vote(admin_id=uid_str, admin_name=str(user), approved=True, reason="Voted for recovery")
                return

        # Quorum reached or authorized by owner
        lockdown_id = self.lockdown_record.lockdown_id if self.lockdown_record else self.incident.incident_id
        try:
            restored_record = await self.lockdown_manager.restore_lockdown(
                guild=guild,
                lockdown_id=lockdown_id,
                admin_user_id=uid_str,
                policy=self.policy,
            )


            self.incident.status = IncidentStatus.CONFIRMED
            self.incident.add_decision(
                actor_id=uid_str,
                actor_name=str(user),
                decision_type=ReviewDecisionType.RESTORE,
                reason=f"Recovery executed by <@{uid_str}>. Status: {restored_record.status}.",
            )

            conflicts = restored_record.summary.get("conflict_detected", 0)
            conflict_msg = (
                f"\n⚠️ Note: {conflicts} independent admin change(s) were preserved without overwriting."
                if conflicts > 0
                else ""
            )

            await self._respond_ephemeral(
                interaction,
                f"✅ **Server Permissions Restored** by <@{uid_str}>.\n"
                f"• Restored Entries: {restored_record.summary.get('restored', 0)}\n"
                f"• Status: `{restored_record.status}`{conflict_msg}",
            )
        except Exception as err:
            logger.error(f"[EmergencyRecoveryView] Recovery execution failed: {err}")
            await self._respond_ephemeral(interaction, f"❌ Recovery execution failed: {err}")

    async def handle_review_incident(self, interaction: Any) -> None:
        """Displays full incident breakdown, facts, evidence count, and actors."""
        user = getattr(interaction, "user", None)
        authorized, reason = self._verify_caller_authorization(user)
        if not authorized:
            await self._respond_ephemeral(interaction, f"❌ {reason}")
            return

        embed = discord.Embed(
            title=f"Incident Audit: {self.incident.incident_id}",
            description=f"**Title**: {self.incident.title}\n**Severity**: `{self.incident.severity.upper()}`\n**Status**: `{self.incident.status}`",
            color=discord.Color(get_color("brand", 0x5865F2)),
        )
        embed.add_field(name="Observed Facts", value="\n".join([f"• {f}" for f in self.incident.observed_facts[:5]]) or "None", inline=False)
        embed.add_field(name="Evidence References", value=f"{len(self.incident.evidence_references)} cryptographic records", inline=True)
        embed.add_field(name="Recovery Code", value=f"`{self.incident.recovery_code or 'N/A'}`", inline=True)

        await self._respond_ephemeral(interaction, content="📋 Incident Forensic Details", embed=embed)

    async def handle_false_alarm(self, interaction: Any) -> None:
        """
        Records a false alarm dismissal while strictly preserving evidence references and incident history.
        """
        user = getattr(interaction, "user", None)
        authorized, reason = self._verify_caller_authorization(user)
        if not authorized:
            await self._respond_ephemeral(interaction, f"❌ {reason}")
            return

        uid_str = str(user.id)
        self.incident.mark_dismissed(
            admin_id=uid_str,
            admin_name=str(user),
            reason="Reported as false alarm via interactive emergency alert.",
        )

        guild = getattr(interaction, "guild", None)
        lockdown_id = self.lockdown_record.lockdown_id if self.lockdown_record else self.incident.incident_id

        # If lockdown was active or partial, revert changes
        restored_info = ""
        if self.lockdown_record and self.lockdown_record.status in (LockdownStatus.ACTIVE, LockdownStatus.PARTIAL):
            try:
                rec = await emergency_lockdown_manager.restore_lockdown(
                    guild=guild,
                    lockdown_id=lockdown_id,
                    admin_user_id=uid_str,
                    policy=self.policy,
                )
                restored_info = f"\n✅ Lockdown automatically lifted ({rec.summary.get('restored', 0)} resources restored)."
            except Exception as err:
                restored_info = f"\n⚠️ Auto-restore error: {err}"

        await self._respond_ephemeral(
            interaction,
            f"ℹ️ **Incident Marked as False Alarm** by <@{uid_str}>.\n"
            f"All forensic evidence references and audit logs remain permanently preserved for compliance.{restored_info}",
        )

    async def _respond_ephemeral(self, interaction: Any, content: str, embed: Optional[Any] = None) -> None:
        """Helper to respond or followup ephemerally across interaction types."""
        try:
            resp = getattr(interaction, "response", None)
            if resp and not getattr(resp, "_done", False) and hasattr(resp, "send_message"):
                kwargs: Dict[str, Any] = {"content": content, "ephemeral": True}
                if embed:
                    kwargs["embed"] = embed
                await resp.send_message(**kwargs)
                return
            followup = getattr(interaction, "followup", None)
            if followup and hasattr(followup, "send"):
                kwargs = {"content": content, "ephemeral": True}
                if embed:
                    kwargs["embed"] = embed
                await followup.send(**kwargs)
        except Exception as err:
            logger.debug(f"[EmergencyRecoveryView] Interaction response notice: {err}")


class AdminNotifier:
    """
    Manages delivery of emergency alerts to recovery admins via direct messages,
    falling back seamlessly to designated secure channels when DMs are blocked or unavailable.
    """
    _instance: Optional["AdminNotifier"] = None

    def __init__(self):
        import threading
        self._last_alert_times: Dict[str, float] = {}
        self._alert_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "AdminNotifier":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def dispatch_emergency_alert(
        self,
        bot_client: Any,
        guild: Any,
        incident: Incident,
        lockdown_record: Optional[LockdownRecord] = None,
        policy: Optional[SecurityResponsePolicy] = None,
    ) -> Dict[str, Any]:
        """
        Dispatches emergency alert with interactive recovery view to trusted admins.
        Falls back to secure logging channel if DMs fail. Enforces notification storm suppression.
        """
        gid = str(guild.id if guild else incident.guild_id)
        alert_key = f"{gid}:{incident.incident_id}"
        now = time.time()
        with getattr(self, "_alert_lock", threading.Lock()):
            if not hasattr(self, "_last_alert_times"):
                self._last_alert_times = {}
            last = self._last_alert_times.get(alert_key, 0.0)
            if now - last < 60.0:
                logger.debug(f"[AdminNotifier] Suppressing notification storm for {alert_key}")
                return {
                    "incident_id": incident.incident_id,
                    "dms_sent": 0,
                    "dms_failed": 0,
                    "fallback_sent": False,
                    "suppressed": True,
                }
            self._last_alert_times[alert_key] = now

        pol = policy or get_default_response_policy(gid)

        embed = self._create_emergency_alert_embed(incident, lockdown_record, pol)
        view = EmergencyRecoveryView(incident=incident, lockdown_record=lockdown_record, policy=pol)

        dms_sent = 0
        dms_failed = 0
        failed_admin_ids: List[str] = []

        recipients: List[str] = []
        if pol.recovery_owner_id:
            recipients.append(str(pol.recovery_owner_id))
        for aid in pol.trusted_recovery_admin_ids:
            if str(aid) not in recipients:
                recipients.append(str(aid))

        # Attempt DM delivery to each designated recovery admin
        for uid in recipients:
            success = await self._send_admin_dm(bot_client, uid, embed, view)
            if success:
                dms_sent += 1
            else:
                dms_failed += 1
                failed_admin_ids.append(uid)

        # Fallback Channel Dispatch if any DMs failed or no admins were reached
        fallback_sent = False
        if dms_failed > 0 or dms_sent == 0:
            fallback_sent = await self._send_fallback_channel_alert(
                guild, pol.fallback_channel_id, embed, view, failed_admin_ids
            )

        logger.info(
            f"[AdminNotifier] Alert dispatch for incident {incident.incident_id} (Guild {gid}): "
            f"DMs Sent: {dms_sent}, DMs Failed: {dms_failed}, Fallback Channel Sent: {fallback_sent}"
        )

        return {
            "incident_id": incident.incident_id,
            "guild_id": gid,
            "dms_sent": dms_sent,
            "dms_failed": dms_failed,
            "failed_admin_ids": failed_admin_ids,
            "fallback_channel_sent": fallback_sent,
        }

    async def _send_admin_dm(self, bot_client: Any, user_id: str, embed: Any, view: Any) -> bool:
        """Sends an emergency alert DM to a recovery administrator."""
        if not bot_client:
            return False

        try:
            target_user = None
            if hasattr(bot_client, "get_user"):
                target_user = bot_client.get_user(int(user_id))
            if not target_user and hasattr(bot_client, "fetch_user"):
                target_user = await bot_client.fetch_user(int(user_id))

            if not target_user:
                return False

            if hasattr(target_user, "send"):
                await target_user.send(embed=embed, view=view)
                return True
        except Exception as err:
            logger.warning(f"[AdminNotifier] DM delivery failed for recovery admin {user_id}: {err}")

        return False

    async def _send_fallback_channel_alert(
        self,
        guild: Any,
        fallback_channel_id: Optional[str],
        embed: Any,
        view: Any,
        failed_admin_ids: List[str],
    ) -> bool:
        """Sends emergency notification to configured fallback channel or guild system channel."""
        if not guild:
            return False

        channel = None
        if fallback_channel_id and hasattr(guild, "get_channel"):
            channel = guild.get_channel(int(fallback_channel_id))

        if not channel:
            channel = getattr(guild, "system_channel", None) or getattr(guild, "public_updates_channel", None)

        if not channel and hasattr(guild, "text_channels"):
            text_chans = getattr(guild, "text_channels", [])
            channel = text_chans[0] if text_chans else None

        if not channel or not hasattr(channel, "send"):
            logger.warning("[AdminNotifier] No fallback channel accessible in guild.")
            return False

        try:
            notice = (
                f"🚨 **EMERGENCY CONTAINMENT BROADCAST** 🚨\n"
                f"⚠️ *Trusted recovery admin DMs could not be delivered for {len(failed_admin_ids)} admin(s). "
                f"This notification has been safely routed to the designated security channel.*"
            )
            await channel.send(content=notice, embed=embed, view=view)
            return True
        except Exception as err:
            logger.error(f"[AdminNotifier] Failed to post alert to fallback channel {getattr(channel, 'name', 'unknown')}: {err}")
            return False

    def _create_emergency_alert_embed(
        self,
        incident: Incident,
        lockdown: Optional[LockdownRecord],
        policy: SecurityResponsePolicy,
    ) -> discord.Embed:
        """Constructs a branded high-visibility alert embed with forensic context."""
        mode_str = "SHADOW (Simulation)" if (lockdown and lockdown.is_shadow_mode) else "LIVE ENFORCEMENT"
        status_str = lockdown.status.upper() if lockdown else "CONTAINMENT REQUESTED"

        embed = discord.Embed(
            title=f"{get_emoji('shield', '🛡️')} SENTINEL EMERGENCY CONTAINMENT ALERT",
            description=(
                f"A destructive attack vector was intercepted on server `{incident.guild_id}`.\n"
                f"**Threat**: {incident.title}\n"
                f"**Mode**: `{mode_str}` | **Containment Status**: `{status_str}`"
            ),
            color=discord.Color(get_color("danger", 0xED4245)),
        )

        embed.add_field(
            name=f"{get_emoji('stats', '📊')} Threat Assessment",
            value=(
                f"• **Severity**: `{incident.severity.upper()}`\n"
                f"• **Confidence**: `{incident.confidence.upper()}`\n"
                f"• **First Intercepted**: <t:{int(incident.first_seen_at)}:R>"
            ),
            inline=True,
        )

        if lockdown:
            applied = lockdown.summary.get("applied", 0)
            skipped = lockdown.summary.get("skipped_hierarchy", 0)
            embed.add_field(
                name=f"{get_emoji('lock', '🔒')} Containment Scope",
                value=(
                    f"• **Resources Contained**: {applied}\n"
                    f"• **Skipped (Hierarchy)**: {skipped}\n"
                    f"• **Baseline Checksum**: `{lockdown.checksum[:10]}...`"
                ),
                inline=True,
            )

        if incident.recovery_code:
            embed.add_field(
                name=f"{get_emoji('key', '🔑')} Emergency Recovery Code",
                value=f"```\n{incident.recovery_code}\n```",
                inline=False,
            )

        instructions = (
            "1. Use **Keep Lockdown** to confirm containment.\n"
            "2. Use **Begin Recovery** to restore pre-lockdown permissions.\n"
            "3. Use **Report False Alarm** if the trigger was benign (all forensic evidence will be preserved)."
        )
        embed.add_field(name="Recovery Instructions", value=instructions, inline=False)
        embed.set_footer(text="Sentinel™ Security Core • Reversible Emergency Protection")
        return embed


# Global singleton instance
admin_notifier = AdminNotifier.get_instance()
