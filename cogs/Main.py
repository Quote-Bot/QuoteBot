import asyncio
import re

import aiohttp
import discord
from aiosqlite import connect
from discord.ext import commands

MARKDOWN = re.compile((r"```.*?```"                      # ```multiline code```
                       r"|`.*?`"                         # `inline code`
                       r"|^>\s.*?$"                      # > quote
                       r"|\*\*\*(?!\s).*?(?<!\s)\*\*\*"  # ***bold italics***
                       r"|\*\*(?!\s).*?(?<!\s)\*\*"      # **bold**
                       r"|\*(?!\s).*?(?<!\s)\*"          # *italics*
                       r"|__.*?__"                       # __underline__
                       r"|~~.*?~~"                       # ~~strikethrough~~
                       r"|\|\|.*?\|\|"                   # ||spoiler||
                       r"|<https?://\S*?>"),             # <suppressed links>
                      re.DOTALL | re.MULTILINE)
MESSAGE_URL = re.compile(r"https?://((canary|ptb|www)\.)?discord(app)?\.com/channels/"
                         r"(?P<guild_id>\d+|@me)/(?P<channel_id>\d+)/"
                         r"(?P<msg_id>\d+)")


class Main(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_message_from_url(self, url_match: re.Match, user: discord.User):
        channel_id, msg_id = map(int, url_match.groups()[-2:])
        if msg := discord.utils.get(self.bot.cached_messages, channel__id=channel_id, id=msg_id):
            return msg
        if url_match['guild_id'] == '@me':
            if msg := await user.fetch_message(msg_id):
                return msg
            return await (user.dm_channel or await user.create_dm()).fetch_message(msg_id)
        if guild := self.bot.get_guild(int(url_match['guild_id'])):
            channel = guild.get_channel(channel_id)
        else:
            channel = self.bot.get_channel(channel_id)
        if not channel:
            return None
        return await channel.fetch_message(msg_id)

    @commands.Cog.listener()
    async def on_message(self, msg):
        if msg.author.bot or not msg.guild or (await self.bot.get_context(msg)).valid:
            return
        async with connect('configs/QuoteBot.db') as db:
            async with db.execute("SELECT quote_links FROM guild WHERE id = ?", (msg.guild.id,)) as cursor:
                if not (await cursor.fetchone())[0]:
                    return
        if msg_url := MESSAGE_URL.search(MARKDOWN.sub('?', msg.content)):
            try:
                if quoted_msg := await self.get_message_from_url(msg_url, msg.author):
                    return await self.bot.quote_message(quoted_msg, msg.channel, msg.author, 'link')
            except (discord.NotFound, discord.Forbidden):
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.name != '💬':
            return
        if (await (await self.bot.db.execute("SELECT on_reaction FROM guild WHERE id = ?", (payload.guild_id,))).fetchone())[0]:
            guild = self.bot.get_guild(payload.guild_id)
            channel = guild.get_channel(payload.channel_id)
            perms = guild.me.permissions_in(channel)
            if payload.member.permissions_in(channel).send_messages and perms.read_message_history and perms.send_messages and perms.embed_links:
                if not (msg := discord.utils.get(self.bot.cached_messages, channel=channel, id=payload.message_id)):
                    msg = await channel.fetch_message(payload.message_id)
                await self.bot.quote_message(msg, channel, payload.member)

    @commands.command(aliases=['q'])
    async def quote(self, ctx, query: str):
        if guild := ctx.guild:
            if (perms := guild.me.permissions_in(ctx.channel)).manage_messages and (await (await self.bot.db.execute("SELECT delete_commands FROM guild WHERE id = ?", (guild.id,))).fetchone())[0]:
                await ctx.message.delete()
            if not perms.send_messages:
                return
            elif not perms.embed_links:
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'META_perms_noembed')}")
        msg = None
        try:
            msg_id = int(query)
        except ValueError:
            if match := MESSAGE_URL.match(query.strip()):
                try:
                    msg = await self.get_message_from_url(match, ctx.author)
                except discord.Forbidden:
                    return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'MAIN_quote_noperms')}")
                except discord.NotFound:
                    pass
            else:
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'MAIN_quote_inputerror')}")
        else:
            if not (msg := discord.utils.get(self.bot.cached_messages, channel=ctx.channel, id=msg_id)) or (msg := discord.utils.get(self.bot.cached_messages, guild=guild, id=msg_id)):
                try:
                    msg = await ctx.channel.fetch_message(msg_id)
                except (discord.NotFound, discord.Forbidden):
                    if guild:
                        for channel in guild.text_channels:
                            perms = guild.me.permissions_in(channel)
                            if perms.read_messages and perms.read_message_history and channel != ctx.channel:
                                try:
                                    msg = await channel.fetch_message(msg_id)
                                except discord.NotFound:
                                    continue
                                else:
                                    break
        if msg:
            await self.bot.quote_message(msg, ctx.channel, ctx.author)
        else:
            await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'MAIN_quote_nomessage')}")

    @commands.command(aliases=['togglereactions', 'togglereact', 'reactions'])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def togglereaction(self, ctx):
        new = int(not (await (await self.bot.db.execute("SELECT on_reaction FROM guild WHERE id = ?", (ctx.guild.id,))).fetchone())[0])
        await self.bot.db.execute("UPDATE guild SET on_reaction = ? WHERE id = ?", (new, ctx.guild.id))
        await self.bot.db.commit()
        await ctx.send(f"{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, 'MAIN_togglereaction_enabled' if new else 'MAIN_togglereaction_disabled')}")

    @commands.command(aliases=['links'])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def togglelinks(self, ctx):
        new = int(not (await (await self.bot.db.execute("SELECT quote_links FROM guild WHERE id = ?", (ctx.guild.id,))).fetchone())[0])
        await self.bot.db.execute("UPDATE guild SET quote_links = ? WHERE id = ?", (new, ctx.guild.id))
        await self.bot.db.commit()
        await ctx.send(f"{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, 'MAIN_togglelinks_enabled' if new else 'MAIN_togglelinks_disabled')}")

    @commands.command(aliases=['delcommands', 'delete'])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def toggledelete(self, ctx):
        new = int(not (await (await self.bot.db.execute("SELECT delete_commands FROM guild WHERE id = ?", (ctx.guild.id,))).fetchone())[0])
        if new and not ctx.me.permissions_in(ctx.channel).manage_messages:
            return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'META_perms_nomanagemessages')}")
        await self.bot.db.execute("UPDATE guild SET delete_commands = ? WHERE id = ?", (new, ctx.guild.id))
        await self.bot.db.commit()
        await ctx.send(f"{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, 'MAIN_toggledelete_enabled' if new else 'MAIN_toggledelete_disabled')}")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def clone(self, ctx, msg_limit: int, channel: discord.TextChannel):
        if not ctx.guild.me.permissions_in(ctx.channel).manage_webhooks:
            await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'META_perms_nowebhook')}")
        elif msg_limit > 50:
            await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'MAIN_clone_msglimit')}")
        else:
            webhook_obj = await ctx.channel.create_webhook(name=self.bot.user.name)
            messages = await channel.history(limit=msg_limit, before=ctx.message).flatten()
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(webhook_obj.url, adapter=discord.AsyncWebhookAdapter(session))
                for msg in messages[::-1]:
                    try:
                        await webhook.send(username=(msg.author.nick if isinstance(msg.author, discord.Member) and msg.author.nick else msg.author.name), avatar_url=msg.author.avatar_url, content=msg.content, embed=(msg.embeds[0] if msg.embeds and msg.embeds[0].type == 'rich' else None), wait=True)
                    except (discord.NotFound, discord.Forbidden):
                        break
                    else:
                        messages.remove(msg)
                        if messages:
                            await asyncio.sleep(0.5)
            await webhook_obj.delete()


def setup(bot):
    bot.add_cog(Main(bot))
