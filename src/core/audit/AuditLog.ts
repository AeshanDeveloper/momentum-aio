import { randomUUID } from "crypto";

import DatabaseManager from "@database/Database";

export type AuditActorType = "dashboard" | "discord" | "api" | "bot" | "plugin" | "system";
export type AuditSource = AuditActorType | "automation";

export interface AuditLogEntry {
  auditId: string;
  guildId?: string;
  actorId?: string;
  actorType: AuditActorType;
  action: string;
  resourceType: string;
  resourceId?: string;
  previousState?: unknown;
  newState?: unknown;
  changedFields?: string[];
  timestamp: Date;
  source: AuditSource;
  requestId?: string;
  ip?: string;
  success: boolean;
  error?: string;
}

const SENSITIVE_KEYS = /token|secret|password|credential|api[-_]?key|private[-_]?key/i;

function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redact);
  if (!value || typeof value !== "object") return value;

  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, child]) => [
      key,
      SENSITIVE_KEYS.test(key) ? "[REDACTED]" : redact(child),
    ])
  );
}

function changedFields(previousState: unknown, newState: unknown): string[] {
  if (!previousState || !newState || typeof previousState !== "object" || typeof newState !== "object") return [];
  const keys = new Set([...Object.keys(previousState), ...Object.keys(newState)]);
  return [...keys].filter((key) => JSON.stringify((previousState as Record<string, unknown>)[key]) !== JSON.stringify((newState as Record<string, unknown>)[key]));
}

export default class AuditLog {
  private static readonly COLLECTION = "audit_logs";

  static async record(input: Omit<AuditLogEntry, "auditId" | "timestamp" | "changedFields" | "previousState" | "newState"> & { previousState?: unknown; newState?: unknown }): Promise<AuditLogEntry> {
    const entry: AuditLogEntry = {
      ...input,
      auditId: randomUUID(),
      previousState: redact(input.previousState),
      newState: redact(input.newState),
      changedFields: changedFields(input.previousState, input.newState),
      timestamp: new Date(),
    };

    await DatabaseManager.insertOne(this.COLLECTION, entry);
    return entry;
  }

  static async list(filter: Record<string, unknown> = {}, skip = 0, limit = 50): Promise<AuditLogEntry[]> {
    return DatabaseManager.find<AuditLogEntry>(this.COLLECTION, filter, {
      sort: { timestamp: -1 },
      skip: Math.max(0, skip),
      limit: Math.min(100, Math.max(1, limit)),
    });
  }

  static async count(filter: Record<string, unknown> = {}): Promise<number> {
    return DatabaseManager.count(this.COLLECTION, filter);
  }

  static async initialize(): Promise<void> {
    await DatabaseManager.createIndex(this.COLLECTION, { guildId: 1, timestamp: -1 });
    await DatabaseManager.createIndex(this.COLLECTION, { resourceType: 1, resourceId: 1, timestamp: -1 });
    await DatabaseManager.createIndex(this.COLLECTION, { actorId: 1, timestamp: -1 });
  }
}

export { redact };
