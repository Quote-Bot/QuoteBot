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


class OwnerOnly(commands.Cog):
    def __init__(self, bot: "QuoteBot") -> None:
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(aliases=["kick"])
    async def leave(self, ctx: commands.Context, guild_id: int) -> None:
        ctx_guild_id = getattr(ctx.guild, "id", None)
        if guild := self.bot.get_guild(guild_id):
            await guild.leave()
            await ctx.send(
                (await self.bot.localize("OWNER_leave_left", ctx_guild_id, "success")).format(
                    discord.utils.escape_markdown(guild.name)
                )
            )
        else:
            await ctx.send(await self.bot.localize("OWNER_leave_notfound", ctx_guild_id, "error"))

    @commands.command(aliases=["reloadextension"])
    async def reload(self, ctx: commands.Context, *, extension: str) -> None:
        try:
            self.bot.reload_extension(f"cogs.{extension}")
        except commands.ExtensionError as error:
            await ctx.send(f":x: {error.__class__.__name__}: {error}`")
        else:
            await ctx.send(
                (await self.bot.localize("OWNER_reload_success", getattr(ctx.guild, "id", None), "success")).format(
                    extension
                )
            )

    @commands.command()
    async def block(self, ctx: commands.Context, guild_id: int) -> None:
        ctx_guild_id = getattr(ctx.guild, "id", None)
        async with self.bot.db_connect() as con:
            await con.insert_blocked_id(guild_id)
            await con.commit()
        await ctx.send(await self.bot.localize("OWNER_block_blocked", ctx_guild_id, "success"))
        if guild := self.bot.get_guild(guild_id):
            await guild.leave()
            await ctx.send(
                (await self.bot.localize("OWNER_leave_left", ctx_guild_id, "success")).format(
                    discord.utils.escape_markdown(guild.name)
                )
            )

    @commands.command()
    async def unblock(self, ctx: commands.Context, guild_id: int) -> None:
        ctx_guild_id = getattr(ctx.guild, "id", None)
        async with self.bot.db_connect() as con:
            if not await con.is_blocked(guild_id):
                await ctx.send(await self.bot.localize("OWNER_unblock_notfound", ctx_guild_id, "error"))
            else:
                await con.delete_blocked_id(guild_id)
                await con.commit()
                await ctx.send(await self.bot.localize("OWNER_unblock_unblocked", ctx_guild_id, "success"))

    @commands.command(aliases=["logout", "close"])
    async def shutdown(self, ctx: commands.Context) -> None:
        try:
            await ctx.send(content=await self.bot.localize("OWNER_shutdown", getattr(ctx.guild, "id", None), "success"))
        except discord.Forbidden:
            pass
        await self.bot.close()


def setup(bot: "QuoteBot") -> None:
    bot.add_cog(OwnerOnly(bot))
