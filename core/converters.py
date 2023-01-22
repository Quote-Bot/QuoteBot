"""
Copyright (C) 2020-2022 JonathanFeenstra, Deivedux, kageroukw

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
import re
from typing import Union

import discord
from discord.ext import commands

_CHANNEL_OR_THREAD_MENTION_RE = re.compile(r"<#([0-9]{15,20})>$")

TextChannelOrThread = Union[discord.TextChannel, discord.Thread]


class ChannelOrThreadNotFound(commands.BadArgument):
    """Exception raised when the bot cannot find the channel or thread.

    This inherits from :exc:`commands.BadArgument`

    Attributes
    -----------
    argument: :class:`str`
        The channel or thread supplied by the caller that was not found.
    """

    def __init__(self, argument: str) -> None:
        self.argument: str = argument
        super().__init__(f'Channel or thread "{argument}" not found.')


class GlobalTextChannelOrThreadConverter(commands.IDConverter[TextChannelOrThread]):
    """Converts to a :class:`~discord.TextChannel` or :class:`~discord.Thread`.

    Modified from :meth:`discord.ext.commands.GuildChannelConverter._resolve_channel` to include all guild channels and
    threads if the argument is an ID or mention.
    """

    async def convert(self, ctx: commands.Context, argument: str) -> TextChannelOrThread:
        bot: commands.Bot = ctx.bot
        match = commands.IDConverter._get_id_match(argument) or _CHANNEL_OR_THREAD_MENTION_RE.match(argument)

        if match is None:
            # not an ID or mention
            result = discord.utils.get(bot.get_all_channels(), name=argument)
        else:
            channel_or_thread_id = int(match.group(1))
            # `bot.get_channel` returns threads and private channels too
            result = bot.get_channel(channel_or_thread_id)

        if not isinstance(result, (discord.TextChannel, discord.Thread)):
            raise ChannelOrThreadNotFound(argument)

        return result


class OptionalGuildConverter(commands.converter.GuildConverter):
    """A :class:`commands.converter.GuildConverter` returning no guild (None) with "0" or "global" as guild-id input."""
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Guild | None:
        if argument.lower() in ("0", "global"):
            return None
        return await super().convert(ctx, argument)


OptionalCurrentGuild = commands.parameter(
    default=lambda ctx: ctx.guild,
    displayed_default="<this server>",
    converter=OptionalGuildConverter,
)
"""`commands.CurrentGuild` with :class:`OptionalGuildConverter`, returning None without a current guild."""