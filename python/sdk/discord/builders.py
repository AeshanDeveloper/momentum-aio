from __future__ import annotations

import re
from typing import Optional, List, Dict, Any, Callable, Union
from enum import Enum
import discord


class SeparatorSpacingSize(Enum):
    Small = discord.SeparatorSpacing.small
    Large = discord.SeparatorSpacing.large


class SelectMenuTypes(Enum):
    CUSTOM = 0
    USER = 1
    ROLE = 2
    CHANNEL = 3


class ButtonStyle(Enum):
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

# Central backward compatibility for discord.ButtonStyle
try:
    _mc = type(discord.ButtonStyle)
    for _cap, _low in [
        ("Danger", "danger"),
        ("Secondary", "secondary"),
        ("Primary", "primary"),
        ("Success", "success"),
        ("Link", "link")
    ]:
        if not hasattr(_mc, _cap):
            setattr(_mc, _cap, property(lambda cls, l=_low: getattr(cls, l)))
except Exception:
    pass


class ButtonBuilder:
    def __init__(self):
        self.label: Optional[str] = None
        self.custom_id: Optional[str] = None
        self.style: discord.ButtonStyle = discord.ButtonStyle.secondary
        self.emoji: Optional[Union[str, discord.PartialEmoji, discord.Emoji]] = None
        self.url: Optional[str] = None
        self.disabled: bool = False
        self.callback: Optional[Callable] = None

    def set_label(self, label: str) -> ButtonBuilder:
        if isinstance(label, str):
            from config.strings import render_string, get_string
            if "{emoji:" in label:
                label = render_string(label)
            elif "." in label and not " " in label:
                val = get_string(label)
                if val:
                    label = val
        self.label = str(label)[:80] if label is not None else None
        return self

    def set_custom_id(self, custom_id: str) -> ButtonBuilder:
        self.custom_id = str(custom_id)[:100] if custom_id is not None else None
        return self

    def set_style(self, style: Union[str, ButtonStyle, discord.ButtonStyle]) -> ButtonBuilder:
        if isinstance(style, ButtonStyle):
            self.style = style.value
        elif isinstance(style, discord.ButtonStyle):
            self.style = style
        elif isinstance(style, str):
            mapping = {
                "primary": discord.ButtonStyle.primary,
                "secondary": discord.ButtonStyle.secondary,
                "success": discord.ButtonStyle.success,
                "danger": discord.ButtonStyle.danger,
                "link": discord.ButtonStyle.link,
            }
            clean = style.lower().strip()
            if clean not in mapping:
                raise ValueError(f"Unknown button style: {style}")
            self.style = mapping[clean]
        return self

    def set_emoji(self, emoji: Union[str, discord.PartialEmoji, discord.Emoji]) -> ButtonBuilder:
        if isinstance(emoji, str):
            from config.settings import EMOJIS
            from config.strings import render_string
            if emoji.startswith("{emoji:") and emoji.endswith("}"):
                emoji = render_string(emoji)
            elif emoji in EMOJIS and EMOJIS.get(emoji):
                emoji = EMOJIS.get(emoji)
        self.emoji = emoji
        return self

    def set_url(self, url: str) -> ButtonBuilder:
        self.url = url
        self.style = discord.ButtonStyle.link
        return self

    def set_disabled(self, disabled: bool) -> ButtonBuilder:
        self.disabled = bool(disabled)
        return self

    def set_callback(self, callback: Callable) -> ButtonBuilder:
        self.callback = callback
        return self

    def build(self) -> discord.ui.Button:
        kwargs: Dict[str, Any] = {
            "style": self.style,
            "disabled": self.disabled,
        }

        if self.label is not None:
            kwargs["label"] = self.label
        if self.emoji is not None:
            kwargs["emoji"] = self.emoji

        if self.style == discord.ButtonStyle.link:
            if not self.url:
                raise ValueError("Link buttons require a valid URL.")
            kwargs["url"] = self.url
        else:
            if self.url:
                raise ValueError("Only link buttons can have a URL.")
            kwargs["custom_id"] = self.custom_id or f"btn_{id(self)}"

        btn = discord.ui.Button(**kwargs)
        if self.callback:
            btn.callback = self.callback
        return btn


