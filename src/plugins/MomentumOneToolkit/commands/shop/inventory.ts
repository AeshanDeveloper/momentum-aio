const {
	MessageFlags,
	SeparatorSpacingSize,
	SlashCommandBuilder,
	ButtonStyle,
	PermissionFlagsBits,
	ModalBuilder,
	TextInputBuilder,
	TextInputStyle
} = require("discord.js");

const {
	CommandType,
	ContainerBuilder,
	ActionRowBuilder,
	SelectMenuTypes
} = require("@sdk/discord");

import config from "@config";
import logger from "@logger";

import InventoryManager, {
	InventoryItem,
	InventorySettings
} from "../../managers/Inventory";

export default {
	name: "inventory",
	aliases: ["inv", "stock"],
	description: "Manage and view the server inventory.",
	category: "Management",
	usage: "inventory [item]",

	builder: new SlashCommandBuilder()
		.setName("inventory")
		.setDescription("Manage and view the server inventory.")
		.addStringOption(option =>
			option
				.setName("sku")
				.setDescription("Open a specific inventory item.")
				.setRequired(false)
		),

	execute: async (ctx, commandType, message, args) => {
		const isSlash = commandType === CommandType.SLASH;

		const E = config.Emojis || {};

		const icon = E.inventory || E.box || "📦";
		const success = E.success || "✅";
		const error = E.error || "❌";
		const info = E.info || "💡";
		const warning = E.warning || "⚠️";
		const edit = E.edit || "✏️";
		const plus = E.plus || "➕";
		const minus = E.minus || "➖";
		const trash = E.delete || E.trash || "🗑️";
		const settingsIcon = E.settings || "⚙️";
		const searchIcon = E.search || "🔎";
		const back = E.back || "↩️";

		const guild = message.guild;

		if (!guild) {
			return isSlash
				? message.reply({
					content: `${error} This command can only be used inside a server.`
				})
				: message.reply(
					`${error} This command can only be used inside a server.`
				);
		}

		const guildId = guild.id;

		const user =
			isSlash
				? message.user
				: message.author;

		const member =
			isSlash
				? message.member
				: message.member;

		const settings =
			await InventoryManager.getOrCreateSettings(
				guildId
			);

		/* =====================================================
		 * PERMISSIONS
		 * ===================================================== */

		const isOwner =
			guild.ownerId === user.id;

		const hasDiscordManagementPermission =
			Boolean(
				member?.permissions?.has(
					PermissionFlagsBits.Administrator
				) ||
				member?.permissions?.has(
					PermissionFlagsBits.ManageGuild
				)
			);

		const configuredPermissions =
			settings.permissions?.manageInventory || [];

		const hasConfiguredPermission =
			configuredPermissions.some(permission => {
				try {
					if (
						typeof permission === "string" &&
						member?.permissions?.has(permission)
					) {
						return true;
					}

					return false;
				} catch {
					return false;
				}
			});

		const canManage =
			isOwner ||
			hasDiscordManagementPermission ||
			hasConfiguredPermission;

		/*
		 * The owner can ALWAYS manage inventory.
		 *
		 * Regular users can still VIEW inventory.
		 */

		/* =====================================================
		 * QUERY
		 * ===================================================== */

		const query =
			isSlash
				? message.options?.getString("sku")?.trim() || ""
				: Array.isArray(args)
					? args.join(" ").trim()
					: "";

		/* =====================================================
		 * SESSION
		 * ===================================================== */

		const sessionId =
			`${user.id}_${Date.now()}`;

		const selectId =
			`inventory_select_${sessionId}`;

		const actionPrefix =
			`inventory_${sessionId}`;

		let currentSearch = "";
		let currentPage = 0;

		const PAGE_SIZE = 8;

		/* =====================================================
		 * HELPERS
		 * ===================================================== */

		const escape = (value: unknown) =>
			String(value ?? "")
				.replace(/\\/g, "\\\\")
				.replace(/`/g, "\\`");

		const formatNumber = (value: number) =>
			Number(value || 0).toLocaleString();

		const formatValue = (value: number) =>
			Number(value || 0).toLocaleString();

		const getItemLabel = (item: InventoryItem) =>
			`${item.emoji || "📦"} ${item.name}`;

		const getItemDescription = (item: InventoryItem) =>
			`${item.sku} • Qty: ${formatNumber(item.quantity)} • Value: ${formatValue(item.value)}`;

		const getMetadataText = (item: InventoryItem) => {
			const metadata = item.metadata || {};
			const entries = Object.entries(metadata);

			if (!entries.length) {
				return "`None`";
			}

			return entries
				.slice(0, 12)
				.map(
					([key, value]) =>
						`\`${escape(key)}\`: \`${escape(
							typeof value === "string"
								? value
								: JSON.stringify(value)
						)}\``
				)
				.join("\n");
		};

		const errorContainer = (title: string, text: string) =>
			new ContainerBuilder()
				.setAccentColor(
					config.Colors?.error ||
					config.Colors?.default ||
					"#ff0000"
				)
				.addTextDisplay(
					`### ${error} ${title}`
				)
				.addTextDisplay(text)
				.build();

		const successContainer = (title: string, text: string) =>
			new ContainerBuilder()
				.setAccentColor(
					config.Colors?.success ||
					config.Colors?.default ||
					"#00ff00"
				)
				.addTextDisplay(
					`### ${success} ${title}`
				)
				.addTextDisplay(text)
				.build();

		/* =====================================================
		 * ITEMS
		 * ===================================================== */

		const getItems = async () => {
			return InventoryManager.getItems(
				guildId,
				{
					limit: PAGE_SIZE,
					skip: currentPage * PAGE_SIZE,
					search: currentSearch || undefined
				}
			);
		};

		const getCount = async () =>
			InventoryManager.countItems(guildId);

		/* =====================================================
		 * MAIN DASHBOARD
		 * ===================================================== */

		const dashboard = async () => {
			const freshSettings =
				await InventoryManager.getOrCreateSettings(
					guildId
				);

			const count =
				await getCount();

			const items =
				await getItems();

			const totalPages =
				Math.max(
					1,
					Math.ceil(
						count / PAGE_SIZE
					)
				);

			currentPage =
				Math.max(
					0,
					Math.min(
						currentPage,
						totalPages - 1
					)
				);

			const c =
				new ContainerBuilder()
					.setAccentColor(
						config.Colors?.cmd_inventory ||
						config.Colors?.default ||
						"#ffffff"
					)
					.addTextDisplay(
						`### ${icon} Inventory`
					)
					.addTextDisplay(
						`Manage the inventory for **${guild.name}**.`
					)
					.addSeparator({
						divider: true,
						spacing:
							SeparatorSpacingSize.Small
					})
					.addTextDisplay(
						`**Items:** \`${formatNumber(count)}\`\n` +
						`**Status:** ${
							freshSettings.enabled
								? `${success} Enabled`
								: `${warning} Disabled`
						}\n` +
						`**Max Items:** \`${formatNumber(
							freshSettings.limits.maxItems
						)}\`\n` +
						`**Max Quantity:** \`${formatNumber(
							freshSettings.limits.maxQuantityPerItem
						)}\``
					);

			if (currentSearch) {
				c.addTextDisplay(
					`${searchIcon} Searching for \`${escape(
						currentSearch
					)}\``
				);
			}

			if (!items.length) {
				c.addSeparator({
					divider: true,
					spacing:
						SeparatorSpacingSize.Small
				});

				c.addTextDisplay(
					`${info} No inventory items found.`
				);
			} else {
				c.addSeparator({
					divider: true,
					spacing:
						SeparatorSpacingSize.Small
				});

				c.addTextDisplay(
					items
						.map(
							item =>
								`• ${getItemLabel(item)} — \`${item.sku}\`\n` +
								`  Qty: **${formatNumber(
									item.quantity
								)}** · Value: **${formatValue(
									item.value
								)}**`
						)
						.join("\n\n")
				);
			}

			/* Item selector */

			if (items.length) {
				c.addActionRow(row =>
					row.addSelectMenu({
						type: SelectMenuTypes.CUSTOM,
						custom_id: selectId,
						placeholder:
							"Select an inventory item",
						minValues: 1,
						maxValues: 1,
						options: items.map(item => ({
							label:
								item.name.slice(0, 100),
							value: item.sku,
							description:
								getItemDescription(
									item
								).slice(0, 100),
							emoji:
								item.emoji
						}))
					})
				);
			}

			/* Management buttons */

			c.addActionRow(row => {
				if (canManage) {
					row.addButton({
						custom_id:
							`${actionPrefix}:create`,
						label: "Create",
						emoji: plus,
						style:
							ButtonStyle.Success
					});

					row.addButton({
						custom_id:
							`${actionPrefix}:search`,
						label: "Search",
						emoji: searchIcon,
						style:
							ButtonStyle.Secondary
					});
				}

				row.addButton({
					custom_id:
						`${actionPrefix}:refresh`,
					label: "Refresh",
					style:
						ButtonStyle.Secondary
				});

				return row;
			});

			if (canManage) {
				c.addActionRow(row => {
					row.addButton({
						custom_id:
							`${actionPrefix}:settings`,
						label: "Settings",
						emoji: settingsIcon,
						style:
							ButtonStyle.Secondary
					});

					row.addButton({
						custom_id:
							`${actionPrefix}:enable`,
						label:
							freshSettings.enabled
								? "Disable"
								: "Enable",
						style:
							freshSettings.enabled
								? ButtonStyle.Danger
								: ButtonStyle.Success
					});

					return row;
				});
			}

			c.addSeparator({
				divider: true,
				spacing:
					SeparatorSpacingSize.Small
			});

			c.addTextDisplay(
				`-# Page ${currentPage + 1} of ${totalPages}` +
				(currentSearch
					? ` • Search: ${currentSearch}`
					: "")
			);

			if (totalPages > 1) {
				c.addActionRow(row => {
					row.addButton({
						custom_id:
							`${actionPrefix}:first`,
						label: "«",
						style:
							ButtonStyle.Secondary,
						disabled:
							currentPage === 0
					});

					row.addButton({
						custom_id:
							`${actionPrefix}:prev`,
						label: "‹",
						style:
							ButtonStyle.Secondary,
						disabled:
							currentPage === 0
					});

					row.addButton({
						custom_id:
							`${actionPrefix}:next`,
						label: "›",
						style:
							ButtonStyle.Secondary,
						disabled:
							currentPage >=
							totalPages - 1
					});

					row.addButton({
						custom_id:
							`${actionPrefix}:last`,
						label: "»",
						style:
							ButtonStyle.Secondary,
						disabled:
							currentPage >=
							totalPages - 1
					});

					return row;
				});
			}

			return c.build();
		};

		/* =====================================================
		 * ITEM DETAILS
		 * ===================================================== */

		const itemDetails = async (
			item: InventoryItem
		) => {
			const c =
				new ContainerBuilder()
					.setAccentColor(
						config.Colors?.cmd_inventory ||
						config.Colors?.default ||
						"#ffffff"
					)
					.addTextDisplay(
						`### ${item.emoji || icon} ${item.name}`
					)
					.addTextDisplay(
						item.description ||
						"No description provided."
					)
					.addSeparator({
						divider: true,
						spacing:
							SeparatorSpacingSize.Small
					})
					.addTextDisplay(
						`**SKU** \`${item.sku}\`\n` +
						`**Quantity** \`${formatNumber(
							item.quantity
						)}\`\n` +
						`**Value** \`${formatValue(
							item.value
						)}\``
					)
					.addSeparator({
						divider: true,
						spacing:
							SeparatorSpacingSize.Small
					})
					.addTextDisplay(
						`**Metadata**\n${getMetadataText(
							item
						)}`
					);

			if (canManage) {
				c.addActionRow(row => {
					row.addButton({
						custom_id:
							`${actionPrefix}:edit:${item.sku}`,
						label: "Edit",
						emoji: edit,
						style:
							ButtonStyle.Primary
					});

					row.addButton({
						custom_id:
							`${actionPrefix}:stock:${item.sku}`,
						label: "Stock",
						emoji: plus,
						style:
							ButtonStyle.Success
					});

					row.addButton({
						custom_id:
							`${actionPrefix}:remove_stock:${item.sku}`,
						label: "Remove Stock",
						emoji: minus,
						style:
							ButtonStyle.Secondary
					});

					return row;
				});

				c.addActionRow(row => {
					row.addButton({
						custom_id:
							`${actionPrefix}:setstock:${item.sku}`,
						label: "Set Quantity",
						style:
							ButtonStyle.Secondary
					});

					row.addButton({
						custom_id:
							`${actionPrefix}:delete:${item.sku}`,
						label: "Delete",
						emoji: trash,
						style:
							ButtonStyle.Danger
					});

					return row;
				});
			}

			c.addActionRow(row =>
				row.addButton({
					custom_id:
						`${actionPrefix}:back`,
					label: "Back",
					emoji: back,
					style:
						ButtonStyle.Secondary
				})
			);

			return c.build();
		};

		/* =====================================================
		 * MODAL HELPERS
		 * ===================================================== */

		const createModal = ({
			id,
			title,
			fields
		}: {
			id: string;
			title: string;
			fields: {
				id: string;
				label: string;
				value?: string;
				placeholder?: string;
				required?: boolean;
				style?: number;
			}[];
		}) => {
			const modal =
				new ModalBuilder()
					.setCustomId(id)
					.setTitle(title.slice(0, 45));

			const rows = fields.map(field => {
				const input =
					new TextInputBuilder()
						.setCustomId(field.id)
						.setLabel(field.label.slice(0, 45))
						.setStyle(
							field.style ||
							TextInputStyle.Short
						)
						.setRequired(
							field.required ?? false
						);

				if (field.value !== undefined) {
					input.setValue(
						String(field.value).slice(
							0,
							4000
						)
					);
				}

				if (field.placeholder) {
					input.setPlaceholder(
						field.placeholder.slice(
							0,
							100
						)
					);
				}

				return new ActionRowBuilder()
					.addComponents(input)
			});

			modal.addComponents(rows);

			return modal;
		};

		/* =====================================================
		 * SEND / EDIT
		 * ===================================================== */

		const payload = container => ({
			components: [container],
			flags: MessageFlags.IsComponentsV2
		});

		const send = async container => {
			return isSlash
				? message.editReply(
					payload(container)
				)
				: message.reply(
					payload(container)
				);
		};

		const editMessage = async (
			interaction,
			container
		) => {
			return interaction.message.edit(
				payload(container)
			);
		};

		/* =====================================================
		 * MODAL SUBMIT HANDLER
		 * ===================================================== */

		const handleModal = async interaction => {
            logger.silly("interaction detected" + interaction.customId)

			if (
				interaction.user.id !==
				user.id
			) {
				return;
			}

			if (
				!interaction.customId.startsWith(
					actionPrefix
				)
			) {
				return;
			}
            
            logger.silly("interaction detected" + interaction.customId)

			try {
				const parts =
					interaction.customId.split(":");

				const action = parts[2];

				/* ---------------------------------------------
				 * CREATE ITEM
				 * --------------------------------------------- */

				if (action === "create") {
					const name =
						interaction.fields
							.getTextInputValue(
								"name"
							)
							.trim();

					const description =
						interaction.fields
							.getTextInputValue(
								"description"
							)
							.trim();

					const emoji =
						interaction.fields
							.getTextInputValue(
								"emoji"
							)
							.trim();

					const quantityRaw =
						interaction.fields
							.getTextInputValue(
								"quantity"
							)
							.trim();

					const valueRaw =
						interaction.fields
							.getTextInputValue(
								"value"
							)
							.trim();

					const quantity =
						quantityRaw
							? Number(quantityRaw)
							: 0;

					const value =
						valueRaw
							? Number(valueRaw)
							: 0;

					const item =
						await InventoryManager.createItem(
							guildId,
							{
								name,
								description:
									description ||
									undefined,
								emoji:
									emoji ||
									undefined,
								quantity,
								value
							}
						);

					currentSearch = "";
					currentPage = 0;

					await interaction.reply({
						components: [
							successContainer(
								"Item Created",
								`${item.emoji || icon} **${item.name}** was created with SKU \`${item.sku}\`.`
							)
						],
						flags:
							MessageFlags.IsComponentsV2,
						ephemeral: true
					});

					return;
				}

				/* ---------------------------------------------
				 * EDIT ITEM
				 * --------------------------------------------- */

				if (action === "edit") {
					const sku = parts[3];

					const item =
						await InventoryManager.getItem(
							guildId,
							sku
						);

					if (!item) {
						return interaction.reply({
							components: [
								errorContainer(
									"Item Not Found",
									`No inventory item exists with SKU \`${sku}\`.`
								)
							],
							flags:
								MessageFlags.IsComponentsV2,
							ephemeral: true
						});
					}

					const name =
						interaction.fields
							.getTextInputValue(
								"name"
							)
							.trim();

					const description =
						interaction.fields
							.getTextInputValue(
								"description"
							)
							.trim();

					const emoji =
						interaction.fields
							.getTextInputValue(
								"emoji"
							)
							.trim();

					const valueRaw =
						interaction.fields
							.getTextInputValue(
								"value"
							)
							.trim();

					const metadataRaw =
						interaction.fields
							.getTextInputValue(
								"metadata"
							)
							.trim();

					let metadata =
						item.metadata || {};

					if (metadataRaw) {
						try {
							metadata =
								JSON.parse(
									metadataRaw
								);

							if (
								typeof metadata !==
								"object" ||
								Array.isArray(metadata) ||
								metadata === null
							) {
								throw new Error();
							}
						} catch {
							return interaction.reply({
								components: [
									errorContainer(
										"Invalid Metadata",
										"Metadata must be valid JSON in object form."
									)
								],
								flags:
									MessageFlags.IsComponentsV2,
								ephemeral: true
							});
						}
					}

					const value =
						valueRaw
							? Number(valueRaw)
							: item.value;

					const updated =
						await InventoryManager.updateItem(
							guildId,
							sku,
							{
								name,
								description,
								emoji:
									emoji ||
									undefined,
								value,
								metadata
							}
						);
                    InventoryManager.sync()
					if (!updated) {
						return interaction.reply({
							components: [
								errorContainer(
									"Item Not Found",
									"That item no longer exists."
								)
							],
							flags:
								MessageFlags.IsComponentsV2,
							ephemeral: true
						});
					}

					await interaction.reply({
						components: [
							successContainer(
								"Item Updated",
								`**${updated.name}** has been updated.`
							)
						],
						flags:
							MessageFlags.IsComponentsV2,
						ephemeral: true
					});

					return;
				}

				/* ---------------------------------------------
				 * ADD STOCK
				 * --------------------------------------------- */

				if (action === "stock") {
					const sku = parts[3];

					const amount =
						Number(
							interaction.fields
								.getTextInputValue(
									"amount"
								)
								.trim()
						);

					const updated =
						await InventoryManager.addQuantity(
							guildId,
							sku,
							amount
						);

					if (!updated) {
						return interaction.reply({
							components: [
								errorContainer(
									"Item Not Found",
									`SKU \`${sku}\` does not exist.`
								)
							],
							flags:
								MessageFlags.IsComponentsV2,
							ephemeral: true
						});
					}

					await interaction.reply({
						components: [
							successContainer(
								"Stock Added",
								`Added **${formatNumber(
									amount
								)}** to **${updated.name}**.\n\nNew quantity: **${formatNumber(
									updated.quantity
								)}**`
							)
						],
						flags:
							MessageFlags.IsComponentsV2,
						ephemeral: true
					});

					return;
				}

				/* ---------------------------------------------
				 * REMOVE STOCK
				 * --------------------------------------------- */

				if (action === "remove_stock") {
					const sku = parts[3];

					const amount =
						Number(
							interaction.fields
								.getTextInputValue(
									"amount"
								)
								.trim()
						);

					const updated =
						await InventoryManager.removeQuantity(
							guildId,
							sku,
							amount
						);

					if (!updated) {
						return interaction.reply({
							components: [
								errorContainer(
									"Item Not Found",
									`SKU \`${sku}\` does not exist.`
								)
							],
							flags:
								MessageFlags.IsComponentsV2,
							ephemeral: true
						});
					}

					await interaction.reply({
						components: [
							successContainer(
								"Stock Removed",
								`Removed **${formatNumber(
									amount
								)}** from **${updated.name}**.\n\nNew quantity: **${formatNumber(
									updated.quantity
								)}**`
							)
						],
						flags:
							MessageFlags.IsComponentsV2,
						ephemeral: true
					});

					return;
				}

				/* ---------------------------------------------
				 * SET STOCK
				 * --------------------------------------------- */

				if (action === "setstock") {
					const sku = parts[3];

					const quantity =
						Number(
							interaction.fields
								.getTextInputValue(
									"quantity"
								)
								.trim()
						);

					const updated =
						await InventoryManager.setQuantity(
							guildId,
							sku,
							quantity
						);

					if (!updated) {
						return interaction.reply({
							components: [
								errorContainer(
									"Item Not Found",
									`SKU \`${sku}\` does not exist.`
								)
							],
							flags:
								MessageFlags.IsComponentsV2,
							ephemeral: true
						});
					}

					await interaction.reply({
						components: [
							successContainer(
								"Quantity Updated",
								`**${updated.name}** now has **${formatNumber(
									updated.quantity
								)}** units.`
							)
						],
						flags:
							MessageFlags.IsComponentsV2,
						ephemeral: true
					});

					return;
				}

				/* ---------------------------------------------
				 * SEARCH
				 * --------------------------------------------- */

				if (action === "search") {
					currentSearch =
						interaction.fields
							.getTextInputValue(
								"search"
							)
							.trim();

					currentPage = 0;

					await interaction.update(
						payload(
							await dashboard()
						)
					);

					return;
				}

				/* ---------------------------------------------
				 * SETTINGS
				 * --------------------------------------------- */

				if (action === "settings") {
					const maxItems =
						Number(
							interaction.fields
								.getTextInputValue(
									"maxItems"
								)
								.trim()
						);

					const maxQuantity =
						Number(
							interaction.fields
								.getTextInputValue(
									"maxQuantity"
								)
								.trim()
						);

					const enabledRaw =
						interaction.fields
							.getTextInputValue(
								"enabled"
							)
							.trim()
							.toLowerCase();

					if (
						!Number.isInteger(maxItems) ||
						maxItems < 1
					) {
						throw new Error(
							"Maximum items must be a positive integer."
						);
					}

					if (
						!Number.isInteger(maxQuantity) ||
						maxQuantity < 1
					) {
						throw new Error(
							"Maximum quantity must be a positive integer."
						);
					}

					await InventoryManager.updateSettings(
						guildId,
						{
							enabled:
								enabledRaw === "true" ||
								enabledRaw === "yes" ||
								enabledRaw === "on",
							limits: {
								maxItems,
								maxQuantityPerItem:
									maxQuantity
							}
						}
					);

					await interaction.update(
						payload(
							await dashboard()
						)
					);

					return;
				}
			} catch (err) {
				console.error(
					"[INVENTORY] Modal interaction failed:",
					err
				);

				const text =
					err instanceof Error
						? err.message
						: "An unexpected error occurred.";

				if (interaction.replied) {
					return;
				}

				return interaction.reply({
					components: [
						errorContainer(
							"Operation Failed",
							text
						)
					],
					flags:
						MessageFlags.IsComponentsV2,
					ephemeral: true
				});
			}
		};

		/* =====================================================
		 * BUTTON / SELECT COLLECTOR
		 * ===================================================== */

		const attachCollector = sent => {
			if (
				!sent?.createMessageComponentCollector
			) {
				logger.error(
					"[INVENTORY] Unable to create collector."
				);
				return;
			}

			const collector =
				sent.createMessageComponentCollector({
					time: 600_000,
					filter: interaction =>
						interaction.user.id ===
						user.id
				});

			collector.on(
				"collect",
				async interaction => {
					try {
                        logger.silly("int recieved: button click: " + interaction.customId)
						/* -------------------------------
						 * SELECT ITEM
						 * ------------------------------- */

						if (
							interaction.isStringSelectMenu()
						) {
							if (
								interaction.customId !==
								selectId
							) {
								return;
							}

							const sku =
								interaction.values?.[0];

							if (!sku) return;

							const item =
								await InventoryManager.getItem(
									guildId,
									sku
								);

							if (!item) {
								return interaction.update(
									payload(
										errorContainer(
											"Item Not Found",
											`SKU \`${sku}\` no longer exists.`
										)
									)
								);
							}

							await interaction.update(
								payload(
									await itemDetails(
										item
									)
								)
							);

							return;
						}

						if (!interaction.isButton()) {
							return;
						}

						const id =
							interaction.customId;

						if (
							!id.startsWith(
								actionPrefix
							)
						) {
							return;
						}

						const parts =
							id.split(":");

						const action =
							parts[1];

						/* -------------------------------
						 * PERMISSION RECHECK
						 * ------------------------------- */

						if (
							[
								"create",
								"edit",
								"stock",
								"remove_stock",
								"setstock",
								"delete",
								"settings",
								"enable"
							].includes(action) &&
							!canManage
						) {
							return interaction.reply({
								components: [
									errorContainer(
										"Permission Denied",
										"You do not have permission to manage this inventory."
									)
								],
								flags:
									MessageFlags.IsComponentsV2,
								ephemeral: true
							});
						}

						/* -------------------------------
						 * REFRESH
						 * ------------------------------- */

						if (
							action ===
							"refresh"
						) {
							await interaction.update(
								payload(
									await dashboard()
								)
							);

							return;
						}

						/* -------------------------------
						 * BACK
						 * ------------------------------- */

						if (
							action ===
							"back"
						) {
							await interaction.update(
								payload(
									await dashboard()
								)
							);

							return;
						}

						/* -------------------------------
						 * CREATE
						 * ------------------------------- */

						if (
							action ===
							"create"
						) {
							const modal =
								createModal({
									id:
										`${actionPrefix}:modal:create`,
									title:
										"Create Inventory Item",
									fields: [
										{
											id:
												"name",
											label:
												"Name",
											placeholder:
												"Item name",
											required:
												true
										},
										{
											id:
												"description",
											label:
												"Description",
											placeholder:
												"Item description",
											style:
												TextInputStyle.Paragraph
										},
										{
											id:
												"emoji",
											label:
												"Emoji",
											placeholder:
												"📦"
										},
										{
											id:
												"quantity",
											label:
												"Starting Quantity",
											placeholder:
												"0"
										},
										{
											id:
												"value",
											label:
												"Item Value",
											placeholder:
												"0"
										}
									]
								});

							await interaction.showModal(
								modal
							);

							return;
						}

						/* -------------------------------
						 * SEARCH
						 * ------------------------------- */

						if (
							action ===
							"search"
						) {
							const modal =
								createModal({
									id:
										`${actionPrefix}:modal:search`,
									title:
										"Search Inventory",
									fields: [
										{
											id:
												"search",
											label:
												"Search",
											placeholder:
												"SKU or item name"
										}
									]
								});

							await interaction.showModal(
								modal
							);

							return;
						}

						/* -------------------------------
						 * SETTINGS
						 * ------------------------------- */

						if (
							action ===
							"settings"
						) {
							const current =
								await InventoryManager.getOrCreateSettings(
									guildId
								);

							const modal =
								createModal({
									id:
										`${actionPrefix}:modal:settings`,
									title:
										"Inventory Settings",
									fields: [
										{
											id:
												"maxItems",
											label:
												"Maximum Items",
											value:
												current
													.limits
													.maxItems
													.toString(),
											required:
												true
										},
										{
											id:
												"maxQuantity",
											label:
												"Maximum Quantity Per Item",
											value:
												current
													.limits
													.maxQuantityPerItem
													.toString(),
											required:
												true
										},
										{
											id:
												"enabled",
											label:
												"Enabled? true / false",
											value:
												current.enabled
													? "true"
													: "false",
											required:
												true
										}
									]
								});

							await interaction.showModal(
								modal
							);

							return;
						}

						/* -------------------------------
						 * ENABLE / DISABLE
						 * ------------------------------- */

						if (
							action ===
							"enable"
						) {
							const current =
								await InventoryManager.getOrCreateSettings(
									guildId
								);

							await InventoryManager.setEnabled(
								guildId,
								!current.enabled
							);

							await interaction.update(
								payload(
									await dashboard()
								)
							);

							return;
						}

						/* -------------------------------
						 * EDIT
						 * ------------------------------- */

						if (
							action ===
							"edit"
						) {
							const sku =
								parts[2];

							const item =
								await InventoryManager.getItem(
									guildId,
									sku
								);

							if (!item) {
								return interaction.reply({
									components: [
										errorContainer(
											"Item Not Found",
											`SKU \`${sku}\` does not exist.`
										)
									],
									flags:
										MessageFlags.IsComponentsV2,
									ephemeral: true
								});
							}

							const modal =
								createModal({
									id:
										`${actionPrefix}:modal:edit:${sku}`,
									title:
										`Edit ${item.name}`,
									fields: [
										{
											id:
												"name",
											label:
												"Name",
											value:
												item.name,
											required:
												true
										},
										{
											id:
												"description",
											label:
												"Description",
											value:
												item.description ||
												"",
											style:
												TextInputStyle.Paragraph
										},
										{
											id:
												"emoji",
											label:
												"Emoji",
											value:
												item.emoji ||
												""
										},
										{
											id:
												"value",
											label:
												"Value",
											value:
												item.value.toString()
										},
										{
											id:
												"metadata",
											label:
												"Metadata JSON",
											value:
												JSON.stringify(
													item.metadata ||
														{},
													null,
													2
												),
											style:
												TextInputStyle.Paragraph
										}
									]
								});

							await interaction.showModal(
								modal
							);

							return;
						}

						/* -------------------------------
						 * ADD STOCK
						 * ------------------------------- */

						if (
							action ===
							"stock"
						) {
							const sku =
								parts[2];

							const modal =
								createModal({
									id:
										`${actionPrefix}:modal:stock:${sku}`,
									title:
										"Add Stock",
									fields: [
										{
											id:
												"amount",
											label:
												"Amount",
											placeholder:
												"100",
											required:
												true
										}
									]
								});

							await interaction.showModal(
								modal
							);

							return;
						}

						/* -------------------------------
						 * REMOVE STOCK
						 * ------------------------------- */

						if (
							action ===
							"remove_stock"
						) {
							const sku =
								parts[2];

							const modal =
								createModal({
									id:
										`${actionPrefix}:modal:remove_stock:${sku}`,
									title:
										"Remove Stock",
									fields: [
										{
											id:
												"amount",
											label:
												"Amount",
											placeholder:
												"10",
											required:
												true
										}
									]
								});

							await interaction.showModal(
								modal
							);

							return;
						}

						/* -------------------------------
						 * SET QUANTITY
						 * ------------------------------- */

						if (
							action ===
							"setstock"
						) {
							const sku =
								parts[2];

							const modal =
								createModal({
									id:
										`${actionPrefix}:modal:setstock:${sku}`,
									title:
										"Set Quantity",
									fields: [
										{
											id:
												"quantity",
											label:
												"New Quantity",
											placeholder:
												"0",
											required:
												true
										}
									]
								});

							await interaction.showModal(
								modal
							);

							return;
						}

						/* -------------------------------
						 * DELETE
						 * ------------------------------- */

						if (
							action ===
							"delete"
						) {
							const sku =
								parts[2];

							const item =
								await InventoryManager.getItem(
									guildId,
									sku
								);

							if (!item) {
								return interaction.reply({
									components: [
										errorContainer(
											"Item Not Found",
											`SKU \`${sku}\` does not exist.`
										)
									],
									flags:
										MessageFlags.IsComponentsV2,
									ephemeral: true
								});
							}

							await interaction.update(
								payload(
									new ContainerBuilder()
										.setAccentColor(
											config.Colors?.error ||
											config.Colors?.default ||
											"#ff0000"
										)
										.addTextDisplay(
											`### ${warning} Delete Item`
										)
										.addTextDisplay(
											`Are you sure you want to delete **${item.name}** (\`${item.sku}\`)?\n\nThis action cannot be undone.`
										)
										.addActionRow(
											row => {
												row.addButton({
													custom_id:
														`${actionPrefix}:confirmdelete:${sku}`,
													label:
														"Delete",
													emoji:
														trash,
													style:
														ButtonStyle.Danger
												});

												row.addButton({
													custom_id:
														`${actionPrefix}:backitem:${sku}`,
													label:
														"Cancel",
													style:
														ButtonStyle.Secondary
												});

												return row;
											}
										)
										.build()
								)
							);

							return;
						}

						/* -------------------------------
						 * CONFIRM DELETE
						 * ------------------------------- */

						if (
							action ===
							"confirmdelete"
						) {
							const sku =
								parts[2];

							const deleted =
								await InventoryManager.deleteItem(
									guildId,
									sku
								);

							if (!deleted) {
								return interaction.reply({
									components: [
										errorContainer(
											"Delete Failed",
											`SKU \`${sku}\` no longer exists.`
										)
									],
									flags:
										MessageFlags.IsComponentsV2,
									ephemeral: true
								});
							}

							await interaction.update(
								payload(
									await dashboard()
								)
							);

							return;
						}

						/* -------------------------------
						 * CANCEL DELETE
						 * ------------------------------- */

						if (
							action ===
							"backitem"
						) {
							const sku =
								parts[2];

							const item =
								await InventoryManager.getItem(
									guildId,
									sku
								);

							if (!item) {
								return interaction.update(
									payload(
										await dashboard()
									)
								);
							}

							await interaction.update(
								payload(
									await itemDetails(
										item
									)
								)
							);

							return;
						}

						/* -------------------------------
						 * PAGINATION
						 * ------------------------------- */

						const count =
							await getCount();

						const totalPages =
							Math.max(
								1,
								Math.ceil(
									count /
										PAGE_SIZE
								)
							);

						if (
							action ===
							"first"
						) {
							currentPage = 0;
						}

						if (
							action ===
							"prev"
						) {
							currentPage =
								Math.max(
									0,
									currentPage -
										1
								);
						}

						if (
							action ===
							"next"
						) {
							currentPage =
								Math.min(
									totalPages -
										1,
									currentPage +
										1
								);
						}

						if (
							action ===
							"last"
						) {
							currentPage =
								totalPages - 1;
						}

						if (
							[
								"first",
								"prev",
								"next",
								"last"
							].includes(
								action
							)
						) {
							await interaction.update(
								payload(
									await dashboard()
								)
							);
						}
					} catch (err) {
						console.error(
							"[INVENTORY] Component interaction failed:",
							err
						);

						if (
							!interaction.replied &&
							!interaction.deferred
						) {
							await interaction.reply({
								components: [
									errorContainer(
										"Operation Failed",
										err instanceof Error
											? err.message
											: "An unexpected error occurred."
									)
								],
								flags:
									MessageFlags.IsComponentsV2,
								ephemeral: true
							});
						}
					}
				}
			);

			collector.on(
				"end",
				() =>
					console.log(
						"[INVENTORY] Inventory collector ended"
					)
			);
		};

		/* =====================================================
		 * INITIAL RESPONSE
		 * ===================================================== */

		if (query) {
			const item =
				await InventoryManager.getItem(
					guildId,
					query
				);

			if (item) {
				const sent =
					await send(
						await itemDetails(item)
					);

				attachCollector(sent);

				return sent;
			}
		}

		const sent =
			await send(
				await dashboard()
			);

		attachCollector(sent);

		/*
		 * Modal submissions aren't component interactions,
		 * therefore listen for the specific modal IDs.
		 *
		 * The listener is removed when the inventory session
		 * ends to avoid leaking listeners.
		 */

		const modalHandler =
			async interaction => {
                logger.silly("Int recieved: " + interaction.customId)
				if (
					!interaction.isModalSubmit()
				) {
					return;
				}

				if (
					interaction.user.id !==
					user.id
				) {
					return;
				}

				if (
					!interaction.customId.startsWith(
						actionPrefix
					)
				) {
					return;
				}

				await handleModal(
					interaction
				);
			};

		message.client.on(
			"interactionCreate",
			modalHandler
		);

		setTimeout(() => {
			message.client.removeListener(
				"interactionCreate",
				modalHandler
			);
            message.delete().catch(() => {});
		}, 600_000);

		return sent;
	}
};