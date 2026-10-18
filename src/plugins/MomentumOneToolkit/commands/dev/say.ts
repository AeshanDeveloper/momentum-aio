import { ContainerBuilder, Messages, Helpers } from "@sdk/discord";

export default {
    name: "say",
    category: "Owner",
    aliases: ["b"],
    description: "",
    args: [],
    usage: "say <text>",
    ownerOnly: true,
    execute: async (ctx, commandType, message, args) => {
   const sayMessage = message.content.split(' ').slice(1).join(' ');
    if (!sayMessage) {
      const me = new ContainerBuilder()
        .setAccentColor(global.Colors.default)
        .addTextDisplay("No text provided")
      return message.reply({embeds: [me]})
    }

    if (sayMessage) {
      message.delete();
   message.channel.send({content: `${sayMessage}`}), {
      allowedMentions: { parse: ["users"] },
    };
     }
  },
};