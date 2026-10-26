from __future__ import annotations
import sys
import enum
import asyncio
from typing import Any, Optional, List, Dict, Callable, Union, Sequence

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
    private = 1
    voice = 2
    group = 3
    category = 4
    news = 5
    news_thread = 10
    public_thread = 11
    private_thread = 12
    stage_voice = 13
    forum = 15

class InteractionType(enum.Enum):
    ping = 1
    application_command = 2
    component = 3
    autocomplete = 4
    modal_submit = 5

class SeparatorSpacing(enum.Enum):
    small = 1
    large = 2
    Small = 1
    Large = 2

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

class Colour:
    def __init__(self, value: int):
        self.value = value
    @classmethod
    def blurple(cls): return cls(0x5865F2)
    @classmethod
    def red(cls): return cls(0xED4245)
    @classmethod
    def green(cls): return cls(0x57F287)
    @classmethod
    def yellow(cls): return cls(0xFEE75C)
    @classmethod
    def default(cls): return cls(0)

Color = Colour

class Permissions:
    def __init__(self, permissions: int = 0, **kwargs):
        self.value = permissions
        self.administrator = kwargs.get("administrator", False)
        self.manage_guild = kwargs.get("manage_guild", False)
        self.manage_roles = kwargs.get("manage_roles", False)
        self.manage_channels = kwargs.get("manage_channels", False)
        self.manage_webhooks = kwargs.get("manage_webhooks", False)
        self.ban_members = kwargs.get("ban_members", False)
        self.kick_members = kwargs.get("kick_members", False)
        self.view_audit_log = kwargs.get("view_audit_log", False)
        self.manage_messages = kwargs.get("manage_messages", False)
        self.send_messages = kwargs.get("send_messages", True)
        self.view_channel = kwargs.get("view_channel", True)
        for k, v in kwargs.items():
            setattr(self, k, v)

class SelectOption:
    def __init__(self, label: str, value: str, description: Optional[str] = None, emoji: Any = None, default: bool = False):
        self.label = label
        self.value = value
        self.description = description
        self.emoji = emoji
        self.default = default

    def to_dict(self):
        d = {"label": self.label, "value": self.value, "default": self.default}
        if self.description: d["description"] = self.description
        if self.emoji: d["emoji"] = self.emoji
        return d

class Embed:
    def __init__(self, **kwargs):
        self.title = kwargs.get("title")
        self.description = kwargs.get("description")
        self.color = kwargs.get("color")
        self.fields = []
    def add_field(self, name: str, value: str, inline: bool = False):
        self.fields.append({"name": name, "value": value, "inline": inline})
        return self

class File:
    def __init__(self, fp: Any, filename: Optional[str] = None):
        self.fp = fp
        self.filename = filename

class Object:
    def __init__(self, id: int):
        self.id = id

class Intents:
    def __init__(self):
        self.guilds = True
        self.members = True
        self.messages = True
        self.message_content = True
        self.dm_messages = True
    @classmethod
    def default(cls): return cls()

class utils:
    @staticmethod
    def get(iterable, **attrs):
        for item in iterable:
            if all(getattr(item, k, None) == v for k, v in attrs.items()):
                return item
        return None
    @staticmethod
    def find(predicate, iterable):
        for item in iterable:
            try:
                if predicate(item):
                    return item
            except Exception:
                pass
        return None
    @staticmethod
    def utcnow():
        import datetime
        return datetime.datetime.utcnow()

class PermissionOverwrite:
    def __init__(self, **kwargs):
        self.read_messages = kwargs.get("read_messages", None)
        self.send_messages = kwargs.get("send_messages", None)
        self.view_channel = kwargs.get("view_channel", None)
        for k, v in kwargs.items():
            setattr(self, k, v)


class DiscordException(Exception): pass
class ClientException(DiscordException): pass
class HTTPException(DiscordException):
    def __init__(self, response=None, message=None):
        self.status = getattr(response, "status", 400)
        self.text = message or ""
        super().__init__(f"{self.status} {self.text}")
