import json
import os
import re
from functools import partial
from sqlite3 import Error, PARSE_COLNAMES, PARSE_DECLTYPES
from sys import stderr
from traceback import print_tb

import discord
from aiohttp import ClientSession
from aiosqlite import connect
from discord.ext import commands


async def get_prefix(bot, msg):
    if msg.guild:
        try:
            return commands.when_mentioned_or(await bot.fetch("SELECT prefix FROM guild WHERE id = ?", (msg.guild.id,)))(
                bot, msg
            )
        except (AttributeError, Error):
            pass
    return commands.when_mentioned_or(bot.config["default_prefix"])(bot, msg)


class QuoteBotHelpCommand(commands.HelpCommand):
    def command_not_found(self, string):
        return string

    def subcommand_not_found(self, command, string):
        return string

    async def send_bot_help(self, mapping):
        ctx = self.context
        bot = ctx.bot
        prefix = (await get_prefix(bot, ctx.message))[-1]
        guild = ctx.guild
        embed = discord.Embed(color=(guild and guild.me.color.value) or bot.config["default_embed_color"])
        embed.add_field(
            name=await bot.localize(guild, "HELPEMBED_links"),
            value=f"[{await bot.localize(guild, 'HELPEMBED_supportserver')}](https://discord.gg/vkWyTGa)\n"
            f"[{await bot.localize(guild, 'HELPEMBED_addme')}](https://discordapp.com/oauth2/authorize?client_id="
            f"{bot.user.id}&permissions=537257984&scope=bot)\n"
            f"[{await bot.localize(guild, 'HELPEMBED_website')}](https://quote-bot.tk/)\n"
            "[GitHub](https://github.com/Quote-Bot/QuoteBot)",
        )
        embed.add_field(
            name=await bot.localize(guild, "HELPEMBED_commands"),
            value=", ".join(f"`{prefix}{command}`" for command in sorted(c.name for c in bot.commands)),
        )
        embed.set_footer(text=(await bot.localize(guild, "HELPEMBED_footer")).format(prefix))
        await ctx.send(embed=embed)

    async def send_cog_help(self, cog):
        return await self.send_error_message(cog.qualified_name)

    async def send_command_help(self, command):
        ctx = self.context
        bot = ctx.bot
        embed = discord.Embed(
            color=(ctx.guild and ctx.guild.me.color.value) or bot.config["default_embed_color"],
            title=self.get_command_signature(command),
            description=await bot.localize(ctx.guild, f"HELP_{command.name}"),
        )
        await ctx.send(embed=embed)

    async def send_error_message(self, error):
        ctx = self.context
        bot = ctx.bot
        return await ctx.send((await bot.localize(ctx.guild, "HELP_notfound", "error")).format(repr(error)))


