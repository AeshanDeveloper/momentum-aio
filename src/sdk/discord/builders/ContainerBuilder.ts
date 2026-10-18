import {
	ContainerBuilder as DiscordContainerBuilder,
	SeparatorSpacingSize as DiscordSeparatorSpacingSize
} from "discord.js";
import SectionBuilder from "./SectionBuilder";
import ActionRowBuilder from "./ActionRowBuilder";

export default class ContainerBuilder {
	
	container: DiscordContainerBuilder;
	constructor () {
		this.container = new DiscordContainerBuilder()
	}
	
	addSeparator({divider = true, spacing = DiscordSeparatorSpacingSize.Small}){
		this.container.addSeparatorComponents((separator) => 
				separator.setDivider(divider || true).setSpacing(spacing || DiscordSeparatorSpacingSize.Small)
			)
		return this;	
	}
	
	addTextDisplay(text = "No text set!"){
		this.container.addTextDisplayComponents((td) =>
			td.setContent(text)
		)
		return this;
	}
	
	addSection(mappings){
		this.container.addSectionComponents(mappings(new SectionBuilder()).build())
		return this;
	}
	
	addActionRow(mappings: any) {
		const result = typeof mappings === "function" ? mappings(new ActionRowBuilder()) : mappings;
		const row = result instanceof ActionRowBuilder ? result.build() : result;

		if (row && Array.isArray(row.components) && row.components.length === 0) {
			return this;
		}

		if (row) {
			this.container.addActionRowComponents(row);
		}

		return this;
	}
	
	setAccentColor(hex = "#ffffff"){
		this.container.setAccentColor(parseInt(hex.replace("#", ""), 16));
		return this;
	}
	
	setSpoiler(isSpoiler){
		this.container.setSpoiler(isSpoiler);
		return this;
	}
	
	setId(id = "not_set"){
		this.container.setId(id);
		return this;
	}
	
	build(){
		return this.container;
	}
	
	toJSON(){
		return this.container.toJSON();
	}
}