class Forbidden(HTTPException): pass
class NotFound(HTTPException): pass
class InvalidArgument(ClientException): pass
class RateLimited(HTTPException):
    def __init__(self, retry_after: float = 2.0):
        self.retry_after = retry_after
        super().__init__(message=f"Rate limited. Retry after {retry_after}s")

class MessageFlags:
    def __init__(self, value: int = 0):
        self.value = value
    @classmethod
    def ephemeral(cls):
        return cls(64)

class BaseItem:
    def __init__(self, id: int = 0, name: str = ""):
        self.id = id
        self.name = name

class User(BaseItem):
    def __init__(self, id: int = 0, name: str = "", bot: bool = False):
        super().__init__(id, name)
        self.bot = bot
        self.discriminator = "0000"
        self.mention = f"<@{id}>"
    def __str__(self):
        return self.name or f"User#{self.discriminator}"
    async def send(self, *args, **kwargs):
        return Message()

class Role(BaseItem):
    def __init__(self, id: int = 0, name: str = "", position: int = 0):
        super().__init__(id, name)
        self.position = position
        self.permissions = Permissions()
        self.managed = False
        self.mention = f"<@&{id}>"
    def is_default(self): return self.position == 0

class Member(User):
    def __init__(self, id: int = 0, name: str = "", guild: Any = None):
        super().__init__(id, name)
        self.guild = guild
        self.roles = []
        self.guild_permissions = Permissions()
        self.top_role = Role(0, "default", 0)
    async def add_roles(self, *roles, **kwargs): pass
    async def remove_roles(self, *roles, **kwargs): pass
    async def kick(self, **kwargs): pass
    async def ban(self, **kwargs): pass
    async def timeout(self, *args, **kwargs): pass

class Channel(BaseItem):
    def __init__(self, id: int = 0, name: str = "", type: ChannelType = ChannelType.text):
        super().__init__(id, name)
        self.type = type
        self.guild = None
    async def send(self, *args, **kwargs): return Message()

class TextChannel(Channel):
    def __init__(self, id: int = 0, name: str = ""):
        super().__init__(id, name, ChannelType.text)
    async def send(self, *args, **kwargs): return Message()
    async def delete(self, **kwargs): pass

class VoiceChannel(Channel):
    def __init__(self, id: int = 0, name: str = ""):
        super().__init__(id, name, ChannelType.voice)

class CategoryChannel(Channel):
    def __init__(self, id: int = 0, name: str = ""):
        super().__init__(id, name, ChannelType.category)
        self.channels = []

class StageChannel(Channel): pass
class Thread(Channel): pass

class abc:
    class GuildChannel(Channel): pass
    class Messageable: pass
    class User(User): pass

class Emoji(BaseItem):
    def __init__(self, id: int = 0, name: str = "", animated: bool = False):
        super().__init__(id, name)
        self.animated = animated

class PartialEmoji(Emoji): pass
class Sticker(BaseItem): pass
GuildSticker = Sticker
class Invite(BaseItem): pass
class ScheduledEvent(BaseItem): pass

class Webhook(BaseItem):
    def __init__(self, id: int = 0, name: str = "", url: str = ""):
        super().__init__(id, name)
        self.url = url
    async def send(self, *args, **kwargs): return Message()

class AuditLogEntry:
    def __init__(self, id: int = 0, action: Any = None, user: Any = None, target: Any = None):
        self.id = id
        self.action = action
        self.user = user
        self.target = target
        self.reason = ""
        self.extra = None
        self.created_at = None

