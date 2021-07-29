from discord.ext import commands


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        if guild.id in await self.bot.fetch("SELECT id FROM blocked", one=False):
            return
        await (bot := self.bot).webhook.send(
            username=bot.user.name,
            avatar_url=bot.user.avatar.url,
            content=(await bot.localize(bot.webhook.guild, "BOTLOG_guild_join", "guild_add")).format(
                guild.name.replace("`", "").replace("*", ""), guild.id, guild.member_count, len(bot.guilds)
            ),
        )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        if guild.id in await self.bot.fetch("SELECT id FROM blocked", one=False):
            return
        await (bot := self.bot).webhook.send(
            username=bot.user.name,
            avatar_url=bot.user.avatar.url,
            content=(await bot.localize(bot.webhook.guild, "BOTLOG_guild_remove", "guild_remove")).format(
                guild.name.replace("`", "").replace("*", ""), guild.id, guild.member_count, len(bot.guilds)
            ),
        )


def setup(bot):
    bot.add_cog(Events(bot))
