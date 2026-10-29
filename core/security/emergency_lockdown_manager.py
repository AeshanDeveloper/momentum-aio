"""
Sentinel™ Emergency Lockdown Manager.

Agent 5 of 8 Security Core: High-performance, policy-controlled emergency containment,
role hierarchy validation, selective dangerous permission stripping, channel lockdowns,
cryptographic baselines, conflict-free reversibility, and posture auditing.

Key capabilities:
- Fast Execution: autonomous execution upon crossing emergency threshold without human consensus.
- Idempotency & Concurrency: per-guild async locks prevent duplicate execution during concurrent bursts.
- Permission & Hierarchy Verification: Never claims complete lockdown if bot lacks permissions
  or role hierarchy prevents modifying higher roles; classifies as PARTIAL_LOCKDOWN.
- Safe Shielding: Sentinel's own roles and designated recovery roles are NEVER stripped.
- Reversibility with Conflict Avoidance: Compares current Discord state with applied state
  to detect independent post-lockdown admin edits, preserving admin intent.
- Resilient Recovery Retries: Interrupted recovery procedures resume safely without losing state.
- Posture Diagnostic Tool: Comprehensive audit of guild hierarchy, permissions, and configuration.
"""

from __future__ import annotations

import time
import asyncio
import threading
from typing import Dict, Any, List, Optional, Set, Tuple, Union, Callable

import discord
from discord import Permissions, PermissionOverwrite

from core.security.role_backup_manager import RoleBackupManager

from config.settings import settings, COLORS, EMOJIS, get_color, get_emoji
from core.logging.logger import logger
from core.security.response_policy import (
    SecurityResponsePolicy,
    ResponseLevel,
    LockdownStatus,
    LockdownTargetType,
    get_default_response_policy,
)
from core.security.lockdown_journal import (
    LockdownRecord,
    JournalEntry,
    JournalEntryStatus,
    LockdownJournalManager,
    lockdown_journal_manager,
)
from core.security.incident import (
    Incident,
    IncidentStatus,
    ProtectiveActionType,
    ActionExecutionStatus,
    PermissionSnapshot,
)
from core.security.threat_assessment import AssessmentResult


# Bitmask flags for dangerous Discord permissions
DANGEROUS_PERMISSION_FLAGS: Dict[str, int] = {
    "administrator": 1 << 3,
    "manage_guild": 1 << 5,
    "manage_roles": 1 << 28,
    "manage_channels": 1 << 4,
    "ban_members": 1 << 2,
    "kick_members": 1 << 1,
    "manage_webhooks": 1 << 29,
    "mention_everyone": 1 << 17,
}


