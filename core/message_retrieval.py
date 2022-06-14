"""
Copyright (C) 2020-2022 JonathanFeenstra, Deivedux, kageroukw

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import re
from typing import Iterator, NamedTuple, Optional

import discord
from discord.ext import commands

DEFAULT_AVATAR_URL = "https://cdn.discordapp.com/embed/avatars/0.png"
MARKDOWN = re.compile(
    (
        r"```.*?```"  # ```multiline code```
        r"|`.*?`"  # `inline code`
        r"|^>\s.*?$"  # > quote
        r"|\*\*\*.*?\*\*\*"  # ***bold italics***
        r"|\*\*.*?\*\*"  # **bold**
        r"|\*(?!\s).*?(?<!\s)\*"  # *italics*
        r"|__.*?__"  # __underline__
        r"|~~.*?~~"  # ~~strikethrough~~
        r"|\|\|.*?\|\|"  # ||spoiler||
        r"|<https?://\S*?>"  # <suppressed links>
    ),
    re.DOTALL | re.MULTILINE,
)
MESSAGE_ID_RE = re.compile(r"(?:(?P<channel_or_thread_id>[0-9]{15,20})[-/\s])?(?P<message_id>[0-9]{15,20})$")
MESSAGE_URL_RE = re.compile(
    r"https?://(?:(canary|ptb|www)\.)?discord(?:app)?\.com/channels/"
    r"(?:(?P<guild_id>[0-9]{15,20})|(?P<dm>@me))/(?P<channel_or_thread_id>[0-9]{15,20})/"
    r"(?P<message_id>[0-9]{15,20})/?(?:$|\s)"
)

_MEMBER_MENTION_RE = re.compile(r"<@!?([0-9]{15,20})>$")
_MEMBER_CONVERTER = commands.MemberConverter()


async def lazy_load_message(messageable: discord.abc.Messageable, msg_id: int) -> discord.Message:
    """Get message from cache if found, otherwise using an API call.

    Args:
        messageable (discord.abc.Messageable): The messageable to get the message from.
        msg_id (int): The message ID to get.

    Raises:
        commands.MessageNotFound: If the message is not found.
        discord.Forbidden: If the bot does not have permission to access the message.
        discord.HTTPException: If the request failed.

    Returns:
        discord.Message: The message.
    """
    if (msg := messageable._state._get_message(msg_id)) is not None:
        return msg
    try:
        return await messageable.fetch_message(msg_id)
    except discord.NotFound:
        raise commands.MessageNotFound(str(msg_id))


class MessageTuple(NamedTuple):
    msg_id: int
    channel_or_thread_id: int
    guild_id: Optional[int]


class MessageRetrievalContext(commands.Context):
    """Custom command invocation context with methods for message retrieval."""

    async def get_message(self, query: str) -> discord.Message:
        """Get message from query.

        The retrieval strategy is as follows (in order):

        1. In a server, check if the query is a member and retrieve their last message in the last 100 messages of the
           current channel or thread.
        2. Check if the query is formatted as a message URL or ID (optionally prefixed with a channel or thread ID).
            2.1. If the query is formatted as a message URL (which includes a guild ID), retrieve the message from the URL.
            2.2. If only a channel or thread and message ID are provided, retrieve the message from the channel or thread.
            2.3. If no channel or thread ID is provided, check the current channel or thread, then the current guild.
        3. Check if the query is a valid regex pattern and retrieve the first match in the last 100 messages of the current
           channel or thread.

        All lookups are first attempted in the local cache, then a request is made to the API.

        Args:
            query (str): Can be a message ID or URL, a member, or a pattern to search for.

        Raises:
            commands.MemberNotFound: If the member is not found.
            commands.MessageNotFound: If the message is not found.
            commands.ChannelNotFound: If the channel is not found.
            commands.GuildNotFound: If the guild is not found.
            commands.UserInputError: If the query is invalid.
            discord.Forbidden: If the bot does not have permission to access the message.
            discord.HTTPException: If the request failed.

        Returns:
            discord.Message: The message.
        """
        if self.guild is not None:
            try:
                member = await _MEMBER_CONVERTER.convert(self, query)
            except commands.MemberNotFound:
                pass
            else:
                try:
                    return await self._get_last_message_from_author(member.id)
                except commands.MessageNotFound:
                    # If the query is a name, fallback to regex search, otherwise raise
                    if _MEMBER_CONVERTER._get_id_match(query) is not None or _MEMBER_MENTION_RE.match(query) is not None:
                        raise
                    return await self._regex_search_message(query)

        if (match := MESSAGE_URL_RE.match(query) or MESSAGE_ID_RE.match(query)) is None:
            return await self._regex_search_message(query)

        return await self._get_message_from_match(match)

    async def _get_message_from_match(self, match: re.Match) -> discord.Message:
        group_dict = match.groupdict()
        msg_id = int(group_dict["message_id"])

        if group_dict.get("dm"):
            return await lazy_load_message(self.author, msg_id)

        if channel_or_thread_id_str := group_dict.get("channel_or_thread_id"):
            channel_or_thread_id = int(channel_or_thread_id_str)
            if guild_id_str := group_dict.get("guild_id"):
                guild_id = int(guild_id_str)
            else:
                guild_id = None
            return await self.get_channel_or_thread_message(MessageTuple(msg_id, channel_or_thread_id, guild_id))
        return await self._get_message_from_unknown_channel_or_thread(msg_id)

    def get_message_urls(self) -> Iterator[re.Match[str]]:
        """Get all message URLs from the message, excluding Markdown-formatted and <suppressed> links.

        Returns:
            Iterator[re.Match[str]]: An iterator of all message URL matches.
        """
        return MESSAGE_URL_RE.finditer(MARKDOWN.sub("?", self.message.content))

    async def get_channel_or_thread_message(self, msg_tuple: MessageTuple) -> discord.Message:
        """Get message from channel or thread.

        Args:
            msg_tuple (MessageTuple): The message tuple.

        Raises:
            commands.MessageNotFound: If the message is not found.
            commands.ChannelNotFound: If the channel is not found.
            commands.GuildNotFound: If the guild is not found.
            discord.Forbidden: If the bot does not have permission to access the message.
            discord.HTTPException: If the request failed.

        Returns:
            discord.Message: The message.
        """
        if msg_tuple.guild_id is None:
            channel = self.bot.get_channel(msg_tuple.channel_or_thread_id)
            if channel is None:
                raise commands.ChannelNotFound(str(msg_tuple.channel_or_thread_id))
            return await lazy_load_message(channel, msg_tuple.msg_id)
        elif guild := self.bot.get_guild(msg_tuple.guild_id):
            if channel_or_thread := guild.get_channel_or_thread(msg_tuple.channel_or_thread_id):
                return await lazy_load_message(channel_or_thread, msg_tuple.msg_id)
            raise commands.ChannelNotFound(str(msg_tuple.channel_or_thread_id))
        raise commands.GuildNotFound(str(msg_tuple.guild_id))

    async def _get_last_message_from_author(self, author_id: int, limit=100) -> discord.Message:
        async for msg in self.history(limit=limit, before=self.message):
            if msg.author.id == author_id:
                return msg
        raise commands.MessageNotFound(str(author_id))

    async def _get_message_from_unknown_channel_or_thread(self, msg_id: int) -> discord.Message:
        if msg := discord.utils.find(lambda msg: msg.id == msg_id, self.bot.cached_messages):
            return msg
        try:
            return await lazy_load_message(self, msg_id)
        except (commands.MessageNotFound, discord.Forbidden):
            if not self.guild:
                raise
            for channel_or_thread in self.guild.text_channels + self.guild.threads:
                try:
                    return await lazy_load_message(channel_or_thread, msg_id)
                except (commands.MessageNotFound, discord.Forbidden):
                    pass
        raise commands.MessageNotFound(str(msg_id))

    async def _regex_search_message(self, query: str, limit: int = 100) -> discord.Message:
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            raise commands.UserInputError(f"Pattern {query:r} cannot be compiled.")
        else:
            async for msg in self.history(limit=limit, before=self.message):
                if pattern.search(msg.content):
                    return msg

            def check(msg: discord.Message) -> bool:
                return (
                    msg.channel == self.channel
                    and msg.created_at < self.message.created_at
                    and bool(pattern.search(msg.content))
                )

            if msg := discord.utils.find(check, self.bot.cached_messages):
                return msg
        raise commands.MessageNotFound(query)
