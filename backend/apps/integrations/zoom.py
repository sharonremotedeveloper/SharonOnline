import os
import requests
import base64
import logging

logger = logging.getLogger(__name__)


class ZoomError(Exception):
    """Zoom refused or failed a request we made (the message carries Zoom's own explanation)."""


class ZoomClient:
    def __init__(self):
        self.account_id = os.environ.get('ZOOM_ACCOUNT_ID')
        self.client_id = os.environ.get('ZOOM_CLIENT_ID')
        self.client_secret = os.environ.get('ZOOM_CLIENT_SECRET')

    def get_access_token(self) -> str:
        if not (self.account_id and self.client_id and self.client_secret):
            logger.warning("Zoom API credentials not configured. Using simulated room URLs.")
            return ""

        url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={self.account_id}"
        auth_header = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()

        response = requests.post(url, headers={
            'Authorization': f'Basic {auth_header}'
        }, timeout=10)

        if response.status_code == 200:
            return response.json().get('access_token')
        logger.error(f"Zoom OAuth token request failed: {response.text}")
        return ""

    def create_meeting(self, topic: str, start_time_iso: str, duration_minutes: int = 25) -> dict:
        token = self.get_access_token()
        if not token:
            # Fallback mock for development/sandbox
            import uuid
            meeting_num = f"{uuid.uuid4().int % 10000000000:010d}"
            return {
                "meeting_id": meeting_num,
                "join_url": f"https://zoom.us/j/{meeting_num}",
                "start_url": f"https://zoom.us/s/{meeting_num}?zak=mock_token",
                "password": "pass" + meeting_num[:4]
            }

        url = "https://api.zoom.us/v2/users/me/meetings"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        data = {
            "topic": topic,
            "type": 2, # Scheduled meeting
            "start_time": start_time_iso,
            "duration": duration_minutes,
            "timezone": "UTC",
            "settings": {
                "host_video": True,
                "participant_video": True,
                "join_before_host": False,
                "mute_upon_entry": False,
                "waiting_room": True
            }
        }
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        if resp.status_code == 201:
            res_data = resp.json()
            return {
                "meeting_id": str(res_data.get('id')),
                "join_url": res_data.get('join_url'),
                "start_url": res_data.get('start_url'),
                "password": res_data.get('password', '')
            }
        # Never fall through to None: the caller would die on a TypeError that hides Zoom's actual reason.
        raise ZoomError(f"Zoom refused to create the meeting (HTTP {resp.status_code}): {resp.text[:300]}")

    def get_meeting_status(self, meeting_id: str) -> dict:
        token = self.get_access_token()
        if not token:
            # Fallback mock for development/sandbox
            return {
                "meeting_id": str(meeting_id),
                "status": "waiting",
                "participant_count": 0
            }

        url = f"https://api.zoom.us/v2/meetings/{meeting_id}"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            res_data = resp.json()
            return {
                "meeting_id": str(res_data.get('id')),
                "status": res_data.get('status', 'waiting'),  # 'waiting', 'started', 'finished'
                "participant_count": res_data.get('participant_count', 0)
            }
        logger.error(f"Failed to fetch Zoom meeting status for {meeting_id}: {resp.text}")
        return {
            "meeting_id": str(meeting_id),
            "status": "error",
            "participant_count": 0
        }

    def delete_meeting(self, meeting_id: str) -> bool:
        """Remove a meeting (cancelled or rescheduled lesson). A meeting Zoom no longer has counts as deleted."""
        token = self.get_access_token()
        if not token:
            return True        # simulated rooms (no credentials) have nothing to delete
        resp = requests.delete(f"https://api.zoom.us/v2/meetings/{meeting_id}", headers={'Authorization': f'Bearer {token}'}, timeout=10)
        if resp.status_code in (204, 404):
            return True
        raise ZoomError(f"Zoom refused to delete meeting {meeting_id} (HTTP {resp.status_code}): {resp.text[:300]}")

    @staticmethod
    def get_webhook_secret() -> str:
        from django.conf import settings
        return getattr(settings, 'ZOOM_WEBHOOK_SECRET_TOKEN', '') or ''

    @classmethod
    def verify_webhook_signature(cls, headers: dict, raw_body: bytes) -> tuple[bool, str]:
        import hmac
        import hashlib
        import time

        zm_signature = headers.get('x-zm-signature') or headers.get('HTTP_X_ZM_SIGNATURE', '')
        zm_timestamp = headers.get('x-zm-request-timestamp') or headers.get('HTTP_X_ZM_REQUEST_TIMESTAMP', '')

        if not zm_signature or not zm_timestamp:
            return False, "Missing Zoom webhook signature or timestamp headers"

        try:
            timestamp_int = int(zm_timestamp)
        except (ValueError, TypeError):
            return False, "Invalid timestamp format in Zoom webhook header"

        # Check replay attack drift (within 300 seconds / 5 minutes)
        if abs(int(time.time()) - timestamp_int) > 300:
            return False, "Request timestamp out of allowable window (replay guard)"

        secret = cls.get_webhook_secret()
        if not secret:
            logger.error("ZOOM_WEBHOOK_SECRET_TOKEN is not configured; rejecting webhook")
            return False, "Zoom webhook secret not configured"
        body_str = raw_body.decode('utf-8', errors='replace')
        message = f"v0:{zm_timestamp}:{body_str}"
        computed_hash = hmac.new(
            secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        expected_signature = f"v0={computed_hash}"

        if not hmac.compare_digest(expected_signature, zm_signature):
            return False, "Invalid HMAC signature"

        return True, "Valid"

    @classmethod
    def generate_url_validation_response(cls, plain_token: str) -> dict:
        import hmac
        import hashlib

        secret = cls.get_webhook_secret()
        encrypted_token = hmac.new(
            secret.encode('utf-8'),
            plain_token.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return {
            "plainToken": plain_token,
            "encryptedToken": encrypted_token
        }


zoom_client = ZoomClient()

