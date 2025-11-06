#!/usr/bin/env python3
"""Send basic email alert via SMTP (uses STARTTLS)."""
import os
import sys
import smtplib
from email.mime.text import MIMEText


def main():
    host = os.environ.get('SMTP_HOST')
    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASS')
    to_addr = os.environ.get('ALERT_TO')
    from_addr = os.environ.get('ALERT_FROM', user)
    subject = os.environ.get('ALERT_SUBJECT', 'One Smart Trade Alert')
    body = os.environ.get('ALERT_BODY', 'No message provided')

    if not all([host, port, user, password, to_addr]):
        print('Missing SMTP configuration', file=sys.stderr)
        sys.exit(1)

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_addr

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        print('Email sent')
    except Exception as e:
        print(f'Failed to send email: {e}', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()


