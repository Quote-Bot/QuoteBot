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
import sqlite3
from typing import Iterable, List

import discord
from discord import app_commands
from discord.ext import commands

from bot import QuoteBot
from core.message_retrieval import DEFAULT_AVATAR_URL
from core.persistence import QuoteBotDatabaseConnection

_MAX_PATTERN_LENGTH = 50


def _should_send_highlight(msg: discord.Message, member: discord.Member, query: str) -> bool:
    return (
        member.id != msg.author.id
        and re.search(query, msg.content, re.IGNORECASE) is not None
        and msg.channel.permissions_for(member).read_messages
    )


class Highlights(commands.Cog):
    def __init__(self, bot: QuoteBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message) -> None:
        if msg.guild is None or not msg.content or msg.author.bot:
            return
        async with self.bot.db_connect() as con:
            highlights = await con.fetch_highlights()
            await self._send_highlights(con, msg, highlights)

    async def _send_highlights(
        self, con: QuoteBotDatabaseConnection, msg: discord.Message, highlights: Iterable[sqlite3.Row]
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
                    await self.bot.quote_message(msg, member, member.send, str(member), "highlight")
                except discord.Forbidden:
                    await con.clear_user_highlights(user_id)
                except discord.HTTPException:
                    continue
        await con.commit()

    @commands.hybrid_command(aliases=["hl", "hladd"])
    async def highlight(self, ctx: commands.Context, *, pattern: str) -> None:
        """
        Highlight mutual server messages matching a regex pattern of up to 50 characters to your DMs.

        Requires allowing direct messages from server members in your 'Privacy & Safety' settings.
        """
        if len(pattern) > _MAX_PATTERN_LENGTH:
            await ctx.send(f":x: **Highlight pattern cannot be longer than {_MAX_PATTERN_LENGTH} characters.**")
            return
        try:
            re.compile(pattern)
        except re.error:
            await ctx.send(":x: **Invalid regular expression. You can test your pattern at: https://pythex.org/.**")
            return
        try:
            await ctx.author.send()
        except discord.Forbidden:
            await ctx.send(
                ":x: **Allow direct messages from server members in your 'Privacy & Safety' settings to make use of Highlights.**"
            )
            return
        except discord.HTTPException:
            pass
        async with self.bot.db_connect() as con:
            if await con.fetch_user_highlight_count(user_id := ctx.author.id) >= 10:
                await ctx.send(":x: **Highlight limit exceeded.**")
                return
            await con.insert_highlight(user_id, pattern)
            await con.commit()
        await ctx.send(f":white_check_mark: **Highlight pattern `{pattern.replace('`', '')}` added.**")

    @commands.hybrid_command(aliases=["highlights", "hllist"])
    async def highlightlist(self, ctx: commands.Context) -> None:
        """List your Highlights."""
        async with self.bot.db_connect() as con:
            highlights = await con.fetch_user_highlights(ctx.author.id)
        if highlights:
            embed = discord.Embed(
                description="\n".join(f"`{highlight.replace('`', '')}`" for highlight in highlights),
                color=ctx.author.color.value,
            )
            embed.set_author(
                name="My Highlights",
                icon_url=getattr(ctx.author.avatar, "url", DEFAULT_AVATAR_URL),
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(":x: **You don't have any Highlights.**")

    @commands.hybrid_command(aliases=["hlremove", "hldelete", "hldel"])
    async def highlightremove(self, ctx: commands.Context, *, pattern: str) -> None:
        """Remove a Highlight."""
        async with self.bot.db_connect() as con:
            if await con.fetch_highlight(user_id := ctx.author.id, pattern):
                await con.delete_highlight(user_id, pattern)
            elif len(matches := await con.fetch_user_highlights_starting_with(user_id, pattern)) == 1:
                await con.delete_highlight(user_id, pattern := matches[0][0])
            else:
                await ctx.send(":x: **Highlight not found.**")
                return
            await con.commit()
        await ctx.send(f":white_check_mark: **Highlight pattern `{pattern.replace('`', '')}` removed.**")

    @highlightremove.autocomplete("pattern")
    async def _pattern_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        async with self.bot.db_connect() as con:
            return [
                app_commands.Choice(
                    name=pattern,
                    value=pattern,
                )
                for pattern in await con.fetch_user_highlights_starting_with(interaction.user.id, current)
            ]

    @commands.hybrid_command(aliases=["hlclear"])
    async def highlightclear(self, ctx: commands.Context) -> None:
        """Clear all your Highlights."""
        async with self.bot.db_connect() as con:
            await con.clear_user_highlights(ctx.author.id)
            await con.commit()
        await ctx.send(":white_check_mark: **Cleared all your Highlights.**")


async def setup(bot: QuoteBot) -> None:
    await bot.add_cog(Highlights(bot))
