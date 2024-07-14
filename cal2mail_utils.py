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
        start: datetime,
        subject: str = "Please set Subject",
        body: str = "Please set Body",
        adress: str = None,
        organizer: str = "organizer",
        description: str = "Please set Description",
        duration: int = None,
        end: datetime = None,
    ):
        # Retrieve SMTP configuration from environment variables
        self.login = os.getenv("EMAIL_LOGIN")
        self.password = os.getenv("EMAIL_PASSWORD")
        self.smtp_server = os.getenv("SMTP_SERVER")
        self.smtp_port = int(
            os.getenv("SMTP_PORT", 587)
        )  # Default SMTP port is set to 587

        self.attendees = attendees
        self.subject = subject
        self.body = body
        self.start = start
        self.organizer = organizer
        self.description = description
        self.adress = adress
        self.duration = duration
        self.end = end

    def create_invite_mail(self) -> MIMEMultipart:
        if self.end is None:
            if self.duration is None:
                duration = datetime.timedelta(minutes=30)
            end = self.start + duration

        organizer = f"ORGANIZER;CN={self.organizer}" + self.CRLF
        fro_m = f"{os.getenv('FROM_NAME', 'nickname')} <{self.login}>"

        dtstart = self.start.strftime("%Y%m%dT%H%M%SZ")
        dtend = end.strftime("%Y%m%dT%H%M%SZ")
        dtstamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%SZ")

        description = "DESCRIPTION: " + self.description + self.CRLF
        attendee = ""
        for att in self.attendees:
            attendee += f"ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=ACCEPTED;RSVP=TRUE{self.CRLF};CN={att};X-NUM-GUESTS=0:{self.CRLF}mailto:{att}{self.CRLF}"
        pass
        # ical = (
        #     "BEGIN:VCALENDAR"
        #     + self.CRLF
        #     + "PRODID:pyICSParser"
        #     + self.CRLF
        #     + "VERSION:2.0"
        #     + self.CRLF
        #     + "CALSCALE:GREGORIAN"
        #     + self.CRLF
        #     + "METHOD:REQUEST"
        #     + self.CRLF
        #     + "BEGIN:VEVENT"
        #     + self.CRLF
        #     + f"DTSTART:{dtstart}"
        #     + self.CRLF
        #     + f"DTEND:{dtend}"
        #     + self.CRLF
        #     + f"DTSTAMP:{dtstamp}"
        #     + self.CRLF
        #     + organizer
        #     + self.CRLF
        #     + f"UID:FIXMEUID{dtstamp}"
        #     + self.CRLF
        #     + attendee
        #     + "CREATED:"
        #     + dtstamp
        #     + self.CRLF
        #     + description
        #     + "LAST-MODIFIED:"
        #     + dtstamp
        #     + self.CRLF
        #     + "LOCATION:"
        #     + self.adress
        #     + self.CRLF
        #     + "SEQUENCE:0"
        #     + self.CRLF
        #     + "STATUS:CONFIRMED"
        #     + self.CRLF
        #     + "SUMMARY: "
        #     + self.subject
        #     + self.CRLF
        #     + "TRANSP:OPAQUE"
        #     + self.CRLF
        #     + "END:VEVENT"
        #     + self.CRLF
        #     + "END:VCALENDAR"
        #     + self.CRLF
        # )

        ical = ("BEGIN:VCALENDAR" + self.CRLF + "PRODID:pyICSParser" + self.CRLF + "VERSION:2.0" + self.CRLF + 
                "CALSCALE:GREGORIAN" + self.CRLF + "METHOD:REQUEST" + self.CRLF + "BEGIN:VEVENT" + self.CRLF +
                f"DTSTART:{dtstart}" + self.CRLF + f"DTEND:{dtend}" + self.CRLF + f"DTSTAMP:{dtstamp}" + self.CRLF +
                organizer + self.CRLF + f"UID:FIXMEUID{dtstamp}" + self.CRLF + attendee + "CREATED:" + dtstamp +
                self.CRLF + description + "LAST-MODIFIED:" + dtstamp + self.CRLF + "LOCATION:" + self.CRLF +
                "SEQUENCE:0" + self.CRLF + "STATUS:CONFIRMED" + self.CRLF + "SUMMARY: "+ self.subject+ self.CRLF + "TRANSP:OPAQUE" + self.CRLF +
                "END:VEVENT" + self.CRLF + "END:VCALENDAR" + self.CRLF)


        msg = MIMEMultipart("mixed")
        msg["Reply-To"] = fro_m
        msg["Date"] = formatdate(localtime=True)
        msg["Subject"] = self.subject
        msg["From"] = fro_m
        msg["To"] = ",".join(attendee)

        part_email = MIMEText(self.body, "html")
        part_cal = MIMEText(ical, "calendar;method=REQUEST")

        msgAlternative = MIMEMultipart("alternative")
        msg.attach(msgAlternative)
        msgAlternative.attach(part_email)
        msgAlternative.attach(part_cal)

        ical_atch = MIMEBase("application/ics", ' ;name="%s"' % ("invite.ics"))
        ical_atch.set_payload(ical)
        encoders.encode_base64(ical_atch)
        ical_atch.add_header(
            "Content-Disposition", 'attachment; filename="%s"' % ("invite.ics")
        )

        msg.attach(ical_atch)
        return msg

    def send_invite(self, attendees, msg):
        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(self.login, self.password)
            server.sendmail(msg["From"], attendees, msg.as_string() )
