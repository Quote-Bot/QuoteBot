import discord
from discord.ext import commands


class OwnerOnly(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

   	def is_owner(self, ctx):
        return ctx.author.id in self.bot.config['owner_ids']

    @commands.command()
    @commands.check(is_owner)
    async def shutdown(self, ctx):
        try:
            await ctx.send(content=f"{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, 'OWNER_shutdown')}")
        except discord.Forbidden:
            pass
        await self.bot.close()


def setup(bot):
    bot.add_cog(OwnerOnly(bot))