class EmergencyLockdownManager:
    """
    Core executor of Sentinel emergency containment and reversible recovery.
    """
    _instance: Optional["EmergencyLockdownManager"] = None

    @classmethod
    def get_instance(cls) -> "EmergencyLockdownManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, journal_manager: Optional[LockdownJournalManager] = None):
        self.journal: LockdownJournalManager = journal_manager or lockdown_journal_manager
        self._guild_locks: Dict[str, asyncio.Lock] = {}
        self._sync_lock = threading.RLock()
        # Rate limiting: guild_id -> list of timestamps
        self._lockdown_history: Dict[str, List[float]] = {}

    def _get_guild_lock(self, guild_id: str) -> asyncio.Lock:
        gid = str(guild_id)
        with self._sync_lock:
            if gid not in self._guild_locks:
                self._guild_locks[gid] = asyncio.Lock()
            return self._guild_locks[gid]

    def _check_rate_limit(self, guild_id: str, max_per_minute: int) -> bool:
        """Returns True if within rate limit, False if exceeded."""
        now = time.time()
        with self._sync_lock:
            timestamps = self._lockdown_history.setdefault(str(guild_id), [])
            # Filter timestamps within last 60 seconds
            timestamps = [t for t in timestamps if now - t < 60.0]
            self._lockdown_history[str(guild_id)] = timestamps
            if len(timestamps) >= max_per_minute:
                return False
            timestamps.append(now)
            return True

    # Hierarchy and Capability Auditing
    def can_modify_role(self, bot_member: Any, role: Any) -> Tuple[bool, str]:
        """
        Validates if bot can edit permissions of a specific role according to Discord hierarchy.
        Returns (can_modify, reason).
        """
        from apps.bot.discord.permissions.resolver import evaluate_role_manageability
        can_mod, status, reason = evaluate_role_manageability(bot_member, role)
        return can_mod, reason

    def can_modify_channel_overwrites(self, bot_member: Any) -> Tuple[bool, str]:
        """Validates if bot has permissions to manage channel overwrites."""
        if not bot_member:
            return False, "Bot member context unavailable"
        bot_perms = getattr(bot_member, "guild_permissions", Permissions())
        if getattr(bot_perms, "manage_channels", False) or getattr(bot_perms, "administrator", False):
            return True, "Bot has manage_channels"
        return False, "Bot lacks manage_channels permission"

    # Emergency Lockdown Execution
    async def execute_emergency_lockdown(
        self,
        guild: Any,
        incident: Incident,
        assessment: AssessmentResult,
        policy: Optional[SecurityResponsePolicy] = None,
        progress_callback: Optional[Callable[[int, int, str], Any]] = None,
    ) -> LockdownRecord:
        """
        Executes policy-controlled emergency containment on a Discord guild.
        Guarantees idempotency, shadow mode adherence, role hierarchy safety,
        pre-lockdown snapshot persistence, and atomic journaling.
        """
        gid = str(guild.id if guild else incident.guild_id)
        lock = self._get_guild_lock(gid)

        async with lock:
            # 1. Idempotency Check: Don't execute duplicate lockdown if already active
            active_lck = self.journal.get_active_lockdown_for_guild(gid)
            if active_lck and active_lck.status in (LockdownStatus.ACTIVE, LockdownStatus.PARTIAL):
                logger.info(
                    f"[EmergencyLockdown] Guild {gid} already has an active lockdown ({active_lck.lockdown_id}). Skipping duplicate execution."
                )
                active_lck.metadata["duplicate_signal_suppressed"] = time.time()
                self.journal.save_lockdown(active_lck)
                return active_lck

            pol = policy or get_default_response_policy(gid)

            # 2. Rate limit check to prevent flapping/thrashing
            if not self._check_rate_limit(gid, pol.lockdown_rate_limit_per_minute):
                logger.warning(f"[EmergencyLockdown] Guild {gid} crossed lockdown rate limit. Throttling.")
                record = LockdownRecord(
                    guild_id=gid,
                    incident_id=incident.incident_id,
                    status=LockdownStatus.FAILED,
                    is_shadow_mode=pol.shadow_mode or not pol.auto_lockdown_enabled,
                    trigger_pattern=incident.title,
                    trigger_score=assessment.threat_score,
                    metadata={"error": "Rate limit exceeded for emergency lockdown"},
                )
                self.journal.save_lockdown(record)
                return record

            is_shadow = pol.shadow_mode or not pol.auto_lockdown_enabled

            # Initialize new LockdownRecord
            record = LockdownRecord(
                guild_id=gid,
                incident_id=incident.incident_id,
                status=LockdownStatus.ATTEMPTED,
                is_shadow_mode=is_shadow,
                trigger_pattern=incident.title,
                trigger_score=assessment.threat_score,
                metadata={
                    "policy_response_level": pol.response_level,
                    "recovery_code": incident.recovery_code,
                    "assessment_pattern": assessment.signal_id,
                },
            )

            bot_member = getattr(guild, "me", None)

            # Pre-lockdown Phase: Capture baseline snapshots and persist BEFORE modifying anything
            if progress_callback:
                try:
                    await progress_callback(1, 4, "Capturing pre-lockdown state and baseline snapshots…")
                except Exception:
                    pass

            # Persistent role backup via RoleBackupManager (64-bit lossless bitfields)
            if guild and hasattr(guild, "roles"):
                RoleBackupManager.capture_role_snapshot(
                    guild=guild,
                    roles=getattr(guild, "roles", []),
                    snapshot_id=record.lockdown_id,
                    operation="emergency_lockdown",
                )

            # Build initial journal entries with pre-lockdown baseline
            self._plan_role_containment(guild, bot_member, pol, is_shadow, record)
            self._plan_channel_containment(guild, bot_member, pol, is_shadow, record)

            # CRITICAL: Persist snapshot to database before executing destructive/restrictive changes
            record.checksum = record.calculate_checksum()
            record.updated_at = time.time()
            self.journal.save_lockdown(record)

            # Step A: Apply Selective Role Dangerous Permission Stripping
            if progress_callback:
                try:
                    await progress_callback(2, 4, "Stripping dangerous role permissions…")
                except Exception:
                    pass
            await self._execute_role_containment(guild, bot_member, pol, is_shadow, record)

            # Step B: Apply Channel & Category Overwrite Lockdown
            if progress_callback:
                try:
                    await progress_callback(3, 4, "Applying restrictive channel & category overwrites…")
                except Exception:
                    pass
            await self._execute_channel_containment(guild, bot_member, pol, is_shadow, record)

            # Determine Final Status (Partial vs Full Active / Verified)
            record.update_summary()
            is_partial = record.summary.get("is_partial", False)
            failed_count = record.summary.get("failed_api", 0)
            verified_count = record.summary.get("verified", 0)
            applied_count = record.summary.get("applied", 0)

            if is_shadow:
                record.status = LockdownStatus.ACTIVE  # In shadow mode, marked active simulation
            elif is_partial or failed_count > 0:
                record.status = LockdownStatus.PARTIAL
            elif verified_count > 0 and failed_count == 0:
                record.status = LockdownStatus.VERIFIED
            else:
                record.status = LockdownStatus.ACTIVE

            # Calculate baseline checksum
            record.checksum = record.calculate_checksum()
            record.updated_at = time.time()
            self.journal.save_lockdown(record)

            if progress_callback:
                try:
                    await progress_callback(4, 4, f"Containment {record.status.upper()} finalized.")
                except Exception:
                    pass

            # Sync with Incident aggregate
            incident.status = IncidentStatus.CONTAINED
            if is_shadow:
                action_status = ActionExecutionStatus.SIMULATED_SHADOW_MODE
            elif record.status == LockdownStatus.VERIFIED:
                action_status = ActionExecutionStatus.VERIFIED
            elif record.status == LockdownStatus.ACTIVE:
                action_status = ActionExecutionStatus.EXECUTED
            else:
                action_status = ActionExecutionStatus.ATTEMPTED

            incident.record_action(
                action_type=ProtectiveActionType.EMERGENCY_LOCKDOWN,
                status=action_status,
                is_shadow_mode=is_shadow,
                target_ids=[e.target_id for e in record.entries if e.status in (JournalEntryStatus.APPLIED, JournalEntryStatus.VERIFIED)],
                details={
                    "lockdown_id": record.lockdown_id,
                    "status": record.status,
                    "summary": record.summary,
                    "checksum": record.checksum,
                },
                snapshot_id=record.lockdown_id,
            )

            logger.info(
                f"[EmergencyLockdown] Completed lockdown {record.lockdown_id} for guild {gid} (Status: {record.status}, "
                f"Shadow: {is_shadow}, Entries: {len(record.entries)}, Applied: {applied_count}, Verified: {verified_count}, "
                f"Skipped Hierarchy: {record.summary.get('skipped_hierarchy', 0)})"
            )
            return record

    def _plan_role_containment(
        self,
        guild: Any,
        bot_member: Any,
        policy: SecurityResponsePolicy,
        is_shadow: bool,
        record: LockdownRecord,
    ) -> None:
        """Plans role containment entries and captures pre-lockdown permissions."""
        if not guild:
            return

        roles: List[Any] = getattr(guild, "roles", [])
        bot_top_role = getattr(bot_member, "top_role", None) if bot_member else None
        bot_role_ids = {r.id for r in getattr(bot_member, "roles", [])} if bot_member else set()
        if bot_top_role:
            bot_role_ids.add(bot_top_role.id)

        preserved_role_ids = {str(rid) for rid in policy.preserved_recovery_role_ids}
        target_role_ids = {str(rid) for rid in policy.target_role_ids}

        for role in roles:
            rid_str = str(role.id)

            if role.id in bot_role_ids:
                continue

            if rid_str in preserved_role_ids:
                entry = JournalEntry(
                    lockdown_id=record.lockdown_id,
                    guild_id=record.guild_id,
                    target_type="role",
                    target_id=rid_str,
                    target_name=getattr(role, "name", "Unknown"),
                    status=JournalEntryStatus.SKIPPED_PRESERVED,
                    metadata={"reason": "Designated preserved recovery role"},
                )
                record.entries.append(entry)
                continue

            is_target = False
            if target_role_ids:
                is_target = rid_str in target_role_ids
            else:
                is_default = getattr(role, "is_default", lambda: False)() or role.id == getattr(guild, "id", None)
                if is_default:
                    is_target = True
                else:
                    role_perms = getattr(role, "permissions", None)
                    perm_val = getattr(role_perms, "value", 0) if role_perms else 0
                    has_dangerous = any(
                        (perm_val & bit) != 0 for bit in DANGEROUS_PERMISSION_FLAGS.values()
                    ) or any(
                        getattr(role_perms, p, False) for p in DANGEROUS_PERMISSION_FLAGS.keys()
                    )
                    if has_dangerous:
                        is_target = True

            if not is_target:
                continue

            current_perms = getattr(role, "permissions", None)
            current_val = getattr(current_perms, "value", 0) if current_perms else 0

            mask = 0
            for perm_name in policy.dangerous_permissions:
                bit = DANGEROUS_PERMISSION_FLAGS.get(perm_name, 0)
                mask |= bit
            new_val = current_val & ~mask

            before_dict = {"permissions_value": current_val}
            applied_dict = {"permissions_value": new_val}

            entry = JournalEntry(
                lockdown_id=record.lockdown_id,
                guild_id=record.guild_id,
                target_type="role",
                target_id=rid_str,
                target_name=getattr(role, "name", "Unknown"),
                before_state=before_dict,
                applied_state=applied_dict,
                status=JournalEntryStatus.CAPTURED,
                metadata={"role_position": getattr(role, "position", 0)},
            )
            record.entries.append(entry)

    def _plan_channel_containment(
        self,
        guild: Any,
        bot_member: Any,
        policy: SecurityResponsePolicy,
        is_shadow: bool,
        record: LockdownRecord,
    ) -> None:
        """Plans channel and category containment entries and captures pre-lockdown overwrites."""
        if not guild:
            return

        # Support both channels and categories
        targets = []
        seen_ids = set()
        for cat in getattr(guild, "categories", []):
            if cat and cat.id not in seen_ids:
                targets.append(cat)
                seen_ids.add(cat.id)
        for ch in getattr(guild, "channels", []):
            if ch and ch.id not in seen_ids:
                targets.append(ch)
                seen_ids.add(ch.id)

        exempt_channels = {str(cid) for cid in policy.exempt_channel_ids}
        default_role = getattr(guild, "default_role", None)

        if not default_role:
            return

        for ch in targets:
            cid_str = str(ch.id)
            if cid_str in exempt_channels:
                continue

            overwrites = getattr(ch, "overwrites", {})
            current_ow = overwrites.get(default_role)
            had_overwrite = (current_ow is not None)

            before_dict = {"had_overwrite": had_overwrite}
            if current_ow:
                for perm_name in policy.channel_deny_permissions:
                    before_dict[perm_name] = getattr(current_ow, perm_name, None)

            applied_dict = {perm_name: False for perm_name in policy.channel_deny_permissions}

            ch_type = "category" if getattr(ch, "type", None) == 4 or hasattr(ch, "channels") else "channel"

            entry = JournalEntry(
                lockdown_id=record.lockdown_id,
                guild_id=record.guild_id,
                target_type="channel_overwrite",
                target_id=str(default_role.id),
                secondary_id=cid_str,
                target_name=f"{ch_type.capitalize()}:{getattr(ch, 'name', cid_str)}",
                before_state=before_dict,
                applied_state=applied_dict,
                status=JournalEntryStatus.CAPTURED,
                metadata={"channel_type": str(getattr(ch, "type", "text"))},
            )
            record.entries.append(entry)

    async def _execute_role_containment(
        self,
        guild: Any,
        bot_member: Any,
        policy: SecurityResponsePolicy,
        is_shadow: bool,
        record: LockdownRecord,
    ) -> None:
        """Applies planned role modifications with hierarchy checking."""
        bot_perms = getattr(bot_member, "guild_permissions", Permissions()) if bot_member else Permissions()
        bot_has_manage_roles = bool(getattr(bot_perms, "manage_roles", False) or getattr(bot_perms, "administrator", False))

        for entry in record.entries:
            if entry.target_type != "role" or entry.status != JournalEntryStatus.CAPTURED:
                continue

            role = guild.get_role(int(entry.target_id)) if hasattr(guild, "get_role") else None
            if not role:
                for r in getattr(guild, "roles", []):
                    if str(r.id) == str(entry.target_id):
                        role = r
                        break

            if not role:
                entry.status = JournalEntryStatus.FAILED_API
                entry.error = "Role not found during execution"
                continue

            can_mod, reason = self.can_modify_role(bot_member, role)
            if not can_mod or not bot_has_manage_roles:
                entry.status = JournalEntryStatus.SKIPPED_HIERARCHY
                entry.error = reason or "Bot lacks manage_roles"
                continue

            current_val = entry.before_state.get("permissions_value", 0)
            new_val = entry.applied_state.get("permissions_value", 0)

            if current_val == new_val:
                entry.status = JournalEntryStatus.SKIPPED_PRESERVED
                entry.metadata["reason"] = "Role already lacked dangerous permissions"
                continue

            if is_shadow:
                entry.status = JournalEntryStatus.SIMULATED
                entry.metadata["shadow_mode"] = True
            else:
                try:
                    new_permissions_obj = Permissions(new_val)
                    await role.edit(
                        permissions=new_permissions_obj,
                        reason=f"Sentinel Emergency Lockdown: Contained incident {record.incident_id}",
                    )
                    entry.status = JournalEntryStatus.VERIFIED
                except Exception as err:
                    entry.status = JournalEntryStatus.FAILED_API
                    entry.error = str(err)
                    logger.error(f"[EmergencyLockdown] Failed to edit role {role.name} ({entry.target_id}): {err}")

    async def _execute_channel_containment(
        self,
        guild: Any,
        bot_member: Any,
        policy: SecurityResponsePolicy,
        is_shadow: bool,
        record: LockdownRecord,
    ) -> None:
        """Applies planned channel/category modifications."""
        can_mod_chan, chan_reason = self.can_modify_channel_overwrites(bot_member)
        default_role = getattr(guild, "default_role", None)

        for entry in record.entries:
            if entry.target_type != "channel_overwrite" or entry.status != JournalEntryStatus.CAPTURED:
                continue

            cid = entry.secondary_id
            ch = None
            if hasattr(guild, "get_channel"):
                ch = guild.get_channel(int(cid))
            if not ch and hasattr(guild, "channels"):
                for c in guild.channels:
                    if str(c.id) == str(cid):
                        ch = c
                        break
            if not ch and hasattr(guild, "categories"):
                for c in guild.categories:
                    if str(c.id) == str(cid):
                        ch = c
                        break

            if not ch or not default_role:
                entry.status = JournalEntryStatus.FAILED_API
                entry.error = "Channel or default role not found during execution"
                continue

            if not can_mod_chan:
                entry.status = JournalEntryStatus.SKIPPED_HIERARCHY
                entry.error = chan_reason
                continue

            if is_shadow:
                entry.status = JournalEntryStatus.SIMULATED
                entry.metadata["shadow_mode"] = True
            else:
                try:
                    current_ow = getattr(ch, "overwrites", {}).get(default_role)
                    new_ow = PermissionOverwrite()
                    if current_ow:
                        for k, v in getattr(current_ow, "__dict__", {}).items():
                            setattr(new_ow, k, v)
                    is_voice = getattr(ch, "type", None) == 2 or isinstance(ch, getattr(discord, "VoiceChannel", ()))
                    deny_perms = list(policy.channel_deny_permissions)
                    if is_voice:
                        deny_perms.extend(["connect", "speak"])
                    for perm_name in deny_perms:
                        setattr(new_ow, perm_name, False)

                    if hasattr(ch, "set_permissions"):
                        await ch.set_permissions(
                            default_role,
                            overwrite=new_ow,
                            reason=f"Sentinel Emergency Lockdown: Channel restricted for {record.incident_id}",
                        )
                    elif hasattr(ch, "edit"):
                        cur_ows = dict(getattr(ch, "overwrites", {}))
                        cur_ows[default_role] = new_ow
                        await ch.edit(
                            overwrites=cur_ows,
                            reason=f"Sentinel Emergency Lockdown: Channel restricted for {record.incident_id}",
                        )
                    entry.status = JournalEntryStatus.VERIFIED
                except Exception as err:
                    entry.status = JournalEntryStatus.FAILED_API
                    entry.error = str(err)
                    logger.error(f"[EmergencyLockdown] Failed to set permissions on channel {getattr(ch, 'name', cid)}: {err}")

    # Reversible Recovery Execution
    async def restore_lockdown(
        self,
        guild: Any,
        lockdown_id: str,
        admin_user_id: Union[str, int],
        policy: Optional[SecurityResponsePolicy] = None,
        force: bool = False,
        progress_callback: Optional[Callable[[int, int, str], Any]] = None,
    ) -> LockdownRecord:
        """
        Reverses Sentinel's lockdown changes by restoring exact pre-lockdown baseline permissions.
        CRITICAL: Detects if an admin independently modified a role or overwrite post-lockdown.
        If a conflict is detected and force=False, Sentinel preserves the admin's changes
        and marks the entry as CONFLICT_DETECTED rather than overwriting human intent!
        """
        record = self.journal.get_lockdown(lockdown_id)
        if not record:
            raise ValueError(f"Lockdown record {lockdown_id} not found in journal")

        gid = str(guild.id if guild else record.guild_id)
        lock = self._get_guild_lock(gid)

        async with lock:
            pol = policy or get_default_response_policy(gid)
            is_shadow = record.is_shadow_mode

            logger.info(
                f"[EmergencyLockdown] Beginning recovery for lockdown {lockdown_id} on guild {gid} (Initiated by {admin_user_id}, Force: {force})"
            )

            # Explicit state transition to RESTORING
            record.status = LockdownStatus.RESTORING
            record.updated_at = time.time()
            self.journal.save_lockdown(record)

            if progress_callback:
                try:
                    await progress_callback(1, 3, "Validating baseline permissions and conflict status…")
                except Exception:
                    pass

            restored_count = 0
            conflict_count = 0
            failed_count = 0

            # Process entries for restoration
            eligible_entries = [
                e for e in record.entries
                if e.status in (JournalEntryStatus.APPLIED, JournalEntryStatus.VERIFIED, JournalEntryStatus.FAILED_RESTORE)
                or (force and e.status == JournalEntryStatus.CONFLICT_DETECTED)
            ]

            total_entries = max(1, len(eligible_entries))
            current_idx = 0

            for entry in eligible_entries:
                current_idx += 1
                if entry.target_type == "role":
                    res_status, err = await self._restore_role_entry(guild, entry, is_shadow, force)
                elif entry.target_type == "channel_overwrite":
                    res_status, err = await self._restore_channel_entry(guild, entry, is_shadow, force)
                else:
                    res_status, err = JournalEntryStatus.SKIPPED_PRESERVED, "Unknown target type"

                entry.status = res_status
                if err:
                    entry.error = err

                if res_status == JournalEntryStatus.RESTORED:
                    entry.restored_at = time.time()
                    restored_count += 1
                elif res_status == JournalEntryStatus.CONFLICT_DETECTED:
                    conflict_count += 1
                elif res_status == JournalEntryStatus.FAILED_RESTORE:
                    failed_count += 1

                if progress_callback and current_idx % 5 == 0:
                    try:
                        await progress_callback(2, 3, f"Restoring permissions… ({current_idx}/{total_entries})")
                    except Exception:
                        pass

            # Update record status
            record.update_summary()
            if conflict_count > 0 and restored_count == 0:
                record.status = LockdownStatus.OVERRIDDEN_BY_ADMIN
            elif failed_count > 0:
                record.status = LockdownStatus.PARTIAL
            else:
                record.status = LockdownStatus.RESTORED

            record.restored_at = time.time()
            record.restored_by = str(admin_user_id)
            record.updated_at = time.time()
            self.journal.save_lockdown(record)

            if progress_callback:
                try:
                    await progress_callback(3, 3, f"Recovery {record.status.upper()} finalized.")
                except Exception:
                    pass

            logger.info(
                f"[EmergencyLockdown] Recovery completed for {lockdown_id}. Result: {record.status} "
                f"(Restored: {restored_count}, Conflicts Preserved: {conflict_count}, Failed: {failed_count})"
            )
            return record

    async def _restore_role_entry(
        self,
        guild: Any,
        entry: JournalEntry,
        is_shadow: bool,
        force: bool,
    ) -> Tuple[str, Optional[str]]:
        """Restores a role entry with post-lockdown conflict detection and missing role detection."""
        if not guild:
            return JournalEntryStatus.RESTORED, None

        role = guild.get_role(int(entry.target_id)) if hasattr(guild, "get_role") else None
        if not role:
            # Fallback search
            for r in getattr(guild, "roles", []):
                if str(r.id) == str(entry.target_id):
                    role = r
                    break

        if not role:
            return JournalEntryStatus.FAILED_RESTORE, f"Role {entry.target_id} no longer exists in guild (deleted)"

        # Read current state
        current_perms = getattr(role, "permissions", None)
        current_val = getattr(current_perms, "value", 0) if current_perms else 0
        entry.current_state = {"permissions_value": current_val}

        applied_val = entry.applied_state.get("permissions_value")
        if applied_val is None:
            applied_val = entry.applied_state.get("permissions")

        before_val = entry.before_state.get("permissions_value")
        if before_val is None:
            before_val = entry.before_state.get("permissions")

        # Conflict Detection:
        # If current state != what Sentinel applied, an admin modified it independently post-lockdown!
        if applied_val is not None and current_val != applied_val and not force:
            logger.warning(
                f"[EmergencyLockdown] Conflict detected for role {role.name} ({role.id}): "
                f"Current={current_val}, Applied={applied_val}. Preserving admin changes."
            )
            return JournalEntryStatus.CONFLICT_DETECTED, "Independent admin changes detected post-lockdown"

        entry.restored_state = {"permissions_value": before_val}

        if is_shadow or before_val is None:
            return JournalEntryStatus.RESTORED, None

        try:
            new_permissions_obj = Permissions(before_val)
            await role.edit(
                permissions=new_permissions_obj,
                reason=f"Sentinel Recovery: Restored baseline permissions for lockdown {entry.lockdown_id}",
            )
            return JournalEntryStatus.RESTORED, None
        except Exception as err:
            logger.error(f"[EmergencyLockdown] Failed to restore role {role.name}: {err}")
            return JournalEntryStatus.FAILED_RESTORE, str(err)

    async def _restore_channel_entry(
        self,
        guild: Any,
        entry: JournalEntry,
        is_shadow: bool,
        force: bool,
    ) -> Tuple[str, Optional[str]]:
        """Restores a channel overwrite entry with conflict detection, had_overwrite handling, and missing channel detection."""
        if not guild or not entry.secondary_id:
            return JournalEntryStatus.RESTORED, None

        cid = entry.secondary_id
        ch = None
        if hasattr(guild, "get_channel"):
            ch = guild.get_channel(int(cid))
        if not ch and hasattr(guild, "channels"):
            for c in guild.channels:
                if str(c.id) == str(cid):
                    ch = c
                    break
        if not ch and hasattr(guild, "categories"):
            for c in guild.categories:
                if str(c.id) == str(cid):
                    ch = c
                    break

        if not ch:
            return JournalEntryStatus.FAILED_RESTORE, f"Channel {entry.secondary_id} no longer exists in guild (deleted)"

        target_obj = guild.get_role(int(entry.target_id)) if hasattr(guild, "get_role") else None
        if not target_obj:
            target_obj = getattr(guild, "default_role", None)

        if not target_obj:
            return JournalEntryStatus.FAILED_RESTORE, f"Target role {entry.target_id} no longer exists in guild"

        # Read current overwrite
        overwrites = getattr(ch, "overwrites", {})
        current_ow = overwrites.get(target_obj)
        current_dict = {}
        if current_ow:
            for k in entry.applied_state.keys():
                current_dict[k] = getattr(current_ow, k, None)
        entry.current_state = current_dict

        # Conflict check: did someone manually change these specific keys post-lockdown?
        if not force and entry.applied_state:
            has_conflict = False
            had_ow_initially = entry.before_state.get("had_overwrite", True)
            if not had_ow_initially and current_ow is None:
                has_conflict = False
            elif current_ow is not None:
                for k, applied_v in entry.applied_state.items():
                    cur_v = current_dict.get(k)
                    if cur_v != applied_v:
                        has_conflict = True
                        break
            if has_conflict:
                logger.warning(
                    f"[EmergencyLockdown] Conflict detected for channel overwrite on {getattr(ch, 'name', cid)}. Preserving admin changes."
                )
                return JournalEntryStatus.CONFLICT_DETECTED, "Independent admin changes detected on channel overwrite"

        entry.restored_state = entry.before_state

        if is_shadow:
            return JournalEntryStatus.RESTORED, None

        had_overwrite = entry.before_state.get("had_overwrite", True)

        try:
            if not had_overwrite:
                # Channel originally had NO overwrite for default_role: clear overwrite completely!
                if hasattr(ch, "set_permissions"):
                    await ch.set_permissions(
                        target_obj,
                        overwrite=None,
                        reason=f"Sentinel Recovery: Cleared lockdown overwrite for {entry.lockdown_id}",
                    )
                elif hasattr(ch, "edit"):
                    cur_ows = dict(getattr(ch, "overwrites", {}))
                    cur_ows.pop(target_obj, None)
                    await ch.edit(
                        overwrites=cur_ows,
                        reason=f"Sentinel Recovery: Cleared lockdown overwrite for {entry.lockdown_id}",
                    )
                if hasattr(ch, "overwrites") and isinstance(ch.overwrites, dict):
                    ch.overwrites.pop(target_obj, None)
            else:
                # Channel originally had an overwrite: restore original settings
                new_ow = current_ow or PermissionOverwrite()
                for k, before_v in entry.before_state.items():
                    if k not in ("had_overwrite", "channel_type", "name"):
                        setattr(new_ow, k, before_v)

                if hasattr(ch, "set_permissions"):
                    await ch.set_permissions(
                        target_obj,
                        overwrite=new_ow,
                        reason=f"Sentinel Recovery: Restored channel permissions for lockdown {entry.lockdown_id}",
                    )
                elif hasattr(ch, "edit"):
                    cur_ows = dict(getattr(ch, "overwrites", {}))
                    cur_ows[target_obj] = new_ow
                    await ch.edit(
                        overwrites=cur_ows,
                        reason=f"Sentinel Recovery: Restored channel permissions for lockdown {entry.lockdown_id}",
                    )
                if hasattr(ch, "overwrites") and isinstance(ch.overwrites, dict):
                    ch.overwrites[target_obj] = new_ow
            return JournalEntryStatus.RESTORED, None
        except Exception as err:
            logger.error(f"[EmergencyLockdown] Failed to restore channel overwrite on {getattr(ch, 'name', cid)}: {err}")
            return JournalEntryStatus.FAILED_RESTORE, str(err)

    # Diagnostic & Posture Auditing
    def audit_guild_security_posture(
        self,
        guild: Any,
        policy: Optional[SecurityResponsePolicy] = None,
    ) -> Dict[str, Any]:
        """
        Performs a full security diagnostic audit on a Discord server.
        Detects role hierarchy weaknesses, missing bot permissions, dangerous defaults,
        and provides an actionable setup checklist.
        """
        gid = str(guild.id if guild else "0")
        pol = policy or get_default_response_policy(gid)
        bot_member = getattr(guild, "me", None)

        findings: List[Dict[str, Any]] = []
        is_ready = True

        # 1. Bot Guild Permissions Check
        required_perms = ["manage_roles", "manage_channels", "view_audit_log"]
        bot_perms = getattr(bot_member, "guild_permissions", Permissions()) if bot_member else Permissions()

        for perm in required_perms:
            has_perm = bool(getattr(bot_perms, perm, False) or getattr(bot_perms, "administrator", False))
            if not has_perm:
                is_ready = False
                findings.append({
                    "check": f"Bot Permission: {perm}",
                    "status": "CRITICAL",
                    "passed": False,
                    "detail": f"Bot lacks `{perm}` permission. Emergency containment cannot modify affected resources.",
                    "remediation": f"Grant `{perm}` to Sentinel's role in Server Settings -> Roles.",
                })
            else:
                findings.append({
                    "check": f"Bot Permission: {perm}",
                    "status": "PASS",
                    "passed": True,
                    "detail": f"Bot has `{perm}` verified.",
                })

        # 2. Bot Role Hierarchy Check
        bot_top_role = getattr(bot_member, "top_role", None) if bot_member else None
        roles: List[Any] = getattr(guild, "roles", [])

        if not bot_top_role:
            is_ready = False
            findings.append({
                "check": "Bot Role Assigned",
                "status": "CRITICAL",
                "passed": False,
                "detail": "Sentinel has no assigned roles with hierarchy position.",
                "remediation": "Assign Sentinel an elevated bot role.",
            })
        else:
            higher_dangerous_roles = []
            for r in roles:
                if r.position > bot_top_role.position:
                    r_perms = getattr(r, "permissions", None)
                    perm_val = getattr(r_perms, "value", 0) if r_perms else 0
                    has_dangerous = any(
                        (perm_val & bit) != 0 for bit in DANGEROUS_PERMISSION_FLAGS.values()
                    ) or any(
                        getattr(r_perms, p, False) for p in DANGEROUS_PERMISSION_FLAGS.keys()
                    )
                    if has_dangerous:
                        higher_dangerous_roles.append(r.name)


            if higher_dangerous_roles:
                findings.append({
                    "check": "Role Hierarchy Containment Power",
                    "status": "WARNING",
                    "passed": False,
                    "detail": f"{len(higher_dangerous_roles)} roles with dangerous permissions are positioned higher than Sentinel: {', '.join(higher_dangerous_roles[:5])}.",
                    "remediation": "Drag Sentinel's role higher in Server Settings -> Roles so it can contain compromised roles.",
                })
            else:
                findings.append({
                    "check": "Role Hierarchy Containment Power",
                    "status": "PASS",
                    "passed": True,
                    "detail": "Sentinel is positioned above administrative roles.",
                })

        # 3. Default @everyone Role Audit
        default_role = getattr(guild, "default_role", None)
        if default_role:
            def_perms = getattr(default_role, "permissions", None)
            def_val = getattr(def_perms, "value", 0) if def_perms else 0
            dangerous_in_everyone = [
                name for name, bit in DANGEROUS_PERMISSION_FLAGS.items() if (def_val & bit) != 0
            ]
            if dangerous_in_everyone:
                findings.append({
                    "check": "@everyone Role Security",
                    "status": "CRITICAL",
                    "passed": False,
                    "detail": f"@everyone possesses administrative privileges: {', '.join(dangerous_in_everyone)}.",
                    "remediation": "Remove dangerous permissions from @everyone immediately.",
                })
            else:
                findings.append({
                    "check": "@everyone Role Security",
                    "status": "PASS",
                    "passed": True,
                    "detail": "@everyone role contains no dangerous administrative permissions.",
                })

        # 4. Recovery Path Audit
        has_owner = bool(pol.recovery_owner_id or getattr(guild, "owner_id", None))
        has_admins = len(pol.trusted_recovery_admin_ids) > 0
        if not has_owner and not has_admins:
            findings.append({
                "check": "Designated Recovery Authority",
                "status": "WARNING",
                "passed": False,
                "detail": "No recovery owner or trusted recovery admins configured in policy.",
                "remediation": "Configure recovery_owner_id and trusted_recovery_admin_ids to establish an unlocking pathway.",
            })
        else:
            findings.append({
                "check": "Designated Recovery Authority",
                "status": "PASS",
                "passed": True,
                "detail": f"Recovery path configured (Owner: {pol.recovery_owner_id or getattr(guild, 'owner_id', None)}, Admins: {len(pol.trusted_recovery_admin_ids)}).",
            })

        # 5. Shadow Mode & Auto Lockdown Status
        mode_str = "SHADOW (Simulation Only)" if pol.shadow_mode or not pol.auto_lockdown_enabled else "LIVE ENFORCEMENT"
        findings.append({
            "check": "Containment Mode",
            "status": "INFO",
            "passed": True,
            "detail": f"Current enforcement mode: {mode_str}. Auto-lockdown: {'Enabled' if pol.auto_lockdown_enabled else 'Disabled (Safe Shadow)'}.",
        })

        # 6. Detailed Dangerous Role Permissions Breakdown
        dangerous_roles_breakdown = []
        for r in roles:
            if r.is_default() or getattr(r, "managed", False):
                continue
            r_perms = getattr(r, "permissions", None)
            perm_val = getattr(r_perms, "value", 0) if r_perms else 0
            held_dangerous = []
            for p_name, bit in DANGEROUS_PERMISSION_FLAGS.items():
                if (perm_val & bit) != 0 or getattr(r_perms, p_name, False):
                    held_dangerous.append(p_name)
            
            if held_dangerous:
                can_mod, mod_reason = self.can_modify_role(bot_member, r)
                is_crit = ("administrator" in held_dangerous or "manage_roles" in held_dangerous) and not can_mod
                sev = "CRITICAL" if is_crit else ("HIGH" if not can_mod else "MEDIUM")
                dangerous_roles_breakdown.append({
                    "role_id": str(r.id),
                    "role_name": r.name,
                    "position": r.position,
                    "dangerous_permissions": held_dangerous,
                    "can_manage": can_mod,
                    "reason": mod_reason,
                    "severity": sev,
                    "remediation": f"Move Sentinel above '{r.name}' to contain it" if not can_mod else "Verify legitimate staff assignment",
                })

        # Compute Numeric Posture Score (0 - 100)
        score = 100
        for f in findings:
            if f.get("status") == "CRITICAL" and not f.get("passed", False):
                score -= 20
            elif f.get("status") == "WARNING" and not f.get("passed", False):
                score -= 10

        # Deduct for unmanageable dangerous roles
        unmanageable_count = sum(1 for dr in dangerous_roles_breakdown if not dr["can_manage"])
        score -= min(25, unmanageable_count * 8)

        if pol.shadow_mode:
            score -= 5

        score = max(0, min(100, score))
        if score >= 90:
            grade = "A"
        elif score >= 75:
            grade = "B"
        elif score >= 60:
            grade = "C"
        elif score >= 40:
            grade = "D"
        else:
            grade = "F"

        is_secure = is_ready and score >= 75 and not any(f["status"] == "CRITICAL" for f in findings)
        overall = "SECURE" if is_secure else "ACTION_REQUIRED"

        return {
            "guild_id": gid,
            "guild_name": getattr(guild, "name", "Unknown Server"),
            "audit_timestamp": time.time(),
            "overall_posture": overall,
            "score": score,
            "max_score": 100,
            "grade": grade,
            "findings": findings,
            "dangerous_roles": dangerous_roles_breakdown,
            "checklist": [
                {
                    "item": f["check"],
                    "passed": f.get("passed", False),
                    "status": f["status"],
                    "remediation": f.get("remediation"),
                }
                for f in findings
            ],
        }


# Global singleton instance
emergency_lockdown_manager = EmergencyLockdownManager.get_instance()
