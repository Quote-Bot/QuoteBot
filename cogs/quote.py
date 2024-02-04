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
import asyncio
from typing import Optional, Union

import discord
from discord import app_commands
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
        avatar_url=getattr(msg.author.display_avatar, "url", DEFAULT_AVATAR_URL),
        content=msg.clean_content if clean_content else msg.content,
        files=[await attachment.to_file() for attachment in msg.attachments],
        embed=(msg.embeds[0] if msg.embeds and msg.embeds[0].type == "rich" else None),
        allowed_mentions=discord.AllowedMentions.none(),
    )


class Quote(commands.Cog):
    def __init__(self, bot: QuoteBot) -> None:
        self.bot = bot
        # https://github.com/Rapptz/discord.py/issues/7823#issuecomment-1086830458
        self.quote_context_menu = app_commands.ContextMenu(name="Quote message", callback=self.quote_from_context_menu)
        self.bot.tree.add_command(self.quote_context_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.quote_context_menu.name, type=self.quote_context_menu.type)

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message) -> None:
        ctx: MessageRetrievalContext = await self.bot.get_context(msg)
        if ctx.valid or not msg.guild:
            return
        async with self.bot.db_connect() as con:
            if await con.is_blocked(msg.guild.id) or not await con.fetch_quote_links(msg.guild.id):
                return
        msg_urls = ctx.get_message_urls()
        if (msg_url_match := next(msg_urls, None)) and next(msg_urls, None) is None:
            # message contains 1 message link
            try:
                async for linked_msg in ctx.get_messages_from_match(msg_url_match):
                    await ctx.typing()
                    await self.bot.quote_message(linked_msg, msg.channel, ctx.send, str(msg.author), "link")
            except _QUOTE_EXCEPTIONS:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.member is None or payload.emoji.name != _QUOTE_EMOJI:
            return
        async with self.bot.db_connect() as con:
            if not await con.fetch_quote_reactions(payload.guild_id):
                return
        if (guild := self.bot.get_guild(payload.guild_id)) is None:
            return
        if (channel_or_thread := guild.get_channel(payload.channel_id) or guild.get_thread(payload.channel_id)) is None:
            return
        if not isinstance(channel_or_thread, (discord.TextChannel, discord.Thread)):
            return
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
                await self.bot.quote_message(msg, channel_or_thread, channel_or_thread.send, str(payload.member))
            except _QUOTE_EXCEPTIONS:
                pass

    async def _send_cloned_messages(
        self, ctx: commands.Context, msg_limit: int, source: Union[discord.TextChannel, discord.Thread]
    ) -> None:
        if ctx.interaction is None:
            if not isinstance(ctx.channel, discord.TextChannel):
                await ctx.send(":x: **This command can only be used in text channels.**")
                return
            webhook = await ctx.channel.create_webhook(name=self.bot.user.name)
        else:
            webhook = ctx.interaction.followup
        messages = [msg async for msg in source.history(limit=msg_limit, before=ctx.message)]
        ignored_exceptions = (discord.HTTPException, discord.NotFound, discord.Forbidden)
        try:
            await webhook_copy(webhook, messages.pop(), clean_content := ctx.guild != source.guild)
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

    async def _quote_last_message(self, ctx: commands.Context) -> None:
        try:
            msg = getattr(ctx.channel, "last_message", None) or await anext(
                ctx.channel.history(limit=1, before=ctx.message), None
            )
            if msg is not None:
                await self.bot.quote_message(msg, ctx.channel, ctx.send, str(ctx.author))
            else:
                await ctx.send(":x: **No messages found in this channel.**")
        except _QUOTE_EXCEPTIONS:
            await ctx.send(":x: **Couldn't find the message.**")

    @commands.hybrid_command(aliases=["q"])
    @commands.bot_has_permissions(send_messages=True)
    @app_commands.describe(query="ID, link or regular expression")
    @delete_message_if_needed
    async def quote(self, ctx: MessageRetrievalContext, *, query: Optional[str] = None) -> None:
        """
        Quote messages using an ID, link or a regular expression matching the content.

        If a link or ID is used, up to 4 following messages can be quoted by adding `+<number of messages>` after the query.

        Example:
        `>quote 12345678901234567 +3`

        This will quote the message with ID 12345678901234567 as well as the 3 following messages.
        """
        if query is None:
            await ctx.typing()
            await self._quote_last_message(ctx)
        else:
            try:
                async for msg in ctx.get_messages(query):
                    await ctx.channel.typing()
                    await self.bot.quote_message(msg, ctx.channel, ctx.send, str(ctx.author))
            except discord.Forbidden:
                await ctx.send(":x: **I don't have permissions to read messages from that channel.**")
            except commands.BadArgument:
                await ctx.send(":x: **Couldn't find the message.**")
            except commands.UserInputError:
                await ctx.send(":x: **Please specify a valid message ID/URL or regular expression.**")

    @commands.hybrid_command()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    @commands.guild_only()
    @commands.cooldown(rate=2, per=300, type=commands.BucketType.guild)
    async def clone(
        self,
        ctx: commands.Context,
        source: Union[discord.TextChannel, discord.Thread],
        number_of_messages: commands.Range[int, 1, _MAX_CLONE_MESSAGES],
    ) -> None:
        """
        Clone up to 50 messages from one channel to another using a webhook.

        Requires the 'Manage Webhooks' permission.
        """
        if ctx.interaction is not None:
            await ctx.interaction.response.defer(thinking=True)
        await self._send_cloned_messages(ctx, number_of_messages, source)

    @app_commands.checks.bot_has_permissions(send_messages=True)
    async def quote_from_context_menu(self, interaction: discord.Interaction, msg: discord.Message) -> None:
        await interaction.response.defer(thinking=True)
        if not isinstance(interaction.channel, discord.abc.Messageable):
            return await interaction.followup.send(":x: **Quoting messages is not supported in this channel type.**")
        await self.bot.quote_message(msg, interaction.channel, interaction.followup.send, str(interaction.user))


async def setup(bot: QuoteBot) -> None:
    await bot.add_cog(Quote(bot))
