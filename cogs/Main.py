import asyncio
import re

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


class Main(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_converter = commands.TextChannelConverter()
        self.user_converter = commands.UserConverter()

    @commands.Cog.listener()
    async def on_message(self, msg):
        if ((ctx := await self.bot.get_context(msg)).valid or msg.author.bot or not msg.guild
                or not (await self.bot.fetch("SELECT quote_links FROM guild WHERE id = ?", (msg.guild.id,)))):
            return
        if match := self.bot.msg_url_regex.search(MARKDOWN.sub('?', msg.content)):
            try:
                quoted_msg = await self.bot.get_message(ctx, match.groupdict())
            except Exception:
                return
            return await self.bot.quote_message(quoted_msg, msg.channel, msg.author, 'link')

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.name != '💬' or not await self.bot.fetch("SELECT on_reaction FROM guild WHERE id = ?", (payload.guild_id,)):
            return
        guild = self.bot.get_guild(payload.guild_id)
        channel = guild.get_channel(payload.channel_id)
        perms = guild.me.permissions_in(channel)
        if payload.member.permissions_in(channel).send_messages and perms.read_message_history and perms.send_messages and perms.embed_links:
            if not (msg := discord.utils.get(self.bot.cached_messages, channel=channel, id=payload.message_id)):
                msg = await channel.fetch_message(payload.message_id)
            await self.bot.quote_message(msg, channel, payload.member)

    @commands.command(aliases=['q'])
    async def quote(self, ctx, *, query: str = None):
        await ctx.trigger_typing()
        if guild := ctx.guild:
            if (perms := guild.me.permissions_in(ctx.channel)).manage_messages and await self.bot.fetch("SELECT delete_commands FROM guild WHERE id = ?", (guild.id,)):
                await ctx.message.delete()
            if not perms.send_messages:
                return
            elif not perms.embed_links:
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'META_perms_noembed')}")
        if query is None:
            try:
                async for msg in ctx.channel.history(limit=1, before=ctx.message):
                    return await self.bot.quote_message(msg, ctx.channel, ctx.author)
            except Exception:
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'MAIN_quote_nomessage')}")
        if match := self.bot.msg_id_regex.match(query) or self.bot.msg_url_regex.match(query):
            try:
                return await self.bot.quote_message(await self.bot.get_message(ctx, match.groupdict()), ctx.channel, ctx.author)
            except discord.Forbidden:
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'MAIN_quote_noperms')}")
            except Exception:
                if match.group('channel_id'):
                    return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'MAIN_quote_nomessage')}")
        try:
            channel = await self.channel_converter.convert(ctx, query)
        except Exception:
            try:
                user = await self.user_converter.convert(ctx, query)
            except Exception:
                if match:
                    return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'MAIN_quote_nomessage')}")
            else:
                try:
                    async for msg in ctx.channel.history(before=ctx.message):
                        if msg.author.id == user.id:
                            return await self.bot.quote_message(msg, ctx.channel, ctx.author)
                except Exception:
                    pass
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'MAIN_quote_nomessage')}")
        else:
            try:
                async for msg in channel.history(limit=1, before=ctx.message):
                    return await self.bot.quote_message(msg, ctx.channel, ctx.author)
            except discord.Forbidden:
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'MAIN_quote_noperms')}")
            except Exception:
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'MAIN_quote_nomessage')}")
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
            webhook = discord.Webhook.from_url(webhook_obj.url, adapter=discord.AsyncWebhookAdapter(self.bot.session))
            for msg in messages[::-1]:
                try:
                    await webhook.send(username=getattr(msg.author, 'nick', msg.author.name),
                                       avatar_url=msg.author.avatar_url,
                                       content=msg.content if ctx.guild == channel.guild else msg.clean_content,
                                       embed=(msg.embeds[0] if msg.embeds and msg.embeds[0].type == 'rich' else None),
                                       wait=True)
                except (discord.NotFound, discord.Forbidden):
                    break
                else:
                    messages.remove(msg)
                    if messages:
                        await asyncio.sleep(0.5)
            await webhook_obj.delete()


def setup(bot):
    bot.add_cog(Main(bot))
