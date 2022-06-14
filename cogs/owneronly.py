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
from typing import Literal, Optional
import discord
from discord.ext import commands

from bot import QuoteBot


class OwnerOnly(commands.Cog):
    def __init__(self, bot: QuoteBot) -> None:
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(aliases=["kick"])
    async def leave(self, ctx: commands.Context, guild_id: int) -> None:
        """Make bot leave the server with the specified ID (owner only)."""
        if guild := self.bot.get_guild(guild_id):
            await guild.leave()
            await ctx.send(
                f":white_check_mark: **Left server `{discord.utils.escape_markdown(guild.name)}`.**", ephemeral=True
            )
        else:
            await ctx.send(":x: **Server not found.**", ephemeral=True)

    @commands.command(aliases=["reloadextension"])
    async def reload(self, ctx: commands.Context, extension: str) -> None:
        """Reload an extension (owner only)."""
        try:
            await self.bot.reload_extension(f"cogs.{extension}")
        except commands.ExtensionError as error:
            await ctx.send(f":x: {error.__class__.__name__}: {error}`")
        else:
            await ctx.send(f":white_check_mark: **Reloaded extension `{extension}`.**", ephemeral=True)

    @commands.command()
    async def block(self, ctx: commands.Context, guild_id: int) -> None:
        """Block the server with the specified ID (owner only)."""
        async with self.bot.db_connect() as con:
            await con.insert_blocked_id(guild_id)
            await con.commit()
        await ctx.send(":white_check_mark: **Server blocked.**", ephemeral=True)
        if guild := self.bot.get_guild(guild_id):
            await guild.leave()

    @commands.command()
    async def unblock(self, ctx: commands.Context, guild_id: int) -> None:
        """Unblock the server with the specified ID (owner only)."""
        async with self.bot.db_connect() as con:
            if not await con.is_blocked(guild_id):
                await ctx.send(":x: **Server was not blocked.**", ephemeral=True)
            else:
                await con.delete_blocked_id(guild_id)
                await con.commit()
                await ctx.send(":white_check_mark: **Server unblocked.**", ephemeral=True)

    @commands.command(aliases=["logout", "close"])
    async def shutdown(self, ctx: commands.Context) -> None:
        """Shutdown the bot (owner only)."""
        try:
            await ctx.send(":white_check_mark: **Shutting down.**", ephemeral=True)
        except discord.Forbidden:
            pass
        await self.bot.close()


async def setup(bot: QuoteBot) -> None:
    await bot.add_cog(OwnerOnly(bot))
