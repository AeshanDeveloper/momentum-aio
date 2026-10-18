# Cache Structure

global.cache = {
    discord: {
        guilds: new Map(),
        channels: new Map(),
        members: new Map(),
        roles: new Map(),
        emojis: new Map(),
        voice: new Map(),
    },

    users: {
        profiles: new Map(),
        permissions: new Map(),
        sessions: new Map(),
    },

    plugins: {
        metadata: new Map(),
        instances: new Map(),
        commands: new Map(),
        events: new Map(),
    },

    web: {
        sessions: new Map(),
        csrf: new Map(),
        rateLimits: new Map(),
    },

    api: {
        responses: new Map(),
        tokens: new Map(),
    },

    database: {
        preparedStatements: new Map(),
        queryResults: new Map(),
    },

    system: {
        config: new Map(),
        metrics: new Map(),
        locks: new Map(),
    },
};