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
import sqlite3
from collections.abc import Iterable
from os import PathLike
from typing import Any

from aiosqlite import Connection
from aiosqlite.context import contextmanager


class AsyncDatabaseConnection(Connection):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    async def enable_foreign_keys(self) -> None:
        await self.execute("PRAGMA foreign_keys = ON")

    @contextmanager
    async def execute_fetchone(self, sql: str, parameters: Iterable[Any] | None = None) -> sqlite3.Row | None:
        if parameters is None:
            parameters = []
        cursor = await self.execute(sql, parameters)
        return await cursor.fetchone()


class GuildConnectionMixin(AsyncDatabaseConnection):
    async def insert_guild(self, guild_id: int, prefix: str) -> None:
        await self.execute(
            "INSERT OR IGNORE INTO guild (guild_id, prefix) VALUES (?, ?)",
            (guild_id, prefix),
        )

    async def fetch_prefix(self, guild_id: int) -> str | None:
        if row := await self.execute_fetchone("SELECT prefix FROM guild WHERE guild_id = ?", (guild_id,)):
            return row[0]
        return None

    async def fetch_quote_reactions(self, guild_id: int) -> bool | None:
        if row := await self.execute_fetchone("SELECT quote_reactions FROM guild WHERE guild_id = ?", (guild_id,)):
            return bool(row[0])

    async def fetch_quote_links(self, guild_id: int) -> bool | None:
        if row := await self.execute_fetchone("SELECT quote_links FROM guild WHERE guild_id = ?", (guild_id,)):
            return bool(row[0])

    async def fetch_delete_commands(self, guild_id: int) -> bool | None:
        if row := await self.execute_fetchone("SELECT delete_commands FROM guild WHERE guild_id = ?", (guild_id,)):
            return bool(row[0])

    async def fetch_snipe_requires_manage_messages(self, guild_id: int) -> bool | None:
        if row := await self.execute_fetchone(
            "SELECT snipe_requires_manage_messages FROM guild WHERE guild_id = ?", (guild_id,)
        ):
            return bool(row[0])

    async def fetch_guild_ids(self) -> Iterable[int]:
        return (row[0] for row in await self.execute_fetchall("SELECT guild_id FROM guild"))

    async def set_prefix(self, guild_id: int, prefix: str) -> None:
        await self.execute("UPDATE guild SET prefix = ? WHERE guild_id = ?", (prefix, guild_id))

    async def set_quote_reactions(self, guild_id: int, quote_reactions: bool) -> None:
        await self.execute("UPDATE guild SET quote_reactions = ? WHERE guild_id = ?", (int(quote_reactions), guild_id))

    async def set_quote_links(self, guild_id: int, quote_links: bool) -> None:
        await self.execute("UPDATE guild SET quote_links = ? WHERE guild_id = ?", (int(quote_links), guild_id))

    async def set_delete_commands(self, guild_id: int, delete_commands: bool) -> None:
        await self.execute("UPDATE guild SET delete_commands = ? WHERE guild_id = ?", (int(delete_commands), guild_id))

    async def set_snipe_requires_manage_messages(self, guild_id: int, snipe_requires_manage_messages: bool) -> None:
        await self.execute(
            "UPDATE guild SET snipe_requires_manage_messages = ? WHERE guild_id = ?",
            (int(snipe_requires_manage_messages), guild_id),
        )

    async def filter_guilds(self, keep_guild_ids: tuple[int, ...]) -> None:
        if (keep_amount := len(keep_guild_ids)) < 1000:
            await self.execute(f"DELETE FROM guild WHERE guild_id NOT IN ({', '.join('?' * keep_amount)})", keep_guild_ids)
        else:
            for i in range(0, keep_amount, 999):
                await self.filter_guilds(keep_guild_ids[i : i + 999])

    async def delete_guild(self, guild_id: int) -> None:
        await self.execute("DELETE FROM guild WHERE guild_id = ?", (guild_id,))


class MessageConnectionMixin(AsyncDatabaseConnection):
    async def insert_channel_or_thread(self, channel_or_thread_id: int, guild_id: int) -> None:
        await self.execute("INSERT OR IGNORE INTO channel VALUES (?, ?)", (channel_or_thread_id, guild_id))

    async def fetch_channels_and_threads(self) -> Iterable[sqlite3.Row]:
        return await self.execute_fetchall("SELECT * FROM channel")

    async def delete_channel_or_thread(self, channel_or_thread_id: int) -> None:
        await self.execute("DELETE FROM channel WHERE channel_id = ?", (channel_or_thread_id,))

    async def insert_message(self, msg_id: int, channel_id: int | None) -> None:
        await self.execute("INSERT OR IGNORE INTO message VALUES (?, ?)", (msg_id, channel_id))

    async def fetch_message_channel_or_thread(self, message_id: int) -> sqlite3.Row | None:
        if row := await self.execute_fetchone(
            """SELECT c.*
            FROM message m, channel c
            ON m.channel_id = c.channel_id
            WHERE m.message_id = ?""",
            (message_id,),
        ):
            return row

    async def delete_message(self, msg_id: int) -> None:
        await self.execute("DELETE FROM message WHERE message_id = ?", (msg_id,))


