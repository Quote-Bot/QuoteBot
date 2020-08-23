import discord
from discord.ext import commands
from cog.Main import bot_config

class Events(commands.Cog):
	def __init__(self, bot):
		self.bot = bot


def setup(bot):
	bot.add_cog(Events(bot))
