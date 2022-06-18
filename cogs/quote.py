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
import asyncio
from typing import Optional

import discord
from discord.ext import commands

from bot import QuoteBot
from core.decorators import delete_message_if_needed
from core.message_retrieval import DEFAULT_AVATAR_URL, MessageRetrievalContext

_MAX_CLONE_MESSAGES = 50
_QUOTE_EMOJI = "💬"
_QUOTE_EXCEPTIONS = (discord.NotFound, discord.Forbidden, discord.HTTPException, commands.BadArgument)


async def webhook_copy(webhook, msg: discord.Message, clean_content: bool = False):
    await webhook.send(
        username=getattr(msg.author, "nick", False) or msg.author.name,
        avatar_url=getattr(msg.author.avatar, "url", DEFAULT_AVATAR_URL),
        content=msg.clean_content if clean_content else msg.content,
        files=[await attachment.to_file() for attachment in msg.attachments],
        embed=(msg.embeds[0] if msg.embeds and msg.embeds[0].type == "rich" else None),
        allowed_mentions=discord.AllowedMentions.none(),
    )


class Main(commands.Cog):
    def __init__(self, bot: QuoteBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message) -> None:
        ctx: MessageRetrievalContext = await self.bot.get_context(msg)
        if ctx.valid or not msg.guild:
            return
        async with self.bot.db_connect() as con:
            if await con.is_blocked(msg.guild.id) or not await con.fetch_quote_links(msg.guild.id):
                return
        msg_urls = ctx.get_message_urls()
        if (msg_url := next(msg_urls, None)) and next(msg_urls, None) is None:
            # message contains 1 message link
            try:
                quoted_msg = await ctx.get_message(msg_url.group(0))
                await self.bot.quote_message(quoted_msg, msg.channel, str(msg.author), "link")
            except _QUOTE_EXCEPTIONS:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.emoji.name != _QUOTE_EMOJI:
            return
        async with self.bot.db_connect() as con:
            if not await con.fetch_quote_reactions(payload.guild_id):
                return
        guild = self.bot.get_guild(payload.guild_id)
        channel_or_thread = guild.get_channel(payload.channel_id) or guild.get_thread(payload.channel_id)
        perms = channel_or_thread.permissions_for(guild.me)
        if (
            channel_or_thread.permissions_for(payload.member).send_messages
            and perms.read_message_history
            and perms.send_messages
        ):
            try:
                msg = channel_or_thread._state._get_message(payload.message_id) or await channel_or_thread.fetch_message(
                    payload.message_id
                )
                await self.bot.quote_message(msg, channel_or_thread, str(payload.member))
            except _QUOTE_EXCEPTIONS:
                pass

    async def _send_quote(self, ctx: MessageRetrievalContext, query: Optional[str]) -> None:
        if query is None:
            try:
                async for msg in ctx.channel.history(limit=1, before=ctx.message):
                    await self.bot.quote_message(msg, ctx.channel, str(ctx.author))
            except _QUOTE_EXCEPTIONS:
                await ctx.send(":x: **Couldn't find the message.**")
        else:
            try:
                msg = await ctx.get_message(query)
                await self.bot.quote_message(msg, ctx.channel, str(ctx.author))
            except discord.Forbidden:
                await ctx.send(":x: **I don't have permissions to read messages from that channel.**")
            except commands.BadArgument:
                await ctx.send(":x: **Couldn't find the message.**")
            except commands.UserInputError:
                await ctx.send(":x: **Please specify a valid message ID/URL or regular expression.**")

    async def _send_cloned_messages(self, ctx: commands.Context, msg_limit: int, channel: discord.TextChannel) -> None:
        webhook = await ctx.channel.create_webhook(name=self.bot.user.name)
        messages = [msg async for msg in channel.history(limit=msg_limit, before=ctx.message)]
        ignored_exceptions = (discord.HTTPException, discord.NotFound, discord.Forbidden)
        try:
            await webhook_copy(webhook, messages.pop(), clean_content := ctx.guild != channel.guild)
        except ignored_exceptions:
            pass
        else:
            for msg in messages[::-1]:
                await asyncio.sleep(0.5)
                try:
                    await webhook_copy(webhook, msg, clean_content)
                except ignored_exceptions:
                    break
        try:
            await webhook.delete()
        except ignored_exceptions:
            pass

    @commands.command(aliases=["q"])
    @delete_message_if_needed
    async def quote(self, ctx: MessageRetrievalContext, *, query: str = None) -> None:
        """Quote a message using an ID, link or a regular expression matching the content."""
        await ctx.typing()
        if ctx.guild is not None:
            perms = ctx.channel.permissions_for(ctx.me)
            if not perms.send_messages:
                return
        await self._send_quote(ctx, query)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.cooldown(rate=2, per=300, type=commands.BucketType.guild)
    async def clone(self, ctx: commands.Context, source_channel: discord.TextChannel, number_of_messages: int) -> None:
        """
        Clone up to 50 messages from one channel to another using a webhook.

        Requires the 'Manage Webhooks' permission.
        """
        if isinstance(ctx.channel, discord.Thread):
            await ctx.send(":x: **This command can't be used in threads.**")
        elif not ctx.channel.permissions_for(ctx.me).manage_webhooks:
            await ctx.send(":x: **I don't have permissions to manage webhooks in this channel.**")
        elif number_of_messages < 1 or number_of_messages > _MAX_CLONE_MESSAGES:
            await ctx.send(f":x: **You can only clone 1 to {_MAX_CLONE_MESSAGES} messages.**")
        else:
            await self._send_cloned_messages(ctx, number_of_messages, source_channel)


async def setup(bot: QuoteBot) -> None:
    await bot.add_cog(Main(bot))
