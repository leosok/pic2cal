import base64
import os
import re
from datetime import date, datetime as DateTime, time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field


class Event(BaseModel):
    name: str
    datetime: DateTime | None = None
    address: str | None = None
    event_date: date | None = None

    @property
    def readable_datetime_str(self) -> str:
        if self.datetime is not None:
            return self.datetime.strftime("%A, %d %B %Y %H:%M:%S")
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
    address: str | None


class ExtractedImage(BaseModel, extra="forbid"):
    message: str
    events: list[ExtractedEvent]


load_dotenv()
PROMPT_IMG_2_JSON_EVENTS = """
Extract events from the image. Preserve their names as written.
Use the current year when the year is missing.
Return null for an unreadable or missing date, start time or location.
Use 00:00 only if the image explicitly says the event starts at midnight.
Use the venue name and address as shown. Do not guess a location.
"""


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
        events=[
            Event(
                name=item.name,
                datetime=DateTime.combine(item.date, item.time.replace(tzinfo=None))
                if item.date is not None and item.time is not None else None,
                event_date=item.date,
                address=item.address.strip() or None if item.address else None,
            )
            for item in extracted.events
        ],
    )
