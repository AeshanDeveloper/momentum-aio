from __future__ import annotations
import sys
import enum
import asyncio
import time
import json
import logging
from typing import Any, Optional, List, Dict, Callable, Union, Sequence

_discord_logger = logging.getLogger("MomentumOne.Discord")

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
    def to_dict(self):
        d = {}
        if self.title: d["title"] = self.title
        if self.description: d["description"] = self.description
        if self.color:
            c = self.color.value if hasattr(self.color, "value") else self.color
            d["color"] = int(c)
        if self.fields:
            d["fields"] = [{"name": str(f["name"]), "value": str(f["value"]), "inline": bool(f.get("inline", False))} for f in self.fields]
        return d

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

class AllowedMentions:
    def __init__(self, everyone: bool = False, users: bool = True, roles: bool = False, replied_user: bool = True):
        self.everyone = everyone
        self.users = users
        self.roles = roles
        self.replied_user = replied_user

    @classmethod
    def none(cls):
        return cls(everyone=False, users=False, roles=False, replied_user=False)

    @classmethod
    def all(cls):
        return cls(everyone=True, users=True, roles=True, replied_user=True)

    def to_dict(self):
        parse = []
        if self.everyone: parse.append("everyone")
        if self.users: parse.append("users")
        if self.roles: parse.append("roles")
        return {"parse": parse, "replied_user": self.replied_user}

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
        self.global_name = None
        self.mention = f"<@{id}>"
    def __str__(self):
        return self.name or f"User#{self.discriminator}"
    async def send(self, *args, **kwargs):
        client = Client._default_instance
        if client and client.token:
            dm_id = await client.http_get_or_create_dm(self.id)
            if dm_id:
                content = args[0] if args else kwargs.get("content")
                return await client.http_send_message(dm_id, content=content, **kwargs)
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
        self._client = None
    async def send(self, *args, **kwargs):
        client = getattr(self, "_client", None) or Client._default_instance
        if client and client.token:
            content = args[0] if args else kwargs.get("content")
            return await client.http_send_message(self.id, content=content, **kwargs)
        return Message(channel=self, guild=getattr(self, "guild", None))

class TextChannel(Channel):
    def __init__(self, id: int = 0, name: str = ""):
        super().__init__(id, name, ChannelType.text)
    async def send(self, *args, **kwargs):
        client = getattr(self, "_client", None) or Client._default_instance
        if client and client.token:
            content = args[0] if args else kwargs.get("content")
            return await client.http_send_message(self.id, content=content, **kwargs)
        return Message(channel=self, guild=getattr(self, "guild", None))
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

