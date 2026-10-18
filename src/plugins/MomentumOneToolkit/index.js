let pluginLogger;

module.exports = class MomentumOneToolkit {
	
	constructor(ctx){
		const { eventBus, EventsList, client, logger, cache, databaseManager, autoLoader } = ctx;
		// this = { ctx, eventBus, EventsList, client, logger, cache, databaseManager}
		this.ctx = ctx,
		this.client = client,
		this.eventBus = eventBus, 
		this.EventsList = EventsList, 
		this.logger = logger, 
		this.cache = cache, 
		this.db = databaseManager, 
		this.autoLoader = autoLoader;
		pluginLogger = logger;
	}
	
	async onLoad(){
		this.autoLoader.commands.setEnabled(true)
		this.autoLoader.commands.setDirectory("commands")
		this.autoLoader.commands.setMapper(file => {
			const f = file?.default ?? file;
			return {
				// Prefix
				name: f.name,
				aliases: f.aliases,
				description: f.description,
				usage: f.usage,
				examples: f.examples,
				userPermissions: f.userPermissions,
				botPermissions: f.botPermissions,
				guildOnly: f.guildOnly,
				nsfw: f.nsfw,
			
				// Slash
				data: f.builder,
			
				// Shared
				category: f.category,
				botPermissions: f.botPermissions,
				cooldown: f.cooldown,
				ownerOnly: f.ownerOnly,
				enabled: f.enabled,
				hidden: f.hidden,
				execute: f.execute,
				sub_commands: f.sub_commands || f.subCommands,
				subCommands: f.sub_commands || f.subCommands,
			};
		});

		this.autoLoader.events.setEnabled(true)
		this.autoLoader.events.setDirectory("events")
		this.autoLoader.events.setMapper(event => {
			const e = event?.default ?? event;
			return {
				name: e.name,
				description: e.description ?? null,
				execute: e.execute,
				enabled: e.enabled ?? true,
				hidden: e.hidden ?? false,
			};
		});
	}
	
	
	async onReady(){
		const { BlacklistManager } = require("../../core/security/BlacklistManager");
		const { AntiSpamService } = require("../../core/security/AntiSpamService");
		const { NoPrefixManager } = require("../../core/security/NoPrefixManager");
		
		void BlacklistManager.init();
		void AntiSpamService.init();
		void NoPrefixManager.init();
	}
	
	async onEnable(){
		const { BlacklistManager } = require("../../core/security/BlacklistManager");
		const { AntiSpamService } = require("../../core/security/AntiSpamService");
		const { NoPrefixManager } = require("../../core/security/NoPrefixManager");
		
		void BlacklistManager.init();
		void AntiSpamService.init();
		void NoPrefixManager.init();
	}
	async onDisable(){
	}
}

