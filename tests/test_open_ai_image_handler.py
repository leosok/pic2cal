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
            "message": "3 events found.",
            "events": [
                {"name": "Dinner", "date": "2026-12-03", "time": None, "end_time": None, "end_date": None, "address": None},
                {"name": "Party", "date": "2026-12-03", "time": "00:00:00", "end_time": "02:30:00", "end_date": None, "address": "Hall"},
                {"name": "Overnight", "date": "2026-12-03", "time": "23:00:00", "end_time": "01:00:00", "end_date": None, "address": None},
            ],
        }))),
    ])
    monkeypatch.setattr("open_ai_image_handler.OpenAI", client)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    response = get_image_description_as_json(base64_image="aW1hZ2U=")

    dinner, party, overnight = response.events
    assert dinner.event_date == date(2026, 12, 3)
    assert dinner.datetime is None
    assert dinner.address is None
    assert dinner.end_datetime is None
    assert party.datetime == datetime(2026, 12, 3, 0, 0)
    assert party.address == "Hall"
    assert party.end_datetime == datetime(2026, 12, 3, 2, 30)
    assert overnight.end_datetime == datetime(2026, 12, 4, 1, 0)
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
        end=datetime(2026, 12, 3, 21, 15),
        address="Hall, Berlin",
        timezone="Europe/Berlin",
    )

    email.send_invite()

    send = smtp.return_value.__enter__.return_value.sendmail
    assert send.call_args.args[:2] == ("sender@example.com", ["recipient@example.com"])
    assert "DTEND;TZID=Europe/Berlin:20261203T211500" in send.call_args.args[2]
    assert r"LOCATION:Hall\, Berlin" in send.call_args.args[2]
