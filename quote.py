import json
import os

import discord
from discord.ext import commands

from db_service import DBService


async def get_prefix(bot, msg):
    try:
        guild_prefix = await (await bot.db.execute("SELECT prefix FROM guild WHERE id = ?", (msg.guild.id,))).fetchone()
        return commands.when_mentioned_or(guild_prefix[0])(bot, msg)
    except Exception:
        return commands.when_mentioned_or(bot.config['default_prefix'])(bot, msg)


class QuoteBot(commands.AutoShardedBot):
    def __init__(self, config):
        super().__init__(help_command=None,
                         command_prefix=get_prefix,
                         case_insensitive=True,
                         owner_ids=config['owner_ids'],
                         status=discord.Status.idle,
                         activity=discord.Game('starting up...'),
                         max_messages=config['max_message_cache'])

        self.config = config

        self.responses = dict()

        for filename in os.listdir(path='localization'):
            with open(os.path.join('localization', filename)) as json_data:
                self.responses[filename[:-5]] = json.load(json_data)

    async def localize(self, guild, query):
        try:
            lang = await (await self.db.execute("SELECT language FROM guild WHERE id = ?", (guild.id,))).fetchone()
            return self.responses[lang[0]][query]
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


if __name__ == '__main__':
    with open(os.path.join('configs', 'credentials.json')) as json_data:
        config = json.load(json_data)
        bot = QuoteBot(config)

    extensions = ['cogs.Main', 'cogs.OwnerOnly']

    for extension in extensions:
        bot.load_extension(extension)

    if bot.config['botlog_webhook_url']:
        bot.load_extension('cogs.Botlog')

    bot.run(config['token'])
