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
from typing import List
import discord
from discord import app_commands
from discord.ext import commands

from bot import QuoteBot


class OwnerOnly(commands.Cog):
    def __init__(self, bot: QuoteBot) -> None:
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.hybrid_command(aliases=["reloadextension"])
    async def reload(self, ctx: commands.Context, extension: str) -> None:
        """Reload an extension (owner only)."""
        try:
            await self.bot.reload_extension(f"cogs.{extension}")
        except commands.ExtensionError as error:
            await ctx.send(f":x: {error.__class__.__name__}: {error}`")
        else:
            await ctx.send(f":white_check_mark: **Reloaded extension `{extension}`.**", ephemeral=True)

    @reload.autocomplete("extension")
    async def _extensions_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=name, value=name.lower())
            for name in self.bot.cogs.keys()
            if current.lower() in name.lower()
        ]

    @commands.hybrid_command(aliases=["kick"])
    async def leave(self, ctx: commands.Context, guild_id: int) -> None:
        """Make bot leave the specified server (owner only)."""
        if guild := self.bot.get_guild(guild_id):
            await guild.leave()
            await ctx.send(
                f":white_check_mark: **Left server `{discord.utils.escape_markdown(guild.name)}`.**", ephemeral=True
            )
        else:
            await ctx.send(":x: **Server not found.**", ephemeral=True)

    @commands.hybrid_command()
    async def block(self, ctx: commands.Context, guild_id: int) -> None:
        """Block the specified server (owner only)."""
        async with self.bot.db_connect() as con:
            await con.insert_blocked_id(guild_id)
            await con.commit()
        await ctx.send(":white_check_mark: **Server blocked.**", ephemeral=True)
        if guild := self.bot.get_guild(guild_id):
            await guild.leave()

    @leave.autocomplete("guild_id")
    @block.autocomplete("guild_id")
    async def _current_guilds_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[int]]:
        return [
            app_commands.Choice(name=guild.name, value=guild.id)
            for guild in self.bot.guilds
            if current.lower() in guild.name.lower() or current in str(guild.id)
        ]

    @commands.hybrid_command()
    async def unblock(self, ctx: commands.Context, guild_id: int) -> None:
        """Unblock the specified server (owner only)."""
        async with self.bot.db_connect() as con:
            if not await con.is_blocked(guild_id):
                await ctx.send(":x: **Server was not blocked.**", ephemeral=True)
            else:
                await con.delete_blocked_id(guild_id)
                await con.commit()
                await ctx.send(":white_check_mark: **Server unblocked.**", ephemeral=True)

    @unblock.autocomplete("guild_id")
    async def _blocked_guilds_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[int]]:
        async with self.bot.db_connect() as con:
            return [
                app_commands.Choice(name=str(blocked_id), value=blocked_id)
                for blocked_id in await con.fetch_blocked_ids()
                if current in str(blocked_id)
            ]

    @commands.hybrid_command()
    async def sync(self, ctx: commands.Context) -> None:
        """Sync the application commands to Discord (owner only)."""
        commands = await self.bot.tree.sync()
        await ctx.send(f":white_check_mark: **Synced {len(commands)} commands.**", ephemeral=True)

    @commands.hybrid_command(aliases=["logout", "close"])
    async def shutdown(self, ctx: commands.Context) -> None:
        """Shutdown the bot (owner only)."""
        try:
            await ctx.send(":white_check_mark: **Shutting down.**", ephemeral=True)
        except discord.Forbidden:
            pass
        await self.bot.close()


async def setup(bot: QuoteBot) -> None:
    await bot.add_cog(OwnerOnly(bot))
