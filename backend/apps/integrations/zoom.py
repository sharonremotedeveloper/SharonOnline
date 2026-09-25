import os
import requests
import base64
import logging

logger = logging.getLogger(__name__)

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
        logger.error(f"Failed to create Zoom meeting: {resp.text}")
        raise RuntimeError(f"Zoom meeting creation failed: {resp.text}")

zoom_client = ZoomClient()
