
from __future__ import annotations

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


class ButtonBuilder:
    def __init__(self):
        self.label: Optional[str] = None
        self.custom_id: Optional[str] = None
        self.style = discord.ButtonStyle.secondary
        self.emoji: Optional[str] = None
        self.url: Optional[str] = None
        self.disabled = False

    def set_label(self, label: str) -> ButtonBuilder:
        self.label = label
        return self

    def set_custom_id(self, custom_id: str) -> ButtonBuilder:
        self.custom_id = custom_id
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
            if style.lower() not in mapping:
                raise ValueError(f"Unknown button style: {style}")
            self.style = mapping[style.lower()]
        return self

    def set_emoji(self, emoji: str) -> ButtonBuilder:
        self.emoji = emoji
        return self

    def set_url(self, url: str) -> ButtonBuilder:
        self.url = url
        self.style = discord.ButtonStyle.link
        return self

    def set_disabled(self, disabled: bool) -> ButtonBuilder:
        self.disabled = disabled
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
                raise ValueError("Link buttons require a URL.")
            kwargs["url"] = self.url
        else:
            if self.url:
                raise ValueError("Only link buttons can have a URL.")
            kwargs["custom_id"] = (
                self.custom_id or f"button_{id(self)}"
            )

        return discord.ui.Button(**kwargs)


class SelectMenuBuilder:
    def __init__(self):
        self.custom_id: Optional[str] = None
        self.placeholder: Optional[str] = None
        self.options: List[discord.SelectOption] = []
        self.min_values = 1
        self.max_values = 1

    def set_custom_id(self, custom_id: str) -> SelectMenuBuilder:
        self.custom_id = custom_id
        return self

    def set_placeholder(self, text: str) -> SelectMenuBuilder:
        self.placeholder = text
        return self

    def set_min_values(self, value: int) -> SelectMenuBuilder:
        self.min_values = value
        return self

    def set_max_values(self, value: int) -> SelectMenuBuilder:
        self.max_values = value
        return self

    def add_option(
        self,
        label: str,
        value: str,
        description: Optional[str] = None,
        emoji: Optional[str] = None,
        default: bool = False,
    ) -> SelectMenuBuilder:
        self.options.append(
            discord.SelectOption(
                label=label,
                value=value,
                description=description,
                emoji=emoji,
                default=default,
            )
        )
        return self

    def build(self) -> discord.ui.Select:
        if not self.options:
            raise ValueError("A string select requires at least one option.")

        return discord.ui.Select(
            custom_id=self.custom_id or f"select_{id(self)}",
            placeholder=self.placeholder,
            options=self.options,
            min_values=self.min_values,
            max_values=self.max_values,
        )


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

        self.components.append(item)
        return self

    def build(self) -> discord.ui.ActionRow:
        if not self.components:
            raise ValueError("An action row cannot be empty.")

        return discord.ui.ActionRow(*self.components)


class ContainerBuilder:
    """Fluent builder for a real Discord Components V2 container."""

    def __init__(self):
        self._accent_color: Optional[int] = 0xFF7B00
        self._components: List[Any] = []
        self._footer_text: Optional[str] = None

    def set_accent_color(self, value: Union[str, int]) -> ContainerBuilder:
        if isinstance(value, str):
            clean = value.strip().removeprefix("#")
            self._accent_color = int(clean, 16)
        else:
            self._accent_color = value

        if not 0 <= self._accent_color <= 0xFFFFFF:
            raise ValueError("Accent color must be between 0x000000 and 0xFFFFFF.")

        return self

    def add_text_display(self, text: str) -> ContainerBuilder:
        if not text.strip():
            raise ValueError("Text display cannot be empty.")

        self._components.append(discord.ui.TextDisplay(text.strip()))
        return self

    def add_separator(
        self,
        divider: bool = True,
        spacing: Optional[SeparatorSpacingSize] = None,
    ) -> ContainerBuilder:
        self._components.append(
            discord.ui.Separator(
                visible=divider,
                spacing=(
                    spacing.value
                    if spacing is not None
                    else discord.SeparatorSpacing.small
                ),
            )
        )
        return self

    def add_field(
        self,
        name: str,
        value: str,
        inline: bool = False,
    ) -> ContainerBuilder:
        # Embeds have fields; Components V2 containers do not.
        # Render fields as Markdown text instead.
        content = f"**{name}**\n{value}"
        self._components.append(discord.ui.TextDisplay(content))
        return self

    def set_footer(self, text: str) -> ContainerBuilder:
        self._footer_text = text
        return self

    def add_action_row(
        self,
        row_or_fn: Any,
    ) -> ContainerBuilder:
        if callable(row_or_fn):
            row = row_or_fn(ActionRowBuilder())
        else:
            row = row_or_fn

        if isinstance(row, ActionRowBuilder):
            self._components.append(row.build())
        elif isinstance(row, discord.ui.ActionRow):
            self._components.append(row)
        else:
            raise TypeError("Expected ActionRowBuilder or discord.ui.ActionRow.")

        return self

    def build(self) -> discord.ui.LayoutView:
        view = discord.ui.LayoutView(timeout=180)
        container = discord.ui.Container(
            *self._components,
            accent_color=self._accent_color,
        )
        view.add_item(container)
        return view
    
    def build_view(self) -> discord.ui.LayoutView:
        return self.build()
