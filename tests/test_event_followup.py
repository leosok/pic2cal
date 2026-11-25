import asyncio
from datetime import date, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from open_ai_image_handler import Event


spec = spec_from_file_location("bot", Path(__file__).resolve().parents[1] / "bot-i.py")
bot = module_from_spec(spec)
spec.loader.exec_module(bot)


def test_replies_complete_only_the_event_they_belong_to():
    async def scenario():
        event = Event(name="Dinner", event_date=date(2026, 12, 3))
        other = Event(name="Party", event_date=date(2026, 12, 4))
        context = SimpleNamespace(chat_data={
            "dinner": {**event.model_dump(), "owner_id": 1},
            "party": {**other.model_dump(), "owner_id": 1},
        })
        photo = SimpleNamespace(reply_text=AsyncMock(side_effect=[
            SimpleNamespace(message_id=10), SimpleNamespace(message_id=11)
        ]))
        await bot.show_event(photo, context, "dinner", event)
        await bot.show_event(photo, context, "party", other)

        async def reply(to, text, next_id=None, user_id=1):
            message = SimpleNamespace(
                reply_to_message=SimpleNamespace(message_id=to),
                text=text,
                reply_text=AsyncMock(return_value=SimpleNamespace(message_id=next_id)),
            )
            await bot.handle_event_reply(
                SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id)), context
            )
            return message.reply_text

        assert not (await reply(10, "18:30", user_id=2)).called
        assert context.chat_data["dinner"]["datetime"] is None
        assert "HH:MM" in (await reply(10, "25:30")).call_args.args[0]
        preview = await reply(10, "18:30")
        assert context.chat_data["party"]["datetime"] is None

        assert "18:30 → 19:30 (1-hour default)" in preview.call_args.args[0]
        assert context.chat_data["dinner"]["datetime"] == datetime(2026, 12, 3, 18, 30)
        assert context.chat_data["dinner"]["address"] is None
        buttons = preview.call_args.kwargs["reply_markup"].inline_keyboard[0]
        assert [button.callback_data for button in buttons] == [
            "send_dinner", "edit_dinner", "cancel_dinner",
        ]

    asyncio.run(scenario())


def test_edit_keeps_other_fields_and_requires_confirmation_again():
    async def scenario():
        event = Event(name="Dinner", datetime=datetime(2026, 12, 3, 18, 30), address="Old Hall")
        context = SimpleNamespace(chat_data={"dinner": {**event.model_dump(), "owner_id": 1}})
        user = SimpleNamespace(id=1)
        query = SimpleNamespace(
            data="edit_dinner",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock(return_value=SimpleNamespace(message_id=20))),
        )
        await bot.button_callback_handler(SimpleNamespace(callback_query=query, effective_user=user), context)
        menu = query.edit_message_reply_markup.call_args.args[0].inline_keyboard[0]
        assert [button.callback_data for button in menu] == [
            "time_dinner", "end_dinner", "location_dinner", "back_dinner",
        ]

        query.data = "location_dinner"
        await bot.button_callback_handler(SimpleNamespace(callback_query=query, effective_user=user), context)
        assert query.edit_message_reply_markup.call_args.kwargs["reply_markup"] is None

        message = SimpleNamespace(
            text="New Hall",
            reply_to_message=SimpleNamespace(message_id=20),
            reply_text=AsyncMock(),
        )
        await bot.handle_event_reply(SimpleNamespace(message=message, effective_user=user), context)

        assert context.chat_data["dinner"]["datetime"] == event.datetime
        assert context.chat_data["dinner"]["address"] == "New Hall"
        assert message.reply_text.call_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "send_dinner"

    asyncio.run(scenario())


def test_edit_end_time_and_send_without_location(monkeypatch):
    invite = MagicMock()
    monkeypatch.setattr(bot, "EmailCalendarInvite", invite)

    async def scenario():
        start = datetime(2026, 12, 3, 23, 0)
        context = SimpleNamespace(
            chat_data={"dinner": {"name": "Dinner", "datetime": start}},
            user_data={bot.USER_EMAIL_KEY: "recipient@example.com"},
        )
        user = SimpleNamespace(id=1, first_name="Alex")
        query = SimpleNamespace(
            data="end_dinner",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock(return_value=SimpleNamespace(message_id=20))),
        )
        update = SimpleNamespace(callback_query=query, effective_user=user)
        await bot.button_callback_handler(update, context)

        message = SimpleNamespace(
            text="2026-12-03 22:00",
            reply_to_message=SimpleNamespace(message_id=20),
            reply_text=AsyncMock(),
        )
        reply = SimpleNamespace(message=message, effective_user=user)
        await bot.handle_event_reply(reply, context)
        assert "end after the start" in message.reply_text.call_args.args[0]

        message.text = "00:30"
        await bot.handle_event_reply(reply, context)
        assert "→ Friday, 04 December 2026 00:30" in message.reply_text.call_args.args[0]
        invite.assert_not_called()

        query.data = "send_dinner"
        await bot.button_callback_handler(update, context)
        assert invite.call_args.kwargs["start"] == start
        assert invite.call_args.kwargs["end"] == datetime(2026, 12, 4, 0, 30)
        assert invite.call_args.kwargs["address"] is None
        invite.return_value.send_invite.assert_called_once()

    asyncio.run(scenario())