class Guild(BaseItem):
    def __init__(self, id: int = 0, name: str = ""):
        super().__init__(id, name)
        self.owner_id = 0
        self.owner = None
        self.me = None
        self.roles = []
        self.channels = []
        self.text_channels = []
        self.voice_channels = []
        self.categories = []
        self.public_updates_channel = None
        self.system_channel = None
        self.member_count: int = 1
        self.members: List[Any] = []
        self.icon: Optional[str] = None
        self.icon_url: Optional[str] = None
        self.unavailable: bool = False

    def get_channel(self, channel_id: int):
        for c in self.channels:
            if c.id == channel_id: return c
        return None

    def get_role(self, role_id: int):
        for r in self.roles:
            if r.id == role_id: return r
        return None

    def get_member(self, user_id: int):
        for m in self.members:
            if m.id == user_id: return m
        if self.me and self.me.id == user_id:
            return self.me
        if self.owner and self.owner.id == user_id:
            return self.owner
        return Member(id=user_id, name=f"User_{user_id}", guild=self)

    async def create_text_channel(self, name: str, **kwargs):
        ch_id = max([c.id for c in self.channels], default=self.id * 10) + 1
        ch = TextChannel(id=ch_id, name=name)
        ch.guild = self
        category = kwargs.get("category")
        if category:
            ch.category = category
            if hasattr(category, "channels"):
                category.channels.append(ch)
        self.channels.append(ch)
        self.text_channels.append(ch)
        return ch

    async def create_category(self, name: str, **kwargs):
        cat_id = max([c.id for c in self.categories], default=self.id * 10 + 50) + 1
        cat = CategoryChannel(id=cat_id, name=name)
        cat.guild = self
        self.categories.append(cat)
        self.channels.append(cat)
        return cat

    async def create_role(self, name: str, **kwargs):
        r_id = max([r.id for r in self.roles], default=self.id * 10 + 100) + 1
        pos = kwargs.get("position", len(self.roles))
        r = Role(id=r_id, name=name, position=pos)
        self.roles.append(r)
        return r

    async def kick(self, user, reason=None): pass
    async def ban(self, user, reason=None, delete_message_days=0): pass
    async def unban(self, user, reason=None): pass
    async def audit_logs(self, limit=10, action=None):
        return
        yield

class Message:
    def __init__(self, id: int = 1000, content: str = "", author: Any = None, channel: Any = None, guild: Any = None):
        self.id = id
        self.content = content
        self.author = author or User()
        self.channel = channel or TextChannel()
        self.guild = guild or Guild()
        self.mentions = []
        self.role_mentions = []
        self.channel_mentions = []
        self.attachments = []
        self.embeds = []
        self.components = []
    async def reply(self, *args, **kwargs): return Message()
    async def edit(self, *args, **kwargs): return Message()
    async def delete(self, **kwargs): pass

class WebhookMessage(Message): pass

class InteractionResponse:
    def __init__(self):
        self._done = False
    def is_done(self) -> bool:
        return self._done
    async def defer(self, ephemeral: bool = False, thinking: bool = False):
        self._done = True
    async def send_message(self, *args, **kwargs):
        self._done = True
        return Message()
    async def edit_message(self, *args, **kwargs):
        self._done = True
        return Message()

class Interaction:
    def __init__(self, id: int = 1, type: InteractionType = InteractionType.component, guild: Any = None, user: Any = None):
        self.id = id
        self.type = type
        self.guild = guild or Guild()
        self.user = user or User()
        self.channel = TextChannel()
        self.data = {}
        self.response = InteractionResponse()
    async def edit_original_response(self, *args, **kwargs):
        return Message()
    async def followup(self):
        pass

