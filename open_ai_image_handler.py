import base64
import os
import re
from datetime import date, datetime as DateTime, time, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field


class Event(BaseModel):
    name: str
    datetime: DateTime | None = None
    address: str | None = None
    event_date: date | None = None
    end_datetime: DateTime | None = None

    @property
    def readable_datetime_str(self) -> str:
        if self.datetime is not None:
            return self.datetime.strftime("%A, %d %B %Y %H:%M")
        if self.event_date is not None:
            return self.event_date.strftime("%A, %d %B %Y")
        return "Date and time unknown"


class ImageResponse(BaseModel):
    message: str
    events: list[Event] = Field(default_factory=list)


class ExtractedEvent(BaseModel, extra="forbid"):
    name: str
    date: date | None
    time: time | None
    end_time: time | None
    end_date: date | None
    address: str | None


class ExtractedImage(BaseModel, extra="forbid"):
    message: str
    events: list[ExtractedEvent]


load_dotenv()
PROMPT_IMG_2_JSON_EVENTS = """
Extract events from the image. Preserve their names as written.
Use the current year when the year is missing.
Return null for an unreadable or missing date, start time, end time or location.
Extract the event's actual start and end, rather than doors opening or last admission.
If the event has an explicit duration and a start time, you may calculate the end.
Only use midnight when stated, shown as 00:00 or 24:00, or implied by an explicit duration.
For 24:00, use 00:00 on the following date.
Set end_date only if the event's ending date is stated, or calculated from 24:00 or an explicit duration.
For a time range without a separate end date, leave end_date null.
Use the venue name and address as shown. Do not guess a location.
"""


def resolve_event_end(start: DateTime, end_time: time, end_date: date | None = None) -> DateTime:
    end = DateTime.combine(end_date or start.date(), end_time.replace(tzinfo=None))
    if end_date is None and end < start:
        end += timedelta(days=1)
    if end <= start:
        raise ValueError("The end must be after the start.")
    return end


def to_event(item: ExtractedEvent) -> Event:
    start = None
    if item.date is not None and item.time is not None:
        start = DateTime.combine(item.date, item.time.replace(tzinfo=None))

    end = None
    if item.end_time is not None:
        if start is not None:
            try:
                end = resolve_event_end(start, item.end_time, item.end_date)
            except ValueError:
                # Ask for an end time if the extracted interval is inconsistent.
                pass
        elif item.end_date or item.date:
            end = DateTime.combine(item.end_date or item.date, item.end_time.replace(tzinfo=None))

    return Event(
        name=item.name,
        datetime=start,
        event_date=item.date,
        end_datetime=end,
        address=(item.address or "").strip() or None,
    )


def clean_json_string(json_string):
    pattern = r"^```json\s*(.*?)\s*```$"
    return re.sub(pattern, r"\1", json_string.strip(), flags=re.DOTALL)


def encode_image(image_path) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def get_image_description_as_json(
    base64_image: str | None = None,
    image_path: str | None = None,
    prompt: str = PROMPT_IMG_2_JSON_EVENTS,
    as_json=True,
    test_data=None,
) -> ImageResponse | str:
    if test_data is not None:
        return ImageResponse.model_validate_json(clean_json_string(test_data)) if as_json else test_data

    if image_path:
        base64_image = encode_image(image_path)
    if not base64_image:
        raise ValueError("Provide an image path or a base64-encoded image.")

    today = DateTime.now(ZoneInfo("Europe/Berlin")).date()
    with OpenAI() as client:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-6.1-terra"),
            messages=[
                {"role": "system", "content": f"{prompt}\nToday's date is {today.isoformat()}."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract the events shown in this image."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        },
                    ],
                },
            ],
            extra_body={
                "max_completion_tokens": 4096,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "event_extraction",
                        "strict": True,
                        "schema": ExtractedImage.model_json_schema(),
                    },
                },
            },
        )

    choice = response.choices[0]
    if choice.finish_reason != "stop" or not choice.message.content:
        raise ValueError("The image could not be processed. Please try another photo.")

    extracted = ExtractedImage.model_validate_json(choice.message.content)
    if not as_json:
        return extracted.message
    return ImageResponse(
        message=extracted.message,
        events=[to_event(item) for item in extracted.events],
    )
