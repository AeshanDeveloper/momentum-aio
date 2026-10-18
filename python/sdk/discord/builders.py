import re
import asyncio
from typing import Optional, List, Dict, Any, Callable, Union
import discord

class MessageFlags:
    IsComponentsV2 = 1 << 15

class SeparatorSpacingSize:
    Small = "small"
    Large = "large"

class SelectMenuTypes:
    CUSTOM = 3
    STRING = 3
    USER = 5
    ROLE = 6
    MENTION = 7
    CHANNEL = 8

class ButtonStyle:
    Primary = discord.ButtonStyle.primary
    Secondary = discord.ButtonStyle.secondary
    Success = discord.ButtonStyle.success
    Danger = discord.ButtonStyle.danger
    Link = discord.ButtonStyle.link
    primary = discord.ButtonStyle.primary
    secondary = discord.ButtonStyle.secondary
    success = discord.ButtonStyle.success
    danger = discord.ButtonStyle.danger
    link = discord.ButtonStyle.link

def parse_emoji(value: Any) -> Optional[Union[str, discord.PartialEmoji]]:
    if not value:
        return None
    if isinstance(value, discord.PartialEmoji):
        return value
    if isinstance(value, dict):
        name = value.get("name")
        id_val = value.get("id")
        animated = value.get("animated", False)
        if id_val:
            return discord.PartialEmoji(name=name, id=int(id_val), animated=animated)
        return name
    text = str(value).strip()
    match = re.match(r"^<(a?):([a-zA-Z0-9_]+):(\d+)>$", text)
    if match:
        animated = match.group(1) == "a"
        name = match.group(2)
        emoji_id = int(match.group(3))
        return discord.PartialEmoji(name=name, id=emoji_id, animated=animated)
    return text

class ButtonBuilder:
    def __init__(self):
        self.label: Optional[str] = None
        self.custom_id: Optional[str] = None
        self.style: discord.ButtonStyle = discord.ButtonStyle.secondary
        self.emoji: Optional[Union[str, discord.PartialEmoji]] = None
        self.url: Optional[str] = None
        self.disabled: bool = False

    def set_label(self, label: Optional[str]) -> "ButtonBuilder":
        self.label = label
        return self
    setLabel = set_label

    def set_custom_id(self, custom_id: str) -> "ButtonBuilder":
        self.custom_id = custom_id
        return self
    setCustomId = set_custom_id

    def set_style(self, style: Any) -> "ButtonBuilder":
        if isinstance(style, str):
            mapping = {
                "primary": discord.ButtonStyle.primary,
                "secondary": discord.ButtonStyle.secondary,
                "success": discord.ButtonStyle.success,
                "danger": discord.ButtonStyle.danger,
                "link": discord.ButtonStyle.link,
            }
            self.style = mapping.get(style.lower(), discord.ButtonStyle.secondary)
        elif isinstance(style, discord.ButtonStyle):
            self.style = style
        return self
    setStyle = set_style

    def set_emoji(self, emoji: Any) -> "ButtonBuilder":
        self.emoji = parse_emoji(emoji)
        return self
    setEmoji = set_emoji

    def set_url(self, url: str) -> "ButtonBuilder":
        self.url = url
        self.style = discord.ButtonStyle.link
        return self
    setURL = set_url
    setUrl = set_url

    def set_disabled(self, disabled: bool) -> "ButtonBuilder":
        self.disabled = disabled
        return self
    setDisabled = set_disabled

    def build(self) -> discord.ui.Button:
        kwargs: Dict[str, Any] = {
            "label": self.label,
            "style": self.style,
            "disabled": self.disabled,
        }
        if self.emoji:
            kwargs["emoji"] = self.emoji
        if self.url:
            kwargs["url"] = self.url
        elif self.custom_id:
            kwargs["custom_id"] = self.custom_id
        else:
            kwargs["custom_id"] = "btn_" + str(id(self))
        return discord.ui.Button(**kwargs)

