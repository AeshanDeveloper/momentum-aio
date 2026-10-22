import sys
import enum
from typing import Any, List, Optional, Dict, Union
from unittest.mock import MagicMock, AsyncMock

class MessageFlags:
    def __init__(self, value: int = 0, **kwargs):
        self.value = value
        self.ephemeral = kwargs.get("ephemeral", False)

class InteractionType(enum.Enum):
    ping = 1
    application_command = 2
    component = 3
    autocomplete = 4
    modal_submit = 5

class ButtonStyle(enum.Enum):
    primary = 1
    secondary = 2
    success = 3
    danger = 4
    link = 5
    Primary = 1
    Secondary = 2
    Success = 3
    Danger = 4
    Link = 5

class ChannelType(enum.Enum):
    text = 0
    voice = 2
    category = 4
    news = 5
    forum = 15

class SeparatorSpacing(enum.Enum):
    small = 1
    large = 2

class AuditLogAction(enum.Enum):
    guild_update = 1
    channel_create = 10
    channel_update = 11
    channel_delete = 12
    channel_overwrite_create = 13
    channel_overwrite_update = 14
    channel_overwrite_delete = 15
    member_kick = 20
    member_prune = 21
    member_ban_add = 22
    member_ban_remove = 23
    member_update = 24
    member_role_update = 25
    member_move = 26
    member_disconnect = 27
    bot_add = 28
    role_create = 30
    role_update = 31
    role_delete = 32
    invite_create = 40
    invite_update = 41
    invite_delete = 42
    webhook_create = 50
    webhook_update = 51
    webhook_delete = 52
    emoji_create = 60
    emoji_update = 61
    emoji_delete = 62
    message_delete = 72
    message_bulk_delete = 73
    message_pin = 74
    message_unpin = 75
    integration_create = 80
    integration_update = 81
    integration_delete = 82
    stage_instance_create = 83
    stage_instance_update = 84
    stage_instance_delete = 85
    sticker_create = 90
    sticker_update = 91
    sticker_delete = 92
    scheduled_event_create = 100
    scheduled_event_update = 101
    scheduled_event_delete = 102
    thread_create = 110
    thread_update = 111
    thread_delete = 112
    automod_rule_create = 140
    automod_rule_update = 141
    automod_rule_delete = 142
    automod_block_message = 143
    automod_flag_to_channel = 144
    automod_user_communication_disabled = 145
    ban = 22
    unban = 23
    kick = 20

class SelectOption:
    def __init__(self, label: str, value: str, description: Optional[str] = None, emoji: Any = None, default: bool = False):
        self.label = label
        self.value = value
        self.description = description
        self.emoji = emoji
        self.default = default

    def to_dict(self) -> Dict[str, Any]:
        d = {"label": self.label, "value": self.value, "default": self.default}
        if self.description:
            d["description"] = self.description
        if self.emoji:
            d["emoji"] = self.emoji
        return d

class Colour:
    def __init__(self, value: int):
        self.value = value

Color = Colour

class PartialEmoji:
    def __init__(self, name: str, id: Optional[int] = None, animated: bool = False):
        self.name = name
        self.id = id
        self.animated = animated

Emoji = PartialEmoji
GuildSticker = PartialEmoji

class Permissions:
    def __init__(self, permissions: int = 0, **kwargs):
        self.value = permissions
        for k, v in kwargs.items():
            setattr(self, k, bool(v))

    administrator = False
    manage_guild = False
    manage_roles = False
    manage_channels = False
    ban_members = False
    kick_members = False
    manage_webhooks = False
    view_audit_log = True

class Intents:
    def __init__(self):
        self.guilds = True
        self.members = True
        self.messages = True
        self.message_content = True
        self.dm_messages = True

    @classmethod
    def default(cls):
        return cls()

class utils:
    @staticmethod
    def utcnow():
        import datetime
        return datetime.datetime.now(datetime.timezone.utc)

class abc:
    class GuildChannel:
        pass

class CategoryChannel(abc.GuildChannel):
    pass

class TextChannel(abc.GuildChannel):
    pass

class VoiceChannel(abc.GuildChannel):
    pass

class StageChannel(abc.GuildChannel):
    pass

class ForumChannel(abc.GuildChannel):
    pass

class Thread(abc.GuildChannel):
    pass

class Guild:
    pass

class Member:
    pass

class User:
    pass

class Role:
    pass

class Invite:
    pass

class AuditLogEntry:
    pass

class Message:
    async def reply(self, *args, **kwargs):
        return self
    async def delete(self, *args, **kwargs):
        pass
    async def edit(self, *args, **kwargs):
        return self

class WebhookMessage(Message):
    pass

class Embed:
    pass

class Interaction:
    pass

class Client:
    def __init__(self, *args, **kwargs):
        self.user = MagicMock()
        self.guilds = []
        self.latency = 0.015
        self._events = {}

    def event(self, coro):
        self._events[coro.__name__] = coro
        return coro

    def is_ready(self) -> bool:
        return True

    def is_closed(self) -> bool:
        return False

    async def start(self, token: str) -> None:
        pass

    async def close(self) -> None:
        pass

class ui:
    class Item:
        def __init__(self, *args, **kwargs):
            self.custom_id = kwargs.get("custom_id", f"item_{id(self)}")
            self.callback = None
            for k, v in kwargs.items():
                setattr(self, k, v)

    class Button(Item):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.label = kwargs.get("label")
            self.style = kwargs.get("style", ButtonStyle.secondary)
            self.disabled = kwargs.get("disabled", False)
            self.emoji = kwargs.get("emoji")
            self.url = kwargs.get("url")

    class Select(Item):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.placeholder = kwargs.get("placeholder")
            self.min_values = kwargs.get("min_values", 1)
            self.max_values = kwargs.get("max_values", 1)
            self.disabled = kwargs.get("disabled", False)
            self.options = kwargs.get("options", [])

    class UserSelect(Select):
        pass

    class RoleSelect(Select):
        pass

    class ChannelSelect(Select):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.channel_types = kwargs.get("channel_types", [])

    class TextDisplay(Item):
        def __init__(self, text: str):
            super().__init__()
            self.text = text

    class Separator(Item):
        def __init__(self, visible: bool = True, spacing: Any = None):
            super().__init__()
            self.visible = visible
            self.spacing = spacing

    class ActionRow(Item):
        def __init__(self, *components):
            super().__init__()
            self.children = list(components)

    class Container(Item):
        def __init__(self, *components, accent_color: Any = None):
            super().__init__()
            self.children = list(components)
            self.accent_color = accent_color

    class LayoutView:
        def __init__(self, timeout: Optional[float] = 180.0):
            self.children: List[Any] = []
            self.timeout = timeout

        def add_item(self, item: Any):
            self.children.append(item)
            return self

    class View(LayoutView):
        pass
