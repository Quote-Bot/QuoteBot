import json
import os
from functools import partial
from sqlite3 import PARSE_COLNAMES, PARSE_DECLTYPES

import discord
from aiosqlite import connect
from discord.ext import commands


async def get_prefix(bot, msg):
    if msg.guild:
        try:
            return commands.when_mentioned_or((await bot.fetch("SELECT prefix FROM guild WHERE id = ?", True, (msg.guild.id,)))[0])(bot, msg)
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
        embed = discord.Embed(color=ctx.guild.me.color.value or bot.config['default_embed_color'])
        embed.add_field(name=await bot.localize(ctx.guild, 'HELPEMBED_links'),
                        value=f"[{await bot.localize(ctx.guild, 'HELPEMBED_supportserver')}](https://discord.gg/vkWyTGa)\n"
                              f"[{await bot.localize(ctx.guild, 'HELPEMBED_addme')}](https://discordapp.com/oauth2/authorize?client_id={bot.user.id}&permissions=537257984&scope=bot)\n"
                              f"[{await bot.localize(ctx.guild, 'HELPEMBED_website')}](https://quote-bot.tk/)\n"
                              "[GitHub](https://github.com/Quote-Bot/QuoteBot)")
        embed.add_field(name=await bot.localize(ctx.guild, 'HELPEMBED_commands'),
                        value=', '.join(f'`{prefix}{command}`' for command in sorted(c.name for c in bot.commands)))
        embed.set_footer(text=(await bot.localize(ctx.guild, 'HELPEMBED_footer')).format(prefix))
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

        self.responses = dict()

        for filename in os.listdir(path='localization'):
            with open(os.path.join('localization', filename), encoding='utf-8') as json_data:
                self.responses[filename[:-5]] = json.load(json_data)

    async def _prepare_db(self):
        async with self.db_connect() as db:
            await db.execute("PRAGMA auto_vacuum = 1")
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("""
                CREATE TABLE
                IF NOT EXISTS guild (
                    id INTEGER PRIMARY KEY,
                    prefix TEXT DEFAULT '%s' NOT NULL,
                    language TEXT DEFAULT '%s' NOT NULL,
                    on_reaction INTEGER DEFAULT 0 NOT NULL,
                    quote_links INTEGER DEFAULT 0 NOT NULL,
                    delete_commands INTEGER DEFAULT 0 NOT NULL,
                    pin_channel INTEGER
                )
            """.format(self.config['default_prefix'], self.config['default_lang']))
            await db.execute("""
                CREATE TABLE
                IF NOT EXISTS personal_quote (
                    id INTEGER PRIMARY KEY,
                    author INTEGER NOT NULL,
                    response TEXT
                )
            """)
            await db.commit()

    async def _update_presence(self):
        await self.change_presence(activity=discord.Activity(
                name=f"messages in {'1 server' if (guild_count := len(self.guilds)) == 1 else f'{guild_count} servers'}",
                type=discord.ActivityType.watching))

    async def fetch(self, sql: str, one=True, *args):
        async with self.db_connect() as db:
            async with db.execute(sql, *args) as cur:
                return await cur.fetchone() if one else await cur.fetchall()

    async def localize(self, guild, query):
        try:
            return self.responses[(await self.fetch("SELECT language FROM guild WHERE id = ?", True, (guild.id,)))[0]][query]
        except Exception:
            return self.responses[self.config['default_lang']][query]

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
        await self._prepare_db()

        async with self.db_connect() as db:
            for guild in self.guilds:
                try:
                    await self.insert_new_guild(db, guild)
                except Exception:
                    continue
            await db.commit()

        print("QuoteBot is ready.")

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

    async def on_message(self, msg):
        if not msg.author.bot:
            await self.process_commands(msg)

    async def close(self):
        print("QuoteBot closed.")
        return await super().close()


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
