import json
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from cal2mail_utils import EmailCalendarInvite
from open_ai_image_handler import get_image_description_as_json


def test_extracts_an_unknown_time_and_explicit_midnight_separately(monkeypatch):
    client = MagicMock()
    create = client.return_value.__enter__.return_value.chat.completions.create
    create.return_value = SimpleNamespace(choices=[
        SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps({
            "message": "2 events found.",
            "events": [
                {"name": "Dinner", "date": "2026-12-03", "time": None, "address": None},
                {"name": "Party", "date": "2026-12-03", "time": "00:00:00", "address": "Hall"},
            ],
        }))),
    ])
    monkeypatch.setattr("open_ai_image_handler.OpenAI", client)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    response = get_image_description_as_json(base64_image="aW1hZ2U=")

    dinner, party = response.events
    assert dinner.event_date == date(2026, 12, 3)
    assert dinner.datetime is None
    assert dinner.address is None
    assert party.datetime == datetime(2026, 12, 3, 0, 0)
    assert party.address == "Hall"
    assert create.call_args.kwargs["model"] == "gpt-6.1-terra"
    assert create.call_args.kwargs["extra_body"]["response_format"]["json_schema"]["strict"]


def test_send_email_msg(monkeypatch):
    smtp = MagicMock()
    monkeypatch.setattr("cal2mail_utils.smtplib.SMTP", smtp)
    monkeypatch.setenv("FROM_EMAIL", "sender@example.com")
    email = EmailCalendarInvite(
        attendees=["recipient@example.com"],
        subject="Dinner",
        start=datetime(2026, 12, 3, 18, 30),
        address="Hall, Berlin",
        timezone="Europe/Berlin",
    )

    email.send_invite()

    send = smtp.return_value.__enter__.return_value.sendmail
    assert send.call_args.args[:2] == ("sender@example.com", ["recipient@example.com"])
    assert r"LOCATION:Hall\, Berlin" in send.call_args.args[2]
