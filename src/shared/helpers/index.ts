import fs from "node:fs";
import path from "path";
import { PermissionFlagsBits } from "discord.js";

const permissionNames = new Map(
    Object.entries(PermissionFlagsBits).map(([name, bit]) => [
        bit,
        name
            .replace(/([A-Z])/g, " $1")
            .replace(/^./, char => char.toUpperCase())
            .trim()
    ])
);

export function getAllFiles(dir: string): string[] {
  const entries = fs.readdirSync(dir, { withFileTypes: true });

  return entries.flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);

    return entry.isDirectory()
      ? getAllFiles(fullPath)
      : fullPath;
  });
}

export function getPermissionName(permission) {
    return permissionNames.get(permission) ?? "Unknown Permission";
}

/**
 * Check user and bot permissions.
 */
export function checkPermissions(
    member,
    botMember,
    userPerms = [],
    botPerms = []
) {
    const missingUser = userPerms.filter(
        permission => !member.permissions.has(permission)
    );

    const missingBot = botPerms.filter(
        permission => !botMember.permissions.has(permission)
    );

    return {
        allowed: missingUser.length === 0 && missingBot.length === 0,

        missingUser,
        missingBot,

        missingUserNames: missingUser.map(getPermissionName),
        missingBotNames: missingBot.map(getPermissionName),
    };
}