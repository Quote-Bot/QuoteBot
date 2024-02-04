"""
Copyright (C) 2020-2024 JonathanFeenstra, Deivedux, kageroukw

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import functools
from typing import Any, Callable, Coroutine

from discord.ext import commands


def delete_message_if_needed(coro: Callable[..., Coroutine]) -> Callable[..., Coroutine]:
    """Delete the message of the decorated cog command coroutine before invoking it.

    Args:
        coro (Callable[..., Coroutine]): The coroutine to decorate.
    Returns:
        Callable[..., Coroutine]: The decorated coroutine.
    """

    @functools.wraps(coro)
    async def decorator(cog: commands.Cog, ctx: commands.Context, *args: Any, **kwargs: Any) -> Any:
        if ctx.guild is not None and ctx.channel.permissions_for(ctx.me).manage_messages:
            async with ctx.bot.db_connect() as con:
                if await con.fetch_delete_commands(ctx.guild.id):
                    await ctx.message.delete()
        return await coro(cog, ctx, *args, **kwargs)

    return decorator
