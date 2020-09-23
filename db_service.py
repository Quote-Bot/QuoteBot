from sqlite3 import PARSE_COLNAMES, PARSE_DECLTYPES

from aiosqlite import connect


class DBService:
    async def __del__(self):
        await self.conn.close()

    @classmethod
    async def create(cls, config):
        self = DBService()
        self.conn = await connect('configs/QuoteBot.db', detect_types=PARSE_DECLTYPES | PARSE_COLNAMES)
        self.c = await self.conn.cursor()

        result = await (await self.c.execute("PRAGMA auto_vacuum")).fetchone()
        if result[0] == 0:
            await self.c.execute("PRAGMA auto_vacuum = 1")

        await self.c.execute("""
            CREATE TABLE
            IF NOT EXISTS guild (
                id INTEGER PRIMARY KEY,
                prefix TEXT DEFAULT '%s' NOT NULL,
                language TEXT DEFAULT '%s' NOT NULL,
                on_reaction INTEGER,
                pin_channel INTEGER
            )
        """.format(config['default_prefix'], config['default_lang']))
        await self.c.execute("""
            CREATE TABLE
            IF NOT EXISTS personal_quote (
                id INTEGER PRIMARY KEY,
                author INTEGER,
                response TEXT
            )
        """)
        return self

    async def execute(self, sql: str, *args):
        return await self.c.execute(sql, *args)

    async def commit(self):
        return await self.conn.commit()
