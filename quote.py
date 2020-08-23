import discord
import DBService
from discord.ext import commands
from configs import credentials
from cogs.Main import bot_config, blacklist_ids

async def get_prefix(bot, message):
	try:
		return commands.when_mentioned_or(DBService.exec("SELECT Prefix FROM Guilds WHERE Guild = " + str(message.guild.id)).fetchone()[0])(bot, message)
	except:
		return commands.when_mentioned_or(bot_config['default_prefix'])(bot, message)

bot = commands.AutoShardedBot(command_prefix = get_prefix, case_insensitive = True, status = discord.Status.idle, activity = discord.Game('starting up...'), max_messages = bot_config['max_message_cache'])
bot.remove_command('help')

@bot.event
async def on_ready():
	await bot.change_presence(status = discord.Status.online)

@bot.event
async def on_message(message):
	if not message.author.bot and DBService.exec("SELECT " + str(message.author.id) + " FROM Blacklist").fetchone() == None:
		await bot.process_commands(message)


bot.run(bot_config['token'])
