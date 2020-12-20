import discord
from discord.ext import commands


class OwnerOnly(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    @commands.command(aliases=['kick'])
    async def leave(self, ctx, guild_id: int):
        if guild := self.bot.get_guild(guild_id):
            await guild.leave()
            await ctx.send(f"{self.bot.config['response_strings']['success']} {(await self.bot.localize(ctx.guild, 'OWNER_leave_left')).format(guild.name.replace('`', '').replace('*', ''))}")
        else:
            await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'OWNER_leave_notfound')}")

    @commands.command()
    async def block(self, ctx, guild_id: int):
        async with self.bot.db_connect() as db:
            await db.execute("INSERT OR IGNORE INTO blocked VALUES (?)", (guild_id,))
            await db.commit()
        await ctx.send(f"{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, 'OWNER_block_blocked')}")
        if guild := self.bot.get_guild(guild_id):
            await guild.leave()
            await ctx.send(f"{self.bot.config['response_strings']['success']} {(await self.bot.localize(ctx.guild, 'OWNER_leave_left')).format(guild.name.replace('`', '').replace('*', ''))}")

    @commands.command()
    async def unblock(self, ctx, guild_id: int):
        async with self.bot.db_connect() as db:
            async with db.execute("SELECT * FROM blocked WHERE id = ?", (guild_id,)) as cur:
                if not await cur.fetchone():
                    return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'OWNER_unblock_notfound')}")
            await db.execute("DELETE FROM blocked WHERE id = ?", (guild_id,))
            await db.commit()
        await ctx.send(f"{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, 'OWNER_unblock_unblocked')}")

    @commands.command(aliases=['logout', 'close'])
    async def shutdown(self, ctx):
        try:
            await ctx.send(content=f"{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, 'OWNER_shutdown')}")
        except discord.Forbidden:
            pass
        await self.bot.close()


def setup(bot):
    bot.add_cog(OwnerOnly(bot))
