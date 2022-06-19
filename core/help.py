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
from typing import List, Mapping, Optional

import discord
from discord.ext import commands


class QuoteBotHelpCommand(commands.HelpCommand):
    _PERMISSIONS = discord.Permissions(
        view_channel=True,
        view_audit_log=True,
        manage_webhooks=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
        external_emojis=True,
        manage_messages=True,
        read_message_history=True,
    )

    def command_not_found(self, string: str) -> str:
        return string

    def subcommand_not_found(self, command: commands.Command, string: str) -> str:
        return string

    async def send_bot_help(self, mapping: Mapping[Optional[commands.Cog], List[commands.Command]]) -> None:
        ctx = self.context
        bot = ctx.bot
        prefix = (await bot.get_prefix(ctx.message))[-1]
        embed = discord.Embed(color=(ctx.guild and ctx.guild.me.color.value) or bot.config["default_embed_color"])
        embed.add_field(
            name="Links",
            value="[Support Server](https://discord.gg/vkWyTGa)\n"
            f"[Add Me]({discord.utils.oauth_url(bot.user.id, permissions=self._PERMISSIONS)})"
            "[Website](https://quote-bot.tk/)\n"
            "[GitHub](https://github.com/Quote-Bot/QuoteBot)",
        )
        embed.add_field(
            name="Commands",
            value=", ".join(f"`{prefix}{command}`" for command in sorted(c.name for c in bot.commands)),
        )
        embed.set_footer(text=f"Use `{prefix}command` for more info on a command.")
        await ctx.send(embed=embed)

    async def send_cog_help(self, cog: commands.Cog) -> None:
        await self.send_error_message(cog.qualified_name)

    async def send_command_help(self, command: commands.Command) -> None:
        ctx = self.context
        embed = discord.Embed(
            color=(ctx.guild and ctx.guild.me.color.value) or ctx.bot.config["default_embed_color"],
            title=self.get_command_signature(command),
            description=command.help,
        )
        await ctx.send(embed=embed)

    async def send_error_message(self, error: str) -> discord.Message:
        return await self.context.send(f":x: **An error occurred in the help command:**\n```\n{error}\n```")
