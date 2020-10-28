import json
import os

import discord
from discord.ext import commands

from db_service import DBService


async def get_prefix(bot, msg):
    try:
        return commands.when_mentioned_or((await (await bot.db.execute("SELECT prefix FROM guild WHERE id = ?", (msg.guild.id,))).fetchone())[0] if msg.guild else bot.config['default_prefix'])(bot, msg)
    except Exception:
        return commands.when_mentioned_or(bot.config['default_prefix'])(bot, msg)


class QuoteBotHelpCommand(commands.HelpCommand):
    def command_not_found(self, string):
        return string

    def subcommand_not_found(self, command, string):
        return string

    async def get_prefix(self, guild):
        try:
            return (await (await bot.db.execute("SELECT prefix FROM guild WHERE id = ?", (guild.id,))).fetchone())[0] if guild else bot.config['default_prefix']
        except Exception:
            return bot.config['default_prefix']

    async def send_bot_help(self, mapping):
        ctx = self.context
        bot = ctx.bot
        prefix = await self.get_prefix(ctx.guild)
        embed = discord.Embed(color=ctx.guild.me.color.value or bot.config['default_embed_color'])
        embed.add_field(name=await bot.localize(ctx.guild, 'HELPEMBED_links'),
                        value=f"[{await bot.localize(ctx.guild, 'HELPEMBED_supportserver')}](https://discord.gg/vkWyTGa)\n"
                              f"[{await bot.localize(ctx.guild, 'HELPEMBED_addme')}](https://discordapp.com/oauth2/authorize?client_id={bot.user.id}&permissions=347136&scope=bot)\n"
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

        self.responses = dict()

        for filename in os.listdir(path='localization'):
            with open(os.path.join('localization', filename), encoding='utf-8') as json_data:
                self.responses[filename[:-5]] = json.load(json_data)

    async def localize(self, guild, query):
        try:
            lang = (await (await self.db.execute("SELECT language FROM guild WHERE id = ?", (guild.id,))).fetchone())[0]
            return self.responses[lang][query]
        except Exception:
            return self.responses[self.config['default_lang']][query]

    async def insert_new_guild(self, guild):
        await self.db.execute(
            """INSERT OR IGNORE INTO guild (id, prefix, language)
               VALUES (?, ?, ?)""",
            (guild.id, self.config['default_prefix'], self.config['default_lang']))

    async def on_ready(self):
        await self.change_presence(status=discord.Status.online)
        self.db = await DBService.create(self.config)

        for guild in self.guilds:
            try:
                await self.insert_new_guild(guild)
            except Exception:
                continue

        await self.db.commit()

    async def on_message(self, message):
        if not message.author.bot:
            await self.process_commands(message)

    async def close(self):
        if db := getattr(self, 'db', False):
            await db.close()
        return await super().close()


if __name__ == '__main__':
    with open(os.path.join('configs', 'credentials.json')) as json_data:
        config = json.load(json_data)
        bot = QuoteBot(config)

    extensions = ['cogs.Main', 'cogs.PersonalQuotes', 'cogs.OwnerOnly']

    for extension in extensions:
        bot.load_extension(extension)

    if bot.config['botlog_webhook_url']:
        bot.load_extension('cogs.Botlog')

    bot.run(config['token'])
