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
import re
import sqlite3
from typing import Iterable

import discord
from discord.ext import commands


def _should_send_highlight(msg: discord.Message, member: discord.Member, query: str) -> bool:
    return (
        member.id != msg.author.id
        and re.search(query, msg.content, re.IGNORECASE) is not None
        and msg.channel.permissions_for(member).read_messages
    )


class Highlights(commands.Cog):
    def __init__(self, bot: "QuoteBot") -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message) -> None:
        if msg.guild is None or not msg.content or msg.author.bot:
            return
        async with self.bot.db_connect() as con:
            highlights = await con.fetch_highlights()
            await self._send_highlights(con, msg, highlights)

    async def _send_highlights(
        self, con: "QuoteBotConnection", msg: discord.Message, highlights: Iterable[sqlite3.Row]
    ) -> None:
        seen_user_ids = set()
        for user_id, query in highlights:
            if not self.bot.get_user(user_id):
                await con.clear_user_highlights(user_id)
            elif not (member := msg.guild.get_member(user_id)):
                continue
            elif user_id not in seen_user_ids and _should_send_highlight(msg, member, query):
                seen_user_ids.add(user_id)
                try:
                    await self.bot.quote_message(msg, member, str(member), "highlight")
                except discord.Forbidden:
                    await con.clear_user_highlights(user_id)
                except discord.HTTPException:
                    continue
        await con.commit()

    @commands.command(aliases=["hl"])
    async def highlight(self, ctx: commands.Context, *, pattern: str) -> None:
        guild_id = getattr(ctx.guild, "id", None)
        if len(pattern) > 50:
            await ctx.send(await self.bot.localize("HIGHLIGHTS_highlight_toolong", guild_id, "error"))
            return
        try:
            re.compile(pattern)
        except re.error:
            await ctx.send(await self.bot.localize("HIGHLIGHTS_highlight_invalid", guild_id, "error"))
            return
        try:
            await ctx.author.send()
        except discord.Forbidden:
            await ctx.send(await self.bot.localize("HIGHLIGHTS_highlight_dmsdisabled", guild_id, "error"))
            return
        except discord.HTTPException:
            pass
        async with self.bot.db_connect() as con:
            if await con.fetch_user_highlight_count(user_id := ctx.author.id) >= 10:
                await ctx.send(await self.bot.localize("HIGHLIGHTS_highlight_limitexceeded", guild_id, "error"))
                return
            await con.insert_highlight(user_id, pattern)
            await con.commit()
        await ctx.send(
            (await self.bot.localize("HIGHLIGHTS_highlight_added", guild_id, "success")).format(
                pattern.replace("`", "").replace("*", "")
            )
        )

    @commands.command(aliases=["highlights", "hllist"])
    async def highlightlist(self, ctx: commands.Context) -> None:
        async with self.bot.db_connect() as con:
            highlights = await con.fetch_user_highlights(ctx.author.id)
        guild_id = getattr(ctx.guild, "id", None)
        if highlights:
            embed = discord.Embed(
                description="\n".join(f"`{highlight.replace('`', '')}`" for highlight in highlights),
                color=ctx.author.color.value or discord.Embed.Empty,
            )
            embed.set_author(
                name=await self.bot.localize("HIGHLIGHTS_highlightlist_embedauthor", guild_id),
                icon_url=ctx.author.avatar.url,
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(await self.bot.localize("HIGHLIGHTS_highlightlist_nohighlights", guild_id, "error"))

    @commands.command(aliases=["hlremove", "hldelete", "hldel"])
    async def highlightremove(self, ctx: commands.Context, *, pattern: str) -> None:
        guild_id = getattr(ctx.guild, "id", None)
        async with self.bot.db_connect() as con:
            if await con.fetch_highlight(user_id := ctx.author.id, pattern):
                await con.delete_highlight(user_id, pattern)
            elif len(matches := await con.fetch_user_highlights_starting_with(user_id, pattern)) == 1:
                await con.delete_highlight(user_id, pattern := matches[0][0])
            else:
                await ctx.send(await self.bot.localize("HIGHLIGHTS_highlightremove_notfound", guild_id, "error"))
                return
            await con.commit()
        await ctx.send(
            (await self.bot.localize("HIGHLIGHTS_highlightremove_removed", guild_id, "success")).format(
                pattern.replace("`", "").replace("*", "")
            )
        )

    @commands.command(aliases=["hlclear"])
    async def highlightclear(self, ctx: commands.Context) -> None:
        async with self.bot.db_connect() as con:
            await con.clear_user_highlights(ctx.author.id)
            await con.commit()
        await ctx.send(
            await self.bot.localize("HIGHLIGHTS_highlightclear_cleared", getattr(ctx.guild, "id", None), "success")
        )


def setup(bot: "QuoteBot") -> None:
    bot.add_cog(Highlights(bot))
