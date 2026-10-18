import { 
		ActionRowBuilder as DiscordActionRowBuilder,
		ButtonStyle,
		ButtonBuilder,
		StringSelectMenuBuilder,
		StringSelectMenuOptionBuilder,
		ChannelSelectMenuBuilder,
		RoleSelectMenuBuilder, 
		UserSelectMenuBuilder, 
		MentionableSelectMenuBuilder, 
		ChannelType
	} from "discord.js";
import {
		SelectMenuTypes
		} from "@sdk/discord"
import logger from "@logger"

export default class ActionRowBuilder {
	TAG = "MomentumActionRowBuilder"
	
	actionRow: DiscordActionRowBuilder;
	
	constructor(){
		this.actionRow = new DiscordActionRowBuilder()
	}
	
	addComponents(components: any = []){
		if (!Array.isArray(components)) {
			components = [components];
		}
		for (const component of components) {
			if (this.actionRow.components.length >= 5) {
				logger.warn(`[${this.TAG}] Could not push more than 5 components in the action row! Ignoring extra component.`);
				break;
			}
			this.actionRow.addComponents(component);
		}
		return this;
	}
	
	addButton({
		style = ButtonStyle.Primary,
		label = null,
		url = undefined,
		emoji = undefined,
		isDisabled = false,
		disabled = undefined,
		custom_id = "not_set"}: {
			style?: ButtonStyle;
			label?: string | null;
			url?: string;
			emoji?: any;
			isDisabled?: boolean;
			disabled?: boolean;
			custom_id?: string;
		} = {}){
			const finalDisabled = disabled !== undefined ? disabled : isDisabled;
			let button = new ButtonBuilder()
				.setStyle(style)
				.setDisabled(finalDisabled);
			if (url) {
				button.setURL(url);
			} else {
				button.setCustomId(custom_id);
			}
			if (![undefined, null].includes(label)) button.setLabel(label);
			if (emoji) button.setEmoji(emoji);
			this.addComponents([button]);
			
		return this;
	}
	
	addSelectMenu({
		custom_id = "not_set", 
		type = SelectMenuTypes.CUSTOM,
		placeholder = "Not set!", 
		minValues = 1,
		maxValues = 1,
		channelTypes = [ChannelType.GuildText, ChannelType.GuildVoice],
		isDisabled = false,
		options = []
	} : {
    	custom_id?: string;
    	type?: SelectMenuTypes;
    	placeholder?: string;
    	minValues?: number;
    	maxValues?: number;
    	channelTypes?: ChannelType[];
    	isDisabled?: boolean;
    	options?: SelectMenuOptions[];
	}){
		let menu, optionBuilders;
		if (this.actionRow.components.length != 0) return logger.error(`[${this.TAG}] No more space left for a select menu to fit into the action row!`);
		switch (type){
			case SelectMenuTypes.CUSTOM:
				if (!options || options.length === 0) {
					logger.warn(`[${this.TAG}] Cannot create custom select menu with 0 options`);
					return this;
				}
				const safeOptions = options.slice(0, 25);
				optionBuilders = safeOptions.map(opt => {
					let builder = new StringSelectMenuOptionBuilder()
						.setLabel(String(opt.label || "Option").slice(0, 100))
						.setValue(String(opt.value || opt.label || "value").slice(0, 100))
						.setDefault(opt.isDefault || false);
				
					if (opt.description && String(opt.description).trim().length > 0) {
						builder.setDescription(String(opt.description).trim().slice(0, 100));
					}
					if (opt.emoji) builder.setEmoji(opt.emoji);
				
					return builder;
				});

				const effectiveMax = Math.max(1, Math.min(maxValues !== undefined ? maxValues : 1, safeOptions.length));
				const effectiveMin = Math.max(1, Math.min(minValues !== undefined ? minValues : 1, effectiveMax));

				menu = new StringSelectMenuBuilder()
					.setCustomId(custom_id)
					.setPlaceholder(placeholder)
					.setMinValues(effectiveMin)
					.setMaxValues(effectiveMax)
					.setDisabled(isDisabled)
					.setOptions(optionBuilders);
				
				this.addComponents(menu);
				break;
				
			case SelectMenuTypes.USER:
				menu = new UserSelectMenuBuilder()
					.setCustomId(custom_id)
					.setPlaceholder(placeholder)
					.setMinValues(Math.max(1, Math.min(minValues !== undefined ? minValues : 1, 25)))
					.setMaxValues(Math.max(1, Math.min(maxValues !== undefined ? maxValues : 1, 25)))
					.setDisabled(isDisabled);
				
				this.addComponents(menu);
				break;
			case SelectMenuTypes.CHANNEL:
				menu = new ChannelSelectMenuBuilder()
					.setCustomId(custom_id)
					.setPlaceholder(placeholder)
					.setMinValues(Math.max(1, Math.min(minValues !== undefined ? minValues : 1, 25)))
					.setMaxValues(Math.max(1, Math.min(maxValues !== undefined ? maxValues : 1, 25)))
					.setDisabled(isDisabled)
					.setChannelTypes(channelTypes);
				
				this.addComponents(menu);
				break;
				
			case SelectMenuTypes.ROLE:
				menu = new RoleSelectMenuBuilder()
					.setCustomId(custom_id)
					.setPlaceholder(placeholder)
					.setMinValues(Math.max(1, Math.min(minValues !== undefined ? minValues : 1, 25)))
					.setMaxValues(Math.max(1, Math.min(maxValues !== undefined ? maxValues : 1, 25)))
					.setDisabled(isDisabled);
				
				this.addComponents(menu);
				break;
				
			case SelectMenuTypes.MENTION:
				menu = new MentionableSelectMenuBuilder()
					.setCustomId(custom_id)
					.setPlaceholder(placeholder)
					.setMinValues(Math.max(1, Math.min(minValues !== undefined ? minValues : 1, 25)))
					.setMaxValues(Math.max(1, Math.min(maxValues !== undefined ? maxValues : 1, 25)))
					.setDisabled(isDisabled);
				
				this.addComponents(menu);
				break;
		}	
		return this;
	}

	addStringSelectMenu({
		custom_id = "not_set",
		placeholder = "Not set!",
		minValues = 1,
		maxValues = 1,
		isDisabled = false,
		disabled = undefined,
		options = [],
	}: {
		custom_id?: string;
		placeholder?: string;
		minValues?: number;
		maxValues?: number;
		isDisabled?: boolean;
		disabled?: boolean;
		options?: SelectMenuOptions[];
	} = {}) {
		return this.addSelectMenu({
			custom_id,
			placeholder,
			minValues,
			maxValues,
			isDisabled: disabled !== undefined ? disabled : isDisabled,
			options,
			type: SelectMenuTypes.CUSTOM,
		});
	}
	
	build(){
		return this.actionRow;
	}
	
	toJSON(){
		return this.actionRow.toJSON();
	}
}


export interface SelectMenuOptions {
	label?: string;
	description?: string;
	value?: string;
	emoji?: string;
	isDefault?: boolean;
}

