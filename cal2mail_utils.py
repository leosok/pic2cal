import smtplib
import datetime
import os
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.utils import formatdate
from email import encoders
from typing import List


class EmailCalendarInvite:
    CRLF = "\r\n"

    def __init__(
        self,
        attendees: List[str],
        start: datetime.datetime,
        subject: str = "Please set Subject",
        from_name: str = "Please set From Name",
        body: str = "Please set Body",
        address: str = "Default address",
        organizer: str = "organizer@example.com",
        description: str = "Please set Description",
        duration: datetime.timedelta = None,
        end: datetime.datetime = None,
    ):
        self.login = os.getenv("EMAIL_LOGIN")
        self.password = os.getenv("EMAIL_PASSWORD")
        self.smtp_server = os.getenv("SMTP_SERVER")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        self.from_name = from_name or os.getenv("FROM_NAME")
        self.attendees = attendees
        self.subject = subject
        self.body = body
        self.start = start
        self.organizer = organizer
        self.description = description
        self.address = address
        self.duration = duration or datetime.timedelta(hours=1)
        self.end = end or start + self.duration

    def create_invite_mail(self) -> MIMEMultipart:

        ORG = 'Image2Cal Bot'
        LANG = 'EN'

        organizer = f"ORGANIZER;CN={self.organizer}"
        fro_m = f"{self.from_name} <{self.login}>"
        dtstart = self.start.strftime("%Y%m%dT%H%M%SZ")
        dtend = self.end.strftime("%Y%m%dT%H%M%SZ")
        dtstamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%SZ")

        attendees_formatted = ""
        for att in self.attendees:
            attendees_formatted += (f"ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=ACCEPTED;RSVP=TRUE;CN={att}:mailto:{att}{self.CRLF}")

        ical = (f"BEGIN:VCALENDAR{self.CRLF}"
                f"PRODID:-//{ORG}//{ORG}//{LANG}{self.CRLF}"
                f"VERSION:2.0{self.CRLF}"
                f"CALSCALE:GREGORIAN{self.CRLF}"
                f"METHOD:REQUEST{self.CRLF}"
                f"BEGIN:VEVENT{self.CRLF}"
                f"DTSTART:{dtstart}{self.CRLF}"
                f"DTEND:{dtend}{self.CRLF}"
                f"DTSTAMP:{dtstamp}{self.CRLF}"
                f"{organizer}{self.CRLF}"
                f"UID:FIXMEUID{dtstamp}{self.CRLF}"
                f"{attendees_formatted}"
                f"CREATED:{dtstamp}{self.CRLF}"
                f"DESCRIPTION:{self.description}{self.CRLF}"
                f"LAST-MODIFIED:{dtstamp}{self.CRLF}"
                f"LOCATION:{self.address}{self.CRLF}"
                f"SEQUENCE:0{self.CRLF}"
                f"STATUS:CONFIRMED{self.CRLF}"
                f"SUMMARY:{self.subject}{self.CRLF}"
                f"TRANSP:OPAQUE{self.CRLF}"
                f"END:VEVENT{self.CRLF}"
                f"END:VCALENDAR{self.CRLF}")

        msg = MIMEMultipart("mixed")
        msg["Reply-To"] = fro_m
        msg["Date"] = formatdate(localtime=True)
        msg["Subject"] = self.subject
        msg["From"] = fro_m
        msg["To"] = ",".join([f"{att}" for att in self.attendees])

        part_email = MIMEText(self.body, "html")
        part_cal = MIMEText(ical, "calendar;method=REQUEST")

        msgAlternative = MIMEMultipart("alternative")
        msg.attach(msgAlternative)
        msgAlternative.attach(part_email)
        msgAlternative.attach(part_cal)

        ical_atch = MIMEBase("application/ics", ' ;name="%s"' % "invite.ics")
        ical_atch.set_payload(ical)
        encoders.encode_base64(ical_atch)
        ical_atch.add_header("Content-Disposition", 'attachment; filename="%s"' % "invite.ics")

        msg.attach(ical_atch)
        return msg

    def send_invite(self):
        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(self.login, self.password)
            server.sendmail(self.login, self.attendees, self.create_invite_mail().as_string())
        print("Email sent! to ", self.attendees)
