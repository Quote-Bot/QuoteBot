# Quote Bot

[![Support Server](https://discordapp.com/api/guilds/741660208119545968/widget.png?style=shield)](https://discord.gg/vkWyTGa)
[![License](https://img.shields.io/github/license/Quote-Bot/QuoteBot)](https://github.com/Quote-Bot/QuoteBot/blob/master/LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

An easy way to quote Discord messages with cross-server support!

## Features

- Quote messages by link or ID
- Snipe deleted/edited messages
- Message cloning
- Saved personal/server quotes
- Highlight messages containing specific words/patterns
- Configurable settings for each server

## Self-hosting

### Local installation

The bot requires [Python 3.11](https://www.python.org/downloads/) and the libraries specified in [Pipfile](Pipfile), which can be installed using [`pipenv`](https://pipenv.pypa.io/en/stable/install/#installing-pipenv):

```sh
pipenv install
```

The following command will then start the bot:

```sh
pipenv run bot
```

### Docker

Alternatively, the bot can be deployed in a [Docker](https://www.docker.com/get-started) container:

```sh
docker-compose up
```