class SelectMenuBuilder:
    def __init__(self):
        self.custom_id: Optional[str] = None
        self.placeholder: Optional[str] = None
        self.options: List[discord.SelectOption] = []
        self.min_values: int = 1
        self.max_values: int = 1
        self.disabled: bool = False
        self.menu_type: SelectMenuTypes = SelectMenuTypes.CUSTOM
        self.callback: Optional[Callable] = None

    def set_custom_id(self, custom_id: str) -> SelectMenuBuilder:
        self.custom_id = str(custom_id)[:100] if custom_id is not None else None
        return self

    def set_placeholder(self, text: str) -> SelectMenuBuilder:
        if isinstance(text, str):
            from config.strings import render_string, get_string
            if "{emoji:" in text:
                text = render_string(text)
            elif "." in text and not " " in text:
                val = get_string(text)
                if val:
                    text = val
        self.placeholder = str(text)[:150] if text is not None else None
        return self

    def set_min_values(self, value: int) -> SelectMenuBuilder:
        self.min_values = max(0, int(value))
        return self

    def set_max_values(self, value: int) -> SelectMenuBuilder:
        self.max_values = max(1, int(value))
        return self

    def set_disabled(self, disabled: bool) -> SelectMenuBuilder:
        self.disabled = bool(disabled)
        return self

    def set_type(self, menu_type: SelectMenuTypes) -> SelectMenuBuilder:
        self.menu_type = menu_type
        return self

    def set_menu_type(self, menu_type: SelectMenuTypes) -> SelectMenuBuilder:
        return self.set_type(menu_type)

    def add_option(
        self,
        label: str,
        value: str,
        description: Optional[str] = None,
        emoji: Optional[Union[str, discord.PartialEmoji, discord.Emoji]] = None,
        default: bool = False,
    ) -> SelectMenuBuilder:
        from config.settings import EMOJIS
        from config.strings import render_string
        if isinstance(emoji, str):
            if emoji.startswith("{emoji:") and emoji.endswith("}"):
                emoji = render_string(emoji)
            elif emoji in EMOJIS and EMOJIS.get(emoji):
                emoji = EMOJIS.get(emoji)
        if isinstance(label, str) and "{emoji:" in label:
            label = render_string(label)
        if isinstance(description, str) and "{emoji:" in description:
            description = render_string(description)

        self.options.append(
            discord.SelectOption(
                label=str(label)[:100],
                value=str(value)[:100],
                description=str(description)[:100] if description else None,
                emoji=emoji if emoji else None,
                default=bool(default),
            )
        )
        return self

    def set_options(
        self,
        options: List[Union[discord.SelectOption, Dict[str, Any], str]]
    ) -> SelectMenuBuilder:
        self.options = []
        for opt in options:
            if isinstance(opt, discord.SelectOption):
                self.options.append(opt)
            elif isinstance(opt, dict):
                self.add_option(
                    label=str(opt.get("label", "Option")),
                    value=str(opt.get("value", opt.get("label", "option"))),
                    description=str(opt.get("description")) if opt.get("description") else None,
                    emoji=opt.get("emoji"),
                    default=bool(opt.get("default", False)),
                )
            elif isinstance(opt, (list, tuple)) and len(opt) >= 2:
                self.add_option(label=str(opt[0]), value=str(opt[1]))
            else:
                self.add_option(label=str(opt), value=str(opt))
        return self

    def set_callback(self, callback: Callable) -> SelectMenuBuilder:
        self.callback = callback
        return self

    def build(self) -> Union[discord.ui.Select, discord.ui.UserSelect, discord.ui.RoleSelect, discord.ui.ChannelSelect]:
        cid = self.custom_id or f"sel_{id(self)}"

        if self.menu_type == SelectMenuTypes.USER:
            item = discord.ui.UserSelect(
                custom_id=cid,
                placeholder=self.placeholder,
                min_values=self.min_values,
                max_values=self.max_values,
                disabled=self.disabled,
            )
        elif self.menu_type == SelectMenuTypes.ROLE:
            item = discord.ui.RoleSelect(
                custom_id=cid,
                placeholder=self.placeholder,
                min_values=self.min_values,
                max_values=self.max_values,
                disabled=self.disabled,
            )
        elif self.menu_type == SelectMenuTypes.CHANNEL:
            item = discord.ui.ChannelSelect(
                custom_id=cid,
                placeholder=self.placeholder,
                min_values=self.min_values,
                max_values=self.max_values,
                disabled=self.disabled,
            )
        else:
            if not self.options:
                self.add_option(label="No options", value="none")
            item = discord.ui.Select(
                custom_id=cid,
                placeholder=self.placeholder,
                options=self.options[:25],
                min_values=min(self.min_values, len(self.options)),
                max_values=min(self.max_values, len(self.options)),
                disabled=self.disabled,
            )

        if self.callback:
            item.callback = self.callback
        return item


