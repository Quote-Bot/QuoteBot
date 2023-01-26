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
import sys

import discord
from discord.ext import commands

from bot import QuoteBot
from core.message_retrieval import DEFAULT_AVATAR_URL


class BotLog(commands.Cog):
    def __init__(self, bot: QuoteBot) -> None:
        self.bot = bot
        botlog_webhook_url = self.bot.config["botlog_webhook_url"]
        try:
            self.webhook = discord.Webhook.from_url(botlog_webhook_url, session=self.bot.session)
        except ValueError:
            print(f"Invalid botlog webhook url: '{botlog_webhook_url}'. Botlog extension will be unloaded.", file=sys.stderr)
            self.bot.loop.create_task(self._unload())

    async def _unload(self) -> None:
        await self.bot.unload_extension("cogs.botlog")

    async def _send_guild_update(self, guild: discord.Guild, join: bool = True) -> None:
        bot = self.bot
        if bot.user is None:
            return
        async with bot.db_connect() as con:
            if await con.is_blocked(guild.id):
                return
        try:
            await self.webhook.send(
                username=bot.user.name,
                avatar_url=getattr(bot.user.display_avatar, "url", DEFAULT_AVATAR_URL),
                content=f":{'in' if join else 'out'}box_tray: **Guild {'added' if join else 'removed'}: "
                f"{discord.utils.escape_markdown(guild.name)}** (ID: {guild.id})\n"
                f"Total guild members: {guild.member_count}\nTotal guilds: {len(bot.guilds)}",
            )
        except discord.NotFound:
            print("The configured botlog webhook was not found. Botlog extension will be unloaded.", file=sys.stderr)
            await self._unload()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self._send_guild_update(guild, join=True)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self._send_guild_update(guild, join=False)


async def setup(bot: QuoteBot) -> None:
    await bot.add_cog(BotLog(bot))
