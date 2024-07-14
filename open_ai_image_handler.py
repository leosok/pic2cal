import base64
import datetime
import json
import logging
import pprint
from typing import List, Optional
from urllib import response
from openai import OpenAI
from dotenv import load_dotenv
import re
from pprint import pprint
from pydantic import BaseModel


class Event(BaseModel):
    name: str
    datetime: datetime.datetime
    address: Optional[str] = None

    @property
    def readable_datetime_str(self) -> str:
        return self.datetime.strftime("%A, %d %B %Y %H:%M:%S")


class ImageResponse(BaseModel):
    message: str
    events: List[Event]


load_dotenv()

client = OpenAI()
PROMPT_IMG_2_JSON_EVENTS = (
    """
You are helping to digitalize a photo of an event / events. 
If no year is provided, assume the current year: 
"""
    + f"{datetime.datetime.now().isoformat()}"
    + """
If you find the event name, please make them unique by adding a number like foo, foo1.
If you find an event you answer with a JSON like this:
{
  "message": "2 events found.",
  "events": [
    {
      "name": "Event Name 1",
      "datetime": "YYYY-MM-DDTHH:MM:SS",
      "address": "123 Example St, City"
    },
    {
      "name": "Event Name 2",
      "datetime": "YYYY-MM-DDTHH:MM:SS",
      "address": null
    }
    // More events can be listed in this array
  ]
}

"""
)


# Function to clean the JSON string which is sometimes wrapped in Markdown code blocks
def clean_json_string(json_string):
    pattern = r"^```json\s*(.*?)\s*```$"
    cleaned_string = re.sub(pattern, r"\1", json_string, flags=re.DOTALL)
    return cleaned_string.strip()


# Function to encode the image
def encode_image(image_path) -> base64:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def get_image_description_as_json(
    base64_image: base64 = None,
    image_path: str = None,
    prompt: str = PROMPT_IMG_2_JSON_EVENTS,
    as_json=True,
    test_data=None,
) -> ImageResponse:
    if image_path:
        base64_image = encode_image(image_path)
    elif not base64_image and not test_data:
        raise ValueError("You must provide either an image path or a base64 encoded")

    
    if not test_data:
      response = client.chat.completions.create(
          model="gpt-4o",
          temperature=0.2,
          messages=[
              {
                  "role": "user",
                  "content": [
                      {"type": "text", "text": PROMPT_IMG_2_JSON_EVENTS},
                      {
                          "type": "image_url",
                          "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                      },
                  ],
              }
          ],
          max_tokens=300,
      )
      resp = response.choices[0].message.content
    else:
      resp = test_data


    logging.info(resp)
    print(resp)
    if as_json:
        clean_resp = clean_json_string(resp)
        return ImageResponse.model_validate_json(clean_resp)
    else:
        return resp.message

