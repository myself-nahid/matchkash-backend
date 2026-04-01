from typing import List
from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushServerError,
    PushTicketError,
)
from requests.exceptions import ConnectionError, HTTPError

def send_push_message(token: str, message: str, title: str = None, extra: dict = None):
    try:
        response = PushClient().publish(
            PushMessage(
                to=token,
                body=message,
                data=extra or {},
                title=title,
                sound="default"
            )
        )
    except PushServerError as exc:
        # Encountered some likely formatting/validation error.
        print(f"Error sending push notification: {exc.errors}")
        raise
    except (ConnectionError, HTTPError) as exc:
        print(f"Connection error sending push notification: {exc}")
        raise

    try:
        # We got a response back, but we don't know whether it's an error yet.
        # This call raises errors so we can handle them with normal exception flows.
        response.validate_response()
        return response
    except DeviceNotRegisteredError:
        # Mark the push token as invalid in your database if you want
        print("Device not registered anymore")
        raise
    except PushTicketError as exc:
        # Encountered some other per-notification error.
        print(f"Push ticket error: {exc.push_response._asdict()}")
        raise
