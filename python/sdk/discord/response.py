from __future__ import annotations

import discord
from typing import Any, Optional, Union, List, Dict
from .builders import ComponentLayoutView, ContainerBuilder


async def send_response(
    target: Any,
    response: Any,
    *,
    ephemeral: bool = False,
    edit: bool = False,
) -> Any:
    """
    Central response dispatcher and adapter for Discord messages and interactions.
    Explicitly handles Components V2 LayoutViews, legacy Embeds, Files, Dictionaries, and plain text.
    Ensures Components V2 views are sent via view= and never passed to embed=.
    Prevents duplicate responses on acknowledged interactions and handles deferred responses.
    """
    if response is None:
        return None

    # If response is already an existing sent message object, return it directly
    if isinstance(response, (discord.Message, discord.WebhookMessage)):
        return response

    # Handle unpacked tuples from paginated commands (built, page, total_pages)
    if isinstance(response, tuple) and len(response) > 0 and not all(isinstance(x, (discord.Embed, discord.File)) for x in response):
        response = response[0]

    # Convert ContainerBuilder to ComponentLayoutView
    if isinstance(response, ContainerBuilder):
        response = response.build()

    # Wrap raw discord.ui.Container into a ComponentLayoutView
    if isinstance(response, discord.ui.Container):
        view = ComponentLayoutView()
        view.add_item(response)
        response = view

    kwargs: Dict[str, Any] = {}

    if isinstance(response, dict):
        # Dictionary payload with potential keys: content, view, embed, embeds, file, files, ephemeral
        for k, v in response.items():
            if k == "view" and isinstance(v, ContainerBuilder):
                kwargs["view"] = v.build()
            elif k == "embed" and isinstance(v, (ComponentLayoutView, discord.ui.LayoutView, ContainerBuilder)):
                kwargs["view"] = v.build() if isinstance(v, ContainerBuilder) else v
            else:
                kwargs[k] = v
    elif isinstance(response, (discord.ui.LayoutView, discord.ui.View, ComponentLayoutView)):
        kwargs["view"] = response
    elif isinstance(response, discord.Embed):
        kwargs["embed"] = response
    elif isinstance(response, (list, tuple)) and len(response) > 0 and all(isinstance(x, discord.Embed) for x in response):
        kwargs["embeds"] = list(response)
    elif isinstance(response, discord.File):
        kwargs["file"] = response
    elif isinstance(response, (list, tuple)) and len(response) > 0 and all(isinstance(x, discord.File) for x in response):
        kwargs["files"] = list(response)
    elif isinstance(response, str):
        kwargs["content"] = response
    elif hasattr(response, "view") and getattr(response, "view") is not None and not isinstance(getattr(response, "view"), property):
        v = getattr(response, "view")
        kwargs["view"] = v.build() if isinstance(v, ContainerBuilder) else v
    else:
        kwargs["content"] = str(response)

    # Clean up redundant embed=None if view is present
    if "view" in kwargs and kwargs.get("embed") is None:
        kwargs.pop("embed", None)

    # 1. Target is a discord.Interaction
    if isinstance(target, discord.Interaction) or hasattr(target, "response"):
        if ephemeral and "ephemeral" not in kwargs:
            kwargs["ephemeral"] = True

        if edit:
            if hasattr(target, "response") and not target.response.is_done():
                return await target.response.edit_message(**kwargs)
            elif hasattr(target, "edit_original_response"):
                return await target.edit_original_response(**kwargs)

        if hasattr(target, "response"):
            if target.response.is_done():
                if hasattr(target, "followup"):
                    return await target.followup.send(**kwargs)
            else:
                return await target.response.send_message(**kwargs)

    # 2. Target is a discord.Message (e.g. prefix command)
    if isinstance(target, discord.Message) or hasattr(target, "reply"):
        if edit and hasattr(target, "edit"):
            return await target.edit(**kwargs)

        try:
            if hasattr(target, "reply"):
                return await target.reply(**kwargs)
        except Exception:
            pass

        if hasattr(target, "channel") and hasattr(target.channel, "send"):
            return await target.channel.send(**kwargs)

    # 3. Target is a Channel / Messageable
    if hasattr(target, "send"):
        return await target.send(**kwargs)

    return None
