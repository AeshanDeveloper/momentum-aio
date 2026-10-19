from typing import Optional, List, Dict, Any, Callable
import discord
from enum import Enum
class ButtonBuilder:
    def __init__(self):
        self.label: Optional[str] = None
        self.custom_id: Optional[str] = None
        self.style: discord.ButtonStyle = discord.ButtonStyle.secondary
        self.emoji: Optional[str] = None
        self.url: Optional[str] = None
        self.disabled: bool = False

    def set_label(self, label: str) -> "ButtonBuilder":
        self.label = label
        return self

    def set_custom_id(self, custom_id: str) -> "ButtonBuilder":
        self.custom_id = custom_id
        return self

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

    def set_emoji(self, emoji: str) -> "ButtonBuilder":
        self.emoji = emoji
        return self

    def set_url(self, url: str) -> "ButtonBuilder":
        self.url = url
        self.style = discord.ButtonStyle.link
        return self

    def set_disabled(self, disabled: bool) -> "ButtonBuilder":
        self.disabled = disabled
        return self

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

    def set_custom_id(self, custom_id: str) -> "SelectMenuBuilder":
        self.custom_id = custom_id
        return self

    def set_placeholder(self, text: str) -> "SelectMenuBuilder":
        self.placeholder = text
        return self

    def add_option(
        self,
        label: str,
        value: str,
        description: Optional[str] = None,
        emoji: Optional[str] = None,
        default: bool = False
    ) -> "SelectMenuBuilder":
        self.options.append(
            discord.SelectOption(
                label=label,
                value=value,
                description=description,
                emoji=emoji,
                default=default
            )
        )
        return self

    def build(self) -> discord.ui.Select:
        return discord.ui.Select(
            custom_id=self.custom_id or f"select_{id(self)}",
            placeholder=self.placeholder,
            options=self.options,
            min_values=self.min_values,
            max_values=self.max_values
        )

class ActionRowBuilder:
    def __init__(self):
        self.components: List[Any] = []

    def add_button(self, builder_or_fn: Any) -> "ActionRowBuilder":
        if callable(builder_or_fn):
            b = builder_or_fn(ButtonBuilder())
            self.components.append(b.build() if isinstance(b, ButtonBuilder) else b)
        elif isinstance(builder_or_fn, ButtonBuilder):
            self.components.append(builder_or_fn.build())
        else:
            self.components.append(builder_or_fn)
        return self

    def add_select_menu(self, builder_or_fn: Any) -> "ActionRowBuilder":
        if callable(builder_or_fn):
            b = builder_or_fn(SelectMenuBuilder())
            self.components.append(b.build() if isinstance(b, SelectMenuBuilder) else b)
        elif isinstance(builder_or_fn, SelectMenuBuilder):
            self.components.append(builder_or_fn.build())
        else:
            self.components.append(builder_or_fn)
        return self

    def build(self) -> discord.ui.View:
        view = discord.ui.View(timeout=180)
        for comp in self.components:
            view.add_item(comp)
        return view

class ContainerBuilder:
    """
    Fluid message container builder creating discord.Embed objects
    mimicking the TypeScript ContainerBuilder SDK.
    """
    def __init__(self):
        self._title: Optional[str] = None
        self._description_chunks: List[str] = []
        self._accent_color: int = 0xFF7B00
        self._fields: List[Dict[str, Any]] = []
        self._footer_text: Optional[str] = None
        self._views: List[discord.ui.View] = []
        self._action_rows: List[ActionRowBuilder] = []

    def set_accent_color(self, hex_or_int: Any) -> "ContainerBuilder":
        if isinstance(hex_or_int, str):
            clean = hex_or_int.replace("#", "").strip()
            try:
                self._accent_color = int(clean, 16)
            except ValueError:
                self._accent_color = 0xFF7B00
        elif isinstance(hex_or_int, int):
            self._accent_color = hex_or_int
        return self

    def add_text_display(self, text: str) -> "ContainerBuilder":
        lines = text.strip()
        if lines.startswith("### "):
            self._title = lines[4:].strip()
        else:
            self._description_chunks.append(lines)
        return self

    def add_separator(self, divider: bool = True, spacing: Optional[str] = None) -> "ContainerBuilder":
        return self

    def add_field(self, name: str, value: str, inline: bool = False) -> "ContainerBuilder":
        self._fields.append({"name": name, "value": value, "inline": inline})
        return self

    def set_footer(self, text: str) -> "ContainerBuilder":
        self._footer_text = text
        return self

    def add_action_row(self, row_or_fn: Any) -> "ContainerBuilder":
        if callable(row_or_fn):
            r = row_or_fn(ActionRowBuilder())
            if isinstance(r, ActionRowBuilder):
                self._action_rows.append(r)
        elif isinstance(row_or_fn, ActionRowBuilder):
            self._action_rows.append(row_or_fn)
        return self

    def build_view(self) -> Optional[discord.ui.View]:
        if not self._action_rows:
            return None
        view = discord.ui.View(timeout=180)
        for row in self._action_rows:
            for item in row.components:
                view.add_item(item)
        return view

    def build(self) -> discord.Embed:
        desc = "\n\n".join(self._description_chunks) if self._description_chunks else None
        embed = discord.Embed(
            title=self._title,
            description=desc,
            color=discord.Color(self._accent_color)
        )
        for f in self._fields:
            embed.add_field(name=f["name"], value=f["value"], inline=f["inline"])
        if self._footer_text:
            embed.set_footer(text=self._footer_text)
        return embed


class SeparatorSpacingSize(Enum):
    Small = discord.SeparatorSpacing.small
    Large = discord.SeparatorSpacing.large
	
class SelectMenuTypes(Enum):
	CUSTOM = 0
	USER = 1
	ROLE = 2
	CHANNEL = 3

class ButtonStyle(Enum):
    Small = discord.SeparatorSpacing.small
    Large = discord.SeparatorSpacing.large
