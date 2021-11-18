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
from typing import Mapping, Optional

import discord
from discord.ext import commands


class QuoteBotHelpCommand(commands.HelpCommand):
    def command_not_found(self, string: str) -> str:
        return string

    def subcommand_not_found(self, command: commands.Command, string: str) -> str:
        return string

    async def send_bot_help(self, mapping: Mapping[Optional[commands.Cog], list[commands.Command]]) -> None:
        ctx = self.context
        bot = ctx.bot
        prefix = (await bot.get_prefix(ctx.message))[-1]
        guild_id = getattr(ctx.guild, "id", None)
        embed = discord.Embed(color=(ctx.guild and ctx.guild.me.color.value) or bot.config["default_embed_color"])
        embed.add_field(
            name=await bot.localize("HELPEMBED_links", guild_id),
            value=f"[{await bot.localize('HELPEMBED_supportserver', guild_id)}](https://discord.gg/vkWyTGa)\n"
            f"[{await bot.localize('HELPEMBED_addme', guild_id)}](https://discordapp.com/oauth2/authorize?client_id="
            f"{bot.user.id}&permissions=537257984&scope=bot)\n"
            f"[{await bot.localize('HELPEMBED_website', guild_id)}](https://quote-bot.tk/)\n"
            "[GitHub](https://github.com/Quote-Bot/QuoteBot)",
        )
        embed.add_field(
            name=await bot.localize("HELPEMBED_commands", guild_id),
            value=", ".join(f"`{prefix}{command}`" for command in sorted(c.name for c in bot.commands)),
        )
        embed.set_footer(text=(await bot.localize("HELPEMBED_footer", guild_id)).format(prefix))
        await ctx.send(embed=embed)

    async def send_cog_help(self, cog: commands.Cog) -> None:
        await self.send_error_message(cog.qualified_name)

    async def send_command_help(self, command: commands.Command) -> None:
        ctx = self.context
        bot = ctx.bot
        embed = discord.Embed(
            color=(ctx.guild and ctx.guild.me.color.value) or bot.config["default_embed_color"],
            title=self.get_command_signature(command),
            description=await bot.localize(f"HELP_{command.name}", getattr(ctx.guild, "id", None)),
        )
        await ctx.send(embed=embed)

    async def send_error_message(self, error: Exception) -> discord.Message:
        ctx = self.context
        bot = ctx.bot
        return await ctx.send(
            (await bot.localize("HELP_notfound", getattr(ctx.guild, "id", None), "error")).format(repr(error))
        )
