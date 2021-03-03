import discord
from discord.ext import commands


class OwnerOnly(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    @commands.command(aliases=["kick"])
    async def leave(self, ctx, guild_id: int):
        if guild := self.bot.get_guild(guild_id):
            await guild.leave()
            await ctx.send(
                (await self.bot.localize(ctx.guild, "OWNER_leave_left", "success")).format(
                    guild.name.replace("`", "").replace("*", "")
                )
            )
        else:
            await ctx.send(await self.bot.localize(ctx.guild, "OWNER_leave_notfound", "error"))

    @commands.command()
    async def block(self, ctx, guild_id: int):
        async with self.bot.db_connect() as con:
            await con.execute("INSERT OR IGNORE INTO blocked VALUES (?)", (guild_id,))
            await con.commit()
        await ctx.send(await self.bot.localize(ctx.guild, "OWNER_block_blocked", "success"))
        if guild := self.bot.get_guild(guild_id):
            await guild.leave()
            await ctx.send(
                (await self.bot.localize(ctx.guild, "OWNER_leave_left", "success")).format(
                    guild.name.replace("`", "").replace("*", "")
                )
            )

    @commands.command()
    async def unblock(self, ctx, guild_id: int):
        async with self.bot.db_connect() as con:
            async with con.execute("SELECT * FROM blocked WHERE id = ?", (guild_id,)) as cur:
                if not await cur.fetchone():
                    return await ctx.send(await self.bot.localize(ctx.guild, "OWNER_unblock_notfound", "error"))
            await con.execute("DELETE FROM blocked WHERE id = ?", (guild_id,))
            await con.commit()
        await ctx.send(await self.bot.localize(ctx.guild, "OWNER_unblock_unblocked", "success"))

    @commands.command(aliases=["logout", "close"])
    async def shutdown(self, ctx):
        try:
            await ctx.send(content=await self.bot.localize(ctx.guild, "OWNER_shutdown", "success"))
        except discord.Forbidden:
            pass
        await self.bot.close()


def setup(bot):
    bot.add_cog(OwnerOnly(bot))
