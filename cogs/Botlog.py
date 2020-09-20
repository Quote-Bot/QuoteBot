import discord
import aiohttp
from discord.ext import commands
from cog.Main import bot_config, get_response

class Events(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	@commands.Cog.listener()
	async def on_guild_join(self, guild):
		async with aiohttp.ClientSession() as session:
			webhook = discord.Webhook.from_url(bot_config['botlog_webhook_url'], adapter = discord.AsyncWebhookAdapter(session))
			await webhook.send(username = self.bot.name, avatar_url = self.bot.avatar_url, content = get_response(None, 'BOTLOG_guild_join').format(str(guild).strip('`'), str(guild.id), str(guild.member_count), str(self.bot.guilds)))

	@commands.Cog.listener()
	async def on_guild_remove(self, guild):
		async with aiohttp.ClientSession() as session:
			webhook = discord.Webhook.from_url(bot_config['botlog_webhook_url'], adapter = discord.AsyncWebhookAdapter(session))
			await webhook.send(username = self.bot.name, avatar_url = self.bot.avatar_url, content = get_response(None, 'BOTLOG_guild_remove').format(str(guild).strip('`'), str(guild.id), str(guild.member_count), str(self.bot.guilds)))


def setup(bot):
	bot.add_cog(Events(bot))
