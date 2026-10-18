import logger from "@logger";
import config from "@config";
import database from "@database/Database";
import { Client } from "discord.js";
import path from "node:path";
import crypto from "node:crypto";
import fs from "node:fs/promises";
import pluginsModel from "@database/models/plugins"
import { pathToFileURL } from "url";
import PluginContext from "@core/plugins/PluginContext"
import AutoLoader from "@sdk/AutoLoader";
import AuditLog from "@core/audit/AuditLog";


interface PluginManifest {
    name: string;
    description?: string;
    version: string;
    author: string;
    repositoryUrl?: string;
    requiredMomentumOneVersion?: string;
    main: string;
	path: string;
    
}

export default class PluginManager {
	client: Client;
	pluginsDirectory = path.resolve("src", "plugins");
	constructor(client){
		this.client = client;
		runtime.services.started++;
		runtime.services.total++;
	}
	
		async enable (data: {id: string}){
			const previous = (await pluginsModel.getAll()).find((plugin) => plugin.pluginId === data.id);
			await pluginsModel.setEnabled(data.id, true);
			void AuditLog.record({
				actorType: "system",
				source: "automation",
				action: "plugin.enabled",
				resourceType: "plugin",
				resourceId: data.id,
				previousState: { enabled: previous?.enabled },
				newState: { enabled: true },
				success: true,
			});
		}
	
		async enableAll(){
			const plugins = await pluginsModel.getAll();
			for (const plugin of plugins) {
				if (!plugin) continue;
				await pluginsModel.setEnabled(plugin.pluginId, true);
				void AuditLog.record({
					actorType: "system",
					source: "automation",
					action: "plugin.enabled",
					resourceType: "plugin",
					resourceId: plugin.pluginId,
					previousState: { enabled: plugin.enabled },
					newState: { enabled: true },
					success: true,
				});
			}
		}
		
		async disable (data: {id: string}){
			const previous = (await pluginsModel.getAll()).find((plugin) => plugin.pluginId === data.id);
			await pluginsModel.setEnabled(data.id, false);
			void AuditLog.record({
				actorType: "system",
				source: "automation",
				action: "plugin.disabled",
				resourceType: "plugin",
				resourceId: data.id,
				previousState: { enabled: previous?.enabled },
				newState: { enabled: false },
				success: true,
			});
		}
		
		async disableAll (){
			const plugins = await pluginsModel.getAll();
			for (const plugin of plugins) {
				if (!plugin) continue;
				await pluginsModel.setEnabled(plugin.pluginId, false);
				void AuditLog.record({
					actorType: "system",
					source: "automation",
					action: "plugin.disabled",
					resourceType: "plugin",
					resourceId: plugin.pluginId,
					previousState: { enabled: plugin.enabled },
					newState: { enabled: false },
					success: true,
				});
			}
		}
	
	async install (link){
		let plugindata = {}
	}
	
	async uninstall (link){
		
	}
	
