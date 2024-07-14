from html import escape
import os
from uuid import uuid4
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
load_dotenv()


# A handler for starting the bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_text(update, context)


# Handle images. Save the image in the /data folder
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file: File = await context.bot.getFile(photo.file_id)
    filename = f"data/{photo.file_id}.jpg"
    await file.download_to_drive(filename)
    await update.message.reply_text("Image is saved. Processing...")

    # Get the image description
    try:
        response = get_image_description_as_json(
            image_path=filename, prompt=PROMPT_IMG_2_JSON_EVENTS
        )
        await update.message.reply_text(f"Checking: {response.message}")

        for event in response.events:
            event_id = str(uuid4())

            # Store the event data in chat_data
            context.chat_data.update({event_id: event.model_dump()})

            button_list = [
                InlineKeyboardButton("✅ Send", callback_data=f"send_{event_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{event_id}"),
            ]
            reply_markup = InlineKeyboardMarkup([button_list])

            await get_event_tile(update, event, reply_markup)

    except ValueError as e:
        await update.message.reply_text(f"Error: {e}")


async def get_event_tile(update, event: Event, reply_markup):
    address_string = f" at <b>{event.address}</b>" if event.address else ""
    await update.message.reply_text(
        f"<b>{event.name}</b>\n<i>{event.readable_datetime_str}</i>{address_string}",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Hello {update.effective_user.first_name}")
    await update.message.reply_text(
        "Please send me an Image to get all events in the image."
    )
    user_email = context.user_data.get(USER_EMAIL_KEY)
    if not user_email:  # will return False if the dict is empty
        await update.message.reply_text(
            "Please set your email adress with /email command"
        )
        # make a button to set email adress
    else:
        await update.message.reply_text(f"Your email adress is: {user_email}")
        # make a button to change email adress


async def set_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Extract email from command
    email_address = update.message.text.partition(" ")[2].strip()

    # Validate input
    if not email_address:
        await update.message.reply_text(
            "Please provide an email address. Usage: /email <email_address>"
        )
        return

    # Validate email format
    email_regex = r"^\S+@\S+\.\S+$"
    if not re.match(email_regex, email_address):
        await update.message.reply_text("Invalid email address. Please try again.")
        return

    # Save validated email address
    context.user_data.update({USER_EMAIL_KEY: email_address})
    await update.message.reply_text(f"Email set to: {email_address}")


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge the callback

    action, event_id = query.data.split("_")
    event_data = context.chat_data.get(event_id)

    if not event_data:
        await query.edit_message_text("Event data not found.")
        return

    # Convert the dictionary back to an Event object if necessary
    event = Event(**event_data)

    if action == "send":
        # Implement the action for approving the event
        await query.edit_message_text(
            # f"✅ <b>SENDING {event.name}</b>\n<i>{event.readable_datetime_str}</i>",
            f"✅ ✉️ <b>{event.name}</b>\n<i>{event.readable_datetime_str}</i>",
            parse_mode=ParseMode.HTML,
        )

        # Send the email
        user_email = context.user_data.get(USER_EMAIL_KEY)
        user_name = update.effective_user.first_name

        email = EmailCalendarInvite(
            attendees=[user_email],
            subject=f"Plz come! {event.name}",
            body=event.name,
            start=event.datetime,
            adress=event.address,
            organizer=user_name,
        )
        msg = email.create_invite_mail()
        email.send_invite(msg)

    elif action == "cancel":
        # Implement the action for canceling the event
        await query.edit_message_text(
            f"❌ <b>{event.name}</b>\n<i>{event.readable_datetime_str}</i>",
            parse_mode=ParseMode.HTML,
        )

    # Optionally, clean up after handling the action
    del context.chat_data[event_id]


def main():
    persistence = PicklePersistence(
        filepath="conversationbot.pickle", update_interval=10
    )
    app = (
        ApplicationBuilder()
        .token(os.environ.get("TELEGRAM_TOKEN"))
        .persistence(persistence)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("email", set_email))

    app.add_handler(
        CallbackQueryHandler(button_callback_handler)
    )  # Handle the button presses

    app.add_handler(MessageHandler(PHOTO, handle_image))
    app.add_handler(MessageHandler(TEXT, handle_text))

    app.run_polling()


main()