# ------------------------------------------------------------------------------
# UI Components
# ------------------------------------------------------------------------------
class ui:
    class Item:
        def __init__(self):
            self._view = None
            self.custom_id = f"item_{id(self)}"

    class View:
        def __init__(self, timeout: Optional[float] = 180.0):
            self.timeout = timeout
            self.children: List[Any] = []
        def add_item(self, item: Any):
            self.children.append(item)
            return self
        def stop(self): pass
        def to_components(self) -> List[Dict[str, Any]]:
            return []

    LayoutView = View

    class Button(Item):
        def __init__(self, style: ButtonStyle = ButtonStyle.secondary, label: Optional[str] = None, emoji: Any = None, custom_id: Optional[str] = None, url: Optional[str] = None, disabled: bool = False):
            super().__init__()
            self.type = 2
            self.style = style
            self.label = label
            self.emoji = emoji
            self.custom_id = custom_id or self.custom_id
            self.url = url
            self.disabled = disabled
            self.callback = None
        def to_dict(self):
            d = {"type": 2, "style": self.style.value if hasattr(self.style, "value") else self.style, "disabled": self.disabled}
            if self.label: d["label"] = self.label
            if self.custom_id: d["custom_id"] = self.custom_id
            if self.url: d["url"] = self.url
            return d

    class Select(Item):
        def __init__(self, custom_id: Optional[str] = None, placeholder: Optional[str] = None, min_values: int = 1, max_values: int = 1, options: Optional[List[SelectOption]] = None, disabled: bool = False):
            super().__init__()
            self.type = 3
            self.custom_id = custom_id or self.custom_id
            self.placeholder = placeholder
            self.min_values = min_values
            self.max_values = max_values
            self.options = options or []
            self.disabled = disabled
            self.callback = None
        def to_dict(self):
            return {
                "type": 3,
                "custom_id": self.custom_id,
                "placeholder": self.placeholder,
                "min_values": self.min_values,
                "max_values": self.max_values,
                "options": [o.to_dict() if hasattr(o, "to_dict") else o for o in self.options],
                "disabled": self.disabled
            }

    class UserSelect(Item):
        def __init__(self, custom_id: Optional[str] = None, placeholder: Optional[str] = None, min_values: int = 1, max_values: int = 1, disabled: bool = False):
            super().__init__()
            self.type = 5
            self.custom_id = custom_id or self.custom_id
            self.placeholder = placeholder
            self.min_values = min_values
            self.max_values = max_values
            self.disabled = disabled
            self.callback = None

    class RoleSelect(Item):
        def __init__(self, custom_id: Optional[str] = None, placeholder: Optional[str] = None, min_values: int = 1, max_values: int = 1, disabled: bool = False):
            super().__init__()
            self.type = 6
            self.custom_id = custom_id or self.custom_id
            self.placeholder = placeholder
            self.min_values = min_values
            self.max_values = max_values
            self.disabled = disabled
            self.callback = None

    class MentionableSelect(Item):
        def __init__(self, custom_id: Optional[str] = None, placeholder: Optional[str] = None, min_values: int = 1, max_values: int = 1, disabled: bool = False):
            super().__init__()
            self.type = 7
            self.custom_id = custom_id or self.custom_id
            self.placeholder = placeholder
            self.min_values = min_values
            self.max_values = max_values
            self.disabled = disabled
            self.callback = None

    class ChannelSelect(Item):
        def __init__(self, custom_id: Optional[str] = None, placeholder: Optional[str] = None, min_values: int = 1, max_values: int = 1, disabled: bool = False, channel_types: Optional[List[Any]] = None):
            super().__init__()
            self.type = 8
            self.custom_id = custom_id or self.custom_id
            self.placeholder = placeholder
            self.min_values = min_values
            self.max_values = max_values
            self.disabled = disabled
            self.channel_types = channel_types
            self.callback = None

    class ActionRow(Item):
        def __init__(self, *components: Any):
            super().__init__()
            self.type = 1
            self.components = list(components)
            self.children = self.components
        def to_dict(self):
            return {
                "type": 1,
                "components": [c.to_dict() if hasattr(c, "to_dict") else c for c in self.components]
            }

    class TextDisplay(Item):
        def __init__(self, content: str = ""):
            super().__init__()
            self.type = 10
            self.content = content
        def to_dict(self):
            return {"type": 10, "content": self.content}

    class Separator(Item):
        def __init__(self, visible: bool = True, spacing: Any = SeparatorSpacing.small, divider: Optional[bool] = None):
            super().__init__()
            self.type = 14
            self.divider = divider if divider is not None else visible
            self.visible = self.divider
            self.spacing = spacing.value if hasattr(spacing, "value") else spacing
        def to_dict(self):
            return {"type": 14, "divider": self.divider, "spacing": self.spacing}

    class Thumbnail(Item):
        def __init__(self, url: str):
            super().__init__()
            self.type = 11
            self.url = url
        def to_dict(self):
            return {"type": 11, "media": {"url": self.url}, "url": self.url}

    class Section(Item):
        def __init__(self, *components: Any, accessory: Any = None):
            super().__init__()
            self.type = 9
            self.components = list(components)
            self.accessory = accessory
        def to_dict(self):
            d = {"type": 9, "components": [c.to_dict() if hasattr(c, "to_dict") else c for c in self.components]}
            if self.accessory:
                d["accessory"] = self.accessory.to_dict() if hasattr(self.accessory, "to_dict") else self.accessory
            return d

    class Container(Item):
        def __init__(self, *components: Any, accent_color: Optional[int] = None, spoiler: bool = False):
            super().__init__()
            self.type = 17
            self.accent_color = accent_color
            self.spoiler = spoiler
            self.components = list(components)
        def to_dict(self):
            return {
                "type": 17,
                "accent_color": self.accent_color,
                "components": [c.to_dict() if hasattr(c, "to_dict") else c for c in self.components]
            }