	public async load(plugin: any, meta: PluginManifest): Promise<void> {
		runtime.plugins.loaded++;
		runtime.plugins.total++;
		
		let autoLoader: AutoLoader = new AutoLoader();
		
    	if (!plugin.installPath) {
			runtime.plugins.loaded--;
			runtime.plugins.failed++;
        	logger.error(
            	`[PluginSystem] Plugin "${plugin.name}" has no install path.`
        	);
        	return;
    	}
	
    	if (!meta.main) {
			runtime.plugins.loaded--;
			runtime.plugins.failed++;
        	logger.error(
            	`[PluginSystem] Plugin "${plugin.name}" does not specify a main entry file.`
        	);
        	return;
    	}
		const relative = path.relative(this.pluginsDirectory, meta.path);
		const folderName = path.basename(meta.path);
		const entry = `@plugins/${folderName}/${meta.main}`;
	
    	let imported: any;
	
    	try {
        	imported = await import(entry);
    	} catch (error) {
			runtime.plugins.loaded--;
			runtime.plugins.failed++;
        	logger.error(
            	`[PluginSystem] Failed to import "${plugin.name}" (${entry}).`,
            	error
        	);
        	return;
    	}
	
    	const PluginClass =
        	imported.default ??
        	imported.Plugin ??
        	imported.plugin ??
        	imported;
	
    	if (typeof PluginClass !== "function") {
			runtime.plugins.loaded--;
			runtime.plugins.failed++;
        	logger.error(
            	`[PluginSystem] Plugin "${plugin.name}" does not export a valid plugin class.`
        	);
        	return;
    	}
	
    	let instance: any;
		let pluginContext: PluginContext;
    	try {
			pluginContext = new PluginContext({
				meta,
				client: this.client
			}, eBus, autoLoader) 
        	instance = new PluginClass(pluginContext);
    	} catch (error) {
			runtime.plugins.loaded--;
			runtime.plugins.failed++;
        	logger.error(
            	`[PluginSystem] Failed to instantiate plugin "${plugin.name}".`,
            	error
        	);
        	return;
    	}
	
    	const lifecycleMethods = [
        	"onLoad",
        	"onReady",
        	"onEnable",
        	"onDisable",
    	] as const;
	
    	for (const method of lifecycleMethods) {
        	if (
            	method in instance &&
            	typeof instance[method] !== "function"
        	) {
				runtime.plugins.loaded--;
				runtime.plugins.failed++;
            	logger.error(
                	`[PluginSystem] Plugin "${plugin.name}" has an invalid "${method}" lifecycle method.`
            	);
            	return;
        	}
    	}
	
    	global.cache.plugins.set(plugin.pluginId, {
			autoLoader: autoLoader,
        	instance,
        	meta,
			pluginContext
    	});
	
    	if (typeof instance.onLoad === "function") {
        	try {
            	await instance.onLoad();
        	} catch (error) {
				runtime.plugins.loaded--;
				runtime.plugins.failed++;
            	logger.error(
                	`[PluginSystem] Plugin "${plugin.name}" threw an error during onLoad().`,
                	error
            	);
            	return;
        	}
    	}
	
    	logger.debug(
        	`[PluginSystem] Loaded plugin "${meta.name}" (${plugin.pluginId}).`
    	);
	}
	
public async loadAll(execute: boolean = false): Promise<void> {
    logger.info("[PluginSystem] Discovering plugins...");

    const manifests = await this.discoverPlugins();
    const registered = await pluginsModel.getAll();

    const registeredByPath = new Map(
        registered.map(plugin => [
            path.resolve(plugin.installPath ?? ""),
            plugin
        ])
    );

    const discoveredPaths = new Set<string>();

    let loaded = 0;
    let skipped = 0;
    let failed = 0;

    for (const manifest of manifests) {
        const installPath = path.resolve(manifest.path);
        discoveredPaths.add(installPath);

        try {
            const checksum = await this.calculateChecksum(installPath);

            let plugin = registeredByPath.get(installPath);
            const isEnabled = process.env.ENABLE_ALL_PLUGINS?.toLowerCase() !== "false";

            if (!plugin) {
                logger.debug(`[PluginSystem] Registering "${manifest.name}"`);

                const pluginRecord = {
                    pluginId: crypto.randomUUID(),
                    name: manifest.name,
                    description: manifest.description,
                    version: manifest.version,
                    author: manifest.author,
                    source: "local" as const,
                    installPath,
                    checksum,
                    repositoryUrl: manifest.repositoryUrl,
                    requiredMomentumOneVersion: manifest.requiredMomentumOneVersion,
                    enabled: isEnabled,
                };

                await pluginsModel.add({
                    ...pluginRecord,
                    enabled: isEnabled ? "true" : "false",
                    requiredCoreVersion: manifest.requiredMomentumOneVersion,
                });

                plugin = pluginRecord;
                registeredByPath.set(installPath, plugin);
            } else {
                await pluginsModel.update(plugin.pluginId, {
                    name: manifest.name,
                    description: manifest.description,
                    version: manifest.version,
                    author: manifest.author,
                    installPath,
                    checksum,
                    repositoryUrl: manifest.repositoryUrl,
requiredCoreVersion:
                        manifest.requiredMomentumOneVersion
					});

                plugin = {
                    ...plugin,
                    name: manifest.name,
                    description: manifest.description,
                    version: manifest.version,
                    author: manifest.author,
                    installPath,
                    checksum,
                    repositoryUrl: manifest.repositoryUrl,
                    requiredMomentumOneVersion:
                        manifest.requiredMomentumOneVersion,
                    enabled: isEnabled ? true : Boolean(plugin.enabled),
                };
            }
				
            if (!plugin.enabled) {
                skipped++;
                continue;
            }

            await this.load(plugin, manifest);
            loaded++;

        } catch (err) {
            failed++;
            logger.error(
                `[PluginSystem] Failed loading "${manifest.name}"`,
                err
            );
        }
    }

    for (const plugin of registered) {
        const dbPath = path.resolve(plugin.installPath ?? "");

        if (discoveredPaths.has(dbPath))
            continue;
			failed++
        logger.warn(
            `[PluginSystem] "${plugin.name}" is missing from disk.`
        );
		await pluginsModel.remove(plugin.pluginId)
    }

    logger.info(
        `[PluginSystem] Loaded=${loaded} Skipped=${skipped} Failed=${failed}`
    );
	
	//if (execute) await this.executeAll("onLoad");
}
	
