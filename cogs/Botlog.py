from discord.ext import commands


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await (bot := self.bot).webhook.send(username=bot.user.name,
                                             avatar_url=bot.user.avatar_url,
                                             content=f"{bot.config['response_strings']['guild_add']} {(await bot.localize(bot.webhook.guild, 'BOTLOG_guild_join')).format(str(guild).strip('`'), guild.id, guild.member_count, len(bot.guilds))}")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        await (bot := self.bot).webhook.send(username=bot.user.name,
                                             avatar_url=bot.user.avatar_url,
                                             content=f"{bot.config['response_strings']['guild_remove']} {(await bot.localize(bot.webhook.guild, 'BOTLOG_guild_remove')).format(str(guild).strip('`'), guild.id, guild.member_count, len(bot.guilds))}")


def setup(bot):
    bot.add_cog(Events(bot))
