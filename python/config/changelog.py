from typing import List, Dict, Any, Optional

CHANGELOG_RELEASES: List[Dict[str, Any]] = [
    {
        "version": "26.7.21",
        "codename": "Interactive Component Forge",
        "releasedAt": "2026-10-18",
        "headline": "Interactive ContainerBuilder SDK, 4-button help pagination, and server command management panel.",
        "summary": "Full interactive Discord component parity with fluid containers, pagination collectors, and server command quick-toggling.",
        "features": [
            "Interactive ContainerBuilder SDK: Action rows, button builders, select menus, and message component collectors.",
            "Dynamic Help Browser: 4-button pagination (⏮️, ◀️, ▶️, ⏭️), category views, and fuzzy search suggestions.",
            "Command Management Panel: Server-level command status tables and quick toggle select menus.",
            "Dashboard Multi-Server Sync: Live server selector, invite link generator, and admin auth session handling."
        ],
        "bugFixes": [
            "Resolved ReferenceError in frontend initAuth handler.",
            "Fixed callback wiring for message component interaction collectors."
        ]
    },
    {
        "version": "26.7.20",
        "codename": "Architectural Harmony",
        "releasedAt": "2026-10-18",
        "headline": "Full Modular Python port, robust TTL caching, centralized Strings.json, ticket automation, and multi-server administration.",
        "summary": "Enterprise-grade release featuring full framework conversion to Python, high-throughput caching, complete permission resolvers, error tracking, and secure ticket management.",
        "features": [
            "Modular Python Architecture: Rebuilt container, plugin manager, event bus, and security layers in pure Python.",
            "Centralized Strings Directory: All conversational and system messaging localized into Strings.json with dot-path resolution.",
            "Advanced Multi-Scope Cooldowns: User, guild, and global rate limit scopes with duration parsing.",
            "Automated Ticket Life Cycle: Support ticket dispatch, channel management, transcript archiving, and administrative overrides.",
            "Comprehensive Observability: Metric tracking, error logging, and cluster diagnostics.",
        ],
        "bugFixes": [
            "Fixed Discord permission bitwise calculations across custom role hierarchy.",
            "Hardened anti-spam sliding window against high-frequency socket bursts.",
            "Corrected TTL cache memory pruning during background synchronization.",
        ]
    },
    {
        "version": "26.6.0",
        "codename": "Security Sentinel",
        "releasedAt": "2026-09-15",
        "headline": "Global blacklist management, no-prefix authorizations, and sliding-window rate limiters.",
        "summary": "Strengthened core security foundations with owner-exempt blacklists, temporary durations, and granular audit trails.",
        "features": [
            "Central Global Blacklist with duration parsing ('1d', '1w', 'permanent').",
            "Sliding Window Anti-Spam protection with automated temporary blacklisting.",
            "No-Prefix authorization manager for designated power users.",
        ],
        "bugFixes": [
            "Fixed race conditions in async event bus execution.",
        ]
    }
]

def get_latest_release() -> Dict[str, Any]:
    return CHANGELOG_RELEASES[0]

def get_previous_release() -> Optional[Dict[str, Any]]:
    return CHANGELOG_RELEASES[1] if len(CHANGELOG_RELEASES) > 1 else None
