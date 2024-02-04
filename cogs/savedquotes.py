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
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from bot import QuoteBot
from core.decorators import delete_message_if_needed
from core.message_retrieval import DEFAULT_AVATAR_URL, MessageRetrievalContext, MessageTuple, lazy_load_message
from core.persistence import QuoteBotDatabaseConnection

_MAX_ALIAS_LENGTH = 50
_MAX_SAVED_QUOTES = 50


async def _has_reached_saved_quote_limit(con: QuoteBotDatabaseConnection, owner_id: int) -> bool:
    return await con.fetch_saved_quote_count(owner_id) >= _MAX_SAVED_QUOTES


class SavedQuotes(commands.Cog):
    def __init__(self, bot: QuoteBot) -> None:
        self.bot = bot

    async def send_saved_quote(self, ctx: MessageRetrievalContext, alias: str, server: bool = False) -> None:
        ctx_guild_id = getattr(ctx.guild, "id", None)
        await ctx.typing()
        async with self.bot.db_connect() as con:
            if msg_id := await con.fetch_saved_quote_message_id(
                owner_id := ctx_guild_id if server else ctx.author.id, alias
            ):
                if row := await con.fetch_message_channel_or_thread(msg_id):
                    channel_or_thread_id, guild_id = row
                    await self._quote_channel_or_thread_message(
                        con, ctx, owner_id, alias, server, MessageTuple(msg_id, channel_or_thread_id, guild_id)
                    )
                else:
                    # Message is a DM
                    try:
                        msg = await lazy_load_message(ctx.author, msg_id)
                        await self.bot.quote_message(
                            msg, ctx.channel, ctx.send, str(ctx.author), "server" if server else "personal"
                        )
                    except discord.Forbidden:
                        await con.delete_saved_quote(owner_id, alias)
                        await con.commit()
                        await ctx.send(":x: **I don't have permissions to read messages from that channel.**")
            else:
                await ctx.send(":x: **Personal Quote not found.**")

    async def _quote_channel_or_thread_message(
        self,
        con: QuoteBotDatabaseConnection,
        ctx: MessageRetrievalContext,
        owner_id: int,
        alias: str,
        server: bool,
        msg_tuple: MessageTuple,
    ) -> None:
        try:
            msg = await ctx.get_channel_or_thread_message(msg_tuple)
            await self.bot.quote_message(msg, ctx.channel, ctx.send, str(ctx.author), "server" if server else "personal")
        except commands.BadArgument as error:
            await con.enable_foreign_keys()
            if isinstance(error, commands.MessageNotFound):
                await con.delete_message(msg_tuple.msg_id)
            elif isinstance(error, commands.ChannelNotFound):
                await con.delete_channel_or_thread(msg_tuple.channel_or_thread_id)
            elif isinstance(error, commands.GuildNotFound):
                await con.delete_guild(msg_tuple.guild_id)
            await con.commit()
            await ctx.send(":x: **Couldn't find the message.**")
        except discord.Forbidden:
            await con.delete_saved_quote(owner_id, alias)
            await con.commit()
            await ctx.send(":x: **I don't have permissions to read messages from that channel.**")

    async def send_list(self, ctx: commands.Context, server: bool = False) -> None:
        guild_id = getattr(ctx.guild, "id", None)
        async with self.bot.db_connect() as con:
            aliases = tuple(await con.fetch_owner_aliases(guild_id if server else ctx.author.id))
            if aliases:
                embed = discord.Embed(
                    description=", ".join(f"`{alias}`" for alias in aliases),
                    color=ctx.author.color.value,
                )
                embed.set_author(
                    name=f"{'Server' if server else 'Personal'} Quotes",
                    icon_url=getattr(ctx.author.avatar, "url", DEFAULT_AVATAR_URL),
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send(f':x: **{"This server has no Server" if server else "You have no Personal"} Quotes.**')

    async def set_saved_quote(self, ctx: MessageRetrievalContext, alias: str, query: str, server: bool = False) -> None:
        guild_id = getattr(ctx.guild, "id", None)
        if len(alias := discord.utils.escape_markdown(alias)) > _MAX_ALIAS_LENGTH:
            await ctx.send(f":x: **Alias can't be longer than {_MAX_ALIAS_LENGTH} characters.**")
            return
        try:
            msg = await anext(ctx.get_messages(query))
        except commands.BadArgument:
            await ctx.send(":x: **Couldn't find the message.**")
        except discord.Forbidden:
            await ctx.send(":x: **I don't have permissions to read messages from that channel.**")
        else:
            async with self.bot.db_connect() as con:
                if await _has_reached_saved_quote_limit(con, owner_id := guild_id if server else ctx.author.id):
                    await ctx.send(
                        f":x: **You can't have more than {_MAX_SAVED_QUOTES} {'Server' if server else 'Personal'} Quotes.**"
                    )
                else:
                    await self._add_saved_quote_to_db(con, owner_id, alias, msg)
                    await ctx.send(f":white_check_mark: **{'Server' if server else 'Personal'} Quote** `{alias}` set.")

    async def _add_saved_quote_to_db(
        self, con: QuoteBotDatabaseConnection, owner_id: int, alias: str, msg: discord.Message
    ) -> None:
        if msg.guild:
            await con.insert_channel_or_thread(msg.channel.id, msg.guild.id)
        await con.insert_message(msg.id, None if isinstance(msg.channel, discord.DMChannel) else msg.channel.id)
        await con.set_saved_quote(owner_id, alias, msg.id)
        await con.commit()

    async def copy_quote(self, ctx: commands.Context, owner_id: int, alias: str, server: bool = False) -> None:
        guild_id = getattr(ctx.guild, "id", None)
        async with self.bot.db_connect() as con:
            # check if new owner already has the quote alias or fewer quotes than limit
            if await con.fetch_saved_quote_message_id(
                new_owner_id := guild_id if server else ctx.author.id, alias
            ) or not await _has_reached_saved_quote_limit(con, new_owner_id):
                if copied_id := await con.fetch_saved_quote_message_id(owner_id, alias):
                    await con.set_saved_quote(new_owner_id, alias, copied_id)
                    await con.commit()
                    await ctx.send(f":white_check_mark: **{'Server' if server else 'Personal'} Quote** `{alias}` set.")
                else:
                    await ctx.send(":x: **Quote not found.**")
            else:
                await ctx.send(
                    f":x: **You can't have more than {_MAX_SAVED_QUOTES} {'Server' if server else 'Personal'} Quotes.**"
                )

    async def remove_quote(self, ctx: commands.Context, alias: str, server: bool = False) -> None:
        guild_id = getattr(ctx.guild, "id", None)
        async with self.bot.db_connect() as con:
            if await con.fetch_saved_quote(owner_id := guild_id if server else ctx.author.id, alias):
                await con.delete_saved_quote(owner_id, alias)
                await con.commit()
                await ctx.send(f":white_check_mark: **{'Server' if server else 'Personal'} Quote** `{alias}` removed.")
            else:
                await ctx.send(":x: **Quote not found.**")

    async def clear_quotes(self, ctx: commands.Context, server=False) -> None:
        guild_id = getattr(ctx.guild, "id", None)
        async with self.bot.db_connect() as con:
            await con.clear_owner_saved_quotes(guild_id if server else ctx.author.id)
            await con.commit()
        await ctx.send(f":white_check_mark: **{'Server' if server else 'Personal'} Quotes** cleared.")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel) -> None:
        async with self.bot.db_connect() as con:
            await con.enable_foreign_keys()
            await con.delete_channel_or_thread(channel.id)
            await con.commit()

    @commands.Cog.listener()
    async def on_message_delete(self, msg: discord.Message) -> None:
        async with self.bot.db_connect() as con:
            await con.enable_foreign_keys()
            await con.delete_message(msg.id)
            await con.commit()

    @commands.hybrid_command(aliases=["personal", "pquote", "pq"])
    @delete_message_if_needed
    async def personalquote(self, ctx: MessageRetrievalContext, alias: str) -> None:
        """Send the specified Personal Quote."""
        await self.send_saved_quote(ctx, alias)

    @commands.hybrid_command(aliases=["plist"])
    async def personallist(self, ctx: commands.Context) -> None:
        """List all your Personal Quotes."""
        await self.send_list(ctx)

    @commands.hybrid_command(aliases=["pset"])
    async def personalset(self, ctx: MessageRetrievalContext, alias: str, *, query: str) -> None:
        """Set a Personal Quote that you can quote in any mutual server."""
        await self.set_saved_quote(ctx, alias, query)

    @commands.hybrid_command(aliases=["pcopy"])
    async def personalcopy(self, ctx: commands.Context, owner_id: int, alias: str) -> None:
        """Copy a Personal/Server Quote so you can use it yourself."""
        await self.copy_quote(ctx, owner_id, alias)

    @commands.hybrid_command(aliases=["premove", "pdelete", "pdel"])
    async def personalremove(self, ctx: commands.Context, alias: str) -> None:
        """Remove a Personal Quote."""
        await self.remove_quote(ctx, alias)

    @commands.hybrid_command(aliases=["pclear"])
    async def personalclear(self, ctx: commands.Context) -> None:
        """Clear all your Personal Quotes."""
        await self.clear_quotes(ctx)

    @personalquote.autocomplete("alias")
    @personalremove.autocomplete("alias")
    async def _personal_alias_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        async with self.bot.db_connect() as con:
            return [
                app_commands.Choice(
                    name=alias,
                    value=alias,
                )
                for alias in await con.fetch_owner_aliases(interaction.user.id)
                if current.lower() in alias.lower()
            ][:25]

    @commands.hybrid_command(aliases=["server", "squote", "sq"])
    @commands.guild_only()
    @delete_message_if_needed
    async def serverquote(self, ctx: MessageRetrievalContext, alias: str) -> None:
        """Send the specified Server Quote."""
        await self.send_saved_quote(ctx, alias, True)

    @commands.hybrid_command(aliases=["slist"])
    @commands.guild_only()
    async def serverlist(self, ctx: commands.Context) -> None:
        """List all Server Quotes."""
        await self.send_list(ctx, True)

    @commands.hybrid_command(aliases=["sset"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def serverset(self, ctx: MessageRetrievalContext, alias: str, *, query: str) -> None:
        """Set a Server Quote that can be quoted in this server.."""
        await self.set_saved_quote(ctx, alias, query, True)

    @commands.hybrid_command(aliases=["scopy"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def servercopy(self, ctx: commands.Context, owner_id: int, alias: str) -> None:
        """Copy a Personal/Server Quote so it can be quoted in this server."""
        await self.copy_quote(ctx, owner_id, alias, True)

    @commands.hybrid_command(aliases=["sremove", "sdelete", "sdel"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def serverremove(self, ctx: commands.Context, alias: str) -> None:
        """Remove a Server Quote."""
        await self.remove_quote(ctx, alias, True)

    @serverquote.autocomplete("alias")
    @serverremove.autocomplete("alias")
    async def _server_alias_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        async with self.bot.db_connect() as con:
            return [
                app_commands.Choice(
                    name=alias,
                    value=alias,
                )
                for alias in await con.fetch_owner_aliases(interaction.guild.id)
            ][:25]

    @commands.hybrid_command(aliases=["sclear"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def serverclear(self, ctx: commands.Context) -> None:
        """Clear all Server Quotes."""
        await self.clear_quotes(ctx, True)


async def setup(bot: QuoteBot) -> None:
    await bot.add_cog(SavedQuotes(bot))
