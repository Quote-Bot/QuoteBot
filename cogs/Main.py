import discord
from discord.ext import commands


class Main(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def quote_embed(self, message, guild, channel, user):
        embed = discord.Embed(description=message.content, color=message.author.color.value or discord.Embed.Empty, timestamp=message.created_at)
        embed.set_author(name=str(message.author), icon_url=message.author.avatar_url)
        if len(message.attachments) > 0:
            if message.channel.is_nsfw() and not channel.is_nsfw():
                embed.add_field(name='Attachment(s)', value=':underage: ' + await self.bot.localize(guild, 'MAIN_quote_nonsfw'))
            elif len(message.attachments) == 1 and message.attachments[0].url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.gifv', '.webp', '.bmp')):
                embed.set_image(url=message.attachments[0].url)
            else:
                embed.add_field(name='Attachment(s)', value='\n'.join('[' + attachment.filename + '](' + attachment.url + ')' for attachment in message.attachments))
        footer_text = await self.bot.localize(guild, 'MAIN_quote_embedfooter')
        embed.set_footer(text=footer_text.format(str(user), message.channel.name))
        return embed

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        try:
            await self.bot.insert_new_guild(guild)
            await self.bot.db.commit()
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.name != '💬':
            return
        on_reaction = await (await self.bot.db.execute("SELECT on_reaction FROM guild WHERE id = ?", (payload.guild_id,))).fetchone()
        if on_reaction[0] == 1:
            guild = self.bot.get_guild(payload.guild_id)
            channel = guild.get_channel(payload.channel_id)
            perms = guild.me.permissions_in(channel)
            if payload.member.permissions_in(channel).send_messages and perms.read_message_history and perms.send_messages and perms.embed_links:
                message = discord.utils.get(self.bot.cached_messages, channel=channel, id=payload.message_id)
                if not message:
                    message = await channel.fetch_message(payload.message_id)
                await channel.send(embed=await self.quote_embed(message, guild, channel, payload.member))

    @commands.command(aliases=['q'])
    async def quote(self, ctx, msg):
        perms = ctx.guild.me.permissions_in(ctx.channel)
        if not perms.send_messages:
            return
        elif not perms.embed_links:
            await ctx.send(content=self.bot.config['response_strings']['error'] + ' ' + await self.bot.localize(ctx.guild, 'META_perms_noembed'))
        else:
            message = None
            try:
                msg_id = int(msg)
            except ValueError:
                try:
                    list_ids = [int(i) for i in msg.strip('https://canary.discord.com/channels/').split('/')]
                except ValueError:
                    return await ctx.send(content=self.bot.config['response_strings']['error'] + ' ' + await self.bot.localize(ctx.guild, 'MAIN_quote_inputerror'))
                else:
                    guild = self.bot.get_guild(list_ids[0])
                    channel = self.bot.get_channel(list_ids[1])
                    if channel:
                        perms = guild.me.permissions_in(channel)
                        if perms.read_messages and perms.read_message_history:
                            message = discord.utils.get(self.bot.cached_messages, channel__id=list_ids[1], id=list_ids[2])
                            if not message:
                                try:
                                    message = await channel.fetch_message(list_ids[2])
                                except discord.NotFound:
                                    pass
                        else:
                            return await ctx.send(content=self.bot.config['response_strings']['error'] + ' ' + await self.bot.localize(ctx.guild, 'MAIN_quote_noperms'))
            else:
                message = discord.utils.get(self.bot.cached_messages, channel=ctx.channel, id=msg_id)
                if not message:
                    message = discord.utils.get(self.bot.cached_messages, guild=ctx.guild, id=msg_id)
                    if not message:
                        try:
                            message = await ctx.channel.fetch_message(msg_id)
                        except (discord.NotFound, discord.Forbidden):
                            for channel in ctx.guild.text_channels:
                                perms = ctx.guild.me.permissions_in(channel)
                                if perms.read_messages and perms.read_message_history and channel != ctx.channel:
                                    try:
                                        message = await channel.fetch_message(msg_id)
                                    except discord.NotFound:
                                        continue
                                    else:
                                        break
            if message:
                await ctx.send(embed=await self.quote_embed(message, ctx.guild, ctx.channel, ctx.author))
            else:
                await ctx.send(content=self.bot.config['response_strings']['error'] + ' ' + await self.bot.localize(ctx.guild, 'MAIN_quote_nomessage'))


def setup(bot):
    bot.add_cog(Main(bot))
