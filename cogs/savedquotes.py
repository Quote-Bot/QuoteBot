"""
Copyright (C) 2020-2021 JonathanFeenstra, Deivedux, kageroukw

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
import discord
from discord.ext import commands

from core.decorators import delete_message_if_needed
from core.message_retrieval import MessageRetrievalContext, MessageTuple, lazy_load_message
from core.persistence import QuoteBotDatabaseConnection

_MAX_ALIAS_LENGTH = 50
_MAX_SAVED_QUOTES = 50


async def _has_reached_saved_quote_limit(con: QuoteBotDatabaseConnection, owner_id: int) -> bool:
    return await con.fetch_saved_quote_count(owner_id) >= _MAX_SAVED_QUOTES


class SavedQuotes(commands.Cog):
    def __init__(self, bot: "QuoteBot") -> None:
        self.bot = bot

    async def send_saved_quote(self, ctx: MessageRetrievalContext, alias: str, server: bool = False) -> None:
        ctx_guild_id = getattr(ctx.guild, "id", None)
        await ctx.trigger_typing()
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
                        await self.bot.quote_message(msg, ctx.channel, str(ctx.author), "server" if server else "personal")
                    except discord.Forbidden:
                        await con.delete_saved_quote(owner_id, alias)
                        await con.commit()
                        await ctx.send(await self.bot.localize("QUOTE_quote_noperms", ctx_guild_id, "error"))
            else:
                await ctx.send(content=await self.bot.localize("SAVED_personalquote_notfound", ctx_guild_id, "error"))

    async def _quote_channel_or_thread_message(
        self,
        con: "QuoteBotConnection",
        ctx: MessageRetrievalContext,
        owner_id: int,
        alias: str,
        server: bool,
        msg_tuple: MessageTuple,
    ) -> None:
        ctx_guild_id = getattr(ctx.guild, "id", None)
        try:
            msg = await ctx.get_channel_or_thread_message(msg_tuple)
            await self.bot.quote_message(msg, ctx.channel, str(ctx.author), "server" if server else "personal")
        except commands.BadArgument as error:
            await con.enable_foreign_keys()
            if isinstance(error, commands.MessageNotFound):
                await con.delete_message(msg_tuple.msg_id)
            elif isinstance(error, commands.ChannelNotFound):
                await con.delete_channel(msg_tuple.channel_or_thread_id)
            elif isinstance(error, commands.GuildNotFound):
                await con.delete_guild(msg_tuple.guild_id)
            await con.commit()
            await ctx.send(await self.bot.localize("QUOTE_quote_nomessage", ctx_guild_id, "error"))
        except discord.Forbidden:
            await con.delete_saved_quote(owner_id, alias)
            await con.commit()
            await ctx.send(await self.bot.localize("QUOTE_quote_noperms", ctx_guild_id, "error"))

    async def send_list(self, ctx: commands.Context, server: bool = False) -> None:
        guild_id = getattr(ctx.guild, "id", None)
        async with self.bot.db_connect() as con:
            aliases = tuple(await con.fetch_owner_aliases(guild_id if server else ctx.author.id))
            if aliases:
                embed = discord.Embed(
                    description=", ".join(f"`{alias}`" for alias in aliases),
                    color=ctx.author.color.value or discord.Embed.Empty,
                )
                embed.set_author(
                    name=await self.bot.localize(f"SAVED_{'server' if server else 'personal'}list_embedauthor", guild_id),
                    icon_url=ctx.author.avatar.url,
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send(
                    content=await self.bot.localize(
                        f"SAVED_{'server' if server else 'personal'}list_noquotes", guild_id, "error"
                    )
                )

    async def set_saved_quote(self, ctx: MessageRetrievalContext, alias: str, query: str, server: bool = False) -> None:
        guild_id = getattr(ctx.guild, "id", None)
        if len(alias := discord.utils.escape_markdown(alias)) > _MAX_ALIAS_LENGTH:
            await ctx.send((await self.bot.localize("SAVED_personalset_invalidalias", guild_id, "error")).format(alias))
            return
        try:
            msg = await ctx.get_message(query)
        except commands.BadArgument:
            await ctx.send(await self.bot.localize("QUOTE_quote_nomessage", guild_id, "error"))
        except discord.Forbidden:
            await ctx.send(await self.bot.localize("QUOTE_quote_noperms", guild_id, "error"))
        else:
            async with self.bot.db_connect() as con:
                if await _has_reached_saved_quote_limit(con, owner_id := guild_id if server else ctx.author.id):
                    await ctx.send(
                        await self.bot.localize(
                            f"SAVED_{'server' if server else 'personal'}set_limitexceeded", guild_id, "error"
                        )
                    )
                else:
                    await self._add_saved_quote_to_db(con, owner_id, alias, msg)
                    await ctx.send(
                        (
                            await self.bot.localize(
                                f"SAVED_{'server' if server else 'personal'}set_set", guild_id, "success"
                            )
                        ).format(alias)
                    )

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
                    await ctx.send(
                        (
                            await self.bot.localize(
                                f"SAVED_{'server' if server else 'personal'}set_set", guild_id, "success"
                            )
                        ).format(alias)
                    )
                else:
                    await ctx.send(await self.bot.localize("SAVED_personalquote_notfound", guild_id, "error"))
            else:
                await ctx.send(
                    await self.bot.localize(
                        f"SAVED_{'server' if server else 'personal'}set_limitexceeded", guild_id, "error"
                    )
                )

    async def remove_quote(self, ctx: commands.Context, alias: str, server: bool = False) -> None:
        guild_id = getattr(ctx.guild, "id", None)
        async with self.bot.db_connect() as con:
            if await con.fetch_saved_quote(owner_id := guild_id if server else ctx.author.id, alias):
                await con.delete_saved_quote(owner_id, alias)
                await con.commit()
                await ctx.send(
                    (
                        await self.bot.localize(
                            f"SAVED_{'server' if server else 'personal'}remove_removed", guild_id, "success"
                        )
                    ).format(alias)
                )
            else:
                await ctx.send(await self.bot.localize("SAVED_personalquote_notfound", guild_id, "error"))

    async def clear_quotes(self, ctx: commands.Context, server=False) -> None:
        guild_id = getattr(ctx.guild, "id", None)
        async with self.bot.db_connect() as con:
            await con.clear_owner_saved_quotes(guild_id if server else ctx.author.id)
            await con.commit()
        await ctx.send(
            await self.bot.localize(f"SAVED_{'server' if server else 'personal'}clear_cleared", guild_id, "success")
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel) -> None:
        async with self.bot.db_connect() as con:
            await con.enable_foreign_keys()
            await con.delete_channel(channel.id)
            await con.commit()

    @commands.Cog.listener()
    async def on_message_delete(self, msg: discord.Message) -> None:
        async with self.bot.db_connect() as con:
            await con.enable_foreign_keys()
            await con.delete_message(msg.id)
            await con.commit()

    @commands.command(aliases=["personal", "pquote", "pq"])
    @delete_message_if_needed
    async def personalquote(self, ctx: MessageRetrievalContext, alias: str) -> None:
        await self.send_saved_quote(ctx, alias)

    @commands.command(aliases=["plist"])
    async def personallist(self, ctx: commands.Context) -> None:
        await self.send_list(ctx)

    @commands.command(aliases=["pset"])
    async def personalset(self, ctx: commands.Context, alias: str, *, query: str) -> None:
        await self.set_saved_quote(ctx, alias, query)

    @commands.command(aliases=["pcopy"])
    async def personalcopy(self, ctx, owner_id: int, alias: str) -> None:
        await self.copy_quote(ctx, owner_id, alias)

    @commands.command(aliases=["premove", "pdelete", "pdel"])
    async def personalremove(self, ctx: commands.Context, alias: str) -> None:
        await self.remove_quote(ctx, alias)

    @commands.command(aliases=["pclear"])
    async def personalclear(self, ctx: commands.Context) -> None:
        await self.clear_quotes(ctx)

    @commands.command(aliases=["server", "squote", "sq"])
    @commands.guild_only()
    @delete_message_if_needed
    async def serverquote(self, ctx: MessageRetrievalContext, alias: str) -> None:
        await self.send_saved_quote(ctx, alias, True)

    @commands.command(aliases=["slist"])
    @commands.guild_only()
    async def serverlist(self, ctx: commands.Context) -> None:
        await self.send_list(ctx, True)

    @commands.command(aliases=["sset"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def serverset(self, ctx: commands.Context, alias: str, *, query: str) -> None:
        await self.set_saved_quote(ctx, alias, query, True)

    @commands.command(aliases=["scopy"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def servercopy(self, ctx: commands.Context, owner_id: int, alias: str) -> None:
        await self.copy_quote(ctx, owner_id, alias, True)

    @commands.command(aliases=["sremove", "sdelete", "sdel"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def serverremove(self, ctx: commands.Context, alias: str) -> None:
        await self.remove_quote(ctx, alias, True)

    @commands.command(aliases=["sclear"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def serverclear(self, ctx: commands.Context) -> None:
        await self.clear_quotes(ctx, True)


def setup(bot: "QuoteBot") -> None:
    bot.add_cog(SavedQuotes(bot))