class ActionRowBuilder:
    def __init__(self):
        self.components: List[Any] = []

    def add_button(self, builder_or_fn: Any) -> ActionRowBuilder:
        if callable(builder_or_fn):
            item = builder_or_fn(ButtonBuilder())
            if isinstance(item, ButtonBuilder):
                item = item.build()
        elif isinstance(builder_or_fn, ButtonBuilder):
            item = builder_or_fn.build()
        else:
            item = builder_or_fn

        if item is not None:
            self.components.append(item)
        return self

    def add_select_menu(self, builder_or_fn: Any) -> ActionRowBuilder:
        if callable(builder_or_fn):
            item = builder_or_fn(SelectMenuBuilder())
            if isinstance(item, SelectMenuBuilder):
                item = item.build()
        elif isinstance(builder_or_fn, SelectMenuBuilder):
            item = builder_or_fn.build()
        else:
            item = builder_or_fn

        if item is not None:
            self.components.append(item)
        return self

    def add_component(self, component: Any) -> ActionRowBuilder:
        if component is not None:
            self.components.append(component)
        return self

    def build(self) -> discord.ui.ActionRow:
        if not self.components:
            raise ValueError("An ActionRow cannot be empty.")
        return discord.ui.ActionRow(*self.components)


class ComponentCollector:
    def __init__(self, view: ComponentLayoutView, target_message: Any = None, timeout: float = 300.0, filter_func: Optional[Callable] = None):
        self.view = view
        self.target_message = target_message
        self.timeout = timeout
        self.filter_func = filter_func
        self.handlers: Dict[str, Callable] = {}
        self.global_handler: Optional[Callable] = None

    def on(self, custom_id_or_event: str, callback: Callable) -> ComponentCollector:
        self.handlers[custom_id_or_event] = callback
        self._wire_component(custom_id_or_event, callback)
        return self

    def on_interaction(self, callback: Callable) -> ComponentCollector:
        self.global_handler = callback
        for comp in self.view.get_interactive_components():
            old_cb = comp.callback
            async def wrapped_global(interaction: discord.Interaction, _comp=comp, _old=old_cb):
                if self.filter_func and not self.filter_func(interaction):
                    try:
                        from .response import send_ui
                        await send_ui(interaction, "permissions.owner_only", ephemeral=True)
                    except Exception:
                        pass
                    return
                if _old:
                    await _old(interaction)
                await callback(interaction)
            comp.callback = wrapped_global
        return self

    def _is_match(self, cid: str, target: Any) -> bool:
        if hasattr(target, "match"):
            return bool(target.match(cid)) or bool(getattr(target, "search", lambda s: False)(cid))
        s_target = str(target)
        return cid == s_target or cid.startswith(f"{s_target}:") or s_target.startswith(f"{cid}:")

    def update_view(self, new_view: ComponentLayoutView) -> None:
        self.view = new_view
        new_view._collector = self
        self._rewire_all()

    def _rewire_all(self) -> None:
        if self.global_handler:
            self.on_interaction(self.global_handler)
        for target, handler in self.handlers.items():
            self._wire_component(target, handler)

    def _wire_component(self, custom_id: Any, callback: Callable) -> None:
        def make_cb(cb, expected_id):
            async def wrapped(interaction: discord.Interaction):
                if self.filter_func and not self.filter_func(interaction):
                    try:
                        from .response import send_ui
                        await send_ui(interaction, "permissions.owner_only", ephemeral=True)
                    except Exception:
                        pass
                    return
                await cb(interaction)
            return wrapped

        for comp in self.view.get_interactive_components():
            cid = getattr(comp, "custom_id", None)
            if cid and self._is_match(cid, custom_id):
                comp.callback = make_cb(callback, cid)


