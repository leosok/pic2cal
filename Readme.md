# pic2cal

A Telegram bot that extracts calendar events from images using OpenAI Vision API and sends email calendar invites.

## How it works

1. Send an image with event information (poster, flyer, etc.) to the bot
2. The bot uses OpenAI Vision API to extract event details (name, date/time, address)
3. Review each extracted event and approve or cancel
4. Approved events generate calendar invites sent via email to your address

**Note:** Set your email address with `/email` before sending invites.

## Setup

Install dependencies with Poetry:

```bash
poetry install
```

## Configuration

Copy `.env.example` to `.env` and configure the required environment variables. See `.env.example` for details.

## Usage

Run the bot:

```bash
poetry run python bot-i.py
```

The bot uses polling to connect to Telegram - it doesn't need to run on a server with a public URL. It connects to Telegram from wherever it runs using the `TELEGRAM_TOKEN` environment variable. Just ensure the machine has internet access.

Send an image with event information to the bot. The bot will extract events and let you approve or cancel sending calendar invites.

## License

MIT
