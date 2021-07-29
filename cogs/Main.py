import asyncio
import re

import discord
from discord.ext import commands

MARKDOWN = re.compile(
    (
        r"```.*?```"  # ```multiline code```
        r"|`.*?`"  # `inline code`
        r"|^>\s.*?$"  # > quote
        r"|\*\*\*(?!\s).*?(?<!\s)\*\*\*"  # ***bold italics***
        r"|\*\*(?!\s).*?(?<!\s)\*\*"  # **bold**
        r"|\*(?!\s).*?(?<!\s)\*"  # *italics*
        r"|__.*?__"  # __underline__
        r"|~~.*?~~"  # ~~strikethrough~~
        r"|\|\|.*?\|\|"  # ||spoiler||
        r"|<https?://\S*?>"  # <suppressed links>
    ),
    re.DOTALL | re.MULTILINE,
)
QUOTE_EXCEPTIONS = (discord.NotFound, discord.Forbidden, discord.HTTPException, commands.BadArgument)


async def webhook_copy(webhook, msg, clean_content=False):
    await webhook.send(
        username=getattr(msg.author, "nick", False) or msg.author.name,
        avatar_url=msg.author.avatar.url,
        content=msg.clean_content if clean_content else msg.content,
        files=[await attachment.to_file() for attachment in msg.attachments],
        embed=(msg.embeds[0] if msg.embeds and msg.embeds[0].type == "rich" else None),
        allowed_mentions=discord.AllowedMentions.none(),
    )


