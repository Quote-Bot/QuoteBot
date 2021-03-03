import discord
from discord.ext import commands


class Snipe(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.deletes = {}
        self.edits = {}

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        self.deletes.pop(guild.id, None)
        self.edits.pop(guild.id, None)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if guild_deletes := self.deletes.get(channel.guild.id):
            guild_deletes.pop(channel.id, None)
        if guild_edits := self.edits.get(channel.guild.id):
            guild_edits.pop(channel.id, None)

    @commands.Cog.listener()
    async def on_message_delete(self, msg):
        if msg.guild and not msg.author.bot and not (await self.bot.get_context(msg)).valid:
            if guild_deletes := self.deletes.get(msg.guild.id):
                guild_deletes[msg.channel.id] = msg
            else:
                self.deletes[msg.guild.id] = {msg.channel.id: msg}

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.guild and not before.author.bot and before.pinned == after.pinned:
            if guild_edits := self.edits.get(before.guild.id):
                guild_edits[before.channel.id] = before
            else:
                self.edits[before.guild.id] = {before.channel.id: before}

    async def snipe_msg(self, ctx, channel, edit=False):
        await ctx.trigger_typing()
        if not channel:
            channel = ctx.channel
        if (
            not ctx.author.permissions_in(channel).read_messages
            or not ctx.author.permissions_in(channel).read_message_history
        ):
            return

        if guild := ctx.guild:
            if (perms := guild.me.permissions_in(ctx.channel)).manage_messages and (
                await self.bot.fetch("SELECT delete_commands FROM guild WHERE id = ?", (guild.id,))
            ):
                await ctx.message.delete()
            if not perms.send_messages:
                return
            if not perms.embed_links:
                return await ctx.send(await self.bot.localize(guild, "META_perms_noembed", "error"))

        try:
            msg = (self.edits if edit else self.deletes)[channel.guild.id][channel.id]
        except KeyError:
            await ctx.send(await self.bot.localize(guild, "MAIN_quote_nomessage", "error"))
        else:
            await self.bot.quote_message(msg, ctx.channel, ctx.author, "snipe")

    @commands.command()
    async def snipe(self, ctx, channel: discord.TextChannel = None):
        await self.snipe_msg(ctx, channel)

    @commands.command()
    async def snipeedit(self, ctx, channel: discord.TextChannel = None):
        await self.snipe_msg(ctx, channel, True)


def setup(bot):
    bot.add_cog(Snipe(bot))
