import discord
import os
import json
import DBService
from discord.ext import commands

with open('configs/credentials.json') as json_data:
	bot_config = json.load(json_data)

responses = dict()
for i in os.listdir(path = 'localization'):
	with open(i) as json_data:
		responses[i.strip('.json')] = json.load(json_data)

def get_response(guild, response):
	lang = DBService.exec("SELECT Language FROM Guilds WHERE Guild = " + str(guild.id)).fetchone()
	try:
		return responses[lang[0]][response]
	except:
		return responses['en-US'][response]

def quote_embed(ctx, message):
	embed = discord.Embed(description = message.content, color = (None if message.author.color.default() else message.author.color), timestamp = message.created_at)
	embed.set_author(name = str(message.author), icon_url = message.author.avatar_url)
	if len(message.attachments) > 0:
		if message.channel.is_nsfw() and not ctx.channel.is_nsfw():
			embed.add_field(name = 'Attachment(s)', value = ':underage: **Explicit content belongs in a NSFW channel.**')
		elif len(message.attachments) == 1 and message.attachments[0].url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.gifv', '.webp', '.bmp')):
			embed.set_image(url = message.attachments[0].url)
		else:
			embed.add_field(name = 'Attachment(s)', value = '\n'.join('[' + attachment.filename + '](' + attachment.url + ')' for attachment in message.attachments))
	embed.set_footer(text = get_response(ctx.guild, 'MAIN_quote_embedfooter').format(str(ctx.author), message.channel.name))
	return embed

class Main(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	@commands.command(aliases = ['q'])
	async def quote(self, ctx, msg_id: int):
		message = None
		async with ctx.typing():
			try:
				message = await ctx.channel.fetch_message(msg_id)
			except (discord.NotFound, discord.Forbidden):
				for channel in ctx.guild.text_channels:
					if ctx.guild.me.permissions_in(channel).read_messages and ctx.guild.me.permissions_in(channel).read_message_history and channel != ctx.channel:
						try:
							message = await channel.fetch_message(msg_id)
						except discord.NotFound:
							continue
						else:
							break

		if message:
			await ctx.send(embed = quote_embed(ctx, message))
		else:
			await ctx.send(content = bot_config['response_strings']['error'] + ' **' + get_response(ctx.guild, 'MAIN_quote_nomessage') + '**')


def setup(bot):
	bot.add_cog(Main(bot))
