import logging
import os
import requests
import sys


# --------------------------------------------------------------------------------
#                                Required Functions
# --------------------------------------------------------------------------------
def send_events(data: list):
    webhook_url = os.environ.get('WEBHOOK_URL')
    for i in range(3):
        req_result = requests.post(webhook_url, json=data)
        if req_result.status_code < 300:
            return
        else:
            logging.error(f'Error with webhook event handling.\nStatus code: {req_result.status_code} - {req_result.text}')


def setup(_):
    if os.environ.get('WEBHOOK_URL') is None:
        logging.error('A webhook url is required to use the webhook event handler. Please add this as the environmental variable "WEBHOOK_URL".')
        sys.exit(1)
  