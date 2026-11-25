import asyncio
import logging
from datetime import datetime
from html import escape
import os
from uuid import uuid4

from aiohttp import web
from dotenv import load_dotenv
from openai import OpenAIError
from telegram import Update, File, ForceReply
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
)
from telegram.ext.filters import COMMAND, PHOTO, TEXT
from telegram.ext import PicklePersistence
from open_ai_image_handler import Event, get_image_description_as_json, resolve_event_end
import re
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler
from cal2mail_utils import DEFAULT_EVENT_DURATION, EmailCalendarInvite
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


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

def event_summary(event: Event) -> str:
    schedule = event.readable_datetime_str
    if event.datetime is not None:
        end = event.end_datetime or (event.datetime + DEFAULT_EVENT_DURATION)
        end_format = "%H:%M" if end.date() == event.datetime.date() else "%A, %d %B %Y %H:%M"
        schedule += f" → {end.strftime(end_format)}"
        if event.end_datetime is None:
            schedule += " (1-hour default)"
    address = f"\n{escape(event.address)}" if event.address else ""
    return f"<b>{escape(event.name)}</b>\n<i>{schedule}</i>{address}"


def event_buttons(event_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Send", callback_data=f"send_{event_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{event_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{event_id}"),
        ]
    ])


async def ask_event_detail(message, context, event_id, event, field):
    if field == "time":
        has_date = event.datetime is not None or event.event_date is not None
        question = "What time does it start? Reply with HH:MM." if has_date else (
            "When does it start? Reply with YYYY-MM-DD HH:MM."
        )
    elif field == "end":
        question = (
            "What time does it end? Reply with HH:MM, or YYYY-MM-DD HH:MM to specify the date. "
            "A time earlier than the start is treated as the following day."
        )
    else:
        question = "Where is it? Reply with the venue name or address."

    prompt = await message.reply_text(
        f"{event_summary(event)}\n\n{question}",
        reply_markup=ForceReply(),
        parse_mode=ParseMode.HTML,
    )
    context.chat_data[f"event_reply:{prompt.message_id}"] = (event_id, field)
    context.chat_data[event_id]["reply_pending"] = True


async def show_event(message, context, event_id, event):
    if event.datetime is None:
        await ask_event_detail(message, context, event_id, event, "time")
    else:
        await message.reply_text(
            event_summary(event),
            reply_markup=event_buttons(event_id),
            parse_mode=ParseMode.HTML,
        )


