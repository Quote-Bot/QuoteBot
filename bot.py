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
import importlib
import json
import os
from sys import stderr
from traceback import print_tb
from typing import Iterable, Optional

import discord
from aiohttp import ClientSession
from aiosqlite import connect
from discord.ext import commands

from core.help import QuoteBotHelpCommand
from core.message_retrieval import DEFAULT_AVATAR_URL, MESSAGE_URL_RE, MessageRetrievalContext
from core.persistence import QuoteBotDatabaseConnection, connect


class QuoteBot(commands.AutoShardedBot):
    def __init__(self, config: dict) -> None:
        super().__init__(
            help_command=QuoteBotHelpCommand(),
            command_prefix=self.get_prefix,
            case_insensitive=True,
            owner_ids=set(config["owner_ids"]),
            status=discord.Status.idle,
            activity=discord.Game("starting up..."),
            max_messages=config["max_message_cache"],
            intents=discord.Intents(
                guild_messages=True,
                guild_reactions=True,
                guilds=True,
                dm_messages=config["intents"]["dm_messages"],
                members=config["intents"]["members"],
            ),
        )

        self.config = config

        self.responses = {}

        for filename in os.listdir(path="localization"):
            with open(os.path.join("localization", filename), encoding="utf-8") as json_data:
                self.responses[filename[:-5]] = json.load(json_data)

        self.loop.create_task(self.startup())

    def db_connect(self) -> QuoteBotDatabaseConnection:
        return connect(os.path.join("configs", "QuoteBot.db"))  # type: ignore

    async def get_context(self, msg: discord.Message, *, cls=MessageRetrievalContext) -> MessageRetrievalContext:
        return await super().get_context(msg, cls=cls)

    async def get_prefix(self, msg: discord.Message) -> list[str]:
        prefix = self.config["default_prefix"]
        if msg.guild:
            async with self.db_connect() as con:
                prefix = await con.fetch_prefix(msg.guild.id) or prefix
        return commands.when_mentioned_or(prefix)(self, msg)

    async def _update_presence(self) -> None:
        guild_count = len(self.guilds)
        await self.change_presence(
            activity=discord.Activity(
                name=f"{guild_count} server{'s' if guild_count != 1 else ''} | {self.config['default_prefix']}help",
                type=discord.ActivityType.watching,
            )
        )

    async def startup(self) -> None:
        self.session = ClientSession(loop=self.loop)
        self._load_extensions()

        async with self.db_connect() as con:
            await con.prepare_db(self.config["default_prefix"], self.config["default_lang"])

        await self.wait_until_ready()
        self.owner_ids.add((await self.application_info()).owner.id)
        await self._update_guilds()

        for guild in self.guilds:
            for thread in await guild.active_threads():
                await self.on_thread_join(thread)

        print("QuoteBot is ready.")

    def _load_extensions(self) -> None:
        for extension in ("highlights", "owneronly", "quote", "savedquotes", "settings", "snipe"):
            self.load_extension(f"cogs.{extension}")

        if self.config["botlog_webhook_url"]:
            self.load_extension("cogs.botlog")

    async def _update_guilds(self) -> None:
        async with self.db_connect() as con:
            await con.enable_foreign_keys()
            await con.filter_guilds(tuple(guild.id for guild in self.guilds))
            await con.commit()
            old_guild_ids = await con.fetch_guild_ids()
            await self._purge_deleted_channels(con)
            await self._insert_valid_new_guilds(con, old_guild_ids)
            await con.commit()

    async def _purge_deleted_channels(self, con: QuoteBotDatabaseConnection) -> None:
        for channel_id, guild_id in await con.fetch_channels_and_threads():
            if not (guild := self.get_guild(guild_id)):
                await con.delete_guild(guild_id)
            elif not guild.get_channel(channel_id):
                await con.delete_channel_or_thread(channel_id)

    async def _insert_valid_new_guilds(self, con: QuoteBotDatabaseConnection, old_guild_ids: Iterable[int]) -> None:
        for guild in self.guilds:
            if await con.is_blocked(guild.id):
                await guild.leave()
            elif guild.id not in old_guild_ids:
                await self.insert_new_guild(con, guild.id)

    async def localize(self, query: str, guild_id: Optional[int] = None, response_type: Optional[str] = None) -> str:
        default_lang = self.config["default_lang"]
        if guild_id is None:
            language = default_lang
        else:
            async with self.db_connect() as con:
                language = await con.fetch_language(guild_id) or default_lang

        response = self.responses[language].get(query, self.responses[default_lang][query])
        if response_type is None:
            return response
        return f"{self.config['response_strings'][response_type]} {response}"

    async def insert_new_guild(self, con, guild_id: int) -> None:
        await con.insert_guild(guild_id, self.config["default_prefix"], self.config["default_lang"])

    async def quote_message(
        self, msg: discord.Message, destination: discord.abc.Messageable, quoted_by: str, quote_type: str = "quote"
    ) -> discord.Message:
        destination_guild_id = getattr(getattr(destination, "guild", None), "id", None)
        if self._is_quote(msg):
            return await self._requote_message(msg, destination, quoted_by, quote_type)

        if not msg.content and msg.embeds:
            return await destination.send(
                await self._get_raw_embed_quote_content(msg, quoted_by, quote_type, destination_guild_id),
                embed=msg.embeds[0],
            )

        embed = await self._create_quote_embed(msg, destination)
        await self._format_quote_embed_footer(msg, quoted_by, quote_type, destination_guild_id, embed)
        return await destination.send(embed=embed)

    def _is_quote(self, msg: discord.Message) -> bool:
        if msg.author == self.user and len(msg.embeds) == 1:
            if msg.content:
                return True
            embed = msg.embeds[0]
            return embed.author.url is not discord.Embed.Empty and bool(MESSAGE_URL_RE.match(embed.author.url))
        return False

    async def _create_quote_embed(self, msg: discord.Message, destination: discord.abc.Messageable) -> discord.Embed:
        destination_guild_id = getattr(getattr(destination, "guild", None), "id", None)
        embed = discord.Embed(
            description=msg.content if getattr(msg.guild, "id", None) == destination_guild_id else msg.clean_content,
            color=msg.author.color.value or discord.Embed.Empty,
            timestamp=msg.created_at,
        )
        embed.set_author(
            name=str(msg.author), url=msg.jump_url, icon_url=getattr(msg.author.avatar, "url", DEFAULT_AVATAR_URL)
        )

        # TODO: embed images from imgur, Gyazo, etc.
        if msg.attachments:
            if (
                not isinstance(msg.channel, (discord.abc.PrivateChannel, discord.PartialMessageable))
                and msg.channel.is_nsfw()
                and (
                    isinstance(destination, (discord.abc.PrivateChannel, discord.PartialMessageable, discord.User))
                    or not destination.is_nsfw()
                )
            ):
                embed.add_field(
                    name=f"{await self.localize('QUOTE_quote_attachments', destination_guild_id)}",
                    value=f":underage: {await self.localize('QUOTE_quote_nonsfw', destination_guild_id)}",
                )
            elif len(msg.attachments) == 1 and (url := msg.attachments[0].url).lower().endswith(
                (".jpg", ".jpeg", ".jfif", ".png", ".gif", ".gifv", ".webp", ".bmp", ".svg", ".tiff")
            ):
                embed.set_image(url=url)
            else:
                embed.add_field(
                    name=f"{await self.localize('QUOTE_quote_attachments', destination_guild_id)}",
                    value="\n".join(f"[{attachment.filename}]({attachment.url})" for attachment in msg.attachments),
                )

        return embed

    async def _requote_message(
        self, msg: discord.Message, destination: discord.abc.Messageable, quoted_by: str, quote_type: str
    ) -> discord.Message:
        embed = msg.embeds[0]
        destination_guild_id = getattr(getattr(destination, "guild", None), "id", None)
        if msg.content:
            # raw embed quote
            msg.content = await self._get_raw_embed_quote_content(msg, quoted_by, quote_type, destination_guild_id)
        else:
            await self._format_quote_embed_footer(msg, quoted_by, quote_type, destination_guild_id, embed)
        return await destination.send(content=msg.content, embed=embed)

    async def _get_raw_embed_quote_content(
        self, msg: discord.Message, quoted_by: str, quote_type: str, destination_guild_id: Optional[int]
    ) -> str:
        return (await self.localize(f"QUOTE_{quote_type}_rawembed", destination_guild_id)).format(
            quoted_by,
            msg.author,
            (self.user if isinstance(msg.channel, discord.abc.PrivateChannel) else msg.channel).mention,
        )

    # TODO: show server name in footer if quoted message is from another server
    async def _format_quote_embed_footer(
        self,
        msg: discord.Message,
        quoted_by: str,
        quote_type: str,
        destination_guild_id: Optional[int],
        embed: discord.Embed,
    ) -> None:
        embed.set_footer(
            text=(await self.localize(f"QUOTE_{quote_type}_embedfooter", destination_guild_id)).format(
                quoted_by, self.user if isinstance(msg.channel, discord.DMChannel) else f"#{msg.channel.name}"
            )
        )

    async def on_ready(self) -> None:
        await self._update_presence()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        async with self.db_connect() as con:
            if await con.is_blocked(guild.id):
                await guild.leave()
            else:
                await self._update_presence()
                await self.insert_new_guild(con, guild.id)
                await con.commit()

        for thread in await guild.active_threads():
            await self.on_thread_join(thread)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self._update_presence()
        async with self.db_connect() as con:
            await con.enable_foreign_keys()
            await con.delete_guild(guild.id)
            await con.commit()

    async def on_thread_join(self, thread: discord.Thread) -> None:
        """Called when a thread is joined or created (API cannot differentiate between the two).

        Bot will join the thread if it has not done so already, so it can respond to commands and reactions.

        Args:
            thread (discord.Thread): The thread that was joined or created.
        """
        if thread.me is None:
            try:
                await thread.join()
            except (discord.Forbidden, discord.HTTPException):
                pass

    async def on_message(self, msg: discord.Message) -> None:
        if not msg.guild or msg.channel.permissions_for(msg.guild.me).send_messages:
            await self.process_commands(msg)

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        guild_id = getattr(ctx.guild, "id", None)
        if isinstance(error, commands.CommandNotFound) or hasattr(ctx.command, "on_error"):
            return
        if isinstance(error := getattr(error, "original", error), commands.NoPrivateMessage):
            try:
                await ctx.author.send(await self.localize("META_command_noprivatemsg", guild_id, "error"))
            except discord.HTTPException:
                pass
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                (await self.localize("META_command_oncooldown", guild_id, "error")).format(round(error.retry_after, 1))
            )
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(await self.localize("META_command_noperms", guild_id, "error"))
        elif isinstance(error, commands.UserInputError):
            await ctx.send(
                (await self.localize("META_command_inputerror", guild_id, "error")).format(
                    f"{(await self.get_prefix(ctx.message))[-1]}help {ctx.command.qualified_name}"
                )
            )
        else:
            if isinstance(error, discord.HTTPException):
                print(f"In {ctx.command.qualified_name}:", file=stderr)
            print(f"{error.__class__.__name__}: {error}", file=stderr)
            print_tb(error.__traceback__)

    async def close(self) -> None:
        print("QuoteBot closed.")
        await self.session.close()
        await super().close()


def install_uvloop_if_found() -> None:
    """Set event loop policy from https://github.com/MagicStack/uvloop if installed.

    Should be faster than the default asyncio event loop, but is not supported on Windows.
    """
    try:
        uvloop = importlib.import_module("uvloop")
    except ModuleNotFoundError:
        pass
    else:
        uvloop.install()  # type: ignore


def main() -> None:
    print("Starting QuoteBot...")
    install_uvloop_if_found()

    with open(os.path.join("configs", "credentials.json")) as config_data:
        quote_bot = QuoteBot(json.load(config_data))

    quote_bot.run(quote_bot.config["token"])


if __name__ == "__main__":
    main()
