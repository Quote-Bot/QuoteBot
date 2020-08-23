import sqlite3
import asyncio

conn = sqlite3.connect('configs/QuoteBot.db')
c = conn.cursor()
c.execute("CREATE TABLE IF NOT EXISTS Guilds (Guild INT PRIMARY KEY, Prefix TEXT, Language TEXT, OnReaction TEXT, PinChannel INT, DelCommands INT)")
c.execute("CREATE TABLE IF NOT EXISTS PersonalQuotes (QuoteID INT PRIMARY KEY, Author INT, Response TEXT)")
c.execute("CREATE TABLE IF NOT EXISTS Blacklist (Id INT PRIMARY KEY, Reason TEXT)")

def exec(sql):
	try:
		return c.execute(sql)
	except sqlite3.IntegrityError:
		raise Exception

def commit():
	return conn.commit()

async def while_commit():
	while True:
		await asyncio.sleep(120)
		conn.commit()

async def main():
	asyncio.ensure_future(while_commit())

if __name__ == 'DBService':
	loop = asyncio.get_event_loop()
	loop.run_until_complete(main())
