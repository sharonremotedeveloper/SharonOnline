"""Focused tests for deterministic Daily room provisioning and cleanup."""
from unittest.mock import Mock, patch

import pytest
from django.test import override_settings

from apps.integrations.services.daily import DailyClient


@pytest.fixture
def client():
    return DailyClient(api_key='real-test-key', domain='example.daily.co')


@override_settings(DAILY_API_KEY='real-test-key', DAILY_DOMAIN='example.daily.co')
def test_ensure_room_reuses_existing_room(client):
    existing = {'name': 'lesson-1', 'url': 'https://example.daily.co/lesson-1'}
    with patch('apps.integrations.services.daily.requests.get', return_value=Mock(status_code=200, json=lambda: existing)) as get:
        with patch('apps.integrations.services.daily.requests.post') as post:
            assert client.ensure_room('lesson-1', 100, 200) == existing
            get.assert_called_once()
            post.assert_not_called()


@override_settings(DAILY_API_KEY='real-test-key', DAILY_DOMAIN='example.daily.co')
def test_ensure_room_creates_private_bounded_room(client):
    missing = Mock(status_code=404)
    created = {'name': 'lesson-1', 'url': 'https://example.daily.co/lesson-1'}
    with patch('apps.integrations.services.daily.requests.get', return_value=missing):
        with patch('apps.integrations.services.daily.requests.post', return_value=Mock(status_code=201, json=lambda: created)) as post:
            assert client.ensure_room('lesson-1', 100, 200) == created
            body = post.call_args.kwargs['json']
            assert body['name'] == 'lesson-1'
            assert body['privacy'] == 'private'
            assert body['properties']['nbf'] == 100
            assert body['properties']['exp'] == 200
            assert body['properties']['enable_recording'] is False


@override_settings(DAILY_API_KEY='real-test-key', DAILY_DOMAIN='example.daily.co')
def test_delete_room_is_idempotent_for_missing_room(client):
    with patch('apps.integrations.services.daily.requests.delete', return_value=Mock(status_code=404)) as delete:
        assert client.delete_room('lesson-1') is True
        delete.assert_called_once()

