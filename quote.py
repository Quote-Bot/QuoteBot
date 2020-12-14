import json
import os
from functools import partial
from sys import stderr
from traceback import print_tb
import re
from sqlite3 import PARSE_COLNAMES, PARSE_DECLTYPES

import discord
from aiohttp import ClientSession
from aiosqlite import connect
from discord.ext import commands


async def get_prefix(bot, msg):
    if msg.guild:
        try:
            return commands.when_mentioned_or(await bot.fetch("SELECT prefix FROM guild WHERE id = ?", (msg.guild.id,)))(bot, msg)
        except Exception:
            pass
    return commands.when_mentioned_or(bot.config['default_prefix'])(bot, msg)


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
        embed = discord.Embed(color=(guild and guild.me.color.value) or bot.config['default_embed_color'])
        embed.add_field(name=await bot.localize(guild, 'HELPEMBED_links'),
                        value=f"[{await bot.localize(guild, 'HELPEMBED_supportserver')}](https://discord.gg/vkWyTGa)\n"
                              f"[{await bot.localize(guild, 'HELPEMBED_addme')}](https://discordapp.com/oauth2/authorize?client_id={bot.user.id}&permissions=537257984&scope=bot)\n"
                              f"[{await bot.localize(guild, 'HELPEMBED_website')}](https://quote-bot.tk/)\n"
                              "[GitHub](https://github.com/Quote-Bot/QuoteBot)")
        embed.add_field(name=await bot.localize(guild, 'HELPEMBED_commands'),
                        value=', '.join(f'`{prefix}{command}`' for command in sorted(c.name for c in bot.commands)))
        embed.set_footer(text=(await bot.localize(guild, 'HELPEMBED_footer')).format(prefix))
        await ctx.send(embed=embed)

    async def send_cog_help(self, cog):
        return await self.send_error_message(cog.qualified_name)

    async def send_command_help(self, command):
        ctx = self.context
        bot = ctx.bot
        embed = discord.Embed(color=ctx.guild.me.color.value or bot.config['default_embed_color'],
                              title=self.get_command_signature(command),
                              description=await bot.localize(ctx.guild, f'HELP_{command.name}'))
        await ctx.send(embed=embed)

    async def send_error_message(self, error):
        ctx = self.context
        bot = ctx.bot
        return await ctx.send(f"{bot.config['response_strings']['error']} {(await bot.localize(ctx.guild, 'HELP_notfound')).format(repr(error))}")


