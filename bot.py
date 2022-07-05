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
import asyncio
import importlib
import json
import os
from sys import stderr
from traceback import print_tb
from typing import Awaitable, Callable, List, Iterable, NamedTuple, Optional, Set

import discord
from aiohttp import ClientSession
from aiosqlite import connect
from discord.ext import commands

from core.help import QuoteBotHelpCommand
from core.message_retrieval import DEFAULT_AVATAR_URL, MESSAGE_URL_RE, MessageRetrievalContext
from core.persistence import QuoteBotDatabaseConnection, connect


class QuoteText(NamedTuple):
    footer: str
    raw_embed: str


class QuoteBot(commands.AutoShardedBot):
    _QUOTE_TYPE_TEXT = {
        "quote": QuoteText("Quoted", "quoted"),
        "link": QuoteText("Linked", "linked"),
        "personal": QuoteText("Personal Quote", "(Personal Quote)"),
        "server": QuoteText("Server Quote", "(Server Quote)"),
        "snipe": QuoteText("Sniped", "sniped"),
    }
    owner_ids: Set[int]

    def __init__(self, config: dict) -> None:
        super().__init__(
            help_command=QuoteBotHelpCommand(),
            command_prefix=self.get_prefix,  # type: ignore
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
                message_content=True,
            ),
        )

        self.config = config
        print("Bot configured.")

    async def setup_hook(self):
        self.loop.create_task(self.startup())

    async def startup(self) -> None:
        self.session = ClientSession(loop=self.loop)
        await self._load_extensions()
        print("Extensions loaded.")

        async with self.db_connect() as con:
            await con.prepare_db(self.config["default_prefix"])
        print("Database prepared.")

        await self.wait_until_ready()
        self.owner_ids.add((await self.application_info()).owner.id)
        await self._update_guilds()
        print("Servers updated.")

        for guild in self.guilds:
            try:
                active_threads = await guild.active_threads()
            except TypeError:
                # Due to a bug in discord.py 2.0.0a, `guild.active_threads()` sometimes raises a TypeError.
                continue
            for thread in active_threads:
                await self.on_thread_create(thread)

        print("QuoteBot is ready.")

    def db_connect(self) -> QuoteBotDatabaseConnection:
        return connect(os.path.join("configs", "QuoteBot.db"))  # type: ignore

    async def get_context(self, msg: discord.Message, *, cls=MessageRetrievalContext) -> MessageRetrievalContext:
        return await super().get_context(msg, cls=cls)

    async def get_prefix(self, msg: discord.Message) -> List[str]:
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

    async def _load_extensions(self) -> None:
        for extension in ("highlights", "owneronly", "quote", "savedquotes", "settings", "snipe"):
            await self.load_extension(f"cogs.{extension}")

        if self.config["botlog_webhook_url"]:
            await self.load_extension("cogs.botlog")

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

    async def insert_new_guild(self, con, guild_id: int) -> None:
        await con.insert_guild(guild_id, self.config["default_prefix"])

    async def quote_message(
        self,
        msg: discord.Message,
        destination: discord.abc.Messageable,
        send_method: Callable[..., Awaitable[Optional[discord.Message]]],
        quoted_by: str,
        quote_type: str = "quote",
    ) -> Optional[discord.Message]:
        destination_guild = getattr(destination, "guild", None)
        if self._is_quote(msg):
            return await self._requote_message(msg, destination_guild, send_method, quoted_by, quote_type)
        if not msg.content and msg.embeds:
            return await send_method(
                self._get_raw_embed_quote_content(msg, quoted_by, quote_type, destination_guild),
                embed=msg.embeds[0],
            )
        embed = await self._create_quote_embed(msg, destination)
        self._format_quote_embed_footer(msg, quoted_by, quote_type, destination_guild, embed)
        return await send_method(embed=embed)

    def _is_quote(self, msg: discord.Message) -> bool:
        if msg.author == self.user and len(msg.embeds) == 1:
            if msg.content:
                return True
            embed = msg.embeds[0]
            return embed.author.url is not None and bool(MESSAGE_URL_RE.match(embed.author.url))
        return False

    async def _create_quote_embed(self, msg: discord.Message, destination: discord.abc.Messageable) -> discord.Embed:
        embed = discord.Embed(
            description=msg.content if msg.guild == getattr(destination, "guild", None) else msg.clean_content,
            color=msg.author.color.value or None,
            timestamp=msg.created_at,
        )
        embed.set_author(
            name=str(msg.author), url=msg.jump_url, icon_url=getattr(msg.author.display_avatar, "url", DEFAULT_AVATAR_URL)
        )
        if msg.attachments:
            self._embed_attachments(msg, destination, embed)
        return embed

    def _embed_attachments(
        self, msg: discord.Message, destination_channel: discord.abc.Messageable, embed: discord.Embed
    ) -> None:
        # TODO: embed images from imgur, Gyazo, etc.
        if (
            isinstance(msg.channel, discord.abc.GuildChannel)
            and msg.channel.is_nsfw()
            and isinstance(destination_channel, discord.abc.GuildChannel)
            and not destination_channel.is_nsfw()
        ):
            embed.add_field(
                name="Attachment(s)",
                value=f":underage: **Message quoted from an NSFW channel.**",
            )
        elif len(msg.attachments) == 1 and (url := msg.attachments[0].url).lower().endswith(
            (".jpg", ".jpeg", ".jfif", ".png", ".gif", ".gifv", ".webp", ".bmp", ".svg", ".tiff")
        ):
            embed.set_image(url=url)
        else:
            embed.add_field(
                name="Attachment(s)",
                value="\n".join(f"[{attachment.filename}]({attachment.url})" for attachment in msg.attachments),
            )

    async def _requote_message(
        self,
        msg: discord.Message,
        destination_guild: Optional[discord.Guild],
        send_method: Callable[..., Awaitable[Optional[discord.Message]]],
        quoted_by: str,
        quote_type: str,
    ) -> Optional[discord.Message]:
        embed = msg.embeds[0]
        if msg.content:
            # raw embed quote
            msg.content = self._get_raw_embed_quote_content(msg, quoted_by, quote_type, destination_guild)
        else:
            self._format_quote_embed_footer(msg, quoted_by, quote_type, destination_guild, embed)
        return await send_method(content=msg.content, embed=embed)

    def _get_raw_embed_quote_content(
        self, msg: discord.Message, quoted_by: str, quote_type: str, destination_guild: Optional[discord.Guild]
    ) -> str:
        if quote_type == "highlight":
            return f"Raw embed highlighted from {msg.author.mention} in {msg.channel.mention} ({msg.guild.name})"
        source = (self.user if msg.channel.type == discord.ChannelType.private else msg.channel).mention
        if destination_guild is not None and msg.guild is not None and msg.guild != destination_guild:
            source = f"{source} ({msg.guild.name})"
        return f"Raw embed {self._QUOTE_TYPE_TEXT[quote_type].raw_embed} by @\u200b{quoted_by} from @\u200b{msg.author} in {source}"

    def _format_quote_embed_footer(
        self,
        msg: discord.Message,
        quoted_by: str,
        quote_type: str,
        destination_guild: Optional[discord.Guild],
        embed: discord.Embed,
    ) -> None:
        if quote_type == "highlight":
            embed.set_footer(text=f"Highlighted from #{msg.channel} ({msg.guild.name})")
            return
        source = self.user if msg.channel.type == discord.ChannelType.private else f"#{msg.channel.name}"
        if destination_guild is not None and msg.guild is not None and msg.guild != destination_guild:
            source = f"{source} ({msg.guild.name})"
        embed.set_footer(text=f"{self._QUOTE_TYPE_TEXT[quote_type].footer} by @\u200b{quoted_by} from {source}")

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
            await self.on_thread_create(thread)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self._update_presence()
        async with self.db_connect() as con:
            await con.enable_foreign_keys()
            await con.delete_guild(guild.id)
            await con.commit()

    async def on_thread_create(self, thread: discord.Thread) -> None:
        """Called when a thread is created.

        Bot will join the thread, so it can respond to commands and reactions.

        Args:
            thread (discord.Thread): The thread that was joined or created.
        """
        try:
            await thread.join()
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def on_message(self, msg: discord.Message) -> None:
        if not msg.guild or msg.channel.permissions_for(msg.guild.me).send_messages:
            await self.process_commands(msg)

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.CommandNotFound) or hasattr(ctx.command, "on_error"):
            return
        if isinstance(error := getattr(error, "original", error), commands.NoPrivateMessage):
            try:
                await ctx.author.send(":x: **This command can only be used in servers.**")
            except discord.HTTPException:
                pass
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f":x: **This command is on cooldown. Try again in {round(error.retry_after, 1)} seconds.**")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(":x: **You don't have permission to use this command.**")
        elif ctx.command is None:
            return
        elif isinstance(error, commands.UserInputError):
            await ctx.send(
                f":x: **Invalid command input. See `{ctx.prefix}help {ctx.command.qualified_name}` for usage info.**"
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
        print("uvloop not found, using default event loop.")
    else:
        uvloop.install()  # type: ignore
        print("uvloop installed.")


async def main() -> None:
    print("Starting QuoteBot...")
    install_uvloop_if_found()

    with open(os.path.join("configs", "credentials.json")) as config_data:
        bot = QuoteBot(json.load(config_data))

    async with bot:
        await bot.start(bot.config["token"])


if __name__ == "__main__":
    asyncio.run(main())
