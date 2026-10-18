import type {
    ReadyPayload,
    AppStartingPayload,
    AppStartedPayload,
    AppStoppingPayload,
    AppShutdownPayload,
    AppReloadingPayload,

    PluginRegisteringPayload,
    PluginRegisteredPayload,
    PluginLoadingPayload,
    PluginLoadedPayload,
    PluginEnablingPayload,
    PluginEnabledPayload,
    PluginDisablingPayload,
    PluginDisabledPayload,
    PluginUnloadingPayload,
    PluginUnloadedPayload,

    ModuleRegisteringPayload,
    ModuleRegisteredPayload,
    ModuleLoadingPayload,
    ModuleLoadedPayload,
    ModuleUnloadingPayload,
    ModuleUnloadedPayload,

    ServiceRegisteringPayload,
    ServiceRegisteredPayload,
    ServiceStartingPayload,
    ServiceStartedPayload,
    ServiceStoppingPayload,
    ServiceStoppedPayload,

    CommandRegisteringPayload,
    CommandRegisteredPayload,
    CommandUnregisteredPayload,

    ListenerRegisteringPayload,
    ListenerRegisteredPayload,
    ListenerUnregisteredPayload,

    ExtensionRegisteredPayload,
    ExtensionLoadedPayload,
    ExtensionUnloadedPayload,

    ConfigLoadingPayload,
    ConfigLoadedPayload,
    ConfigReloadedPayload,

    DatabaseConnectingPayload,
    DatabaseConnectedPayload,
    DatabaseDisconnectedPayload,
    DatabaseReconnectingPayload,

    BeforePluginLoadPayload,
    AfterPluginLoadPayload,
    BeforeCommandRegisterPayload,
    AfterCommandRegisterPayload,
    BeforeServiceStartPayload,
    AfterServiceStartPayload,

    ErrorPayload,
    WarningPayload,
} from "./Payloads";

export interface EventMap {

    [global.EventsList.READY]: ReadyPayload;
    [global.EventsList.STARTING]: AppStartingPayload;
    [global.EventsList.STARTED]: AppStartedPayload;
    [global.EventsList.STOPPING]: AppStoppingPayload;
    [global.EventsList.SHUTDOWN]: AppShutdownPayload;
    [global.EventsList.RELOADING]: AppReloadingPayload;
    [global.EventsList.PLUGIN_REGISTERING]: PluginRegisteringPayload;
    [global.EventsList.PLUGIN_REGISTERED]: PluginRegisteredPayload;
    [global.EventsList.PLUGIN_LOADING]: PluginLoadingPayload;
    [global.EventsList.PLUGIN_LOADED]: PluginLoadedPayload;
    [global.EventsList.PLUGIN_ENABLING]: PluginEnablingPayload;
    [global.EventsList.PLUGIN_ENABLED]: PluginEnabledPayload;
    [global.EventsList.PLUGIN_DISABLING]: PluginDisablingPayload;
    [global.EventsList.PLUGIN_DISABLED]: PluginDisabledPayload;
    [global.EventsList.PLUGIN_UNLOADING]: PluginUnloadingPayload;
    [global.EventsList.PLUGIN_UNLOADED]: PluginUnloadedPayload;

    [global.EventsList.MODULE_REGISTERING]: ModuleRegisteringPayload;
    [global.EventsList.MODULE_REGISTERED]: ModuleRegisteredPayload;
    [global.EventsList.MODULE_LOADING]: ModuleLoadingPayload;
    [global.EventsList.MODULE_LOADED]: ModuleLoadedPayload;
    [global.EventsList.MODULE_UNLOADING]: ModuleUnloadingPayload;
    [global.EventsList.MODULE_UNLOADED]: ModuleUnloadedPayload;

    [global.EventsList.SERVICE_REGISTERING]: ServiceRegisteringPayload;
    [global.EventsList.SERVICE_REGISTERED]: ServiceRegisteredPayload;
    [global.EventsList.SERVICE_STARTING]: ServiceStartingPayload;
    [global.EventsList.SERVICE_STARTED]: ServiceStartedPayload;
    [global.EventsList.SERVICE_STOPPING]: ServiceStoppingPayload;
    [global.EventsList.SERVICE_STOPPED]: ServiceStoppedPayload;

[global.EventsList.COMMAND_REGISTERING]: CommandRegisteringPayload;
    [global.EventsList.COMMAND_REGISTERED]: CommandRegisteredPayload;
    [global.EventsList.COMMAND_UNREGISTERED]: CommandUnregisteredPayload;

    [global.EventsList.LISTENER_REGISTERING]: ListenerRegisteringPayload;
    [global.EventsList.LISTENER_REGISTERED]: ListenerRegisteredPayload;
    [global.EventsList.LISTENER_UNREGISTERED]: ListenerUnregisteredPayload;
    [global.EventsList.EXTENSION_REGISTERED]: ExtensionRegisteredPayload;
    [global.EventsList.EXTENSION_LOADED]: ExtensionLoadedPayload;
    [global.EventsList.EXTENSION_UNLOADED]: ExtensionUnloadedPayload;

    [global.EventsList.CONFIG_LOADING]: ConfigLoadingPayload;
    [global.EventsList.CONFIG_LOADED]: ConfigLoadedPayload;
    [global.EventsList.CONFIG_RELOADED]: ConfigReloadedPayload;
	
    [global.EventsList.DATABASE_CONNECTING]: DatabaseConnectingPayload;
    [global.EventsList.DATABASE_CONNECTED]: DatabaseConnectedPayload;
    [global.EventsList.DATABASE_DISCONNECTED]: DatabaseDisconnectedPayload;
    [global.EventsList.DATABASE_RECONNECTING]: DatabaseReconnectingPayload;

    [global.EventsList.BEFORE_PLUGIN_LOAD]: BeforePluginLoadPayload;
    [global.EventsList.AFTER_PLUGIN_LOAD]: AfterPluginLoadPayload;
    [global.EventsList.BEFORE_COMMAND_REGISTER]: BeforeCommandRegisterPayload;
    [global.EventsList.AFTER_COMMAND_REGISTER]: AfterCommandRegisterPayload;
    [global.EventsList.BEFORE_SERVICE_START]: BeforeServiceStartPayload;
    [global.EventsList.AFTER_SERVICE_START]: AfterServiceStartPayload;


    [global.EventsList.ERROR]: ErrorPayload;
    [global.EventsList.WARNING]: WarningPayload;
}

export type EventPayload<E extends keyof EventMap> = EventMap[E] & {
    event: E;
    timestamp: number;
};