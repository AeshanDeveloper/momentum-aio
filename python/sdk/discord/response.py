from __future__ import annotations

import logging
from typing import Any, Optional, Union, List, Dict
import discord
from .builders import ComponentLayoutView, ContainerBuilder, build_ui

_logger = logging.getLogger("MomentumOne.Response")


async def send_ui(
    target: Any,
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
    ephemeral: bool = False,
    edit: bool = False,
) -> Any:
    view = build_ui(
        key=key,
        title=title,
        description=description,
        details=details,
        footer=footer,
        style=style,
        color=color,
        variables=variables,
        action_rows=action_rows,
        components=components,
        timeout=timeout,
    )
    return await send_response(target, view, ephemeral=ephemeral, edit=edit)


async def send_response(
    target: Any,
    response: Any,
    *,
    ephemeral: bool = False,
    edit: bool = False,
) -> Any:
    if response is None:
        return None

    if isinstance(response, (discord.Message, discord.WebhookMessage)):
        return response

    if isinstance(response, tuple) and len(response) > 0 and not all(isinstance(x, (discord.Embed, discord.File)) for x in response):
        response = response[0]

    if isinstance(response, ContainerBuilder):
        response = response.build()

    if isinstance(response, discord.ui.Container):
        view = ComponentLayoutView()
        view.add_item(response)
        response = view

    # GUARANTEE: If response is a raw string, convert it into a standardized Components V2 container
    if isinstance(response, str):
        response = build_ui(description=response, style="default")

    kwargs: Dict[str, Any] = {}

    if isinstance(response, dict):
        for k, v in response.items():
            if k == "view" and isinstance(v, ContainerBuilder):
                kwargs["view"] = v.build()
            elif k == "embed" and isinstance(v, (ComponentLayoutView, discord.ui.LayoutView, ContainerBuilder)):
                kwargs["view"] = v.build() if isinstance(v, ContainerBuilder) else v
            else:
                kwargs[k] = v
        if "view" not in kwargs and "content" in kwargs and isinstance(kwargs["content"], str):
            kwargs["view"] = build_ui(description=kwargs.pop("content"), style="default")
    elif isinstance(response, (discord.ui.LayoutView, discord.ui.View, ComponentLayoutView)):
        kwargs["view"] = response
    elif isinstance(response, discord.File):
        kwargs["file"] = response
    elif isinstance(response, (list, tuple)) and len(response) > 0 and all(isinstance(x, discord.File) for x in response):
        kwargs["files"] = list(response)
    elif hasattr(response, "view") and getattr(response, "view") is not None and not isinstance(getattr(response, "view"), property):
        v = getattr(response, "view")
        kwargs["view"] = v.build() if isinstance(v, ContainerBuilder) else v
    else:
        kwargs["view"] = build_ui(description=str(response), style="default")

    if "view" in kwargs:
        kwargs.pop("embed", None)
        kwargs.pop("content", None)
        v = kwargs.get("view")
        if hasattr(v, "deduplicate_custom_ids"):
            v.deduplicate_custom_ids()

    try:
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

        if hasattr(target, "send"):
            return await target.send(**kwargs)

    except Exception as err:
        _logger.error(f"[ResponseAdapter] Failed to deliver response: {err}")
        try:
            minimal_fallback = build_ui(key="common.error", variables={"message": "Failed to display message."}, style="error")
            if isinstance(target, discord.Interaction) and hasattr(target, "followup"):
                return await target.followup.send(view=minimal_fallback, ephemeral=True)
            elif hasattr(target, "send"):
                return await target.send(view=minimal_fallback)
        except Exception:
            pass

    return None
