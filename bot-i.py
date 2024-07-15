import asyncio
import logging
from html import escape
import os
from uuid import uuid4

import pytz
from aiohttp import web
from dotenv import load_dotenv
from telegram import Update, File
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
)
from telegram.ext.filters import PHOTO, TEXT
from telegram.ext import PicklePersistence
from open_ai_image_handler import (
    get_image_description_as_json,
    PROMPT_IMG_2_JSON_EVENTS,
)
import re
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler
from cal2mail_utils import EmailCalendarInvite
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from open_ai_image_handler import Event

USER_EMAIL_KEY = "user_email_adress"
USER_IS_EXPERT_KEY = "user_is_expert"
TIMEZONE = 'Europe/Berlin'
load_dotenv()


def setup_logging() -> logging.Logger:
    """
    Setup the logging for the bot
    :return:
    """
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    # Silence httpx and aiohttp logger
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    return logging.getLogger(__name__)


logger = setup_logging()

async def get_event_tile(update, event: Event, reply_markup):
    address_string = f" at <b>{event.address}</b>" if event.address else ""
    await update.message.reply_text(
        f"<b>{event.name}</b>\n<i>{event.readable_datetime_str}</i>{address_string}",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"User {update.effective_user.id} ({update.effective_user.first_name}) started the bot")
    return await handle_text(update, context)


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"Image received from user {user.id} ({user.first_name})")

    photo = update.message.photo[-1]
    file: File = await context.bot.getFile(photo.file_id)
    filename = f"data/{photo.file_id}.jpg"
    await file.download_to_drive(filename)
    logger.info(f"Image saved as {filename}")

    await update.message.reply_text("Image is saved. Processing...")

    try:
        response = get_image_description_as_json(
            image_path=filename, prompt=PROMPT_IMG_2_JSON_EVENTS
        )
        logger.info(f"Image processed successfully for user {user.id}")
        await update.message.reply_text(f"Checking: {response.message}")

        for event in response.events:
            event_id = str(uuid4())
            context.chat_data.update({event_id: event.model_dump()})
            logger.info(f"Event '{event.name}' extracted and stored with ID {event_id}")

            button_list = [
                InlineKeyboardButton("✅ Send", callback_data=f"send_{event_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{event_id}"),
            ]
            reply_markup = InlineKeyboardMarkup([button_list])

            await get_event_tile(update, event, reply_markup)

    except ValueError as e:
        logger.error(f"Error processing image for user {user.id}: {str(e)}")
        await update.message.reply_text(f"Error: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"Received text message from user {user.id} ({user.first_name})")

    await update.message.reply_text(f"Hello {user.first_name}")
    await update.message.reply_text(
        "Please send me an Image to get all events in the image."
    )
    user_email = context.user_data.get(USER_EMAIL_KEY)
    if not user_email:
        logger.info(f"User {user.id} has no email address set")
        await update.message.reply_text(
            "Please set your email address with /email command"
        )
    else:
        logger.info(f"User {user.id} has email address: {user_email}")
        await update.message.reply_text(f"Your email address is: {user_email}")


async def set_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    email_address = update.message.text.partition(" ")[2].strip()

    if not email_address:
        logger.warning(f"User {user.id} attempted to set email without providing an address")
        await update.message.reply_text(
            "Please provide an email address. Usage: /email <email_address>"
        )
        return

    email_regex = r"^\S+@\S+\.\S+$"
    if not re.match(email_regex, email_address):
        logger.warning(f"User {user.id} provided invalid email address: {email_address}")
        await update.message.reply_text("Invalid email address. Please try again.")
        return

    context.user_data.update({USER_EMAIL_KEY: email_address})
    logger.info(f"User {user.id} ({user.first_name}) set email to: {email_address}")
    await update.message.reply_text(f"Email set to: {email_address}")


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    action, event_id = query.data.split("_")
    event_data = context.chat_data.get(event_id)

    if not event_data:
        logger.warning(f"Event data not found for ID {event_id} (User: {user.id})")
        await query.edit_message_text("Event data not found.")
        return

    event = Event(**event_data)

    if action == "send":
        logger.info(f"User {user.id} approved event: {event.name}")
        await query.edit_message_text(
            f"✅ ✉️ <b>{event.name}</b>\n<i>{event.readable_datetime_str}</i>",
            parse_mode=ParseMode.HTML,
        )

        user_email = context.user_data.get(USER_EMAIL_KEY)
        user_name = update.effective_user.first_name

        email = EmailCalendarInvite(
            from_name="Image2Cal",
            attendees=[user_email],
            subject=f"{event.name}",
            body=event.name,
            start=event.datetime,
            address=event.address,
            organizer=user_name,
            timezone=TIMEZONE
        )
        email.create_invite_mail()
        email.send_invite()
        logger.info(f"Calendar invite sent to {user_email} for event: {event.name}")

    elif action == "cancel":
        logger.info(f"User {user.id} cancelled event: {event.name}")
        await query.edit_message_text(
            f"❌ <b>{event.name}</b>\n<i>{event.readable_datetime_str}</i>",
            parse_mode=ParseMode.HTML,
        )

    del context.chat_data[event_id]
    logger.info(f"Event {event_id} removed from chat data")

async def health(request):
    """A simple health check endpoint."""
    return web.Response(text="OK")

def main():
    logger.info("Starting TELEGRAM bot")
    persistence = PicklePersistence(filepath="conversationbot.pickle", update_interval=10)
    app = ApplicationBuilder().token(os.environ.get("TELEGRAM_TOKEN")).persistence(persistence).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("email", set_email))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_handler(MessageHandler(PHOTO, handle_image))
    app.add_handler(MessageHandler(TEXT, handle_text))

    # Set up aiohttp web server
    web_app = web.Application()
    web_app.router.add_get('/healthz', health)

    # Run the web server and bot together
    runner = web.AppRunner(web_app)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    loop.run_until_complete(site.start())

    logger.info("Bot is ready to receive messages and web server is running")
    loop.run_until_complete(app.run_polling())



if __name__ == "__main__":
    main()