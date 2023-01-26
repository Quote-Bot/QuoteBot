"""
Copyright (C) 2020-2023 JonathanFeenstra, Deivedux, kageroukw

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
from typing import Optional, Union

import discord
from discord.ext import commands

from bot import QuoteBot
from core.converters import GlobalTextChannelOrThreadConverter, TextChannelOrThread
from core.decorators import delete_message_if_needed


class Snipe(commands.Cog):
    def __init__(self, bot: QuoteBot) -> None:
        self.bot = bot
        self.deletes = {}
        self.edits = {}

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        self.deletes.pop(guild.id, None)
        self.edits.pop(guild.id, None)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if isinstance(channel, discord.TextChannel):
            self._clear_channel_or_thread_deletes(channel)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        self._clear_channel_or_thread_deletes(thread)

    @commands.Cog.listener()
    async def on_thread_remove(self, thread: discord.Thread) -> None:
        self._clear_channel_or_thread_deletes(thread)

    @commands.Cog.listener()
    async def on_message_delete(self, msg: discord.Message) -> None:
        if msg.guild and not msg.author.bot and not (await self.bot.get_context(msg)).valid:
            if guild_deletes := self.deletes.get(msg.guild.id):
                guild_deletes[msg.channel.id] = msg
            else:
                self.deletes[msg.guild.id] = {msg.channel.id: msg}

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.guild and not before.author.bot and before.pinned == after.pinned:
            if guild_edits := self.edits.get(before.guild.id):
                guild_edits[before.channel.id] = before
            else:
                self.edits[before.guild.id] = {before.channel.id: before}

    def _clear_channel_or_thread_deletes(self, channel_or_thread: TextChannelOrThread) -> None:
        if guild_deletes := self.deletes.get(channel_or_thread.guild.id):
            guild_deletes.pop(channel_or_thread.id, None)
        if guild_edits := self.edits.get(channel_or_thread.guild.id):
            guild_edits.pop(channel_or_thread.id, None)

    async def snipe_msg(
        self,
        ctx: commands.Context,
        channel_or_thread: Optional[TextChannelOrThread],
        edit: bool = False,
    ) -> None:
        await ctx.typing()
        if channel_or_thread is None:
            channel_or_thread = ctx.channel
        author = channel_or_thread.guild.get_member(ctx.author.id)
        if not isinstance(author, discord.Member):
            raise commands.MemberNotFound(author)
        if (
            not channel_or_thread.permissions_for(author).read_messages
            or not channel_or_thread.permissions_for(author).read_message_history
        ):
            await ctx.send(":x: **You don't have permission to use this command.**")
        else:
            if ctx.guild is not None:
                perms = ctx.channel.permissions_for(ctx.me)
                if not perms.send_messages:
                    return
            await self._send_snipe(ctx, channel_or_thread, edit)

    async def _send_snipe(self, ctx: commands.Context, channel_or_thread: TextChannelOrThread, edit: bool = False) -> None:
        try:
            msg = (self.edits if edit else self.deletes)[channel_or_thread.guild.id][channel_or_thread.id]
        except KeyError:
            await ctx.send(":x: **Couldn't find the message.**")
        else:
            await self.bot.quote_message(msg, ctx.channel, ctx.send, str(ctx.author), "snipe")

    async def _snipe_if_permitted(
        self, ctx: commands.Context, channel_or_thread: TextChannelOrThread, edit: bool = False
    ) -> None:
        if channel_or_thread is None:
            if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
                raise commands.NoPrivateMessage("Sniping DMs is not supported.")
            channel_or_thread = ctx.channel
        if await self._has_snipe_permission(ctx.author, channel_or_thread):
            await self.snipe_msg(ctx, channel_or_thread, edit)
        else:
            await ctx.send(":x: **You don't have permission to snipe messages.**")

    async def _has_snipe_permission(
        self, user: Union[discord.User, discord.Member], channel_or_thread: TextChannelOrThread
    ) -> bool:
        member = channel_or_thread.guild.get_member(user.id)
        if not isinstance(member, discord.Member):
            return False
        if channel_or_thread.permissions_for(member).manage_messages:
            return True
        async with self.bot.db_connect() as con:
            return not await con.fetch_snipe_requires_manage_messages(channel_or_thread.guild.id)

    @commands.hybrid_command()
    @delete_message_if_needed
    async def snipe(
        self, ctx: commands.Context, channel_or_thread: Optional[GlobalTextChannelOrThreadConverter] = None
    ) -> None:
        """Snipe the last cached deleted message from a specified channel or the current channel."""
        await self._snipe_if_permitted(ctx, channel_or_thread)  # type: ignore

    @commands.hybrid_command()
    @delete_message_if_needed
    async def snipeedit(
        self, ctx: commands.Context, channel_or_thread: Optional[GlobalTextChannelOrThreadConverter] = None
    ) -> None:
        """Snipe the last cached edited message from a specified channel or the current channel."""
        await self._snipe_if_permitted(ctx, channel_or_thread, True)  # type: ignore


async def setup(bot: QuoteBot) -> None:
    await bot.add_cog(Snipe(bot))