class ComponentLayoutView(discord.ui.LayoutView):
    def __init__(self, timeout: Optional[float] = 180.0):
        super().__init__(timeout=timeout)
        self._collector: Optional[ComponentCollector] = None

    def add_item(self, item: Any) -> ComponentLayoutView:
        super().add_item(item)
        if self._collector:
            self._collector._rewire_all()
        return self

    @property
    def view(self) -> ComponentLayoutView:
        return self

    @property
    def embed(self) -> None:
        return None

    def build(self) -> ComponentLayoutView:
        return self

    def build_view(self) -> ComponentLayoutView:
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {}

    def get_interactive_components(self) -> List[Any]:
        items = []
        for child in self.children:
            if hasattr(child, "children"):
                for sub in child.children:
                    if hasattr(sub, "children"):
                        items.extend(sub.children)
                    else:
                        items.append(sub)
            else:
                items.append(child)
        return items

    def create_message_component_collector(
        self,
        target_message: Any = None,
        timeout: float = 300.0,
        filter_func: Optional[Callable] = None,
    ) -> ComponentCollector:
        self._collector = ComponentCollector(self, target_message, timeout, filter_func)
        return self._collector


class ContainerBuilder:
    def __init__(self):
        self._accent_color: Optional[int] = 0x0844C5
        self._components: List[Any] = []
        self._footer_text: Optional[str] = None
        self._timeout: float = 180.0

    def set_accent_color(self, value: Union[str, int, discord.Colour]) -> ContainerBuilder:
        if isinstance(value, str):
            from config.settings import COLORS
            if value in COLORS:
                value = COLORS[value]
            clean = str(value).strip().removeprefix("#")
            try:
                self._accent_color = int(clean, 16)
            except ValueError:
                self._accent_color = 0x0844C5
        elif isinstance(value, int):
            self._accent_color = value
        elif isinstance(value, discord.Colour):
            self._accent_color = value.value
        else:
            self._accent_color = 0x0844C5

        self._accent_color = max(0, min(0xFFFFFF, self._accent_color))
        return self

    def add_text_display(self, text: str) -> ContainerBuilder:
        if text is not None and str(text).strip():
            from config.strings import render_string
            rendered = render_string(str(text).strip())
            self._components.append(discord.ui.TextDisplay(rendered))
        return self

    def add_separator(
        self,
        divider: bool = True,
        spacing: Optional[SeparatorSpacingSize] = None,
    ) -> ContainerBuilder:
        sp_val = spacing.value if isinstance(spacing, SeparatorSpacingSize) else (
            spacing if isinstance(spacing, discord.SeparatorSpacing) else discord.SeparatorSpacing.small
        )
        self._components.append(discord.ui.Separator(visible=bool(divider), spacing=sp_val))
        return self

    def add_field(
        self,
        name: str,
        value: str,
        inline: bool = False,
    ) -> ContainerBuilder:
        from config.strings import render_string
        rend_name = render_string(str(name))
        rend_val = render_string(str(value))
        content = f"**{rend_name}**\n{rend_val}"
        self._components.append(discord.ui.TextDisplay(content))
        return self

    def set_footer(self, text: str, icon_url: Optional[str] = None) -> ContainerBuilder:
        if text:
            from config.strings import render_string
            self._footer_text = render_string(str(text))
        else:
            self._footer_text = None
        return self

    def set_timeout(self, timeout: float) -> ContainerBuilder:
        self._timeout = float(timeout)
        return self

    def add_action_row(self, row_or_fn: Any) -> ContainerBuilder:
        if callable(row_or_fn):
            row = row_or_fn(ActionRowBuilder())
        else:
            row = row_or_fn

        if isinstance(row, ActionRowBuilder):
            built_row = row.build()
            self._components.append(built_row)
        elif isinstance(row, discord.ui.ActionRow):
            self._components.append(row)
        elif row is not None:
            self._components.append(row)

        return self

    def build_container(self) -> discord.ui.Container:
        comps = list(self._components)
        if self._footer_text:
            comps.append(discord.ui.Separator(visible=False, spacing=discord.SeparatorSpacing.small))
            comps.append(discord.ui.TextDisplay(f"-# {self._footer_text}"))

        return discord.ui.Container(
            *comps,
            accent_color=self._accent_color,
        )

    def build(self) -> ComponentLayoutView:
        view = ComponentLayoutView(timeout=self._timeout)
        container = self.build_container()
        view.add_item(container)
        return view

    def build_view(self) -> ComponentLayoutView:
        return self.build()


