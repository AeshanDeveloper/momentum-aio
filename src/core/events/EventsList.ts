export enum EventsList {
    // Application
    READY = "app.ready",
    STARTING = "app.starting",
    STARTED = "app.started",
    STOPPING = "app.stopping",
    SHUTDOWN = "app.shutdown",
    RELOADING = "app.reloading",

    // Plugins
    PLUGIN_REGISTERING = "plugin.registering",
    PLUGIN_REGISTERED = "plugin.registered",
    PLUGIN_LOADING = "plugin.loading",
    PLUGIN_LOADED = "plugin.loaded",
    PLUGIN_ENABLING = "plugin.enabling",
    PLUGIN_ENABLED = "plugin.enabled",
    PLUGIN_DISABLING = "plugin.disabling",
    PLUGIN_DISABLED = "plugin.disabled",
    PLUGIN_UNLOADING = "plugin.unloading",
    PLUGIN_UNLOADED = "plugin.unloaded",

    // Modules
    MODULE_REGISTERING = "module.registering",
    MODULE_REGISTERED = "module.registered",
    MODULE_LOADING = "module.loading",
    MODULE_LOADED = "module.loaded",
    MODULE_UNLOADING = "module.unloading",
    MODULE_UNLOADED = "module.unloaded",

    // Services
    SERVICE_REGISTERING = "service.registering",
    SERVICE_REGISTERED = "service.registered",
    SERVICE_STARTING = "service.starting",
    SERVICE_STARTED = "service.started",
    SERVICE_STOPPING = "service.stopping",
    SERVICE_STOPPED = "service.stopped",

    // Commands
    COMMAND_REGISTERING = "command.registering",
    COMMAND_REGISTERED = "command.registered",
    COMMAND_UNREGISTERED = "command.unregistered",

    // Listeners
    LISTENER_REGISTERING = "listener.registering",
    LISTENER_REGISTERED = "listener.registered",
    LISTENER_UNREGISTERED = "listener.unregistered",

    // Extensions
    EXTENSION_REGISTERED = "extension.registered",
    EXTENSION_LOADED = "extension.loaded",
    EXTENSION_UNLOADED = "extension.unloaded",

    // Configuration
    CONFIG_LOADING = "config.loading",
    CONFIG_LOADED = "config.loaded",
    CONFIG_RELOADED = "config.reloaded",

    // Database
    DATABASE_CONNECTING = "database.connecting",
    DATABASE_CONNECTED = "database.connected",
    DATABASE_DISCONNECTED = "database.disconnected",
    DATABASE_RECONNECTING = "database.reconnecting",

	// Between Actions
	BEFORE_PLUGIN_LOAD = "before.plugin.load",
	AFTER_PLUGIN_LOAD = "after.plugin.load",
	BEFORE_COMMAND_REGISTER = "before.command.register",
	AFTER_COMMAND_REGISTER = "after.command.register",
	BEFORE_SERVICE_START = "before.service.start",
	AFTER_SERVICE_START = "after.service.start",
	
    // Errors
    ERROR = "system.error",
    WARNING = "system.warning"
	
}