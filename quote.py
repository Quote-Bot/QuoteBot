import discord
import json
from discord.ext import commands
from configs import credentials

with open('configs/credentials.json') as json_data:
	response_json = json.load(json_data)

default_prefix = response_json['default_prefix']
token = response_json['token']
del response_json

bot = commands.AutoShardedBot(command_prefix = commands.when_mentioned_or(default_prefix), case_insensitive = True, status = discord.Status.idle, activity = discord.Game('starting up...'))
bot.remove_command('help')

@bot.event
async def on_ready():
	await bot.change_presence(status = discord.Status.online)

@bot.event
async def on_message(message):
	if message.author.bot:
		return
	else:
		await bot.process_commands(message)


bot.run(token)