class SelectMenuBuilder:
    def __init__(self):
        self.custom_id: Optional[str] = None
        self.placeholder: Optional[str] = None
        self.options: List[discord.SelectOption] = []
        self.min_values: int = 1
        self.max_values: int = 1
        self.disabled: bool = False

    def set_custom_id(self, custom_id: str) -> "SelectMenuBuilder":
        self.custom_id = custom_id
        return self
    setCustomId = set_custom_id

    def set_placeholder(self, text: str) -> "SelectMenuBuilder":
        self.placeholder = text
        return self
    setPlaceholder = set_placeholder

    def set_min_values(self, val: int) -> "SelectMenuBuilder":
        self.min_values = val
        return self
    setMinValues = set_min_values

    def set_max_values(self, val: int) -> "SelectMenuBuilder":
        self.max_values = val
        return self
    setMaxValues = set_max_values

    def set_disabled(self, disabled: bool) -> "SelectMenuBuilder":
        self.disabled = disabled
        return self
    setDisabled = set_disabled

    def add_option(
        self,
        label: str,
        value: str,
        description: Optional[str] = None,
        emoji: Optional[Any] = None,
        default: bool = False,
        isDefault: Optional[bool] = None
    ) -> "SelectMenuBuilder":
        self.options.append(
            discord.SelectOption(
                label=str(label)[:100],
                value=str(value)[:100],
                description=str(description)[:100] if description else None,
                emoji=parse_emoji(emoji),
                default=isDefault if isDefault is not None else default
            )
        )
        return self
    addOption = add_option

    def build(self) -> discord.ui.Select:
        return discord.ui.Select(
            custom_id=self.custom_id or f"select_{id(self)}",
            placeholder=self.placeholder,
            options=self.options,
            min_values=self.min_values,
            max_values=self.max_values,
            disabled=self.disabled
        )

class ActionRowBuilder:
    def __init__(self):
        self.components: List[Any] = []

    def add_components(self, components: Any) -> "ActionRowBuilder":
        if not isinstance(components, list):
            components = [components]
        for comp in components:
            if len(self.components) >= 5:
                break
            if isinstance(comp, (ButtonBuilder, SelectMenuBuilder)):
                self.components.append(comp.build())
            elif isinstance(comp, discord.ui.Item):
                self.components.append(comp)
        return self
    addComponents = add_components

    def add_button(self, builder_or_fn_or_kwargs: Any = None, **kwargs) -> "ActionRowBuilder":
        if callable(builder_or_fn_or_kwargs):
            b = builder_or_fn_or_kwargs(ButtonBuilder())
            btn = b.build() if isinstance(b, ButtonBuilder) else b
            self.components.append(btn)
        elif isinstance(builder_or_fn_or_kwargs, ButtonBuilder):
            self.components.append(builder_or_fn_or_kwargs.build())
        elif isinstance(builder_or_fn_or_kwargs, discord.ui.Button):
            self.components.append(builder_or_fn_or_kwargs)
        elif isinstance(builder_or_fn_or_kwargs, dict):
            b = ButtonBuilder()
            opts = builder_or_fn_or_kwargs
            if "label" in opts: b.set_label(opts["label"])
            if "custom_id" in opts: b.set_custom_id(opts["custom_id"])
            if "style" in opts: b.set_style(opts["style"])
            if "emoji" in opts: b.set_emoji(opts["emoji"])
            if "url" in opts: b.set_url(opts["url"])
            disabled = opts.get("disabled", opts.get("isDisabled", False))
            b.set_disabled(disabled)
            self.components.append(b.build())
        elif kwargs:
            b = ButtonBuilder()
            if "label" in kwargs: b.set_label(kwargs["label"])
            if "custom_id" in kwargs: b.set_custom_id(kwargs["custom_id"])
            if "style" in kwargs: b.set_style(kwargs["style"])
            if "emoji" in kwargs: b.set_emoji(kwargs["emoji"])
            if "url" in kwargs: b.set_url(kwargs["url"])
            disabled = kwargs.get("disabled", kwargs.get("isDisabled", False))
            b.set_disabled(disabled)
            self.components.append(b.build())
        return self
    addButton = add_button

    def add_select_menu(self, builder_or_fn_or_kwargs: Any = None, **kwargs) -> "ActionRowBuilder":
        if callable(builder_or_fn_or_kwargs):
            b = builder_or_fn_or_kwargs(SelectMenuBuilder())
            menu = b.build() if isinstance(b, SelectMenuBuilder) else b
            self.components.append(menu)
        elif isinstance(builder_or_fn_or_kwargs, SelectMenuBuilder):
            self.components.append(builder_or_fn_or_kwargs.build())
        elif isinstance(builder_or_fn_or_kwargs, discord.ui.Select):
            self.components.append(builder_or_fn_or_kwargs)
        elif isinstance(builder_or_fn_or_kwargs, dict):
            opts = builder_or_fn_or_kwargs
            b = SelectMenuBuilder()
            if "custom_id" in opts: b.set_custom_id(opts["custom_id"])
            if "placeholder" in opts: b.set_placeholder(opts["placeholder"])
            if "minValues" in opts: b.set_min_values(opts["minValues"])
            elif "min_values" in opts: b.set_min_values(opts["min_values"])
            if "maxValues" in opts: b.set_max_values(opts["maxValues"])
            elif "max_values" in opts: b.set_max_values(opts["max_values"])
            disabled = opts.get("disabled", opts.get("isDisabled", False))
            b.set_disabled(disabled)
            for opt in opts.get("options", []):
                if isinstance(opt, dict):
                    b.add_option(
                        label=opt.get("label", "Option"),
                        value=opt.get("value", opt.get("label", "value")),
                        description=opt.get("description"),
                        emoji=opt.get("emoji"),
                        default=opt.get("default", opt.get("isDefault", False))
                    )
            self.components.append(b.build())
        elif kwargs:
            b = SelectMenuBuilder()
            if "custom_id" in kwargs: b.set_custom_id(kwargs["custom_id"])
            if "placeholder" in kwargs: b.set_placeholder(kwargs["placeholder"])
            if "minValues" in kwargs: b.set_min_values(kwargs["minValues"])
            elif "min_values" in kwargs: b.set_min_values(kwargs["min_values"])
            if "maxValues" in kwargs: b.set_max_values(kwargs["maxValues"])
            elif "max_values" in kwargs: b.set_max_values(kwargs["max_values"])
            disabled = kwargs.get("disabled", kwargs.get("isDisabled", False))
            b.set_disabled(disabled)
            for opt in kwargs.get("options", []):
                if isinstance(opt, dict):
                    b.add_option(
                        label=opt.get("label", "Option"),
                        value=opt.get("value", opt.get("label", "value")),
                        description=opt.get("description"),
                        emoji=opt.get("emoji"),
                        default=opt.get("default", opt.get("isDefault", False))
                    )
            self.components.append(b.build())
        return self
    addSelectMenu = add_select_menu
    addStringSelectMenu = add_select_menu
    add_string_select_menu = add_select_menu

    def build(self) -> "ActionRowBuilder":
        return self

    def toJSON(self) -> Dict[str, Any]:
        return {"type": 1, "components": [getattr(c, "to_component_dict", lambda: {})() for c in self.components]}