class QuoteBot(commands.AutoShardedBot):
    def __init__(self, config):
        super().__init__(help_command=QuoteBotHelpCommand(),
                         command_prefix=get_prefix,
                         case_insensitive=True,
                         owner_ids=set(config['owner_ids']),
                         status=discord.Status.idle,
                         activity=discord.Game('starting up...'),
                         max_messages=config['max_message_cache'],
                         intents=discord.Intents(guild_messages=True,
                                                 guild_reactions=True,
                                                 guilds=True,
                                                 dm_messages=config['intents']['dm_messages'],
                                                 members=config['intents']['members']))

        self.config = config
        self.db_connect = partial(connect, 'configs/QuoteBot.db', detect_types=PARSE_DECLTYPES | PARSE_COLNAMES)

        self.msg_id_regex = re.compile(r'(?:(?P<channel_id>[0-9]{15,21})(?:-|/|\s))?(?P<message_id>[0-9]{15,21})$')
        self.msg_url_regex = re.compile(r'https?://(?:(canary|ptb|www)\.)?discord(?:app)?\.com/channels/'
                                        r'(?:(?P<guild_id>[0-9]{15,21})|(?P<dm>@me))/(?P<channel_id>[0-9]{15,21})/'
                                        r'(?P<message_id>[0-9]{15,21})/?(?:$|\s)')

        self.responses = dict()

        for filename in os.listdir(path='localization'):
            with open(os.path.join('localization', filename), encoding='utf-8') as json_data:
                self.responses[filename[:-5]] = json.load(json_data)

        self.loop.create_task(self.startup())

    async def _prepare_db(self):
        async with self.db_connect() as db:
            await db.execute("PRAGMA auto_vacuum = 1")
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(f"""
                CREATE TABLE
                IF NOT EXISTS guild (
                    id INTEGER PRIMARY KEY,
                    prefix TEXT DEFAULT '{self.config['default_prefix']}' NOT NULL,
                    language TEXT DEFAULT '{self.config['default_lang']}' NOT NULL,
                    on_reaction INTEGER DEFAULT 0 NOT NULL,
                    quote_links INTEGER DEFAULT 0 NOT NULL,
                    delete_commands INTEGER DEFAULT 0 NOT NULL,
                    pin_channel INTEGER
                )
            """)
            await db.execute("""
                CREATE TABLE
                IF NOT EXISTS channel (
                    id INTEGER NOT NULL PRIMARY KEY,
                    guild_id INTEGER NOT NULL REFERENCES guild ON DELETE CASCADE
                )
            """)
            await db.execute("""
                CREATE TABLE
                IF NOT EXISTS message (
                    id INTEGER NOT NULL PRIMARY KEY,
                    channel_id INTEGER REFERENCES channel ON DELETE CASCADE
                )
            """)
            await db.execute("""
                CREATE TABLE
                IF NOT EXISTS personal_quote (
                    owner_id INTEGER NOT NULL REFERENCES guild ON DELETE CASCADE,
                    alias TEXT NOT NULL,
                    message_id INTEGER NOT NULL REFERENCES message ON DELETE CASCADE,
                    PRIMARY KEY (owner_id, alias)
                )
            """)
            await db.commit()

    async def _update_presence(self):
        await self.change_presence(activity=discord.Activity(
                name=f"messages in {'1 server' if (guild_count := len(self.guilds)) == 1 else f'{guild_count} servers'}",
                type=discord.ActivityType.watching))

    async def startup(self):
        self.session = ClientSession(loop=self.loop)
        if botlog_webhook_url := self.config['botlog_webhook_url']:
            self.webhook = discord.Webhook.from_url(botlog_webhook_url,
                                                    adapter=discord.AsyncWebhookAdapter(self.session))
        await self._prepare_db()
        await self.wait_until_ready()
        self.owner_ids.add((await self.application_info()).owner.id)

        if guilds := self.guilds:
            async with self.db_connect() as db:
                db.row_factory = lambda cur, row: row[0]
                async with db.execute(f"SELECT id FROM guild WHERE id NOT IN ({', '.join(str(guild.id) for guild in guilds)})") as cur:
                    removed_guild_ids = ', '.join(str(guild_id) for guild_id in await cur.fetchall())
                if removed_guild_ids:
                    await db.execute(f"DELETE FROM guild WHERE id IN ({removed_guild_ids})")
                    await db.execute(f"DELETE FROM personal_quote WHERE owner_id IN ({removed_guild_ids})")
                for guild in guilds:
                    try:
                        await self.insert_new_guild(db, guild)
                    except Exception:
                        continue
                await db.commit()

        print("QuoteBot is ready.")

    async def fetch(self, sql: str, params: tuple, one=True, single_column=True):
        async with self.db_connect() as db:
            if single_column:
                db.row_factory = lambda cur, row: row[0]
            async with db.execute(sql, params) as cur:
                return await cur.fetchone() if one else await cur.fetchall()

    async def localize(self, guild, query):
        try:
            return self.responses[(await self.fetch("SELECT language FROM guild WHERE id = ?", (guild.id,)))][query]
        except Exception:
            return self.responses[self.config['default_lang']][query]

    async def get_message(self, ctx, msg_dict):
        msg_id = int(msg_dict['message_id'])
        if msg_dict.get('dm'):
            return discord.utils.get(self.cached_messages,
                                     channel=(channel := await ctx.author.create_dm()),
                                     id=msg_id) or await channel.fetch_message(msg_id)
        if channel_id := msg_dict.get('channel_id'):
            channel_id = int(channel_id)
            if msg := discord.utils.get(self.cached_messages, channel__id=channel_id, id=msg_id):
                return msg

            if guild_id := msg_dict.get('guild_id'):
                guild_id = int(guild_id)
                if msg := discord.utils.get(self.cached_messages, guild__id=guild_id, id=msg_id):
                    return msg
                if guild := self.get_guild(guild_id):
                    if channel := guild.get_channel(channel_id):
                        if msg := await channel.fetch_message(msg_id):
                            return msg
                        raise commands.MessageNotFound(msg_id)
                raise commands.ChannelNotFound(channel_id)

            if channel := self.bot.get_channel(channel_id):
                if msg := await channel.fetch_message(msg_id):
                    return msg
                raise commands.MessageNotFound(msg_id)
            raise commands.ChannelNotFound(channel_id)

        try:
            return discord.utils.get(self.cached_messages,
                                     channel=ctx.channel,
                                     id=msg_id) or await ctx.channel.fetch_message(msg_id)
        except (discord.NotFound, discord.Forbidden):
            if guild := ctx.guild:
                for channel in guild.text_channels:
                    if channel == ctx.channel:
                        continue
                    try:
                        return await channel.fetch_message(msg_id)
                    except (discord.NotFound, discord.Forbidden):
                        continue
            try:
                return await ctx.author.fetch_message(msg_id)
            except (discord.NotFound, discord.Forbidden):
                if msg := self._connection._get_message(msg_id) or discord.utils.get(self.cached_messages, id=msg_id):
                    return msg
            raise

    async def insert_new_guild(self, db, guild):
        await db.execute("INSERT OR IGNORE INTO guild (id, prefix, language) VALUES (?, ?, ?)",
                         (guild.id, self.config['default_prefix'], self.config['default_lang']))

    async def quote_message(self, msg, channel, user, type='quote'):
        guild = getattr(channel, 'guild', None)
        if not msg.content and msg.embeds:
            return await channel.send((await self.localize(guild, f'MAIN_{type}_rawembed')).format(user, msg.author, (self.user if isinstance(msg.channel, discord.DMChannel) else msg.channel).mention), embed=msg.embeds[0])
        embed = discord.Embed(description=msg.content if msg.guild == guild else msg.clean_content, color=msg.author.color.value or discord.Embed.Empty, timestamp=msg.created_at)
        embed.set_author(name=str(msg.author), url=msg.jump_url, icon_url=msg.author.avatar_url)
        if msg.attachments:
            if not isinstance(msg.channel, discord.DMChannel) and msg.channel.is_nsfw() and (isinstance(channel, discord.DMChannel) or not channel.is_nsfw()):
                embed.add_field(name=f"{await self.localize(guild, 'MAIN_quote_attachments')}",
                                value=f":underage: {await self.localize(guild, 'MAIN_quote_nonsfw')}")
            elif len(msg.attachments) == 1 and (url := msg.attachments[0].url).lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.gifv', '.webp', '.bmp')):
                embed.set_image(url=url)
            else:
                embed.add_field(name=f"{await self.localize(guild, 'MAIN_quote_attachments')}",
                                value='\n'.join(f'[{attachment.filename}]({attachment.url})' for attachment in msg.attachments))
        embed.set_footer(text=(await self.localize(guild, f'MAIN_{type}_embedfooter')).format(user, self.user if isinstance(msg.channel, discord.DMChannel) else f'#{msg.channel.name}'))
        await channel.send(embed=embed)

    async def on_ready(self):
        await self._update_presence()

    async def on_guild_join(self, guild):
        await self._update_presence()
        try:
            async with self.db_connect() as db:
                await self.insert_new_guild(db, guild)
                await db.commit()
        except Exception:
            pass

    async def on_guild_remove(self, guild):
        await self._update_presence()
        async with self.db_connect() as db:
            await db.execute("DELETE FROM guild WHERE id = ?", (guild.id,))
            await db.execute("DELETE FROM personal_quote WHERE owner_id = ?", (guild.id,))
            await db.commit()

    async def on_message(self, msg):
        if not msg.author.bot:
            await self.process_commands(msg)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound) or hasattr(ctx.command, 'on_error'):
            return
        guild = getattr(ctx, 'guild', None)
        if isinstance(error := getattr(error, 'original', error), commands.NoPrivateMessage):
            try:
                await ctx.author.send(f"{self.config['response_strings']['error']} {await self.localize(guild, 'META_command_noprivatemsg')}")
            except discord.HTTPException:
                pass
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"{self.config['response_strings']['error']} {(await self.localize(guild, 'META_command_oncooldown')).format(round(error.retry_after, 1))}")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(f"{self.config['response_strings']['error']} {await self.localize(guild, 'META_command_noperms')}")
        elif isinstance(error, commands.UserInputError):
            await ctx.send(f"{self.config['response_strings']['error']} {(await self.localize(guild, 'META_command_inputerror')).format(f'{(await self.get_prefix(ctx.message))[-1]}help {ctx.command.qualified_name}')}")
        else:
            if isinstance(error, discord.HTTPException):
                print(f'In {ctx.command.qualified_name}:', file=stderr)
            print(f'{error.__class__.__name__}: {error}', file=stderr)
            print_tb(error.__traceback__)

    async def close(self):
        print("QuoteBot closed.")
        await self.session.close()
        await super().close()


if __name__ == '__main__':
    print("Starting QuoteBot...")
    with open(os.path.join('configs', 'credentials.json')) as json_data:
        config = json.load(json_data)
        bot = QuoteBot(config)

    extensions = ['cogs.Main', 'cogs.OwnerOnly', 'cogs.PersonalQuotes', 'cogs.Snipe']

    for extension in extensions:
        bot.load_extension(extension)

    if bot.config['botlog_webhook_url']:
        bot.load_extension('cogs.Botlog')

    bot.run(config['token'])
