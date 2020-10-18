import re
import aiohttp
import asyncio

import discord
from discord.ext import commands

MESSAGE_URL = re.compile(r"https?://((canary|ptb|www)\.)?discord(app)?\.com/channels/"
                         r"(?P<guild_id>\d+)/(?P<channel_id>\d+)/"
                         r"(?P<msg_id>\d+)")


class Main(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def quote_embed(self, msg, guild, channel, user):
        embed = discord.Embed(description=msg.content, color=msg.author.color.value or discord.Embed.Empty, timestamp=msg.created_at)
        embed.set_author(name=str(msg.author), icon_url=msg.author.avatar_url)
        if msg.attachments:
            if msg.channel.is_nsfw() and not channel.is_nsfw():
                embed.add_field(name=f"{await self.bot.localize(guild, 'MAIN_quote_attachments')}", value=f":underage: {await self.bot.localize(guild, 'MAIN_quote_nonsfw')}")
            elif len(msg.attachments) == 1 and (url := msg.attachments[0].url).lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.gifv', '.webp', '.bmp')):
                embed.set_image(url=url)
            else:
                embed.add_field(name=f"{await self.bot.localize(guild, 'MAIN_quote_attachments')}", value='\n'.join(f'[{attachment.filename}]({attachment.url})' for attachment in msg.attachments))
        footer_text = await self.bot.localize(guild, 'MAIN_quote_embedfooter')
        embed.set_footer(text=footer_text.format(str(user), msg.channel.name))
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
                if not (msg := discord.utils.get(self.bot.cached_messages, channel=channel, id=payload.message_id)):
                    msg = await channel.fetch_message(payload.message_id)
                await channel.send(embed=await self.quote_embed(msg, guild, channel, payload.member))

    @commands.command(aliases=['q'])
    async def quote(self, ctx, query: str):
        perms = ctx.guild.me.permissions_in(ctx.channel)
        if not perms.send_messages:
            return
        elif not perms.embed_links:
            return await ctx.send(content=f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'META_perms_noembed')}")
        msg = None
        try:
            msg_id = int(query)
        except ValueError:
            if match := MESSAGE_URL.match(query.strip()):
                guild_id, channel_id, msg_id = map(int, match.groups()[-3:])
                if (guild := self.bot.get_guild(guild_id)) and (channel := guild.get_channel(channel_id)):
                    perms = guild.me.permissions_in(channel)
                    if perms.read_messages and perms.read_message_history:
                        if not (msg := discord.utils.get(self.bot.cached_messages, channel__id=channel_id, id=msg_id)):
                            try:
                                msg = await channel.fetch_message(msg_id)
                            except discord.NotFound:
                                pass
                    else:
                        return await ctx.send(content=f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'MAIN_quote_noperms')}")
            else:
                return await ctx.send(content=f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'MAIN_quote_inputerror')}")
        else:
            if not (msg := discord.utils.get(self.bot.cached_messages, channel=ctx.channel, id=msg_id)) or (msg := discord.utils.get(self.bot.cached_messages, guild=ctx.guild, id=msg_id)):
                try:
                    msg = await ctx.channel.fetch_message(msg_id)
                except (discord.NotFound, discord.Forbidden):
                    for channel in ctx.guild.text_channels:
                        perms = ctx.guild.me.permissions_in(channel)
                        if perms.read_messages and perms.read_message_history and channel != ctx.channel:
                            try:
                                msg = await channel.fetch_message(msg_id)
                            except discord.NotFound:
                                continue
                            else:
                                break
        if msg:
            await ctx.send(embed=await self.quote_embed(msg, ctx.guild, ctx.channel, ctx.author))
        else:
            await ctx.send(content=f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'MAIN_quote_nomessage')}")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def togglereaction(self, ctx):
        toggle = await (await self.bot.db.execute("SELECT on_reaction FROM guild WHERE id = ?", (str(ctx.guild.id),))).fetchone()
        if toggle[0] == 0:
            await self.bot.db.execute("UPDATE guild SET on_reaction = 1 WHERE id = ?", (str(ctx.guild.id),))
            await self.bot.db.commit()
            await ctx.send(content=f"{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, 'MAIN_togglereaction_enabled')}")
        else:
            await self.bot.db.execute("UPDATE guild SET on_reaction = 0 WHERE id = ?", (str(ctx.guild.id),))
            await self.bot.db.commit()
            await ctx.send(content=f"{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, 'MAIN_togglereaction_disabled')}")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clone(self, ctx, msgs: int, channel: discord.TextChannel):
        if not ctx.guild.me.permissions_in(channel).manage_webhooks:
            await ctx.send(content=f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'META_perms_nowebhooktarget')}")
        elif msgs > 50:
            await ctx.send(content=f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'MAIN_clone_msglimit')}")
        else:
            bot_msg = await ctx.send(content=(await self.bot.localize(ctx.guild, 'MAIN_clone_inprogress')).format(str(msg)))
            webhook_obj = await channel.create_webhook(name=self.bot.name)
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(self.bot.config['botlog_webhook_url'], adapter=discord.AsyncWebhookAdapter(session))
                async for msg in ctx.history(limit=msgs, oldest_first=True):
                    await webhook.send(username=msg.author.name, avatar_url=msg.author.avatar_url, content=msg.content, embeds=msg.embeds, wait=True)
                    try:
                        await asyncio.sleep(0.5)
                    except (discord.NotFound, discord.Forbidden):
                        return await bot_msg.edit(content=f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'MAIN_clone_webhookfail')}")
            await bot_msg.edit(content=f"{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, 'MAIN_clone_success')}")
            await webhook_obj.delete()


def setup(bot):
    bot.add_cog(Main(bot))
