import discord
import DBService
from discord.ext import commands
from cogs.Main import bot_config, get_response

class OwnerOnly(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	@commands.command()
	async def shutdown(self, ctx):
		try:
			await ctx.send(content = bot_config['response_strings']['success'] + ' ' + get_response(None, 'OWNER_shutdown'))
		except discord.Forbidden:
			pass
		DBService.commit()
		await self.bot.logout()


def setup(bot):
	bot.add_cog(OwnerOnly(bot))
