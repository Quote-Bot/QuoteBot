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


class Settings(commands.Cog):
    def __init__(self, bot: "QuoteBot") -> None:
        self.bot = bot

    @commands.command(aliases=["langs", "localizations"])
    async def languages(self, ctx: commands.Context) -> None:
        await ctx.send(
            embed=discord.Embed(
                title=f":map: {await self.bot.localize('SETTINGS_languages_title', getattr(ctx.guild, 'id', None))}",
                description="\n".join(f":flag_{tag[3:].lower()}: **{tag}**" for tag in sorted(self.bot.responses.keys())),
                color=(ctx.guild and ctx.guild.me.color.value) or self.bot.config["default_embed_color"],
            )
        )

    @commands.command(aliases=["togglereactions", "togglereact", "reactions"])
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def togglereaction(self, ctx: commands.Context) -> None:
        async with self.bot.db_connect() as con:
            new = not await con.fetch_quote_reactions(ctx.guild.id)
            await con.set_quote_reactions(ctx.guild.id, new)
            await con.commit()
        await ctx.send(
            await self.bot.localize(
                "SETTINGS_togglereaction_enabled" if new else "SETTINGS_togglereaction_disabled", ctx.guild.id, "success"
            )
        )

    @commands.command(aliases=["links"])
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def togglelinks(self, ctx: commands.Context) -> None:
        async with self.bot.db_connect() as con:
            new = not await con.fetch_quote_links(ctx.guild.id)
            await con.set_quote_links(ctx.guild.id, new)
            await con.commit()
        await ctx.send(
            await self.bot.localize(
                "SETTINGS_togglelinks_enabled" if new else "SETTINGS_togglelinks_disabled", ctx.guild.id, "success"
            )
        )

    @commands.command(aliases=["delcommands", "delete"])
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def toggledelete(self, ctx: commands.Context) -> None:
        async with self.bot.db_connect() as con:
            new = not await con.fetch_delete_commands(ctx.guild.id)
            if new and not ctx.channel.permissions_for(ctx.me).manage_messages:
                await ctx.send(await self.bot.localize("META_perms_nomanagemessages", ctx.guild.id, "error"))
                return
            await con.set_delete_commands(ctx.guild.id, new)
            await con.commit()
        await ctx.send(
            await self.bot.localize(
                "SETTINGS_toggledelete_enabled" if new else "SETTINGS_toggledelete_disabled", ctx.guild.id, "success"
            )
        )

    @commands.command(aliases=["snipepermission", "snipeperms"])
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def togglesnipepermission(self, ctx: commands.Context) -> None:
        async with self.bot.db_connect() as con:
            new = await con.fetch_snipe_requires_manage_messages(ctx.guild.id)
            if new and not ctx.channel.permissions_for(ctx.me).manage_messages:
                await ctx.send(await self.bot.localize("META_perms_nomanagemessages", ctx.guild.id, "error"))
                return
            await con.set_snipe_requires_manage_messages(ctx.guild.id, new)
            await con.commit()
        await ctx.send(
            await self.bot.localize(
                "SETTINGS_togglesnipepermission_enabled" if new else "SETTINGS_togglesnipepermission_disabled",
                ctx.guild.id,
                "success",
            )
        )

    @commands.command(aliases=["prefix"])
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setprefix(self, ctx: commands.Context, prefix: str) -> None:
        if len(prefix) > 3:
            await ctx.send(await self.bot.localize("SETTINGS_setprefix_toolong", ctx.guild.id, "error"))
        else:
            async with self.bot.db_connect() as con:
                await con.set_prefix(ctx.guild.id, prefix)
                await con.commit()
            await ctx.send((await self.bot.localize("SETTINGS_setprefix_set", ctx.guild.id, "success")).format(prefix))

    @commands.command(aliases=["language", "setlang", "lang", "localize"])
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setlanguage(self, ctx: commands.Context, language: str) -> None:
        if len(language) != 5 or (language := language[:2].lower() + language[2:].upper()) not in self.bot.responses:
            await ctx.send(await self.bot.localize("SETTINGS_setlanguage_notavailable", ctx.guild.id, "error"))
        else:
            async with self.bot.db_connect() as con:
                await con.set_language(ctx.guild.id, language)
                await con.commit()
            await ctx.send((await self.bot.localize("SETTINGS_setlanguage_set", ctx.guild.id, "success")).format(language))


def setup(bot: "QuoteBot") -> None:
    bot.add_cog(Settings(bot))