async def handle_event_reply(update, context):
    message = update.message
    if message.reply_to_message is None:
        return False
    key = f"event_reply:{message.reply_to_message.message_id}"
    pending = context.chat_data.get(key)
    if pending is None:
        return False

    event_id, field = pending
    data = context.chat_data.get(event_id)
    if data is None or data.get("owner_id", update.effective_user.id) != update.effective_user.id:
        return True

    event = Event.model_validate(data)
    value = message.text.strip()
    if field == "time":
        event_date = event.datetime.date() if event.datetime is not None else event.event_date
        try:
            if event_date is None:
                event.datetime = datetime.strptime(value, "%Y-%m-%d %H:%M")
            else:
                event.datetime = datetime.combine(event_date, datetime.strptime(value, "%H:%M").time())
        except ValueError:
            await message.reply_text(
                "Use HH:MM (for example 18:30)." if event_date is not None
                else "Use YYYY-MM-DD HH:MM (for example 2026-12-03 18:30)."
            )
            return True
        event.event_date = event.datetime.date()
        if event.end_datetime is not None and event.end_datetime <= event.datetime:
            event.end_datetime = None
    elif field == "end":
        try:
            end_date = None
            if " " in value:
                end = datetime.strptime(value, "%Y-%m-%d %H:%M")
                end_date = end.date()
            else:
                end = datetime.strptime(value, "%H:%M")
            event.end_datetime = resolve_event_end(event.datetime, end.time(), end_date)
        except ValueError:
            await message.reply_text(
                "Enter an end after the start. Use HH:MM or YYYY-MM-DD HH:MM."
            )
            return True
    else:
        if not value or "\n" in value or "\r" in value:
            await message.reply_text("Please enter the venue name or address on one line.")
            return True
        event.address = value

    data.update(event.model_dump())
    data.pop("reply_pending", None)
    del context.chat_data[key]
    await show_event(message, context, event_id, event)
    return True


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
        response = await asyncio.to_thread(get_image_description_as_json, image_path=filename)
        logger.info(f"Image processed successfully for user {user.id}")
        if not response.events:
            await update.message.reply_text("No events found in this image.")

        for event in response.events:
            event_id = str(uuid4())
            context.chat_data[event_id] = {**event.model_dump(), "owner_id": user.id}
            await show_event(update.message, context, event_id, event)

    except (ValueError, OpenAIError):
        logger.exception("Image processing failed for user %s", user.id)
        await update.message.reply_text("Could not process this image. Please try again.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await handle_event_reply(update, context):
        return
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
    user = update.effective_user
    action, event_id = query.data.split("_", 1)
    event_data = context.chat_data.get(event_id)

    if not event_data:
        await query.answer("Event data not found.")
        return
    if event_data.get("owner_id", user.id) != user.id:
        await query.answer("Only the person who submitted the event can change it.")
        return

    if event_data.get("reply_pending"):
        await query.answer("Please reply to the question in the chat.")
        return

    await query.answer()
    event = Event(**event_data)

    if action == "edit":
        await query.edit_message_reply_markup(InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Start time", callback_data=f"time_{event_id}"),
                InlineKeyboardButton("End time", callback_data=f"end_{event_id}"),
                InlineKeyboardButton("Location", callback_data=f"location_{event_id}"),
                InlineKeyboardButton("Back", callback_data=f"back_{event_id}"),
            ]
        ]))
        return
    if action == "back":
        await query.edit_message_reply_markup(event_buttons(event_id))
        return
    if action in ("time", "end", "location"):
        event_data.setdefault("owner_id", user.id)
        await ask_event_detail(query.message, context, event_id, event, action)
        await query.edit_message_reply_markup(reply_markup=None)
        return
    if action == "send" and event.datetime is None:
        event_data.setdefault("owner_id", user.id)
        await show_event(query.message, context, event_id, event)
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if action == "send":
        user_email = context.user_data.get(USER_EMAIL_KEY)
        if not user_email:
            await query.message.reply_text("Please set your email address with /email first.")
            return

        email = EmailCalendarInvite(
            from_name="Image2Cal",
            attendees=[user_email],
            subject=f"{event.name}",
            body=event.name,
            start=event.datetime,
            end=event.end_datetime,
            address=event.address,
            organizer=user.first_name,
            timezone=TIMEZONE
        )
        await asyncio.to_thread(email.send_invite)
        del context.chat_data[event_id]
        await query.edit_message_text(
            f"✅ ✉️ {event_summary(event)}", parse_mode=ParseMode.HTML
        )
        return

    elif action == "cancel":
        logger.info(f"User {user.id} cancelled event: {event.name}")
        await query.edit_message_text(
            f"❌ {event_summary(event)}",
            parse_mode=ParseMode.HTML,
        )

    del context.chat_data[event_id]
    logger.info(f"Event {event_id} removed from chat data")

async def health(request):
    """A simple health check endpoint."""
    return web.Response(text="OK")

async def incoming(request):
    """Incoming webhook endpoint that returns 200."""
    return web.Response(status=200)

def main():
    logger.info("Starting TELEGRAM bot")
    persistence = PicklePersistence(filepath="conversationbot.pickle", update_interval=10)
    app = ApplicationBuilder().token(os.environ.get("TELEGRAM_TOKEN")).persistence(persistence).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("email", set_email))
    app.add_handler(CallbackQueryHandler(
        button_callback_handler, pattern=r"^(send|cancel|edit|time|end|location|back)_[0-9a-f-]+$"
    ))
    app.add_handler(MessageHandler(PHOTO, handle_image))
    app.add_handler(MessageHandler(TEXT & ~COMMAND, handle_text))

    # Set up aiohttp web server
    web_app = web.Application()
    web_app.router.add_get('/healthz', health)
    web_app.router.add_post('/incoming', incoming)

    # Run the web server and bot together
    runner = web.AppRunner(web_app)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    loop.run_until_complete(site.start())

    logger.info("Bot is ready to receive messages and web server is running")
    app.run_polling()



if __name__ == "__main__":
    main()