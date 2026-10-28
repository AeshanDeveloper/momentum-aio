from . import (
    channel_create,
    channel_delete,
    channel_update,
    member_ban,
    member_unban,
    member_join,
    member_remove,
    member_update,
    role_create,
    role_delete,
    role_update,
    guild_update,
    invite_create,
    invite_delete,
    emojis_update,
    webhooks_update,
    message_delete,
    message_edit,
    message_bulk_delete,
)

ALL_LOGGING_EVENT_MODULES = [
    channel_create,
    channel_delete,
    channel_update,
    member_ban,
    member_unban,
    member_join,
    member_remove,
    member_update,
    role_create,
    role_delete,
    role_update,
    guild_update,
    invite_create,
    invite_delete,
    emojis_update,
    webhooks_update,
]

EXTENDED_LOGGING_EVENT_MODULES = [
    message_delete,
    message_edit,
    message_bulk_delete,
]

FULL_LOGGING_EVENT_MODULES = ALL_LOGGING_EVENT_MODULES + EXTENDED_LOGGING_EVENT_MODULES