class Client:
    def __init__(self, intents: Optional[Intents] = None):
        self.intents = intents or Intents.default()
        self.user = User(id=1563628961379123302, name="Sentinel™", bot=True)
        self.guilds: List[Guild] = []
        self._event_hooks: Dict[str, List[Callable]] = {}
        self._closed: bool = False
        self._ready: bool = False
        self.latency: float = 0.025

    def is_closed(self) -> bool:
        return self._closed

    def is_ready(self) -> bool:
        return self._ready

    def event(self, coro: Callable):
        name = coro.__name__
        if name not in self._event_hooks:
            self._event_hooks[name] = []
        self._event_hooks[name].append(coro)
        return coro

    def add_guild(self, guild: Guild) -> None:
        if not any(g.id == guild.id for g in self.guilds):
            self.guilds.append(guild)

    async def start(self, token: str):
        self._closed = False
        self._ready = False

        # If a live Discord bot token is provided, attempt to fetch user info and guilds via REST API
        if token and len(token) > 20 and not token.startswith("sentinel_"):
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    headers = {"Authorization": f"Bot {token}"}
                    # 1. Fetch current bot user
                    try:
                        async with session.get(
                            "https://discord.com/api/v10/users/@me",
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=4)
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                self.user.id = int(data.get("id", self.user.id))
                                self.user.name = data.get("username", self.user.name)
                                if data.get("global_name"):
                                    self.user.global_name = data.get("global_name")
                    except Exception:
                        pass

                    # 2. Fetch bot guilds
                    try:
                        async with session.get(
                            "https://discord.com/api/v10/users/@me/guilds?with_counts=true",
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=4)
                        ) as resp:
                            if resp.status == 200:
                                guilds_data = await resp.json()
                                for g_data in guilds_data:
                                    gid = int(g_data["id"])
                                    if not any(g.id == gid for g in self.guilds):
                                        g_obj = Guild(id=gid, name=g_data.get("name", f"Guild {gid}"))
                                        g_obj.owner_id = int(g_data.get("owner_id", 0)) if g_data.get("owner_id") else 0
                                        g_obj.member_count = g_data.get("approximate_member_count") or g_data.get("member_count") or 1
                                        g_obj.icon = g_data.get("icon")
                                        self.guilds.append(g_obj)
                    except Exception:
                        pass
            except Exception:
                pass

        self._ready = True
        if "on_ready" in self._event_hooks:
            for hook in self._event_hooks["on_ready"]:
                try:
                    res = hook()
                    if hasattr(res, "__await__"):
                        await res
                except Exception:
                    pass

    async def close(self):
        self._closed = True
        self._ready = False

    async def wait_until_ready(self):
        while not self._ready:
            await asyncio.sleep(0.05)

    async def change_presence(self, *args, **kwargs):
        pass

    def get_guild(self, guild_id: int):
        for g in self.guilds:
            if g.id == guild_id: return g
        return None

    def get_channel(self, channel_id: int):
        for g in self.guilds:
            c = g.get_channel(channel_id)
            if c: return c
        return None

    def get_user(self, user_id: int):
        return None

    async def fetch_user(self, user_id: int):
        return User(id=user_id, name=f"User_{user_id}")

    async def fetch_channel(self, channel_id: int):
        return self.get_channel(channel_id) or TextChannel(id=channel_id)

    async def fetch_guild(self, guild_id: int):
        return self.get_guild(guild_id) or Guild(id=guild_id)
