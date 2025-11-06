#!/usr/bin/env python3
"""Send alert to a webhook URL (e.g., Slack/Discord/Custom)."""
import os
import sys
import json
import httpx


def main():
    url = os.environ.get('ALERT_WEBHOOK_URL')
    if not url:
        print('ALERT_WEBHOOK_URL not set', file=sys.stderr)
        sys.exit(1)
    title = os.environ.get('ALERT_TITLE', 'One Smart Trade Alert')
    message = os.environ.get('ALERT_MESSAGE', 'No message provided')
    payload = {"text": f"{title}: {message}"}
    try:
        r = httpx.post(url, json=payload, timeout=10.0)
        r.raise_for_status()
        print('Alert sent')
    except Exception as e:
        print(f'Failed to send alert: {e}', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()


