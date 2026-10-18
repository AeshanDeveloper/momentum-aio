import EBus from "@core/events/EventBus";
import {EventsList} from "@core/events/EventsList";
import packageJson from "../../package.json" with { type: "json" };

export {};

export interface RuntimeStats {
    startedAt: number;
    uptime: number;

    version: string;

    status: "starting" | "running" | "stopping" | "stopped";

    services: {
        total: number;
        registered: number;
		failed: number;
		disabled: number;
        started: number;
        stopped: number;
    };

    plugins: {
        total: number;
        loaded: number;
		failed: number;
        enabled: number;
        disabled: number;
    };

    modules: {
        total: number;
		failed: number;
        loaded: number;
    };

    commands: {
        total: number;
		loaded: number;
		disabled: number;
		enabled: number;
		failed: number;
    };

    listeners: {
        total: number;
    };

    extensions: {
        total: number;
    };

    database: {
        connected: boolean;
        host?: string;
        database?: string;
    };

    bot: {
        ready: boolean;
        guilds: number;
        users: number;
        ping: number; // in milliseconds
    };

    dashboard: {
        running: boolean;
        port?: number;
    };

    memory: {
        rss: number;
        heapUsed: number;
        heapTotal: number;
    };
}

declare global {
  namespace NodeJS {
    interface Global {
      APP_SECRET: string;
    }
  }
  var eBus: EBus;
      var EventsList: typeof EventsList;
  var cache: any;
  var runtime: RuntimeStats;
}

// Declarations


global.EventsList = EventsList;
global.commands = new Map()
global.cache = {
	discord: {
		guilds: new Map(),
		users: new Map()
	},
	plugins: new Map(),
	commands: {
		prefix: new Map(),
		slash: new Map(),
		hybrid: new Map(),
	}
}

global.runtime = {
    startedAt: Date.now(),
    uptime: 0,
    version: packageJson.version,
    status: "starting",
	
    services: {
        total: 0,
        registered: 0,
        started: 0,
        stopped: 0,
    },
    plugins: {
        total: 0,
        loaded: 0,
        enabled: 0,
        disabled: 0,
    },

    modules: {
        total: 0,
        loaded: 0,
    },

    commands: {
        total: 0,
    },

    listeners: {
        total: 0,
    },

    extensions: {
        total: 0,
    },

    database: {
        connected: false,
    },

    bot: {
        ready: false,
        guilds: 0,
        users: 0,
        ping: 0,
    },

    dashboard: {
        running: false,
    },

    memory: {
        rss: 0,
        heapUsed: 0,
        heapTotal: 0,
    }
};

global.eBus = new EBus();
