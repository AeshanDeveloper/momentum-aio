import {
	SectionBuilder as DiscordSectionBuilder,
	TextDisplayBuilder,
	ButtonBuilder,
	ThumbnailBuilder,
	ButtonStyle,
} from "discord.js";

import {
	AccessoryTypes
} from "@sdk/discord"

export default class SectionBuilder {
	section: DiscordSectionBuilder;
	constructor (){
		this.section = new DiscordSectionBuilder()
	}
	
	addSeparator({divider = true, spacing = DiscordSeparatorSpacingSize.Small}){
		this.section.addTextDisplayComponents((separator) => 
				separator.setDivider(divider).setSpacing(spacing)
			)
		return this;
	}
	
	addTextDisplay(text = "No text set!"){
		this.section.addTextDisplayComponents((td) =>
			td.setContent(text)
		)
		return this;
	}
		
	setAccessory({
			type = AccessoryTypes.Button,
			id = 1,
			custom_id = "not_set", 
			label = "Not Set", 
			description = "Not set",
			style = ButtonStyle.Primary,
			url = undefined,
			emoji = undefined,
			isDisabled = false,
			isSpoiler = false
		}){
			
			switch(type) {
				case AccessoryTypes.Button:
					this.section.setButtonAccessory(new Button()
						.setCustomId(custom_id)
						.setLabel(label)
						.setStyle(style)
						.setURL(url)
						.setEmoji(emoji)
						.setDisabled(isDisabled)
					)
					break;
					
				case AccessoryTypes.Thumbnail:
					this.section.setThumbnailAccessory(new ThumbnailBuilder()
						.setId(id)
						.setURL(url)
						.setDescription(description)
						.setSpoiler(isSpoiler)
					)
					break;
			}
			return this;
		}
		
			
	build(){
		return this.section;
	}
	
	toJSON(){
		return this.section.toJSON()
	}
}