class QuoteBot(commands.AutoShardedBot):
    def __init__(self, config):
        super().__init__(
            help_command=QuoteBotHelpCommand(),
            command_prefix=get_prefix,
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
        self.db_connect = partial(connect, "configs/QuoteBot.db", detect_types=PARSE_DECLTYPES | PARSE_COLNAMES)

        self.msg_id_regex = re.compile(r"(?:(?P<channel_id>[0-9]{15,21})(?:-|/|\s))?(?P<message_id>[0-9]{15,21})$")
        self.msg_url_regex = re.compile(
            r"https?://(?:(canary|ptb|www)\.)?discord(?:app)?\.com/channels/"
            r"(?:(?P<guild_id>[0-9]{15,21})|(?P<dm>@me))/(?P<channel_id>[0-9]{15,21})/"
            r"(?P<message_id>[0-9]{15,21})/?(?:$|\s)"
        )

        self.responses = {}

        for filename in os.listdir(path="localization"):
            with open(os.path.join("localization", filename), encoding="utf-8") as json_data:
                self.responses[filename[:-5]] = json.load(json_data)

        self.loop.create_task(self.startup())

    async def _prepare_db(self):
        async with self.db_connect() as con:
            await con.executescript(
                f"""
                PRAGMA auto_vacuum = 1;
                PRAGMA foreign_keys = ON;
                CREATE TABLE
                IF NOT EXISTS guild (
                    id INTEGER PRIMARY KEY,
                    prefix TEXT DEFAULT '{self.config['default_prefix']}' NOT NULL,
                    language TEXT DEFAULT '{self.config['default_lang']}' NOT NULL,
                    on_reaction INTEGER DEFAULT 0 NOT NULL,
                    quote_links INTEGER DEFAULT 0 NOT NULL,
                    delete_commands INTEGER DEFAULT 0 NOT NULL,
                    snipe_requires_manage_messages INTEGER DEFAULT 0 NOT NULL,
                    pin_channel INTEGER
                );
                CREATE TABLE
                IF NOT EXISTS channel (
                    id INTEGER NOT NULL PRIMARY KEY,
                    guild_id INTEGER NOT NULL REFERENCES guild ON DELETE CASCADE
                );
                CREATE TABLE
                IF NOT EXISTS message (
                    id INTEGER NOT NULL PRIMARY KEY,
                    channel_id INTEGER REFERENCES channel ON DELETE CASCADE
                );
                CREATE TABLE
                IF NOT EXISTS personal_quote (
                    owner_id INTEGER NOT NULL REFERENCES guild ON DELETE CASCADE,
                    alias TEXT NOT NULL,
                    message_id INTEGER NOT NULL REFERENCES message ON DELETE CASCADE,
                    PRIMARY KEY (owner_id, alias)
                );
                CREATE TABLE
                IF NOT EXISTS highlight (
                    user_id INTEGER NOT NULL,
                    query TEXT NOT NULL,
                    PRIMARY KEY (user_id, query)
                );
                CREATE TABLE
                IF NOT EXISTS blocked (
                    id INTEGER NOT NULL PRIMARY KEY
                );
            """
            )
            await con.commit()

    async def _update_presence(self):
        guild_count = len(self.guilds)
        await self.change_presence(
            activity=discord.Activity(
                name=f"{guild_count} server{'s' if guild_count != 1 else ''} | >help",
                type=discord.ActivityType.watching,
            )
        )

    async def startup(self):
        self.session = ClientSession(loop=self.loop)
        if botlog_webhook_url := self.config["botlog_webhook_url"]:
            self.webhook = discord.Webhook.from_url(botlog_webhook_url, session=self.session)
        await self._prepare_db()
        await self.wait_until_ready()
        self.owner_ids.add((await self.application_info()).owner.id)

        if guilds := self.guilds:
            async with self.db_connect() as con:
                con.row_factory = lambda cur, row: row[0]
                async with con.execute(
                    f"SELECT id FROM guild WHERE id NOT IN ({', '.join(str(guild.id) for guild in guilds)})"
                ) as cur:
                    removed_guild_ids = ", ".join(str(guild_id) for guild_id in await cur.fetchall())
                if removed_guild_ids:
                    await con.execute(f"DELETE FROM guild WHERE id IN ({removed_guild_ids})")
                    await con.execute(f"DELETE FROM personal_quote WHERE owner_id IN ({removed_guild_ids})")
                for guild in guilds:
                    try:
                        await self.insert_new_guild(con, guild)
                    except Error:
                        continue
                await con.commit()

        print("QuoteBot is ready.")

    async def fetch(self, sql: str, params: tuple = (), one=True, single_column=True):
        async with self.db_connect() as con:
            if single_column:
                con.row_factory = lambda cur, row: row[0]
            async with con.execute(sql, params) as cur:
                return await cur.fetchone() if one else await cur.fetchall()

    async def localize(self, guild, query, response_type=None):
        try:
            response = self.responses[(await self.fetch("SELECT language FROM guild WHERE id = ?", (guild.id,)))][query]
        except (AttributeError, KeyError):
            response = self.responses[self.config["default_lang"]][query]
        if response_type is None:
            return response
        return f"{self.config['response_strings'][response_type]} {response}"

    async def get_message(self, ctx, msg_dict):
        msg_id = int(msg_dict["message_id"])
        if msg_dict.get("dm"):
            return ctx.author._state._get_message(msg_id) or await ctx.author.fetch_message(msg_id)
        if channel_id := msg_dict.get("channel_id"):
            channel_id = int(channel_id)
            if guild_id := msg_dict.get("guild_id"):
                if not (guild := self.get_guild(int(guild_id))) or not (channel := guild.get_channel(channel_id)):
                    raise commands.ChannelNotFound(channel_id)
            elif not (channel := self.get_channel(channel_id)):
                raise commands.ChannelNotFound(channel_id)
            return channel._state._get_message(msg_id) or await channel.fetch_message(msg_id)
        if msg := ctx._state._get_message(msg_id) or self._connection._get_message(msg_id):
            return msg
        try:
            return await ctx.channel.fetch_message(msg_id)
        except (discord.NotFound, discord.Forbidden):
            try:
                return await ctx.author.fetch_message(msg_id)
            except (discord.NotFound, discord.Forbidden):
                if guild := ctx.guild:
                    for channel in guild.text_channels:
                        if channel == ctx.channel:
                            continue
                        try:
                            return await channel.fetch_message(msg_id)
                        except (discord.NotFound, discord.Forbidden):
                            continue
            raise

    async def insert_new_guild(self, con, guild):
        await con.execute(
            "INSERT OR IGNORE INTO guild (id, prefix, language) VALUES (?, ?, ?)",
            (guild.id, self.config["default_prefix"], self.config["default_lang"]),
        )

    async def quote_message(self, msg, destination, quoted_by, quote_type="quote"):
        guild = getattr(destination, "guild", None)
        from_dm = isinstance(msg.channel, discord.DMChannel)
        if not msg.content and msg.embeds:
            return await destination.send(
                (await self.localize(guild, f"MAIN_{quote_type}_rawembed")).format(
                    quoted_by, msg.author, (self.user if from_dm else msg.channel).mention
                ),
                embed=msg.embeds[0],
            )
        embed = discord.Embed(
            description=msg.content if msg.guild == guild else msg.clean_content,
            color=msg.author.color.value or discord.Embed.Empty,
            timestamp=msg.created_at,
        )
        embed.set_author(name=str(msg.author), url=msg.jump_url, icon_url=msg.author.avatar.url)
        if msg.attachments:
            if (
                not from_dm
                and msg.channel.is_nsfw()
                and (isinstance(destination, (discord.DMChannel, discord.User)) or not destination.is_nsfw())
            ):
                embed.add_field(
                    name=f"{await self.localize(guild, 'MAIN_quote_attachments')}",
                    value=f":underage: {await self.localize(guild, 'MAIN_quote_nonsfw')}",
                )
            elif len(msg.attachments) == 1 and (url := msg.attachments[0].url).lower().endswith(
                (".jpg", ".jpeg", ".jfif", ".png", ".gif", ".gifv", ".webp", ".bmp", ".svg", ".tiff")
            ):
                embed.set_image(url=url)
            else:
                embed.add_field(
                    name=f"{await self.localize(guild, 'MAIN_quote_attachments')}",
                    value="\n".join(f"[{attachment.filename}]({attachment.url})" for attachment in msg.attachments),
                )
        embed.set_footer(
            text=(await self.localize(guild, f"MAIN_{quote_type}_embedfooter")).format(
                quoted_by, self.user if from_dm else f"#{msg.channel.name}"
            )
        )
        await destination.send(embed=embed)

    async def on_ready(self):
        await self._update_presence()

    async def on_guild_join(self, guild):
        if guild.id in await self.fetch("SELECT id FROM blocked", one=False):
            return await guild.leave()
        await self._update_presence()
        try:
            async with self.db_connect() as con:
                await self.insert_new_guild(con, guild)
                await con.commit()
        except Error:
            pass

    async def on_guild_remove(self, guild):
        await self._update_presence()
        async with self.db_connect() as con:
            await con.execute("PRAGMA foreign_keys = ON")
            await con.execute("DELETE FROM guild WHERE id = ?", (guild.id,))
            await con.commit()

    async def on_message(self, msg):
        if not msg.author.bot and msg.channel.permissions_for(msg.guild.me).send_messages:
            await self.process_commands(msg)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound) or hasattr(ctx.command, "on_error"):
            return
        if isinstance(error := getattr(error, "original", error), commands.NoPrivateMessage):
            try:
                await ctx.author.send(await self.localize(ctx.guild, "META_command_noprivatemsg", "error"))
            except discord.HTTPException:
                pass
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                (await self.localize(ctx.guild, "META_command_oncooldown", "error")).format(round(error.retry_after, 1))
            )
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(await self.localize(ctx.guild, "META_command_noperms", "error"))
        elif isinstance(error, commands.UserInputError):
            await ctx.send(
                (await self.localize(ctx.guild, "META_command_inputerror", "error")).format(
                    f"{(await self.get_prefix(ctx.message))[-1]}help {ctx.command.qualified_name}"
                )
            )
        else:
            if isinstance(error, discord.HTTPException):
                print(f"In {ctx.command.qualified_name}:", file=stderr)
            print(f"{error.__class__.__name__}: {error}", file=stderr)
            print_tb(error.__traceback__)

    async def close(self):
        print("QuoteBot closed.")
        await self.session.close()
        await super().close()


if __name__ == "__main__":
    print("Starting QuoteBot...")
    with open(os.path.join("configs", "credentials.json")) as config_data:
        quote_bot = QuoteBot(json.load(config_data))

    extensions = ["cogs.Main", "cogs.OwnerOnly", "cogs.PersonalQuotes", "cogs.Snipe", "cogs.Highlights"]

    for extension in extensions:
        quote_bot.load_extension(extension)

    if quote_bot.config["botlog_webhook_url"]:
        quote_bot.load_extension("cogs.Botlog")

    quote_bot.run(quote_bot.config["token"])