class BlockedConnectionMixin(AsyncDatabaseConnection):
    async def insert_blocked_id(self, blocked_id: int) -> None:
        await self.execute("INSERT OR IGNORE INTO blocked VALUES (?)", (blocked_id,))

    async def is_blocked(self, guild_id: int) -> bool:
        return bool(await self.execute_fetchone("SELECT 1 FROM blocked WHERE blocked_id = ?", (guild_id,)))

    async def fetch_blocked_ids(self) -> Iterable[int]:
        return (row[0] for row in await self.execute_fetchall("SELECT blocked_id FROM blocked"))

    async def delete_blocked_id(self, blocked_id: int) -> None:
        await self.execute("DELETE FROM blocked WHERE blocked_id = ?", (blocked_id,))


class HighlightConnectionMixin(AsyncDatabaseConnection):
    async def insert_highlight(self, user_id: int, query: str, guild_id: int = 0) -> None:
        await self.execute("INSERT OR IGNORE INTO highlight VALUES (?, ?, ?)", (user_id, query, guild_id))

    async def fetch_highlight(self, user_id: int, query: str, guild_id: int | None = None) -> sqlite3.Row | None:
        if guild_id is None:
            return await self.execute_fetchone("SELECT * FROM highlight WHERE user_id = ? AND query = ?", (user_id, query))
        return await self.execute_fetchone(
            "SELECT * FROM highlight WHERE user_id = ? AND query = ? AND guild_id = ?", (user_id, query, guild_id)
        )

    async def fetch_highlights(self) -> Iterable[sqlite3.Row]:
        return await self.execute_fetchall("SELECT * FROM highlight")

    async def fetch_user_highlights(
        self, user_id: int, guild_id: int = 0, order_by_guild=False
    ) -> tuple[tuple[str, int], ...]:
        """All relevant guilds included:
        `guild_id = 0` includes all guilds,
        `guild_id != 0` includes the global guilds (0).
        """
        return tuple(
            (row["query"], row["guild_id"])
            for row in await self.execute_fetchall(
                (
                    f"SELECT query, guild_id FROM highlight WHERE user_id = ? {'AND guild_id IN (?, 0)' if guild_id else ''}"
                    f"{' ORDER BY guild_id' if order_by_guild else ''}"
                ),
                (user_id, guild_id) if guild_id else (user_id,),
            )
        )

    async def fetch_user_highlight_guilds(self, user_id: int, pattern: str, exclude_global_guild=False) -> tuple[int]:
        return tuple(
            row["guild_id"]
            for row in await self.execute_fetchall(
                (
                    "SELECT guild_id FROM highlight WHERE user_id = ? AND query = ?"
                    f"{' AND guild_id != 0' if exclude_global_guild else ''}"
                ),
                (user_id, pattern),
            )
        )

    async def fetch_user_highlight_count(self, user_id: int) -> int:
        return (await self.execute_fetchone("SELECT COUNT(query) FROM highlight WHERE user_id = ?", (user_id,)))[0]  # type: ignore

    async def fetch_user_highlights_starting_with(
        self, user_id: int, prefix: str, guild_id: int = 0
    ) -> tuple[tuple[str, int], ...]:
        if guild_id != 0:
            rows = await self.execute_fetchall(
                "SELECT query, guild_id FROM highlight WHERE user_id = ? AND (guild_id = ? OR guild_id = 0) AND query LIKE ?",
                (user_id, guild_id, f"{prefix}%"),
            )
        else:
            rows = await self.execute_fetchall(
                "SELECT query, guild_id FROM highlight WHERE user_id = ? AND query LIKE ?", (user_id, f"{prefix}%")
            )
        return tuple(tuple(row) for row in rows)

    async def delete_highlight(self, user_id: int, query: str, guild_id: int = 0) -> None:
        if guild_id:
            await self.execute(
                "DELETE FROM highlight WHERE user_id = ? AND guild_id = ? AND query = ?", (user_id, guild_id, query)
            )
        else:
            await self.execute("DELETE FROM highlight WHERE user_id = ? AND query = ?", (user_id, query))

    async def clear_user_highlights(self, user_id: int, guild_id: int = 0) -> None:
        if guild_id != 0:
            await self.execute("DELETE FROM highlight WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        else:
            await self.execute("DELETE FROM highlight WHERE user_id = ?", (user_id,))


class SavedQuoteConnectionMixin(AsyncDatabaseConnection):
    async def set_saved_quote(self, owner_id: int, alias: str, msg_id: int) -> None:
        await self.execute("INSERT OR REPLACE INTO saved_quote VALUES (?, ?, ?)", (owner_id, alias, msg_id))

    async def fetch_saved_quote(self, owner_id: int, alias: str) -> sqlite3.Row | None:
        return await self.execute_fetchone("SELECT * FROM saved_quote WHERE owner_id = ? AND alias = ?", (owner_id, alias))

    async def fetch_owner_aliases(self, owner_id: int) -> Iterable[str]:
        rows = await self.execute_fetchall("SELECT alias FROM saved_quote WHERE owner_id = ?", (owner_id,))
        return (row[0] for row in rows)

    async def fetch_saved_quote_message_id(self, owner_id: int, alias: int) -> int | None:
        if row := await self.execute_fetchone(
            "SELECT message_id FROM saved_quote WHERE owner_id = ? AND alias = ?", (owner_id, alias)
        ):
            return row[0]

    async def fetch_saved_quote_count(self, owner_id: int) -> int:
        return (await self.execute_fetchone("SELECT COUNT(alias) FROM saved_quote WHERE owner_id = ?", (owner_id,)))[0]  # type: ignore

    async def delete_saved_quote(self, owner_id: int, alias: str) -> None:
        await self.execute("DELETE FROM saved_quote WHERE owner_id = ? AND alias = ?", (owner_id, alias))

    async def clear_owner_saved_quotes(self, owner_id: int) -> None:
        await self.execute("DELETE FROM saved_quote WHERE owner_id = ?", (owner_id,))


class QuoteBotDatabaseConnection(
    GuildConnectionMixin,
    MessageConnectionMixin,
    BlockedConnectionMixin,
    HighlightConnectionMixin,
    SavedQuoteConnectionMixin,
):
    async def __aenter__(self) -> "QuoteBotDatabaseConnection":
        con = await self
        con.row_factory = sqlite3.Row
        await con.execute("PRAGMA journal_mode = WAL")
        return con  # type: ignore

    async def prepare_db(self, default_prefix: str) -> None:
        await self.executescript(
            f"""
            PRAGMA auto_vacuum = 1;
            PRAGMA foreign_keys = ON;

            CREATE TABLE
            IF NOT EXISTS guild (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT DEFAULT '{default_prefix}' NOT NULL,
                quote_reactions INTEGER DEFAULT 0 NOT NULL,
                quote_links INTEGER DEFAULT 0 NOT NULL,
                delete_commands INTEGER DEFAULT 0 NOT NULL,
                snipe_requires_manage_messages INTEGER DEFAULT 0 NOT NULL
            );
            CREATE TABLE
            IF NOT EXISTS channel (
                channel_id INTEGER NOT NULL PRIMARY KEY,
                guild_id INTEGER NOT NULL REFERENCES guild ON DELETE CASCADE
            );
            CREATE TABLE
            IF NOT EXISTS message (
                message_id INTEGER NOT NULL PRIMARY KEY,
                channel_id INTEGER REFERENCES channel ON DELETE CASCADE
            );
            CREATE TABLE
            IF NOT EXISTS saved_quote (
                owner_id INTEGER NOT NULL,
                alias TEXT NOT NULL,
                message_id INTEGER NOT NULL REFERENCES message ON DELETE CASCADE,
                PRIMARY KEY (owner_id, alias)
            );
            CREATE TABLE
            IF NOT EXISTS highlight (
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                guild_id INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, query, guild_id)
            );
            CREATE TABLE
            IF NOT EXISTS blocked (
                blocked_id INTEGER NOT NULL PRIMARY KEY
            );

            CREATE TRIGGER
            IF NOT EXISTS delete_saved_guild_quotes
                AFTER DELETE ON guild
            BEGIN
                DELETE FROM saved_quote
                WHERE owner_id = old.guild_id;
            END;

            CREATE TRIGGER
            IF NOT EXISTS delete_guild_highlights
                AFTER DELETE ON guild
            BEGIN
                DELETE FROM highlight
                WHERE guild_id = old.guild_id;
            END;
        """
        )
        await self.commit()


def connect(database: str | bytes | PathLike, iter_chunk_size: int = 64) -> QuoteBotDatabaseConnection:
    return QuoteBotDatabaseConnection(
        lambda: sqlite3.connect(
            database, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, isolation_level=None
        ),
        iter_chunk_size=iter_chunk_size,
    )
