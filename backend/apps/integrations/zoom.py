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

    def credentials_configured(self) -> bool:
        return bool(self.account_id and self.client_id and self.client_secret)

    def get_access_token(self) -> str:
        """'' only when no credentials are configured. With credentials, any failure RAISES ZoomError (Slice F0 review B1):
        an OAuth outage must never look like "no credentials" and fall into the simulated path."""
        if not self.credentials_configured():
            return ""

        url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={self.account_id}"
        auth_header = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()

        response = requests.post(url, headers={
            'Authorization': f'Basic {auth_header}'
        }, timeout=10)

        token = None
        if response.status_code == 200:
            try:
                token = response.json().get('access_token')
            except (ValueError, AttributeError):
                token = None
        if token:
            return token
        logger.error("Zoom OAuth token request failed: HTTP %s", response.status_code)    # never the provider body
        raise ZoomError(f"Zoom OAuth token request failed (HTTP {response.status_code})")

    def _token(self):
        """A bearer token, or None when simulation is allowed: no credentials AND settings.ZOOM_SIMULATE_WITHOUT_CREDENTIALS
        (only local settings enable it; production inherits False) AND settings.DEBUG (docker compose also runs the local
        settings, so a shared/staging stack with DEBUG off never fabricates rooms or a 'waiting' status). Otherwise ZoomError."""
        token = self.get_access_token()
        if token:
            return token
        from django.conf import settings
        if settings.DEBUG and getattr(settings, 'ZOOM_SIMULATE_WITHOUT_CREDENTIALS', False):
            logger.warning("Zoom API credentials not configured. Using simulated rooms (local settings only).")
            return None
        raise ZoomError("Zoom credentials are not configured and simulation is disabled")

    def create_meeting(self, topic: str, start_time_iso: str, duration_minutes: int = 25) -> dict:
        token = self._token()
        if token is None:
            # Simulated room: local development / tests only (see _token)
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
        """{'status': <Zoom's status or None>}. A non-200 raises ZoomError; a missing status is None (the caller's 'unknown')."""
        token = self._token()
        if token is None:
            # Simulated status: local development / tests only (see _token)
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
                "status": res_data.get('status'),  # 'waiting' | 'started'; anything else / absent = unknown to the caller
                "participant_count": res_data.get('participant_count', 0)
            }
        logger.error("Failed to fetch Zoom meeting status for %s: HTTP %s", meeting_id, resp.status_code)
        raise ZoomError(f"Zoom meeting status request failed (HTTP {resp.status_code})")

    def get_past_instances(self, meeting_id: str) -> list:
        """Ended instances of a meeting (`GET /past_meetings/{id}/instances`). A scheduled meeting goes back to `waiting` after
        it ends, so `waiting` + a past instance means the lesson DID take place. Only a 200 with a list is an answer;
        anything else raises ZoomError (the probe then says 'unknown')."""
        token = self._token()
        if token is None:
            return []          # simulated rooms never ran
        resp = requests.get(f"https://api.zoom.us/v2/past_meetings/{meeting_id}/instances",
                            headers={'Authorization': f'Bearer {token}'}, timeout=10)
        if resp.status_code == 200:
            meetings = resp.json().get('meetings')
            if isinstance(meetings, list):
                return meetings
        logger.error("Zoom past-instances request inconclusive for %s: HTTP %s", meeting_id, resp.status_code)
        raise ZoomError(f"Zoom past-instances request inconclusive (HTTP {resp.status_code})")

    def delete_meeting(self, meeting_id: str) -> bool:
        """Remove a meeting (cancelled or rescheduled lesson). A meeting Zoom no longer has counts as deleted."""
        token = self._token()
        if token is None:
            return True        # simulated rooms (no credentials, local settings) have nothing to delete
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

