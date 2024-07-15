import pytest
import pytz

from cal2mail_utils import EmailCalendarInvite
from open_ai_image_handler import Event, get_image_description_as_json


test_json1 = '''```json
        {
        "message": "1 event found.",
        "events": [
            {
            "name": "Geburtstag (40!)",
            "datetime": "2024-07-20T16:00:00",
            "address": null
            }
        ]
        }
        ```'''

test_json2 = '''{
        "message": "4 events found.",
        "events": [
            {
            "name": "Behandlungstermin",
            "datetime": "2024-07-11T10:40:00",
            "address": "Hardenbergstr. 20, 10623 Berlin"
            },
            {
            "name": "Behandlungstermin",
            "datetime": "2024-07-17T13:00:00",
            "address": "Hardenbergstr. 20, 10623 Berlin"
            },
            {
            "name": "Behandlungstermin",
            "datetime": "2024-07-19T13:10:00",
            "address": "Hardenbergstr. 20, 10623 Berlin"
            },
            {
            "name": "Behandlungstermin",
            "datetime": "2024-07-25T10:50:00",
            "address": "Hardenbergstr. 20, 10623 Berlin"
            }
        ]
            }'''


def test_get_image_description_as_json():
    assert get_image_description_as_json(test_json1) == {
        "message": "1 event found.",
        "events": [
            {
                "name": "Geburtstag (40!)",
                "datetime": "2024-07-20T16:00:00",
                "address": None
            }
        ]
    }
    
    assert get_image_description_as_json(test_json2) == {
        "message": "4 events found.",
        "events": [
            {
                "name": "Behandlungstermin",
                "datetime": "2024-07-11T10:40:00",
                "address": "Hardenbergstr. 20, 10623 Berlin"
            },
            {
                "name": "Behandlungstermin",
                "datetime": "2024-07-17T13:00:00",
                "address": "Hardenbergstr. 20, 10623 Berlin"
            },
            {
                "name": "Behandlungstermin",
                "datetime": "2024-07-19T13:10:00",
                "address": "Hardenbergstr. 20, 10623 Berlin"
            },
            {
                "name": "Behandlungstermin",
                "datetime": "2024-07-25T10:50:00",
                "address": "Hardenbergstr. 20, 10623 Berlin"
            }
        ]
    }


# test the send_email with the events
def test_send_email_msg():

    image_response = get_image_description_as_json(test_data=test_json1)

    event = image_response.events[0]

    # Send the email
    user_email = 'l.sokolov@gmx.de'
    attendees = ['leonid.sokolov@big-picture.com']
    berlin_tz = 'Europe/Berlin'
    user_name = 'leo'
    email = EmailCalendarInvite(
        attendees=attendees,
        from_name='Image2Cal',
        subject=f"Plz come! {event.name}",
        body=event.name,
        start=event.datetime,
        address=event.address,
        organizer=user_name,
        timezone=berlin_tz
    )
    msg = email.create_invite_mail()
    email.send_invite()
