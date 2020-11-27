import discord
from discord.ext import commands


class PersonalQuotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_quote(self, ctx, alias: str, server=False):
        await ctx.trigger_typing()
        async with self.bot.db_connect() as db:
            if (guild := ctx.guild) and guild.me.permissions_in(ctx.channel).manage_messages and (await (await db.execute("SELECT delete_commands FROM guild WHERE id = ?", (guild.id,))).fetchone())[0]:
                await ctx.message.delete()
            if quoted := await (await db.execute("SELECT message_id FROM personal_quote WHERE owner_id = ? AND alias = ?", (owner_id := ctx.guild.id if server else ctx.author.id, alias))).fetchone():
                msg_dict = {'message_id': (msg_id := quoted[0])}
                if channel_id := (await (await db.execute("SELECT channel_id FROM message WHERE id = ?", (msg_id,))).fetchone())[0]:
                    msg_dict['channel_id'] = channel_id
                    msg_dict['guild_id'] = (await (await db.execute("SELECT guild_id FROM channel WHERE id = ?", (channel_id,))).fetchone())[0]
                else:
                    msg_dict['dm'] = True
                try:
                    msg = await self.bot.get_message(ctx, msg_dict)
                except Exception as e:
                    await db.execute('PRAGMA foreign_keys = ON')
                    if isinstance(e, commands.ChannelNotFound):
                        await db.execute("DELETE FROM channel WHERE id = ?", (channel_id,))
                    elif isinstance(e, commands.MessageNotFound):
                        await db.execute("DELETE FROM message WHERE id = ?", (msg_id,))
                    else:
                        await db.execute("DELETE FROM personal_quote WHERE owner_id = ? AND alias = ?", (owner_id, alias))
                    await db.commit()
                    if isinstance(e, discord.Forbidden):
                        return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'MAIN_quote_noperms')}")
                    return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'MAIN_quote_nomessage')}")
                return await self.bot.quote_message(msg, ctx.channel, ctx.author, 'server' if server else 'personal')
        await ctx.send(content=f"{self.bot.config['response_strings']['error']} {await self.bot.localize(guild, 'PERSONAL_personalquote_notfound')}")

    async def send_list(self, ctx, server=False):
        if fetch_quotes := await self.bot.fetch("SELECT alias FROM personal_quote WHERE owner_id = ?", (ctx.guild.id if server else ctx.author.id,), False):
            embed = discord.Embed(description=', '.join(f'`{alias}`' for alias in fetch_quotes), color=ctx.author.color.value or discord.Embed.Empty)
            embed.set_author(name=await self.bot.localize(ctx.guild, f"PERSONAL_{'server' if server else 'personal'}list_embedauthor"), icon_url=ctx.author.avatar_url)
            await ctx.send(embed=embed)
        else:
            await ctx.send(content=f"""{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, f"PERSONAL_{'server' if server else 'personal'}list_noquotes")}""")

    async def set_quote(self, ctx, alias: str, query: str, server=False):
        if len(alias := discord.utils.escape_markdown(alias)) > 50:
            return await ctx.send(f"{self.bot.config['response_strings']['error']} {(await self.bot.localize(ctx.guild, 'PERSONAL_personalset_invalidalias')).format(alias)}")
        if match := self.bot.msg_id_regex.match(query) or self.bot.msg_url_regex.match(query):
            try:
                msg = await self.bot.get_message(ctx, match.groupdict())
            except discord.Forbidden:
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'MAIN_quote_noperms')}")
            except Exception:
                return await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'MAIN_quote_nomessage')}")
            async with self.bot.db_connect() as db:
                async with db.execute("SELECT COUNT(alias) FROM personal_quote WHERE owner_id = ?", (owner_id := ctx.guild.id if server else ctx.author.id,)) as cur:
                    if (await cur.fetchone())[0] >= 50:
                        return await ctx.send(f"""{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, f"PERSONAL_{'server' if server else 'personal'}set_limitexceeded")}""")
                if msg.guild:
                    await db.execute("INSERT OR IGNORE INTO channel VALUES (?, ?)", (msg.channel.id, msg.guild.id))
                await db.execute("INSERT OR IGNORE INTO message VALUES (?, ?)", (msg.id, None if isinstance(msg.channel, discord.DMChannel) else msg.channel.id))
                await db.execute("INSERT OR REPLACE INTO personal_quote VALUES (?, ?, ?)", (owner_id, alias, msg.id))
                await db.commit()
            return await ctx.send(content=f"""{self.bot.config['response_strings']['success']} {(await self.bot.localize(ctx.guild, f"PERSONAL_{'server' if server else 'personal'}set_set")).format(alias)}""")
        await ctx.send(f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'MAIN_quote_nomessage')}")

    async def copy_quote(self, ctx, owner_id: int, alias: str, server=False):
        async with self.bot.db_connect() as db:
            if await (await db.execute("SELECT message_id FROM personal_quote WHERE owner_id = ? AND alias = ?", (new_owner_id := ctx.guild.id if server else ctx.author.id, alias))).fetchone() or (await (await db.execute("SELECT COUNT(alias) FROM personal_quote WHERE owner_id = ?", (new_owner_id,))).fetchone())[0] < 50:
                if copied := await (await db.execute("SELECT message_id FROM personal_quote WHERE owner_id = ? AND alias = ?", (owner_id, alias))).fetchone():
                    await db.execute("INSERT OR REPLACE INTO personal_quote VALUES (?, ?, ?)", (new_owner_id, alias, copied[0]))
                    await db.commit()
                    return await ctx.send(content=f"""{self.bot.config['response_strings']['success']} {(await self.bot.localize(ctx.guild, f"PERSONAL_{'server' if server else 'personal'}set_set")).format(alias)}""")
                return await ctx.send(f"""{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, f"PERSONAL_{'server' if server else 'personal'}set_limitexceeded")}""")
        await ctx.send(content=f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'PERSONAL_personalquote_notfound')}")

    async def remove_quote(self, ctx, alias: str, server=False):
        async with self.bot.db_connect() as db:
            if await (await db.execute("SELECT * FROM personal_quote WHERE owner_id = ? AND alias = ?", (owner_id := ctx.guild.id if server else ctx.author.id, alias))).fetchone():
                await db.execute("DELETE FROM personal_quote WHERE owner_id = ? AND alias = ?", (owner_id, alias))
                await db.commit()
                await ctx.send(content=f"""{self.bot.config['response_strings']['success']} {(await self.bot.localize(ctx.guild, f"PERSONAL_{'server' if server else 'personal'}remove_removed")).format(alias)}""")
            else:
                await ctx.send(content=f"{self.bot.config['response_strings']['error']} {await self.bot.localize(ctx.guild, 'PERSONAL_personalquote_notfound')}")

    async def clear_quotes(self, ctx, server=False):
        async with self.bot.db_connect() as db:
            await db.execute("DELETE FROM personal_quote WHERE owner_id = ?", (ctx.guild.id if server else ctx.author.id,))
            await db.commit()
        await ctx.send(content=f"""{self.bot.config['response_strings']['success']} {await self.bot.localize(ctx.guild, f"PERSONAL_{'server' if server else 'personal'}clear_cleared")}""")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        async with self.bot.db_connect() as db:
            await db.execute('PRAGMA foreign_keys = ON')
            await db.execute("DELETE FROM channel WHERE id = ?", (channel.id,))
            await db.commit()

    @commands.Cog.listener()
    async def on_message_delete(self, msg):
        async with self.bot.db_connect() as db:
            await db.execute('PRAGMA foreign_keys = ON')
            await db.execute("DELETE FROM message WHERE id = ?", (msg.id,))
            await db.commit()

    @commands.command(aliases=['personal', 'pquote', 'pq'])
    async def personalquote(self, ctx, alias: str):
        await self.send_quote(ctx, alias)

    @commands.command(aliases=['plist'])
    async def personallist(self, ctx):
        await self.send_list(ctx)

    @commands.command(aliases=['pset'])
    async def personalset(self, ctx, alias: str, *, query: str):
        await self.set_quote(ctx, alias, query)

    @commands.command(aliases=['pcopy'])
    async def personalcopy(self, ctx, owner_id: int, alias: str):
        await self.copy_quote(ctx, owner_id, alias)

    @commands.command(aliases=['premove', 'pdelete', 'pdel'])
    async def personalremove(self, ctx, alias: str):
        await self.remove_quote(ctx, alias)

    @commands.command(aliases=['pclear'])
    async def personalclear(self, ctx):
        await self.clear_quotes(ctx)

    @commands.command(aliases=['server', 'squote', 'sq'])
    async def serverquote(self, ctx, alias: str):
        await self.send_quote(ctx, alias, True)

    @commands.command(aliases=['slist'])
    async def serverlist(self, ctx):
        await self.send_list(ctx, True)

    @commands.command(aliases=['sset'])
    @commands.has_permissions(manage_messages=True)
    async def serverset(self, ctx, alias: str, *, query: str):
        await self.set_quote(ctx, alias, query, True)

    @commands.command(aliases=['scopy'])
    @commands.has_permissions(manage_messages=True)
    async def servercopy(self, ctx, owner_id: int, alias: str):
        await self.copy_quote(ctx, owner_id, alias, True)

    @commands.command(aliases=['sremove', 'sdelete', 'sdel'])
    @commands.has_permissions(manage_messages=True)
    async def serverremove(self, ctx, alias: str):
        await self.remove_quote(ctx, alias, True)

    @commands.command(aliases=['sclear'])
    @commands.has_permissions(manage_messages=True)
    async def serverclear(self, ctx):
        await self.clear_quotes(ctx, True)


def setup(bot):
    bot.add_cog(PersonalQuotes(bot))