class SeparatorBuilder:
    def __init__(self):
        self.divider = True
        self.spacing = SeparatorSpacingSize.Small

    def set_divider(self, divider: bool) -> "SeparatorBuilder":
        self.divider = divider
        return self
    setDivider = set_divider

    def set_spacing(self, spacing: str) -> "SeparatorBuilder":
        self.spacing = spacing
        return self
    setSpacing = set_spacing

    def build(self) -> "SeparatorBuilder":
        return self

class TextDisplayBuilder:
    def __init__(self, content: str = ""):
        self.content = content

    def set_content(self, text: str) -> "TextDisplayBuilder":
        self.content = text
        return self
    setContent = set_content

    def build(self) -> "TextDisplayBuilder":
        return self

class SectionBuilder:
    def __init__(self):
        self.texts: List[str] = []
        self.button: Optional[Any] = None

    def add_text_display(self, text: str) -> "SectionBuilder":
        self.texts.append(text)
        return self
    addTextDisplay = add_text_display

    def add_button(self, btn: Any) -> "SectionBuilder":
        self.button = btn
        return self
    addButton = add_button

    def build(self) -> "SectionBuilder":
        return self

class MessageComponentCollector:
    """
    Message component collector providing .on('collect', fn) and .on('end', fn)
    matching discord.js collectors in Python.
    """
    def __init__(self, message: Any = None, view: Optional[discord.ui.View] = None, time_ms: float = 300_000, filter_fn: Optional[Callable[[Any], bool]] = None):
        self.message = message
        self.view = view
        self.time_seconds = time_ms / 1000.0 if time_ms > 1000 else time_ms
        self.filter_fn = filter_fn
        self._listeners: Dict[str, List[Callable[[Any], Any]]] = {"collect": [], "end": []}
        self.is_ended = False

        if self.view:
            self._wire_view(self.view)

        # Schedule timeout
        if self.time_seconds > 0:
            asyncio.create_task(self._schedule_timeout())

    def _wire_view(self, view: discord.ui.View):
        collector = self
        view.timeout = self.time_seconds

        for item in view.children:
            original_callback = getattr(item, "callback", None)

            async def item_cb(interaction: discord.Interaction, it=item, orig=original_callback):
                await collector._handle_interaction(interaction)
                if orig and orig != item_cb:
                    try:
                        await orig(interaction)
                    except Exception:
                        pass

            item.callback = item_cb

    def on(self, event: str, listener: Callable[[Any], Any]) -> "MessageComponentCollector":
        if event in self._listeners:
            self._listeners[event].append(listener)
        return self

    async def _handle_interaction(self, interaction: discord.Interaction):
        if self.is_ended:
            return

        # Augment interaction with discord.js-compatible helpers
        setattr(interaction, "customId", interaction.data.get("custom_id", "") if interaction.data else "")
        setattr(interaction, "values", interaction.data.get("values", []) if interaction.data else [])
        setattr(interaction, "isButton", lambda: interaction.data.get("component_type") == 2 if interaction.data else False)
        setattr(interaction, "is_button", interaction.isButton)

        async def defer_update():
            if not interaction.response.is_done():
                await interaction.response.defer()
        setattr(interaction, "deferUpdate", defer_update)

        async def update_msg(payload: Any):
            embed = None
            view = None
            if isinstance(payload, dict):
                components = payload.get("components", [])
                if components and isinstance(components[0], BuiltContainer):
                    embed = components[0].to_embed()
                    view = components[0].to_view()
                elif "embed" in payload:
                    embed = payload["embed"]
                    view = payload.get("view")
            elif isinstance(payload, BuiltContainer):
                embed = payload.to_embed()
                view = payload.to_view()

            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                if hasattr(interaction, "message") and interaction.message:
                    await interaction.message.edit(embed=embed, view=view)
                elif hasattr(interaction, "edit_original_response"):
                    await interaction.edit_original_response(embed=embed, view=view)
        setattr(interaction, "update", update_msg)

        # Filter check
        if self.filter_fn:
            try:
                allowed = self.filter_fn(interaction)
                if not allowed:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("❌ You are not authorized to use these buttons.", ephemeral=True)
                    return
            except Exception:
                return

        for cb in list(self._listeners.get("collect", [])):
            try:
                res = cb(interaction)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as err:
                pass

    async def _schedule_timeout(self):
        await asyncio.sleep(self.time_seconds)
        self.stop()

    def stop(self):
        if not self.is_ended:
            self.is_ended = True
            for cb in list(self._listeners.get("end", [])):
                try:
                    res = cb()
                    if asyncio.iscoroutine(res):
                        asyncio.create_task(res)
                except Exception:
                    pass

