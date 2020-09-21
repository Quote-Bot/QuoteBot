import sqlite3
import asyncio

conn = sqlite3.connect('configs/QuoteBot.db')
c = conn.cursor()

if c.execute("PRAGMA auto_vacuum").fetchone()[0] == 0:
	c.execute("PRAGMA auto_vacuum = 1")

c.execute("CREATE TABLE IF NOT EXISTS Guilds (Guild INT PRIMARY KEY, Prefix TEXT, Language TEXT, OnReaction INT, PinChannel INT)")
c.execute("CREATE TABLE IF NOT EXISTS PersonalQuotes (QuoteID INT PRIMARY KEY, Author INT, Response TEXT)")

COMMIT = False

def exec(sql):
	try:
		return c.execute(sql)
	except sqlite3.IntegrityError:
		raise Exception
	else:
		if not sql.startswith('SELECT'):
			global COMMIT
			COMMIT = True

def commit():
	return conn.commit()

async def while_commit():
	'''
	This is my very cheap workaround of "eventual consistency". I know it's bad,
	and I'm welcoming of any change you think is better than this.
	'''
	global COMMIT
	while True:
		if COMMIT:
			conn.commit()
			COMMIT = False
		await asyncio.sleep(2)

async def main():
	asyncio.ensure_future(while_commit())

if __name__ == 'DBService':
	loop = asyncio.get_event_loop()
	loop.run_until_complete(main())
