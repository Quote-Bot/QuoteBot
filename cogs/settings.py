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
from discord.ext import commands

from bot import QuoteBot


class Settings(commands.Cog):
    def __init__(self, bot: QuoteBot) -> None:
        self.bot = bot

    @commands.hybrid_command(aliases=["togglereactions", "togglereact", "reactions"])
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    @commands.guild_only()
    async def togglereaction(self, ctx: commands.Context) -> None:
        """
        Toggle quoting by adding :speech_balloon: reactions to messages in the server.

        Requires the 'Manage Server' permission.
        """
        async with self.bot.db_connect() as con:
            new = not await con.fetch_quote_reactions(ctx.guild.id)
            await con.set_quote_reactions(ctx.guild.id, new)
            await con.commit()
        await ctx.send(f":white_check_mark: **Quoting messages by adding reactions {'enabled' if new else 'disabled'}.**")

    @commands.hybrid_command(aliases=["links"])
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    @commands.guild_only()
    async def togglelinks(self, ctx: commands.Context) -> None:
        """
        Toggle quoting linked messages in the server.

        Requires the 'Manage Server' permission.
        """
        async with self.bot.db_connect() as con:
            new = not await con.fetch_quote_links(ctx.guild.id)
            await con.set_quote_links(ctx.guild.id, new)
            await con.commit()
        await ctx.send(f":white_check_mark: **Quoting linked messages {'enabled' if new else 'disabled'}.**")

    @commands.hybrid_command(aliases=["delcommands", "delete"])
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    @commands.bot_has_guild_permissions(manage_messages=True)
    @commands.guild_only()
    async def toggledelete(self, ctx: commands.Context) -> None:
        """
        Toggle deleting quote command messages in the server.

        Requires the 'Manage Server' permission.
        """
        async with self.bot.db_connect() as con:
            new = not await con.fetch_delete_commands(ctx.guild.id)
            await con.set_delete_commands(ctx.guild.id, new)
            await con.commit()
        await ctx.send(f":white_check_mark: **Deleting quote command messages {'enabled' if new else 'disabled'}.**")

    @commands.hybrid_command(aliases=["snipepermission", "snipeperms"])
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    @commands.guild_only()
    async def togglesnipepermission(self, ctx: commands.Context) -> None:
        """
        Toggle whether the snipe command requires the 'Manage Messages' permission in the server.

        Requires the 'Manage Server' permission.
        """
        async with self.bot.db_connect() as con:
            new = not await con.fetch_snipe_requires_manage_messages(ctx.guild.id)
            await con.set_snipe_requires_manage_messages(ctx.guild.id, new)
            await con.commit()
        await ctx.send(
            f":white_check_mark: **Snipe commands {'now' if new else 'no longer'} require the 'Manage Messages' permission.**"
        )

    @commands.hybrid_command(aliases=["prefix"])
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_guild=True))
    @commands.guild_only()
    async def setprefix(self, ctx: commands.Context, prefix: str) -> None:
        """
        Set the command prefix for the server.

        Requires the 'Manage Server' permission.
        """
        if len(prefix) > 3:
            await ctx.send(":x: **Prefix must be less than 4 characters.**")
        else:
            async with self.bot.db_connect() as con:
                await con.set_prefix(ctx.guild.id, prefix)
                await con.commit()
            await ctx.send(f":white_check_mark: **Prefix set to '{prefix}' in this server.**")


async def setup(bot: QuoteBot) -> None:
    await bot.add_cog(Settings(bot))
