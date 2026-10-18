type BasePayload = {
  executor: "system" | "pluginSystem" | "database" | "autoLoader" | "botManager" | "unknown";
};

export interface ReadyPayload extends BasePayload {
    startupTime: number;
    uptime: number;
    pluginsLoaded: number;
    modulesLoaded: number;
    servicesStarted: number;
}

export interface AppStartingPayload extends BasePayload {
  version: string;
  app: string;
}

export interface AppStartedPayload extends BasePayload {
  duration: number;
  pluginsLoaded: number;
  modulesLoaded: number;
  servicesStarted: number;
  memoryUsage: NodeJS.MemoryUsage;
  app: string;
}

export interface AppStoppingPayload extends BasePayload {
  reason: string;
  uptime: number;
  app: string
}

export interface PluginRegisteringPayload extends BasePayload {
  pluginId: string;
  name: string;
  version: string;
  author: string;
  path: string;
}

export interface PluginRegisteredPayload extends BasePayload {
  pluginId: string;
  name: string;
  version: string;
  loadTime: number;
}

export interface PluginEnabledPayload extends BasePayload {
  pluginId: string;
  name: string;
}

export interface PluginDisabledPayload extends BasePayload {
  pluginId: string;
  name: string;
  reason?: string;
}

export interface PluginErrorPayload extends BasePayload {
  pluginId: string;
  name: string;
  error: Error;
}

export interface ServiceStartingPayload extends BasePayload {
  service: string;
}

export interface ServiceStartedPayload extends BasePayload {
  service: string;
  duration: number;
}

export interface ServiceStoppedPayload extends BasePayload {
  service: string;
  uptime: number;
}

export interface ModuleLoadingPayload extends BasePayload {
  module: string;
}

export interface ModuleLoadedPayload extends BasePayload {
  module: string;
  duration: number;
}

export interface ModuleErrorPayload extends BasePayload {
  module: string;
  error: Error;
}

export interface DatabaseConnectingPayload extends BasePayload {
  host: string;
  database: string;
}

export interface DatabaseConnectedPayload extends BasePayload {
  host: string;
  database: string;
  duration: number;
}

export interface DatabaseDisconnectedPayload extends BasePayload {
  reason?: string;
}

export interface DatabaseQueryPayload extends BasePayload {
  query: string;
  duration: number;
  affectedRows?: number;
}

export interface CacheHitPayload extends BasePayload {
  key: string;
}

export interface CacheMissPayload extends BasePayload {
  key: string;
}

export interface CacheSetPayload extends BasePayload {
  key: string;
  ttl?: number;
}

export interface CommandExecutingPayload extends BasePayload {
  command: string;
  userId: string;
  guildId?: string;
  channelId?: string;
}

export interface CommandExecutedPayload extends BasePayload {
  command: string;
  duration: number;
  success: boolean;
}

export interface EventPublishedPayload extends BasePayload {
  event: string;
  listeners: number;
}

export interface EventHandledPayload extends BasePayload {
  event: string;
  duration: number;
}

export interface ErrorPayload extends BasePayload {
  error: Error;
  fatal: boolean;
}

export interface ReadyPayload extends BasePayload {}

export interface AppReloadingPayload extends BasePayload {
    reason: string;
}

export interface AppShutdownPayload extends BasePayload {
    uptime: number;
    reason?: string;
}


export interface ModuleRegisteringPayload extends BasePayload {
    moduleId: string;
    name: string;
}

export interface ModuleRegisteredPayload extends BasePayload {
    moduleId: string;
    name: string;
    duration: number;
}

export interface ModuleUnloadingPayload extends BasePayload {
    moduleId: string;
    name: string;
}

export interface ModuleUnloadedPayload extends BasePayload {
    moduleId: string;
    name: string;
    duration: number;
}

export interface ServiceRegisteringPayload extends BasePayload {
    serviceId: string;
    name: string;
}

export interface ServiceRegisteredPayload extends BasePayload {
    serviceId: string;
    name: string;
    duration: number;
}

export interface ServiceStoppingPayload extends BasePayload {
    serviceId: string;
    name: string;
}

export interface ServiceStoppedPayload extends BasePayload {
    serviceId: string;
    name: string;
    duration: number;
}

export interface CommandRegisteringPayload extends BasePayload {
    commandId: string;
    name: string;
}

export interface CommandRegisteredPayload extends BasePayload {
    commandId: string;
    name: string;
    duration: number;
}

export interface CommandUnregisteredPayload extends BasePayload {
    commandId: string;
    name: string;
}

export interface ListenerRegisteringPayload extends BasePayload {
    listenerId: string;
    event: string;
}

export interface ListenerRegisteredPayload extends BasePayload {
    listenerId: string;
    event: string;
    duration: number;
}

export interface ListenerUnregisteredPayload extends BasePayload {
    listenerId: string;
    event: string;
}


export interface ExtensionRegisteredPayload extends BasePayload {
    extensionId: string;
    name: string;
}

export interface ExtensionLoadedPayload extends BasePayload {
    extensionId: string;
    name: string;
    duration: number;
}

export interface ExtensionUnloadedPayload extends BasePayload {
    extensionId: string;
    name: string;
    duration: number;
}

export interface ConfigLoadingPayload extends BasePayload {
    file: string;
}

export interface ConfigLoadedPayload extends BasePayload {
    file: string;
    duration: number;
}

export interface ConfigReloadedPayload extends BasePayload {
    file: string;
    duration: number;
}


export interface DatabaseReconnectingPayload extends BasePayload {
    attempt: number;
}

export interface BeforePluginLoadPayload extends BasePayload {
    pluginId: string;
    name: string;
    version: string;
    path: string;
}

export interface AfterPluginLoadPayload extends BasePayload {
    pluginId: string;
    name: string;
    version: string;
    path: string;
    duration: number;
    success: boolean;
}

export interface BeforeCommandRegisterPayload extends BasePayload {
    commandId: string;
    name: string;
    description: string;
    aliases: string[];
}

export interface AfterCommandRegisterPayload extends BasePayload {
    commandId: string;
    name: string;
    description: string;
    aliases: string[];
    duration: number;
    success: boolean;
}

export interface BeforeServiceStartPayload extends BasePayload {
    serviceId: string;
    name: string;
}

export interface AfterServiceStartPayload extends BasePayload {
    serviceId: string;
    name: string;
    duration: number;
    success: boolean;
}

export interface WarningPayload extends BasePayload {
    message: string;
    warningCode?: string;
}