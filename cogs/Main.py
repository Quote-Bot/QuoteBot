import asyncio
import re

import aiohttp
import discord
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
MESSAGE_ID = re.compile(r'(?:(?P<channel_id>[0-9]{15,21})(?:-|/|\s))?(?P<message_id>[0-9]{15,21})$')
MESSAGE_URL = re.compile(r'https?://(?:(canary|ptb|www)\.)?discord(?:app)?\.com/channels/'
                         r'(?:(?P<guild_id>[0-9]{15,21})|(?P<dm>@me))/(?P<channel_id>[0-9]{15,21})/'
                         r'(?P<message_id>[0-9]{15,21})/?(?:$|\s)')


class Main(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_message(self, ctx, group_dict):
        msg_id = int(group_dict['message_id'])
        if group_dict.get('dm'):
            return discord.utils.get(self.bot.cached_messages,
                                     channel=(channel := await ctx.author.create_dm()),
                                     id=msg_id) or await channel.fetch_message(msg_id)
        if channel_id := group_dict.get('channel_id'):
            channel_id = int(channel_id)
            if msg := discord.utils.get(self.bot.cached_messages, channel__id=channel_id, id=msg_id):
                return msg

            if guild_id := group_dict.get('guild_id'):
                guild_id = int(guild_id)
                if msg := discord.utils.get(self.bot.cached_messages, guild__id=guild_id, id=msg_id):
                    return msg
                if guild := self.bot.get_guild(guild_id):
                    if channel := guild.get_channel(channel_id):
                        if msg := await channel.fetch_message(msg_id):
                            return msg
                        raise commands.MessageNotFound(msg_id)
                raise commands.ChannelNotFound(channel_id)

            if channel := self.bot.get_channel(channel_id):
                if msg := await channel.fetch_message(msg_id):
                    return msg
                raise commands.MessageNotFound(msg_id)
            raise commands.ChannelNotFound(channel_id)

        try:
            return discord.utils.get(self.bot.cached_messages,
                                     channel=ctx.channel,
                                     id=msg_id) or await ctx.channel.fetch_message(msg_id)
        except (discord.NotFound, discord.Forbidden):
            if guild := ctx.guild:
                for channel in guild.text_channels:
                    if channel == ctx.channel:
                        continue
                    try:
                        return await channel.fetch_message(msg_id)
                    except (discord.NotFound, discord.Forbidden):
                        continue
            try:
                return await ctx.author.fetch_message(msg_id)
            except (discord.NotFound, discord.Forbidden):
                if msg := self.bot._connection._get_message(msg_id) or discord.utils.get(self.bot.cached_messages, id=msg_id):
                    return msg
            raise

    @commands.Cog.listener()
    async def on_message(self, msg):
        if ((ctx := await self.bot.get_context(msg)).valid or msg.author.bot or not msg.guild
                or (await self.bot.fetch("SELECT quote_links FROM guild WHERE id = ?", True, (msg.guild.id,)))[0]):
            return
        if match := MESSAGE_URL.search(MARKDOWN.sub('?', msg.content)):
            try:
                quoted_msg = await self.get_message(ctx, match.groupdict())
            except Exception:
                return
            return await self.bot.quote_message(quoted_msg, msg.channel, msg.author, 'link')

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.name != '💬' or not (await self.bot.fetch("SELECT on_reaction FROM guild WHERE id = ?", True, (payload.guild_id,)))[0]:
            return
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
            if (perms := guild.me.permissions_in(ctx.channel)).manage_messages and (await self.bot.fetch("SELECT delete_commands FROM guild WHERE id = ?", True, (guild.id,)))[0]:
                await ctx.message.delete()
            if not perms.send_messages:
                return
            elif not perms.embed_links:
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'META_perms_noembed')}")
        if match := MESSAGE_ID.match(query) or MESSAGE_URL.match(query):
            try:
                msg = await self.get_message(ctx, match.groupdict())
            except discord.Forbidden:
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'MAIN_quote_noperms')}")
            except Exception:
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'MAIN_quote_nomessage')}")
            else:
                return await self.bot.quote_message(msg, ctx.channel, ctx.author)
        return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'MAIN_quote_inputerror')}")

    @commands.command(aliases=['togglereactions', 'togglereact', 'reactions'])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def togglereaction(self, ctx):
        async with self.bot.db_connect() as db:
            new = int(not (await (await db.execute("SELECT on_reaction FROM guild WHERE id = ?", (ctx.guild.id,))).fetchone())[0])
            await db.execute("UPDATE guild SET on_reaction = ? WHERE id = ?", (new, ctx.guild.id))
            await db.commit()
        await ctx.send(f"{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, 'MAIN_togglereaction_enabled' if new else 'MAIN_togglereaction_disabled')}")

    @commands.command(aliases=['links'])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def togglelinks(self, ctx):
        async with self.bot.db_connect() as db:
            new = int(not (await (await db.execute("SELECT quote_links FROM guild WHERE id = ?", (ctx.guild.id,))).fetchone())[0])
            await db.execute("UPDATE guild SET quote_links = ? WHERE id = ?", (new, ctx.guild.id))
            await db.commit()
        await ctx.send(f"{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, 'MAIN_togglelinks_enabled' if new else 'MAIN_togglelinks_disabled')}")

    @commands.command(aliases=['delcommands', 'delete'])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def toggledelete(self, ctx):
        async with self.bot.db_connect() as db:
            new = int(not (await (await db.execute("SELECT delete_commands FROM guild WHERE id = ?", (ctx.guild.id,))).fetchone())[0])
            if new and not ctx.me.permissions_in(ctx.channel).manage_messages:
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'META_perms_nomanagemessages')}")
            await db.execute("UPDATE guild SET delete_commands = ? WHERE id = ?", (new, ctx.guild.id))
            await db.commit()
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
