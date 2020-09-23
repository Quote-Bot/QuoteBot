import aiohttp
import discord
from discord.ext import commands


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(self.bot.config['botlog_webhook_url'], adapter=discord.AsyncWebhookAdapter(session))
            localized_content = await self.bot.localize(webhook.guild, 'BOTLOG_guild_join')
            await webhook.send(username=self.bot.user.name, avatar_url=self.bot.user.avatar_url, content=localized_content.format(str(guild).strip('`'), guild.id, guild.member_count, len(self.bot.guilds)))

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(self.bot.config['botlog_webhook_url'], adapter=discord.AsyncWebhookAdapter(session))
            localized_content = await self.bot.localize(webhook.guild, 'BOTLOG_guild_remove')
            await webhook.send(username=self.bot.user.name, avatar_url=self.bot.user.avatar_url, content=localized_content.format(str(guild).strip('`'), guild.id, guild.member_count, len(self.bot.guilds)))


def setup(bot):
    bot.add_cog(Events(bot))
