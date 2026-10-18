# MomentumOne Control Platform

Enterprise-grade modular Discord platform, administrative control center, and plugin engine converted to Python.

## Architecture

- **Core Engine (`python/core/`)**:
  - `container`: IoC container for dependency injection and service resolution.
  - `events`: Synchronous and asynchronous pub/sub `EventBus`.
  - `security`: `BlacklistManager`, `AntiSpamService` (sliding window), `CooldownManager` (user/guild/global scopes), `NoPrefixManager`, `ServerCommandManager`.
  - `logging`: Formatted logging and `ErrorTracker` exception diagnostics.
  - `telemetry`: `ObservabilityManager` and `DiscordTelemetry` monitoring latency and command invocations.
  - `audit`: `AuditLog` with sensitive key redaction and state diff tracking.
  - `plugins`: Dynamic plugin loader, manifest validator, and lifecycle management.

- **Localization (`Strings.json` & `python/Strings.json`)**:
  - Centralized messaging for system notifications, permissions, antispam, cooldowns, and all bot commands.

- **Storage (`python/database/`)**:
  - `DatabaseManager` supporting MongoDB (via Motor/PyMongo) and automatic in-memory / local JSON store fallback for zero-configuration development.

- **Discord SDK & Bot (`python/sdk/` & `python/apps/bot/`)**:
  - Fluid builders (`ContainerBuilder`, `ActionRowBuilder`, `ButtonBuilder`, `SelectMenuBuilder`).
  - Bitwise and guild permissions resolver (`check_permissions`).
  - Support ticket lifecycle manager (`TicketManager`) with channel creation and transcript generation.

- **Web Dashboard & REST API (`python/apps/api/`)**:
  - Listens on `0.0.0.0:3000` serving the editorial control center dashboard and complete `/api/*` endpoints.

## Running

```bash
# Start the platform
python3 main.py

# Run tests
python3 tests/test_python_framework.py
```