	private async discoverPlugins(): Promise<PluginManifest[]> {
    	const plugins: PluginManifest[] = [];
	
    	const entries = await fs.readdir(this.pluginsDirectory, {
        	withFileTypes: true
    	});
	
    	for (const entry of entries) {
        	if (!entry.isDirectory()) continue;
	
        	const pluginPath = path.relative(process.cwd(), path.join(this.pluginsDirectory, entry.name));
        	const manifestPath = path.join(pluginPath, "plugin.json");
	
        	try {
            	await fs.access(manifestPath);
	
            	const manifest = JSON.parse(
                	await fs.readFile(manifestPath, "utf8")
            	) as PluginManifest;
	
            	// Basic validation
            	if (
                	!manifest.name ||
                	!manifest.version ||
                	!manifest.author ||
                	!manifest.main
            	) {
                	logger.debug(
                    	`[PluginSystem] Skipping "${entry.name}" the plugin's configutation files are invalid or have missing values.`
                	);
                	continue;
            	}
	
            	plugins.push({
                	...manifest,
                	path: pluginPath
            	});
        	} catch (error) {
            	logger.debug(
                	`[PluginSystem] Skipping "${entry.name}" because plugin.json could not be loaded.`,
                	error
            	);
        	}
    	}
	
    	logger.debug(`[PluginSystem] Discovered ${plugins.length} plugin(s).`);
	
    	return plugins;
	}
	
	async unloadAll () {
		
	}
	
	async reload (){
		
	}
	
	async reloadAll (){
		
	}
	
	async add (data: {
        pluginId: string;
        name: string;
        description?: string;
        version: string;
        author: string;
        source: "unknown" | "mone-registry" | "github" | "local";
        installPath?: string;
        checksum?: string;
        repositoryUrl?: string;
        requiredCoreVersion?: string;
    }){
		await pluginsModel.add(data);
	}
	
	async delete ({id}){
		await pluginsModel.remove(id);
	}
	
	private async calculateChecksum(pluginPath: string): Promise<string> {
    	const hash = crypto.createHash("sha256");
	
    	const walk = async (dir: string): Promise<void> => {
        	const entries = (await fs.readdir(dir, { withFileTypes: true }))
            	.sort((a, b) => a.name.localeCompare(b.name));
	
        	for (const entry of entries) {
            	const fullPath = path.join(dir, entry.name);
	
            	// Ignore transient files/folders
            	if (
                	entry.name === "node_modules" ||
                	entry.name === ".git" ||
                	entry.name === ".DS_Store"
            	) {
                	continue;
            	}
	
            	if (entry.isDirectory()) {
                	await walk(fullPath);
            	} else {
                	hash.update(path.relative(pluginPath, fullPath));
                	hash.update(await fs.readFile(fullPath));
            	}
        	}
    	};
	
    	await walk(pluginPath);
	
    	return hash.digest("hex");
	}
	
	async executeAll(event: "onLoad" | "onReady" | "onEnable" | "onDisable") {
    	const supportedEvents = ["onLoad", "onReady", "onEnable", "onDisable"];
	
    	if (!supportedEvents.includes(event)) {
        	return logger.debug(`Unrecognised event named '${event}'`);
    	}
	
    	for (const [id, plugin] of global.cache.plugins) {
        	switch (event) {
            	case "onLoad": {
                	plugin.instance.onLoad?.();
                	break;
            	}
	
            	case "onReady": {
                	plugin.instance.onReady?.();
                	break;
            	}
	
            	case "onEnable": {
                	plugin.instance.onEnable?.();
                	break;
            	}
	
            	case "onDisable": {
                	plugin.instance.onDisable?.();
                	break;
            	}
        	}
    	}
	}
} 