def serialize_discord_payload(
    content: Optional[str] = None,
    *,
    embed: Optional[Any] = None,
    embeds: Optional[List[Any]] = None,
    view: Optional[Any] = None,
    message_reference: Optional[Dict[str, Any]] = None,
    allowed_mentions: Optional[Any] = None,
    ephemeral: bool = False,
    **kwargs: Any
) -> Dict[str, Any]:
    out_content = str(content) if content is not None else ""
    out_embeds: List[Dict[str, Any]] = []
    out_components: List[Dict[str, Any]] = []

    raw_embeds = []
    if embed:
        raw_embeds.append(embed)
    if embeds:
        raw_embeds.extend(embeds)

    for e in raw_embeds:
        if hasattr(e, "to_dict"):
            out_embeds.append(e.to_dict())
        elif isinstance(e, dict):
            out_embeds.append(e)
        else:
            emb_dict: Dict[str, Any] = {}
            if getattr(e, "title", None): emb_dict["title"] = str(e.title)
            if getattr(e, "description", None): emb_dict["description"] = str(e.description)
            if getattr(e, "color", None):
                c = e.color.value if hasattr(e.color, "value") else e.color
                if c: emb_dict["color"] = int(c)
            if getattr(e, "fields", None):
                emb_dict["fields"] = [{"name": str(f.get("name", "")), "value": str(f.get("value", "")), "inline": bool(f.get("inline", False))} for f in e.fields]
            if emb_dict:
                out_embeds.append(emb_dict)

    if view:
        children = getattr(view, "children", None)
        if children is None and (hasattr(view, "components") or hasattr(view, "_components")):
            children = [view]
        elif children is None:
            children = [view]

        for child in (children or []):
            if child is None:
                continue
            # If child is Container or has components and accent_color
            if hasattr(child, "components") and hasattr(child, "accent_color"):
                cont_title = getattr(child, "title", None)
                cont_color = getattr(child, "accent_color", None)
                cont_desc_lines: List[str] = []
                cont_footer = None
                cont_thumbnail = None
                cont_fields: List[Dict[str, Any]] = []

                for comp in getattr(child, "components", []):
                    c_type = getattr(comp, "type", None)
                    if c_type == 10:  # TextDisplay
                        t_content = getattr(comp, "content", "")
                        if t_content:
                            t_str = str(t_content).strip()
                            if t_str.startswith("-# "):
                                cont_footer = t_str[3:].strip()
                            elif not cont_title and (t_str.startswith("### ") or t_str.startswith("## ") or t_str.startswith("# ")):
                                cont_title = t_str.lstrip("#").strip()
                            else:
                                cont_desc_lines.append(t_str)
                    elif c_type == 14:  # Separator
                        if (getattr(comp, "divider", False) or getattr(comp, "visible", False)) and cont_desc_lines:
                            cont_desc_lines.append("────────────────────────")
                    elif c_type == 11:  # Thumbnail
                        cont_thumbnail = getattr(comp, "url", None)
                    elif c_type == 1 or hasattr(comp, "components"):  # ActionRow
                        out_components.append(comp.to_dict() if hasattr(comp, "to_dict") else comp)
                    elif hasattr(comp, "to_dict"):
                        out_components.append({"type": 1, "components": [comp.to_dict()]})

                emb_dict = {}
                if cont_title: emb_dict["title"] = str(cont_title)
                if cont_desc_lines: emb_dict["description"] = "\n".join(cont_desc_lines)
                if cont_color is not None:
                    c_val = cont_color.value if hasattr(cont_color, "value") else cont_color
                    if c_val: emb_dict["color"] = int(c_val)
                if cont_footer: emb_dict["footer"] = {"text": str(cont_footer)}
                if cont_thumbnail: emb_dict["thumbnail"] = {"url": str(cont_thumbnail)}
                if emb_dict:
                    out_embeds.append(emb_dict)
            elif getattr(child, "type", None) == 1 or hasattr(child, "components"):
                out_components.append(child.to_dict() if hasattr(child, "to_dict") else child)
            elif hasattr(child, "to_dict"):
                out_components.append({"type": 1, "components": [child.to_dict()]})

    payload: Dict[str, Any] = {}
    if out_content:
        payload["content"] = out_content
    if out_embeds:
        payload["embeds"] = out_embeds
    if out_components:
        payload["components"] = out_components
    if message_reference:
        payload["message_reference"] = message_reference
    if allowed_mentions:
        payload["allowed_mentions"] = allowed_mentions.to_dict() if hasattr(allowed_mentions, "to_dict") else allowed_mentions
    if ephemeral:
        payload["flags"] = 64

    if not payload.get("content") and not payload.get("embeds") and not payload.get("components"):
        payload["content"] = "\u200b"

    return payload

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
        self._client = None

    async def reply(self, *args, **kwargs):
        client = getattr(self, "_client", None) or Client._default_instance
        if client and client.token:
            content = args[0] if args else kwargs.get("content")
            kwargs["message_reference"] = {
                "message_id": self.id,
                "channel_id": self.channel.id,
                "fail_if_not_exists": False
            }
            return await client.http_send_message(self.channel.id, content=content, **kwargs)
        return Message(id=int(time.time() * 1000), content=str(args[0] if args else kwargs.get("content", "")), channel=self.channel, guild=self.guild)

    async def edit(self, *args, **kwargs):
        client = getattr(self, "_client", None) or Client._default_instance
        if client and client.token:
            content = args[0] if args else kwargs.get("content")
            return await client.http_edit_message(self.channel.id, self.id, content=content, **kwargs)
        if args: self.content = str(args[0])
        elif "content" in kwargs: self.content = str(kwargs["content"])
        return self

    async def delete(self, **kwargs):
        client = getattr(self, "_client", None) or Client._default_instance
        if client and client.token:
            await client.http_delete_message(self.channel.id, self.id)

class WebhookMessage(Message): pass

class InteractionResponse:
    def __init__(self, interaction: Optional[Any] = None, client: Optional[Any] = None):
        self._done = False
        self._interaction = interaction
        self._client = client

    def is_done(self) -> bool:
        return self._done

    async def defer(self, ephemeral: bool = False, thinking: bool = False):
        self._done = True
        client = self._client or getattr(self._interaction, "_client", None) or Client._default_instance
        if client and client.token and self._interaction:
            await client.http_interaction_callback(
                self._interaction.id,
                self._interaction.token,
                callback_type=5,
                data={"flags": 64} if ephemeral else None
            )

    async def send_message(self, *args, **kwargs):
        self._done = True
        client = self._client or getattr(self._interaction, "_client", None) or Client._default_instance
        if client and client.token and self._interaction:
            content = args[0] if args else kwargs.get("content")
            return await client.http_interaction_send_message(self._interaction, content=content, **kwargs)
        return Message(channel=getattr(self._interaction, "channel", None), guild=getattr(self._interaction, "guild", None))

    async def edit_message(self, *args, **kwargs):
        self._done = True
        client = self._client or getattr(self._interaction, "_client", None) or Client._default_instance
        if client and client.token and self._interaction:
            content = args[0] if args else kwargs.get("content")
            return await client.http_interaction_edit_message(self._interaction, content=content, **kwargs)
        return Message(channel=getattr(self._interaction, "channel", None), guild=getattr(self._interaction, "guild", None))