class BuiltContainer(discord.Embed):
    """
    Subclass of discord.Embed that also carries view action rows and components.
    Works directly anywhere a discord.Embed or discord.ui.View is expected!
    """
    def __init__(
        self,
        title: Optional[str] = None,
        description: Optional[str] = None,
        color: Optional[discord.Color] = None,
        fields: Optional[List[Dict[str, Any]]] = None,
        footer: Optional[str] = None,
        view: Optional[discord.ui.View] = None,
        action_rows: Optional[List[ActionRowBuilder]] = None
    ):
        super().__init__(title=title, description=description, color=color or discord.Color(0x0844C5))
        self.view: discord.ui.View = view or discord.ui.View(timeout=300)
        self.action_rows = action_rows or []
        for f in (fields or []):
            self.add_field(name=f["name"], value=f["value"], inline=f.get("inline", False))
        if footer:
            self.set_footer(text=footer)

    def to_embed(self) -> discord.Embed:
        return self

    def to_view(self) -> discord.ui.View:
        return self.view

    def toJSON(self) -> Dict[str, Any]:
        return {
            "type": 17,
            "embed": self.to_dict(),
            "components": [r.toJSON() for r in self.action_rows]
        }

class ContainerBuilder:
    """
    Rich Discord ContainerBuilder matching TypeScript SDK ContainerBuilder.
    Constructs both discord.Embed representation and interactive discord.ui.View rows.
    """
    def __init__(self):
        self._accent_color: int = 0x0844C5
        self._title: Optional[str] = None
        self._text_chunks: List[str] = []
        self._fields: List[Dict[str, Any]] = []
        self._footer_text: Optional[str] = None
        self._action_rows: List[ActionRowBuilder] = []
        self._spoiler: bool = False
        self._id: str = "not_set"

    def set_accent_color(self, hex_or_int: Any = "#0844C5") -> "ContainerBuilder":
        if isinstance(hex_or_int, str):
            clean = hex_or_int.replace("#", "").strip()
            try:
                self._accent_color = int(clean, 16)
            except ValueError:
                self._accent_color = 0x0844C5
        elif isinstance(hex_or_int, int):
            self._accent_color = hex_or_int
        return self
    setAccentColor = set_accent_color

    def add_separator(self, opts: Any = None, **kwargs) -> "ContainerBuilder":
        # Separator visually represented cleanly in embed text
        self._text_chunks.append("---")
        return self
    addSeparator = add_separator
    addSeparatorComponents = add_separator

    def add_text_display(self, text: str = "") -> "ContainerBuilder":
        lines = str(text).strip()
        if lines.startswith("### ") and not self._title:
            parts = lines[4:].split("\n", 1)
            self._title = parts[0].strip()
            if len(parts) > 1 and parts[1].strip():
                self._text_chunks.append(parts[1].strip())
        else:
            self._text_chunks.append(lines)
        return self
    addTextDisplay = add_text_display
    addTextDisplayComponents = add_text_display

    def add_section(self, mappings: Any) -> "ContainerBuilder":
        if callable(mappings):
            sec = mappings(SectionBuilder())
            if isinstance(sec, SectionBuilder):
                for t in sec.texts:
                    self.add_text_display(t)
                if sec.button:
                    row = ActionRowBuilder()
                    row.add_button(sec.button)
                    self._action_rows.append(row)
        return self
    addSection = add_section
    addSectionComponents = add_section

    def add_action_row(self, mappings: Any) -> "ContainerBuilder":
        if callable(mappings):
            row = ActionRowBuilder()
            res = mappings(row)
            if isinstance(res, ActionRowBuilder):
                self._action_rows.append(res)
            else:
                self._action_rows.append(row)
        elif isinstance(mappings, ActionRowBuilder):
            self._action_rows.append(mappings)
        return self
    addActionRow = add_action_row
    addActionRowComponents = add_action_row

    def set_spoiler(self, is_spoiler: bool) -> "ContainerBuilder":
        self._spoiler = is_spoiler
        return self
    setSpoiler = set_spoiler

    def set_id(self, custom_id: str = "not_set") -> "ContainerBuilder":
        self._id = custom_id
        return self
    setId = set_id

    def add_field(self, name: str, value: str, inline: bool = False) -> "ContainerBuilder":
        self._fields.append({"name": name, "value": value, "inline": inline})
        return self
    addField = add_field

    def set_footer(self, text: str) -> "ContainerBuilder":
        self._footer_text = text
        return self
    setFooter = set_footer

    def build_view(self, timeout: float = 300) -> discord.ui.View:
        view = discord.ui.View(timeout=timeout)
        row_idx = 0
        for action_row in self._action_rows:
            for comp in action_row.components:
                if hasattr(comp, "row"):
                    comp.row = min(row_idx, 4)
                view.add_item(comp)
            row_idx += 1
        return view

    def build(self) -> BuiltContainer:
        # Assemble description
        chunks = []
        for c in self._text_chunks:
            if c == "---":
                if chunks and chunks[-1] != "":
                    chunks.append("────────────────────────")
            else:
                chunks.append(c)

        desc = "\n\n".join(chunks) if chunks else None
        view = self.build_view()

        container = BuiltContainer(
            title=self._title,
            description=desc,
            color=discord.Color(self._accent_color),
            fields=self._fields,
            footer=self._footer_text,
            view=view,
            action_rows=self._action_rows
        )
        return container

    def toJSON(self) -> Dict[str, Any]:
        return self.build().toJSON()

def attach_collector(
    sent_or_interaction: Any,
    view: Optional[discord.ui.View] = None,
    time_ms: float = 300_000,
    filter_fn: Optional[Callable[[Any], bool]] = None
) -> MessageComponentCollector:
    """
    Attaches a MessageComponentCollector to a sent message or interaction.
    Also injects createMessageComponentCollector onto the object for discord.js compatibility.
    """
    target_view = view
    if not target_view and hasattr(sent_or_interaction, "view"):
        target_view = sent_or_interaction.view

    collector = MessageComponentCollector(
        message=sent_or_interaction,
        view=target_view,
        time_ms=time_ms,
        filter_fn=filter_fn
    )

    def create_collector_fn(opts: Optional[Dict[str, Any]] = None, **kwargs) -> MessageComponentCollector:
        options = opts or kwargs or {}
        time_val = options.get("time", 300_000)
        filter_val = options.get("filter")
        return MessageComponentCollector(
            message=sent_or_interaction,
            view=target_view,
            time_ms=time_val,
            filter_fn=filter_val
        )

    setattr(sent_or_interaction, "createMessageComponentCollector", create_collector_fn)
    setattr(sent_or_interaction, "create_message_component_collector", create_collector_fn)
    return collector