def build_ui(
    key: Optional[str] = None,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    details: Optional[str] = None,
    footer: Optional[str] = None,
    style: Optional[str] = None,
    color: Optional[Union[str, int, discord.Colour]] = None,
    variables: Optional[Dict[str, Any]] = None,
    action_rows: Optional[List[Any]] = None,
    components: Optional[List[Any]] = None,
    timeout: float = 180.0,
) -> ComponentLayoutView:
    from config.strings import get_string_def, render_string
    from config.settings import COLORS

    node: Any = None
    if key:
        node = get_string_def(key)

    def_title = None
    def_desc = None
    def_details = None
    def_footer = None
    def_style = "default"
    def_color = None

    if isinstance(node, dict):
        def_title = node.get("title")
        def_desc = node.get("description") or node.get("desc")
        def_details = node.get("details")
        def_footer = node.get("footer")
        def_style = node.get("style", "default")
        def_color = node.get("color")
    elif isinstance(node, str):
        def_desc = node

    final_title = title if title is not None else def_title
    final_desc = description if description is not None else def_desc
    final_details = details if details is not None else def_details
    final_footer = footer if footer is not None else def_footer
    final_style = (style or def_style or "default").lower().strip()

    vars_dict = dict(variables or {})

    res_title = render_string(final_title, vars_dict) if final_title else None
    res_desc = render_string(final_desc, vars_dict) if final_desc else None
    res_details = render_string(final_details, vars_dict) if final_details else None
    res_footer = render_string(final_footer, vars_dict) if final_footer else None

    # Resolve accent color
    accent_val = color or def_color
    if accent_val is None:
        style_color_key = {
            "success": "success",
            "error": "error",
            "danger": "error",
            "warning": "warning",
            "warn": "warning",
            "info": "info",
            "default": "default",
            "neutral": "neutral",
        }.get(final_style, "default")
        accent_val = COLORS.get(style_color_key, COLORS.get("default", "#0844C5"))

    builder = ContainerBuilder().set_accent_color(accent_val).set_timeout(timeout)

    if res_title:
        builder.add_text_display(f"### {res_title}")
        if res_desc or res_details:
            builder.add_separator(divider=True, spacing=SeparatorSpacingSize.Small)

    if res_desc:
        builder.add_text_display(res_desc)

    if res_details:
        builder.add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        builder.add_text_display(res_details)

    if res_footer:
        builder.set_footer(res_footer)

    if action_rows:
        for r in action_rows:
            builder.add_action_row(r)

    if components:
        for c in components:
            if isinstance(c, (ActionRowBuilder, discord.ui.ActionRow)):
                builder.add_action_row(c)
            elif isinstance(c, (ButtonBuilder, discord.ui.Button)):
                builder.add_action_row(lambda row: row.add_button(c))
            elif isinstance(c, (SelectMenuBuilder, discord.ui.Select, discord.ui.UserSelect, discord.ui.RoleSelect, discord.ui.ChannelSelect)):
                builder.add_action_row(lambda row: row.add_select_menu(c))

    return builder.build()


# Monkey-patches
if not hasattr(discord.ui.Container, "build"):
    def _container_build_patch(self) -> ComponentLayoutView:
        v = ComponentLayoutView()
        v.add_item(self)
        return v
    discord.ui.Container.build = _container_build_patch

if not hasattr(discord.ui.Container, "build_view"):
    discord.ui.Container.build_view = discord.ui.Container.build

if not hasattr(discord.ui.Container, "embed"):
    discord.ui.Container.embed = property(lambda self: None)

if not hasattr(discord.ui.LayoutView, "build"):
    discord.ui.LayoutView.build = lambda self: self

if not hasattr(discord.ui.LayoutView, "build_view"):
    discord.ui.LayoutView.build_view = lambda self: self

if not hasattr(discord.ui.LayoutView, "to_dict"):
    discord.ui.LayoutView.to_dict = lambda self: {}

if not hasattr(discord.ui.LayoutView, "embed"):
    discord.ui.LayoutView.embed = property(lambda self: None)