class InteractionFollowup:
    def __init__(self, interaction: Optional[Any] = None, client: Optional[Any] = None):
        self._interaction = interaction
        self._client = client

    async def send(self, *args, **kwargs):
        client = self._client or getattr(self._interaction, "_client", None) or Client._default_instance
        if client and client.token and self._interaction:
            content = args[0] if args else kwargs.get("content")
            return await client.http_followup_send(self._interaction, content=content, **kwargs)
        return Message(channel=getattr(self._interaction, "channel", None), guild=getattr(self._interaction, "guild", None))

class Interaction:
    def __init__(self, id: int = 1, type: InteractionType = InteractionType.component, guild: Any = None, user: Any = None):
        self.id = id
        self.token = ""
        self.type = type
        self.guild = guild or Guild()
        self.user = user or User()
        self.channel = TextChannel()
        self.data = {}
        self._client = None
        self.response = InteractionResponse(self)
        self.followup = InteractionFollowup(self)

    async def edit_original_response(self, *args, **kwargs):
        client = self._client or Client._default_instance
        if client and client.token:
            content = args[0] if args else kwargs.get("content")
            return await client.http_edit_original_response(self, content=content, **kwargs)
        return Message(channel=self.channel, guild=self.guild)

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
            return [c.to_dict() if hasattr(c, "to_dict") else c for c in self.children]

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
        def to_dict(self):
            return {"type": 5, "custom_id": self.custom_id, "placeholder": self.placeholder, "min_values": self.min_values, "max_values": self.max_values, "disabled": self.disabled}

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
        def to_dict(self):
            return {"type": 6, "custom_id": self.custom_id, "placeholder": self.placeholder, "min_values": self.min_values, "max_values": self.max_values, "disabled": self.disabled}

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
        def to_dict(self):
            return {"type": 7, "custom_id": self.custom_id, "placeholder": self.placeholder, "min_values": self.min_values, "max_values": self.max_values, "disabled": self.disabled}

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
        def to_dict(self):
            return {"type": 8, "custom_id": self.custom_id, "placeholder": self.placeholder, "min_values": self.min_values, "max_values": self.max_values, "disabled": self.disabled}

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
    _default_instance: Optional[Client] = None

    def __init__(self, intents: Optional[Intents] = None):
        Client._default_instance = self
        self.intents = intents or Intents.default()
        self.user = User(id=1563628961379123302, name="Sentinel™", bot=True)
        self.guilds: List[Guild] = []
        self._event_hooks: Dict[str, List[Callable]] = {}
        self._closed: bool = False
        self._ready: bool = False
        self.latency: float = 0.025
        self.token: Optional[str] = None
        self._session: Any = None
        self._ws: Any = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._seq: Optional[int] = None
        self._session_id: Optional[str] = None
        self._resume_gateway_url: Optional[str] = None
        self._gateway_url: str = "wss://gateway.discord.gg/?v=10&encoding=json"
        self._last_heartbeat_sent: float = 0.0
        self._heartbeat_acked: bool = True
        self._intents_val: int = 3276799

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

    async def _dispatch_event(self, event_name: str, *args, **kwargs):
        if event_name in self._event_hooks:
            for hook in self._event_hooks[event_name]:
                try:
                    res = hook(*args, **kwargs)
                    if hasattr(res, "__await__"):
                        asyncio.create_task(res)
                except Exception as err:
                    _discord_logger.error(f"[Gateway] Error in {event_name} handler: {err}")

    async def _fetch_bot_guilds_rest(self):
        if not self.token or not self._session:
            return
        headers = {"Authorization": f"Bot {self.token}"}
        try:
            import aiohttp
            async with self._session.get(
                "https://discord.com/api/v10/users/@me/guilds?with_counts=true",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status == 200:
                    guilds_data = await resp.json()
                    new_guilds = []
                    for g_data in guilds_data:
                        gid = int(g_data["id"])
                        existing = self.get_guild(gid)
                        if existing:
                            existing.name = g_data.get("name", existing.name)
                            existing.icon = g_data.get("icon", existing.icon)
                            existing.member_count = g_data.get("approximate_member_count") or g_data.get("member_count") or existing.member_count
                            existing.owner_id = int(g_data.get("owner_id", existing.owner_id or 0))
                            new_guilds.append(existing)
                        else:
                            g_obj = Guild(id=gid, name=g_data.get("name", f"Guild {gid}"))
                            g_obj.owner_id = int(g_data.get("owner_id", 0)) if g_data.get("owner_id") else 0
                            g_obj.member_count = g_data.get("approximate_member_count") or g_data.get("member_count") or 1
                            g_obj.icon = g_data.get("icon")
                            new_guilds.append(g_obj)
                    self.guilds = new_guilds
        except Exception as err:
            _discord_logger.debug(f"[Gateway] Error fetching guilds REST: {err}")

    async def _heartbeat_loop(self, ws: Any, interval: float):
        try:
            while not ws.closed and not self._closed:
                await asyncio.sleep(interval)
                if ws.closed or self._closed:
                    break
                self._last_heartbeat_sent = time.perf_counter()
                self._heartbeat_acked = False
                await ws.send_json({"op": 1, "d": self._seq})
        except asyncio.CancelledError:
            pass
        except Exception as err:
            _discord_logger.debug(f"[Gateway] Heartbeat exception: {err}")

    async def _handle_dispatch(self, t: str, d: Any):
        if not t or not d:
            return

        if t == "READY":
            user_data = d.get("user", {})
            self.user.id = int(user_data.get("id", self.user.id))
            self.user.name = user_data.get("username", self.user.name)
            self.user.discriminator = user_data.get("discriminator", "0000")
            if user_data.get("global_name"):
                self.user.global_name = user_data.get("global_name")
            self._session_id = d.get("session_id")
            if d.get("resume_gateway_url"):
                self._resume_gateway_url = f"{d['resume_gateway_url']}?v=10&encoding=json"

            # Fetch live guild list via REST
            await self._fetch_bot_guilds_rest()

            self._ready = True
            await self._dispatch_event("on_ready")

        elif t == "RESUMED":
            self._ready = True
            _discord_logger.info("[Gateway] Session successfully resumed.")
            await self._dispatch_event("on_resumed")

        elif t == "GUILD_CREATE":
            gid = int(d["id"])
            existing = self.get_guild(gid)
            if existing:
                guild = existing
                guild.name = d.get("name", guild.name)
                guild.icon = d.get("icon", guild.icon)
                guild.member_count = d.get("member_count", guild.member_count)
                guild.owner_id = int(d.get("owner_id", guild.owner_id or 0))
            else:
                guild = Guild(id=gid, name=d.get("name", f"Guild {gid}"))
                guild.icon = d.get("icon")
                guild.member_count = d.get("member_count", 1)
                guild.owner_id = int(d.get("owner_id", 0)) if d.get("owner_id") else 0
                self.guilds.append(guild)

            # Channels
            guild.channels = []
            guild.text_channels = []
            guild.voice_channels = []
            guild.categories = []
            for ch_data in d.get("channels", []):
                ch_id = int(ch_data["id"])
                ch_type = ch_data.get("type", 0)
                ch_name = ch_data.get("name", "")
                if ch_type == 4:
                    cat = CategoryChannel(id=ch_id, name=ch_name)
                    cat.guild = guild
                    cat._client = self
                    guild.categories.append(cat)
                    guild.channels.append(cat)
                elif ch_type == 2:
                    vc = VoiceChannel(id=ch_id, name=ch_name)
                    vc.guild = guild
                    vc._client = self
                    guild.voice_channels.append(vc)
                    guild.channels.append(vc)
                else:
                    tc = TextChannel(id=ch_id, name=ch_name)
                    tc.guild = guild
                    tc._client = self
                    guild.text_channels.append(tc)
                    guild.channels.append(tc)

            # Roles
            guild.roles = []
            for r_data in d.get("roles", []):
                r_id = int(r_data["id"])
                role = Role(id=r_id, name=r_data.get("name", ""), position=r_data.get("position", 0))
                guild.roles.append(role)

            # Bot member
            me = Member(id=self.user.id, name=self.user.name, guild=guild)
            me.bot = True
            guild.me = me

            await self._dispatch_event("on_guild_join", guild)

        elif t == "GUILD_DELETE":
            gid = int(d["id"])
            if not d.get("unavailable", False):
                removed = self.get_guild(gid)
                if removed:
                    self.guilds = [g for g in self.guilds if g.id != gid]
                    await self._dispatch_event("on_guild_remove", removed)

        elif t == "GUILD_UPDATE":
            gid = int(d["id"])
            before = self.get_guild(gid)
            after = Guild(id=gid, name=d.get("name", getattr(before, "name", "")))
            if before:
                after.owner_id = int(d.get("owner_id", before.owner_id))
                after.icon = d.get("icon", before.icon)
            await self._dispatch_event("on_guild_update", before, after)

        elif t == "MESSAGE_CREATE":
            msg_id = int(d["id"])
            content = d.get("content", "")
            channel_id = int(d.get("channel_id", 0))
            guild_id = int(d["guild_id"]) if d.get("guild_id") else None

            guild = self.get_guild(guild_id) if guild_id else None
            channel = (guild.get_channel(channel_id) if guild else None) or self.get_channel(channel_id)
            if not channel:
                channel = TextChannel(id=channel_id, name="channel")
                channel._client = self
                if guild:
                    channel.guild = guild
                    guild.channels.append(channel)
                    guild.text_channels.append(channel)

            author_data = d.get("author", {})
            author_id = int(author_data.get("id", 0))
            author_name = author_data.get("username", "Unknown")
            is_bot = bool(author_data.get("bot", False))

            if guild:
                author = Member(id=author_id, name=author_name, guild=guild)
                author.bot = is_bot
                author.discriminator = author_data.get("discriminator", "0000")
                member_data = d.get("member", {})
                for rid in member_data.get("roles", []):
                    r = guild.get_role(int(rid))
                    if r: author.roles.append(r)
            else:
                author = User(id=author_id, name=author_name, bot=is_bot)
                author.discriminator = author_data.get("discriminator", "0000")

            msg = Message(id=msg_id, content=content, author=author, channel=channel, guild=guild)
            msg._client = self
            channel._client = self

            await self._dispatch_event("on_message", msg)

        elif t == "INTERACTION_CREATE":
            int_id = int(d["id"])
            token = d.get("token", "")
            int_type = InteractionType(d.get("type", 3))
            guild_id = int(d["guild_id"]) if d.get("guild_id") else None
            channel_id = int(d["channel_id"]) if d.get("channel_id") else None
            guild = self.get_guild(guild_id) if guild_id else None
            channel = (guild.get_channel(channel_id) if guild else None) or TextChannel(id=channel_id or 0)
            channel._client = self

            user_data = d.get("member", {}).get("user") or d.get("user") or {}
            user_id = int(user_data.get("id", 0))
            user_name = user_data.get("username", "Unknown")
            user = Member(id=user_id, name=user_name, guild=guild) if guild else User(id=user_id, name=user_name)
            user.bot = bool(user_data.get("bot", False))

            interaction = Interaction(id=int_id, type=int_type, guild=guild, user=user)
            interaction.token = token
            interaction.data = d.get("data", {})
            interaction.channel = channel
            interaction._client = self
            interaction.response = InteractionResponse(interaction=interaction, client=self)
            interaction.followup = InteractionFollowup(interaction=interaction, client=self)

            await self._dispatch_event("on_interaction", interaction)

        elif t == "GUILD_MEMBER_ADD":
            guild = self.get_guild(int(d["guild_id"]))
            user_data = d.get("user", {})
            member = Member(id=int(user_data.get("id", 0)), name=user_data.get("username", ""), guild=guild)
            member.bot = bool(user_data.get("bot", False))
            if guild:
                guild.member_count = (guild.member_count or 0) + 1
                guild.members.append(member)
            await self._dispatch_event("on_member_join", member)

        elif t == "GUILD_MEMBER_REMOVE":
            guild = self.get_guild(int(d["guild_id"]))
            user_data = d.get("user", {})
            member = Member(id=int(user_data.get("id", 0)), name=user_data.get("username", ""), guild=guild)
            if guild:
                guild.member_count = max(1, (guild.member_count or 1) - 1)
                guild.members = [m for m in guild.members if m.id != member.id]
            await self._dispatch_event("on_member_remove", member)

        elif t == "GUILD_MEMBER_UPDATE":
            guild = self.get_guild(int(d["guild_id"]))
            user_data = d.get("user", {})
            before = Member(id=int(user_data.get("id", 0)), name=user_data.get("username", ""), guild=guild)
            after = Member(id=int(user_data.get("id", 0)), name=user_data.get("username", ""), guild=guild)
            await self._dispatch_event("on_member_update", before, after)

        elif t == "GUILD_BAN_ADD":
            guild = self.get_guild(int(d["guild_id"]))
            user_data = d.get("user", {})
            user = User(id=int(user_data.get("id", 0)), name=user_data.get("username", ""))
            await self._dispatch_event("on_member_ban", guild, user)

        elif t == "GUILD_BAN_REMOVE":
            guild = self.get_guild(int(d["guild_id"]))
            user_data = d.get("user", {})
            user = User(id=int(user_data.get("id", 0)), name=user_data.get("username", ""))
            await self._dispatch_event("on_member_unban", guild, user)

        elif t == "CHANNEL_CREATE":
            ch = TextChannel(id=int(d["id"]), name=d.get("name", ""))
            ch.guild = self.get_guild(int(d.get("guild_id", 0)))
            ch._client = self
            if ch.guild:
                ch.guild.channels.append(ch)
                ch.guild.text_channels.append(ch)
            await self._dispatch_event("on_guild_channel_create", ch)

        elif t == "CHANNEL_DELETE":
            ch = TextChannel(id=int(d["id"]), name=d.get("name", ""))
            ch.guild = self.get_guild(int(d.get("guild_id", 0)))
            ch._client = self
            if ch.guild:
                ch.guild.channels = [c for c in ch.guild.channels if c.id != ch.id]
                ch.guild.text_channels = [c for c in ch.guild.text_channels if c.id != ch.id]
            await self._dispatch_event("on_guild_channel_delete", ch)

        elif t == "CHANNEL_UPDATE":
            ch = TextChannel(id=int(d["id"]), name=d.get("name", ""))
            ch.guild = self.get_guild(int(d.get("guild_id", 0)))
            ch._client = self
            await self._dispatch_event("on_guild_channel_update", ch, ch)

        elif t == "GUILD_ROLE_CREATE":
            r_data = d.get("role", {})
            role = Role(id=int(r_data.get("id", 0)), name=r_data.get("name", ""), position=r_data.get("position", 0))
            guild = self.get_guild(int(d.get("guild_id", 0)))
            if guild:
                guild.roles.append(role)
            await self._dispatch_event("on_guild_role_create", role)

        elif t == "GUILD_ROLE_DELETE":
            rid = int(d.get("role_id", 0))
            guild = self.get_guild(int(d.get("guild_id", 0)))
            role = (guild.get_role(rid) if guild else None) or Role(id=rid)
            if guild:
                guild.roles = [r for r in guild.roles if r.id != rid]
            await self._dispatch_event("on_guild_role_delete", role)

        elif t == "GUILD_ROLE_UPDATE":
            r_data = d.get("role", {})
            role = Role(id=int(r_data.get("id", 0)), name=r_data.get("name", ""), position=r_data.get("position", 0))
            await self._dispatch_event("on_guild_role_update", role, role)

        elif t == "WEBHOOKS_UPDATE":
            ch = TextChannel(id=int(d.get("channel_id", 0)))
            ch.guild = self.get_guild(int(d.get("guild_id", 0)))
            await self._dispatch_event("on_webhooks_update", ch)

        elif t == "INVITE_CREATE":
            inv = Invite(id=0, name=d.get("code", ""))
            await self._dispatch_event("on_invite_create", inv)

        elif t == "INVITE_DELETE":
            inv = Invite(id=0, name=d.get("code", ""))
            await self._dispatch_event("on_invite_delete", inv)

        elif t == "AUTO_MODERATION_RULE_CREATE":
            await self._dispatch_event("on_auto_moderation_rule_create", d)

        elif t == "AUTO_MODERATION_RULE_UPDATE":
            await self._dispatch_event("on_auto_moderation_rule_update", d)

        elif t == "AUTO_MODERATION_RULE_DELETE":
            await self._dispatch_event("on_auto_moderation_rule_delete", d)

        elif t == "GUILD_AUDIT_LOG_ENTRY_CREATE":
            entry = AuditLogEntry(id=int(d.get("id", 0)), action=d.get("action_type"))
            await self._dispatch_event("on_audit_log_entry_create", entry)

        elif t == "THREAD_DELETE":
            thread = Thread(id=int(d.get("id", 0)), name=d.get("name", ""))
            await self._dispatch_event("on_thread_delete", thread)

    async def _handle_ws_connection(self, ws: Any):
        import aiohttp
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    continue

                op = data.get("op")
                d = data.get("d")
                s = data.get("s")
                t = data.get("t")

                if s is not None:
                    self._seq = s

                if op == 10:  # HELLO
                    heartbeat_interval = d.get("heartbeat_interval", 41250) / 1000.0
                    if self._heartbeat_task and not self._heartbeat_task.done():
                        self._heartbeat_task.cancel()
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws, heartbeat_interval))

                    if self._session_id and self._seq is not None:
                        resume_payload = {
                            "op": 6,
                            "d": {
                                "token": self.token,
                                "session_id": self._session_id,
                                "seq": self._seq
                            }
                        }
                        await ws.send_json(resume_payload)
                    else:
                        identify_payload = {
                            "op": 2,
                            "d": {
                                "token": self.token,
                                "intents": self._intents_val,
                                "properties": {
                                    "os": "linux",
                                    "browser": "MomentumOne",
                                    "device": "MomentumOne"
                                }
                            }
                        }
                        await ws.send_json(identify_payload)

                elif op == 11:  # HEARTBEAT_ACK
                    self._heartbeat_acked = True
                    self.latency = max(0.001, time.perf_counter() - self._last_heartbeat_sent)

                elif op == 1:  # HEARTBEAT REQUEST
                    await ws.send_json({"op": 1, "d": self._seq})

                elif op == 7:  # RECONNECT
                    _discord_logger.info("[Gateway] Reconnect requested by Discord Gateway.")
                    break

                elif op == 9:  # INVALID_SESSION
                    _discord_logger.warn("[Gateway] Invalid session received.")
                    resumable = bool(d)
                    if not resumable:
                        self._session_id = None
                        self._seq = None
                    await asyncio.sleep(1.0)
                    break

                elif op == 0:  # DISPATCH
                    await self._handle_dispatch(t, d)

            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    async def _run_gateway_loop(self):
        import aiohttp
        backoff = 1.0
        while not self._closed:
            try:
                if not self._session or self._session.closed:
                    self._session = aiohttp.ClientSession()

                target_url = self._resume_gateway_url or self._gateway_url
                _discord_logger.info(f"[Gateway] Connecting to Discord Gateway at {target_url}...")

                async with self._session.ws_connect(
                    target_url,
                    max_msg_size=16 * 1024 * 1024,
                    autoping=True,
                    heartbeat=30.0
                ) as ws:
                    self._ws = ws
                    backoff = 1.0
                    await self._handle_ws_connection(ws)

                    if ws.close_code == 4004:
                        _discord_logger.error("[Gateway] Authentication failed (4004). Please verify BOT_TOKEN.")
                        break
                    elif ws.close_code == 4014:
                        _discord_logger.warn("[Gateway] Disallowed intents (4014). Reconnecting with standard intents...")
                        self._intents_val = 3276543
                        self._session_id = None
                        self._seq = None
                        await asyncio.sleep(1.0)
                        continue

            except asyncio.CancelledError:
                break
            except Exception as err:
                if self._closed:
                    break
                _discord_logger.error(f"[Gateway] Connection error: {err}. Reconnecting in {backoff:.1f}s...")
                await asyncio.sleep(backoff)
                backoff = min(60.0, backoff * 1.5)

    async def start(self, token: str):
        self._closed = False
        self._ready = False
        self.token = token.strip() if token else ""
        Client._default_instance = self

        is_real_token = bool(self.token and len(self.token) > 20 and not self.token.startswith("sentinel_"))

        if not is_real_token:
            self._ready = True
            if "on_ready" in self._event_hooks:
                for hook in self._event_hooks["on_ready"]:
                    try:
                        res = hook()
                        if hasattr(res, "__await__"):
                            await res
                    except Exception:
                        pass
            while not self._closed:
                await asyncio.sleep(1.0)
            return

        await self._run_gateway_loop()

    async def close(self):
        self._closed = True
        self._ready = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()

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

    # --------------------------------------------------------------------------
    # REST API Methods
    # --------------------------------------------------------------------------
    async def http_get_or_create_dm(self, user_id: int) -> Optional[int]:
        if not self.token:
            return None
        import aiohttp
        session = self._session or aiohttp.ClientSession()
        headers = {"Authorization": f"Bot {self.token}", "Content-Type": "application/json"}
        try:
            async with session.post(
                "https://discord.com/api/v10/users/@me/channels",
                json={"recipient_id": str(user_id)},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return int(data["id"])
        except Exception:
            pass
        return None

    async def http_send_message(self, channel_id: int, content: Optional[str] = None, **kwargs) -> Message:
        if not self.token:
            return Message(id=int(time.time() * 1000), content=str(content or ""), channel=TextChannel(id=channel_id))
        import aiohttp
        session = self._session or aiohttp.ClientSession()
        headers = {"Authorization": f"Bot {self.token}", "Content-Type": "application/json"}
        payload = serialize_discord_payload(content, **kwargs)
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        try:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    author_data = data.get("author", {})
                    author = User(id=int(author_data.get("id", 0)), name=author_data.get("username", "Sentinel™"), bot=True)
                    ch = self.get_channel(channel_id) or TextChannel(id=channel_id)
                    msg = Message(id=int(data.get("id", time.time() * 1000)), content=data.get("content", ""), author=author, channel=ch, guild=getattr(ch, "guild", None))
                    msg._client = self
                    return msg
                elif resp.status == 400 and "components" in payload:
                    # Fallback without components if components structure rejected
                    payload.pop("components", None)
                    async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp2:
                        if resp2.status in (200, 201):
                            data = await resp2.json()
                            ch = self.get_channel(channel_id) or TextChannel(id=channel_id)
                            msg = Message(id=int(data.get("id", time.time() * 1000)), content=data.get("content", ""), author=self.user, channel=ch, guild=getattr(ch, "guild", None))
                            msg._client = self
                            return msg
                text = await resp.text()
                _discord_logger.error(f"[REST] Failed to send message to channel {channel_id}: {resp.status} {text}")
        except Exception as err:
            _discord_logger.error(f"[REST] Exception sending message to channel {channel_id}: {err}")
        return Message(id=int(time.time() * 1000), content=str(content or ""), channel=TextChannel(id=channel_id))

    async def http_edit_message(self, channel_id: int, message_id: int, content: Optional[str] = None, **kwargs) -> Message:
        if not self.token:
            return Message(id=message_id, channel=TextChannel(id=channel_id))
        import aiohttp
        session = self._session or aiohttp.ClientSession()
        headers = {"Authorization": f"Bot {self.token}", "Content-Type": "application/json"}
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}"
        payload = serialize_discord_payload(content, **kwargs)
        try:
            async with session.patch(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status in (200, 204):
                    data = await resp.json()
                    return Message(id=message_id, content=data.get("content", ""), channel=TextChannel(id=channel_id))
        except Exception as err:
            _discord_logger.error(f"[REST] Edit message error: {err}")
        return Message(id=message_id, channel=TextChannel(id=channel_id))

    async def http_delete_message(self, channel_id: int, message_id: int) -> None:
        if not self.token:
            return
        import aiohttp
        session = self._session or aiohttp.ClientSession()
        headers = {"Authorization": f"Bot {self.token}"}
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}"
        try:
            async with session.delete(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                pass
        except Exception as err:
            _discord_logger.error(f"[REST] Delete message error: {err}")

    async def http_interaction_callback(self, interaction_id: int, interaction_token: str, callback_type: int = 4, data: Optional[Dict[str, Any]] = None):
        if not self.token:
            return
        import aiohttp
        session = self._session or aiohttp.ClientSession()
        headers = {"Authorization": f"Bot {self.token}", "Content-Type": "application/json"}
        url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
        body: Dict[str, Any] = {"type": callback_type}
        if data:
            body["data"] = data
        try:
            async with session.post(url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status not in (200, 204):
                    t = await resp.text()
                    _discord_logger.debug(f"[REST] Interaction callback {resp.status}: {t}")
        except Exception as err:
            _discord_logger.error(f"[REST] Interaction callback error: {err}")

    async def http_interaction_send_message(self, interaction: Any, content: Optional[str] = None, **kwargs) -> Message:
        payload = serialize_discord_payload(content, **kwargs)
        await self.http_interaction_callback(interaction.id, interaction.token, callback_type=4, data=payload)
        return Message(channel=getattr(interaction, "channel", None), guild=getattr(interaction, "guild", None))

    async def http_interaction_edit_message(self, interaction: Any, content: Optional[str] = None, **kwargs) -> Message:
        payload = serialize_discord_payload(content, **kwargs)
        await self.http_interaction_callback(interaction.id, interaction.token, callback_type=7, data=payload)
        return Message(channel=getattr(interaction, "channel", None), guild=getattr(interaction, "guild", None))

    async def http_edit_original_response(self, interaction: Any, content: Optional[str] = None, **kwargs) -> Message:
        if not self.token:
            return Message(channel=getattr(interaction, "channel", None), guild=getattr(interaction, "guild", None))
        import aiohttp
        session = self._session or aiohttp.ClientSession()
        headers = {"Authorization": f"Bot {self.token}", "Content-Type": "application/json"}
        bot_id = self.user.id if self.user else 1563628961379123302
        url = f"https://discord.com/api/v10/webhooks/{bot_id}/{interaction.token}/messages/@original"
        payload = serialize_discord_payload(content, **kwargs)
        try:
            async with session.patch(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status in (200, 204):
                    data = await resp.json()
                    return Message(id=int(data.get("id", time.time() * 1000)), content=data.get("content", ""), channel=getattr(interaction, "channel", None), guild=getattr(interaction, "guild", None))
        except Exception as err:
            _discord_logger.error(f"[REST] Edit original response error: {err}")
        return Message(channel=getattr(interaction, "channel", None), guild=getattr(interaction, "guild", None))

    async def http_followup_send(self, interaction: Any, content: Optional[str] = None, **kwargs) -> Message:
        if not self.token:
            return Message(channel=getattr(interaction, "channel", None), guild=getattr(interaction, "guild", None))
        import aiohttp
        session = self._session or aiohttp.ClientSession()
        headers = {"Authorization": f"Bot {self.token}", "Content-Type": "application/json"}
        bot_id = self.user.id if self.user else 1563628961379123302
        url = f"https://discord.com/api/v10/webhooks/{bot_id}/{interaction.token}"
        payload = serialize_discord_payload(content, **kwargs)
        try:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return Message(id=int(data.get("id", time.time() * 1000)), content=data.get("content", ""), channel=getattr(interaction, "channel", None), guild=getattr(interaction, "guild", None))
        except Exception as err:
            _discord_logger.error(f"[REST] Followup send error: {err}")
        return Message(channel=getattr(interaction, "channel", None), guild=getattr(interaction, "guild", None))