class Main(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_converter = commands.UserConverter()

    @commands.Cog.listener()
    async def on_message(self, msg):
        if (
            (ctx := await self.bot.get_context(msg)).valid
            or msg.author.bot
            or not msg.guild
            or not (await self.bot.fetch("SELECT quote_links FROM guild WHERE id = ?", (msg.guild.id,)))
        ):
            return
        if match := self.bot.msg_url_regex.search(MARKDOWN.sub("?", msg.content)):
            try:
                quoted_msg = await self.bot.get_message(ctx, match.groupdict())
                await self.bot.quote_message(quoted_msg, msg.channel, msg.author, "link")
            except QUOTE_EXCEPTIONS:
                pass

    @commands.Cog.listener()
    async def on_thread_join(self, thread):
        if not thread.me:
            try:
                await thread.join()
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.name != "💬" or not await self.bot.fetch(
            "SELECT on_reaction FROM guild WHERE id = ?", (payload.guild_id,)
        ):
            return
        guild = self.bot.get_guild(payload.guild_id)
        channel = guild.get_channel(payload.channel_id)
        perms = channel.permissions_for(guild.me)
        if (
            channel.permissions_for(payload.member).send_messages
            and perms.read_message_history
            and perms.send_messages
            and perms.embed_links
        ):
            try:
                msg = channel._state._get_message(payload.message_id) or await channel.fetch_message(payload.message_id)
                await self.bot.quote_message(msg, channel, payload.member)
            except QUOTE_EXCEPTIONS:
                pass

    @commands.command(aliases=["q"])
    async def quote(self, ctx, *, query: str = None):
        await ctx.trigger_typing()
        if guild := ctx.guild:
            if (perms := ctx.channel.permissions_for(ctx.me)).manage_messages and await self.bot.fetch(
                "SELECT delete_commands FROM guild WHERE id = ?", (guild.id,)
            ):
                await ctx.message.delete()
            if not perms.send_messages:
                return
            if not perms.embed_links:
                return await ctx.send(await self.bot.localize(guild, "META_perms_noembed", "error"))
        if query is None:
            try:
                async for msg in ctx.channel.history(limit=1, before=ctx.message):
                    await self.bot.quote_message(msg, ctx.channel, ctx.author)
            except QUOTE_EXCEPTIONS:
                await ctx.send(await self.bot.localize(guild, "MAIN_quote_nomessage", "error"))
        elif match := self.bot.msg_id_regex.match(query) or self.bot.msg_url_regex.match(query):
            try:
                return await self.bot.quote_message(
                    await self.bot.get_message(ctx, match.groupdict()), ctx.channel, ctx.author
                )
            except discord.Forbidden:
                return await ctx.send(await self.bot.localize(guild, "MAIN_quote_noperms", "error"))
            except (discord.NotFound, discord.HTTPException, commands.BadArgument):
                if match.group("channel_id"):
                    return await ctx.send(await self.bot.localize(guild, "MAIN_quote_nomessage", "error"))
            try:
                user = await self.user_converter.convert(ctx, query)
            except QUOTE_EXCEPTIONS:
                await ctx.send(await self.bot.localize(guild, "MAIN_quote_nomessage", "error"))
            else:
                try:
                    async for msg in ctx.channel.history(limit=150, before=ctx.message):
                        if msg.author.id == user.id:
                            return await self.bot.quote_message(msg, ctx.channel, ctx.author)
                except QUOTE_EXCEPTIONS:
                    pass
                await ctx.send(await self.bot.localize(guild, "MAIN_quote_nomessage", "error"))
        else:
            try:
                async for msg in ctx.channel.history(limit=150, before=ctx.message):
                    if re.search(query, msg.content, re.IGNORECASE):
                        return await self.bot.quote_message(msg, ctx.channel, ctx.author)
            except QUOTE_EXCEPTIONS:
                pass
            except re.error:
                return await ctx.send(await self.bot.localize(guild, "MAIN_quote_inputerror", "error"))
            await ctx.send(await self.bot.localize(guild, "MAIN_quote_nomessage", "error"))

    @commands.command(aliases=["langs", "localizations"])
    async def languages(self, ctx):
        await ctx.send(
            embed=discord.Embed(
                title=f":map: {await self.bot.localize(guild := ctx.guild, 'MAIN_languages_title')}",
                description="\n".join(f":flag_{tag[3:].lower()}: **{tag}**" for tag in sorted(self.bot.responses.keys())),
                color=(guild and guild.me.color.value) or self.bot.config["default_embed_color"],
            )
        )

    @commands.command(aliases=["togglereactions", "togglereact", "reactions"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def togglereaction(self, ctx):
        async with self.bot.db_connect() as con:
            new = int(
                not (await (await con.execute("SELECT on_reaction FROM guild WHERE id = ?", (ctx.guild.id,))).fetchone())[0]
            )
            await con.execute("UPDATE guild SET on_reaction = ? WHERE id = ?", (new, ctx.guild.id))
            await con.commit()
        await ctx.send(
            await self.bot.localize(
                ctx.guild, "MAIN_togglereaction_enabled" if new else "MAIN_togglereaction_disabled", "success"
            )
        )

    @commands.command(aliases=["links"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def togglelinks(self, ctx):
        async with self.bot.db_connect() as con:
            new = int(
                not (await (await con.execute("SELECT quote_links FROM guild WHERE id = ?", (ctx.guild.id,))).fetchone())[0]
            )
            await con.execute("UPDATE guild SET quote_links = ? WHERE id = ?", (new, ctx.guild.id))
            await con.commit()
        await ctx.send(
            await self.bot.localize(ctx.guild, "MAIN_togglelinks_enabled" if new else "MAIN_togglelinks_disabled", "success")
        )

    @commands.command(aliases=["delcommands", "delete"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def toggledelete(self, ctx):
        async with self.bot.db_connect() as con:
            new = int(
                not (
                    await (await con.execute("SELECT delete_commands FROM guild WHERE id = ?", (ctx.guild.id,))).fetchone()
                )[0]
            )
            if new and not ctx.channel.permissions_for(ctx.me).manage_messages:
                return await ctx.send(await self.bot.localize(ctx.guild, "META_perms_nomanagemessages", "error"))
            await con.execute("UPDATE guild SET delete_commands = ? WHERE id = ?", (new, ctx.guild.id))
            await con.commit()
        await ctx.send(
            await self.bot.localize(
                ctx.guild, "MAIN_toggledelete_enabled" if new else "MAIN_toggledelete_disabled", "success"
            )
        )

    @commands.command(aliases=["snipepermission", "snipeperms"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def togglesnipepermission(self, ctx):
        async with self.bot.db_connect() as con:
            new = int(
                not (
                    await (
                        await con.execute("SELECT snipe_requires_manage_messages FROM guild WHERE id = ?", (ctx.guild.id,))
                    ).fetchone()
                )[0]
            )
            if new and not ctx.channel.permissions_for(ctx.me).manage_messages:
                return await ctx.send(await self.bot.localize(ctx.guild, "META_perms_nomanagemessages", "error"))
            await con.execute("UPDATE guild SET snipe_requires_manage_messages = ? WHERE id = ?", (new, ctx.guild.id))
            await con.commit()
        await ctx.send(
            await self.bot.localize(
                ctx.guild, "MAIN_togglesnipepermission_enabled" if new else "MAIN_togglesnipepermission_disabled", "success"
            )
        )

    @commands.command(aliases=["prefix"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setprefix(self, ctx, prefix: str):
        if len(prefix) > 3:
            return await ctx.send(await self.bot.localize(ctx.guild, "MAIN_setprefix_toolong", "error"))
        async with self.bot.db_connect() as con:
            await con.execute("UPDATE guild SET prefix = ? WHERE id = ?", (prefix, ctx.guild.id))
            await con.commit()
        await ctx.send((await self.bot.localize(ctx.guild, "MAIN_setprefix_set", "success")).format(prefix))

    @commands.command(aliases=["language", "setlang", "lang", "localize"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setlanguage(self, ctx, language: str):
        if language not in self.bot.responses:
            return await ctx.send(await self.bot.localize(ctx.guild, "MAIN_setlanguage_notavailable", "error"))
        async with self.bot.db_connect() as con:
            await con.execute("UPDATE guild SET language = ? WHERE id = ?", (language, ctx.guild.id))
            await con.commit()
        await ctx.send((await self.bot.localize(ctx.guild, "MAIN_setlanguage_set", "success")).format(language))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def clone(self, ctx, msg_limit: int, channel: discord.TextChannel):
        if not ctx.channel.permissions_for(ctx.me).manage_webhooks:
            await ctx.send(await self.bot.localize(ctx.guild, "META_perms_nowebhook", "error"))
        elif msg_limit < 1 or msg_limit > 50:
            await ctx.send(await self.bot.localize(ctx.guild, "MAIN_clone_msglimit", "error"))
        else:
            webhook = await ctx.channel.create_webhook(name=self.bot.user.name)
            messages = await channel.history(limit=msg_limit, before=ctx.message).flatten()
            ignored = (discord.HTTPException, discord.NotFound, discord.Forbidden)
            try:
                await webhook_copy(webhook, messages.pop(), clean_content := ctx.guild != channel.guild)
            except ignored:
                pass
            else:
                for msg in messages[::-1]:
                    await asyncio.sleep(0.5)
                    try:
                        await webhook_copy(webhook, msg, clean_content)
                    except ignored:
                        break
            try:
                await webhook.delete()
            except ignored:
                pass


def setup(bot):
    bot.add_cog(Main(bot))
