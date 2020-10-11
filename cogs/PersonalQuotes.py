import discord
from discord.ext import commands

class PersonalQuotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def personal_embed(self, user, response):
        embed = discord.Embed(description=response, color=user.color.value or discord.Embed.Empty)
        embed.set_author(name=str(user), icon_url=user.avatar_url)
        embed.set_footer(text=f"{await self.bot.localize(guild, 'MAIN_personal_embedfooter')}")
        return embed

    @commands.command(aliases = ['padd'])
    async def personaladd(self, ctx, *, response: str):
        await self.bot.db.execute("INSERT INTO personal_quote (author, response) VALUES (?, '?')", (str(ctx.author.id), response.replace('\'', '\'\'')))
        await self.bot.db.commit()
        quote_id = await (await self.bot.db.execute("SELECT id FROM personal_quote WHERE author = ? ORDER BY id DESC", (str(ctx.author.id)))).fetchone()
        await ctx.send(content=f"{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, 'PERSONAL_personaladd_added').format(str(quote_id[0]))}")

    @commands.command(aliases = ['premove'])
    async def personalremove(self, ctx, quote_id: int):
        quote_fetch = await (await self.bot.db.execute("SELECT * FROM personal_quote WHERE id = ?", (str(quote_id)))).fetchone()
        if not quote_fetch:
            await ctx.send(content=f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'PERSONAL_personalremove_noquote')}")
        elif quote_fetch[1] != ctx.author.id:
            await ctx.send(content=f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'PERSONAL_personalremove_wrongquote')}")
        else:
            await self.bot.db.execute("DELETE FROM personal_quote WHERE id = ?", ())


def setup(bot):
    bot.add_cog(PersonalQuotes(bot))
