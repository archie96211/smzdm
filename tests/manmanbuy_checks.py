"""Offline contracts for the optional QR login bridge. No real notifications."""
import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from yarl import URL
from src.manmanbuy import AlertSettings, Connection, Inputs, install, public_product_url
from src.database import DatabaseManager


class LoginChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.connection = Connection(self.tmp.name)

    async def asyncTearDown(self):
        await self.connection.close()
        self.tmp.cleanup()

    async def test_private_persistence_and_restart(self):
        client = await self.connection.get_client()
        client.cookie_jar.update_cookies({'60014_mmmuser': 'private-test', 'analytics': 'ignore'}, response_url=URL('https://home.manmanbuy.com'))
        self.connection.save(client)
        raw = self.connection.path.read_text()
        self.assertNotIn('analytics', raw)
        self.assertEqual(self.connection.path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('private-test', json.dumps(self.connection.status()))
        other = Connection(self.tmp.name)
        try:
            restored = await other.get_client()
            self.assertEqual(restored.cookie_jar.filter_cookies(URL('https://tool.manmanbuy.com'))['60014_mmmuser'].value, 'private-test')
        finally:
            await other.close()

    async def test_qr_expiry_closes_temporary_session(self):
        client = AsyncMock()
        self.connection.pending = {'id': 'test-id', 'deadline': time.monotonic()-1, 'client': client}
        self.assertEqual(await self.connection.poll_login('test-id'), {'state': 'qr_expired'})
        client.close.assert_awaited_once()
        self.assertIsNone(self.connection.pending)

    async def test_waiting_does_not_replace_existing_session(self):
        self.connection.state = 'connected'
        self.connection.pending = {'id': 'test-id', 'deadline': time.monotonic()+60, 'last_poll': 0, 'scene': 'private-scene', 'client': AsyncMock()}
        with patch.object(self.connection, 'json_request', AsyncMock(return_value={'data': {'status': 0}})):
            self.assertEqual(await self.connection.poll_login('test-id'), {'state': 'waiting'})
        self.assertEqual(self.connection.state, 'connected')

    async def test_login_success_saves_and_validates(self):
        client = await self.connection.get_client()
        client.cookie_jar.update_cookies({'60014_mmmuser': 'test-session'}, response_url=URL('https://home.manmanbuy.com'))
        self.connection.client = None
        self.connection.pending = {'id': 'test-id', 'deadline': time.monotonic()+60, 'last_poll': 0, 'scene': 'test-scene', 'client': client}
        async def valid(): self.connection.state = 'connected'
        with patch.object(self.connection, 'json_request', AsyncMock(return_value={'data': {'status': 1}})), patch.object(self.connection, 'validate', valid):
            result = await self.connection.poll_login('test-id')
        self.assertEqual(result['state'], 'connected')
        self.assertTrue(self.connection.path.exists())
        self.assertIsNone(self.connection.pending)

    async def test_challenge_marks_reconnection_without_leaking(self):
        parser = Inputs(); parser.ticket = 'test-ticket'
        self.connection.state = 'connected'
        with patch.object(self.connection, 'page', AsyncMock(return_value=parser)), patch.object(self.connection, 'json_request', AsyncMock(return_value=402)):
            with self.assertRaises(HTTPException):
                await self.connection.query('https://item.jd.com/5089253.html')
        self.assertEqual(self.connection.state, 'verification_required')

    async def test_expiry_alert_is_deduplicated_across_restart_and_reset_after_recovery(self):
        self.connection.path.parent.mkdir(parents=True)
        self.connection.path.write_text('{}')
        self.connection.database = Mock()
        self.connection.database.get_config.return_value = AlertSettings(
            enabled=True, channels=['bark', 'dingtalk']).model_dump_json()
        self.connection.available_channels = Mock(return_value={'bark': True, 'dingtalk': True})
        self.connection.send_alert = AsyncMock(return_value=True)

        async def expired():
            self.connection.state = 'expired'

        with patch.object(self.connection, 'validate', expired):
            await self.connection.check_and_alert()
            await self.connection.check_and_alert()
        self.assertEqual(self.connection.send_alert.await_count, 2)
        self.assertEqual(self.connection.alert_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.connection.alert_sent(), {'bark', 'dingtalk'})

        restarted = Connection(self.tmp.name, self.connection.database)
        restarted.available_channels = self.connection.available_channels
        restarted.send_alert = AsyncMock(return_value=True)
        try:
            async def expired_again():
                restarted.state = 'expired'
            async def connected():
                restarted.state = 'connected'
            with patch.object(restarted, 'validate', expired_again):
                await restarted.check_and_alert()
            restarted.send_alert.assert_not_awaited()
            with patch.object(restarted, 'validate', connected):
                await restarted.check_and_alert()
            self.assertFalse(restarted.alert_sent())
            with patch.object(restarted, 'validate', expired_again):
                await restarted.check_and_alert()
            self.assertEqual(restarted.send_alert.await_count, 2)
        finally:
            await restarted.close()

    async def test_alert_retries_failed_delivery_and_ignores_network_failure(self):
        self.connection.path.parent.mkdir(parents=True)
        self.connection.path.write_text('{}')
        self.connection.database = Mock()
        self.connection.database.get_config.return_value = AlertSettings(
            enabled=True, channels=['bark']).model_dump_json()
        self.connection.available_channels = Mock(return_value={'bark': True})
        self.connection.send_alert = AsyncMock(side_effect=[False, True])

        async def network_failure():
            raise asyncio.TimeoutError()
        with patch.object(self.connection, 'validate', network_failure):
            await self.connection.check_and_alert()
        self.connection.send_alert.assert_not_awaited()

        async def expired():
            self.connection.state = 'expired'
        with patch.object(self.connection, 'validate', expired):
            await self.connection.check_and_alert()
            self.assertFalse(self.connection.alert_sent())
            await self.connection.check_and_alert()
        self.assertTrue(self.connection.alert_sent())

    async def test_challenge_alert_does_not_require_history_page_validation(self):
        self.connection.path.parent.mkdir(parents=True)
        self.connection.path.write_text('{}')
        self.connection.database = Mock()
        self.connection.database.get_config.return_value = AlertSettings(
            enabled=True, channels=['bark']).model_dump_json()
        self.connection.available_channels = Mock(return_value={'bark': True})
        self.connection.state = 'verification_required'
        self.connection.send_alert = AsyncMock(return_value=True)
        with patch.object(self.connection, 'validate', AsyncMock()) as validate:
            await self.connection.check_and_alert()
        validate.assert_not_awaited()
        self.connection.send_alert.assert_awaited_once()

    async def test_disabled_and_missing_channel_never_send(self):
        self.connection.database = Mock()
        self.connection.database.get_config.return_value = '{}'
        self.connection.send_alert = AsyncMock()
        await self.connection.check_and_alert()
        self.connection.path.parent.mkdir(parents=True)
        self.connection.path.write_text('{}')
        async def expired():
            self.connection.state = 'expired'
        with patch.object(self.connection, 'validate', expired):
            await self.connection.check_and_alert()
        self.connection.database.get_config.return_value = AlertSettings(
            enabled=True, channels=['bark']).model_dump_json()
        self.connection.available_channels = Mock(return_value={'bark': False})
        with patch.object(self.connection, 'validate', expired):
            await self.connection.check_and_alert()
        self.connection.send_alert.assert_not_awaited()

    async def test_selected_channels_route_to_existing_notifiers(self):
        self.connection.database = Mock()
        self.connection.database.get_bark_config.return_value = {'device_key': 'test-key'}
        self.connection.database.get_config.side_effect = lambda key: {
            'dingtalk_webhook': 'https://example.invalid/webhook',
            'dingtalk_secret': 'secret',
            'wxpusher_app_token': 'token',
            'wxpusher_uid': 'uid',
        }.get(key)
        self.connection.notifier.send_message = AsyncMock(return_value=True)
        self.connection.dingtalk_notifier.send_text = AsyncMock(return_value=True)
        self.connection.wechat_notifier.send_message = AsyncMock(return_value=True)
        self.connection.wxpusher_notifier.send_markdown = AsyncMock(return_value=True)
        settings = AlertSettings(enabled=True, channels=['bark', 'dingtalk', 'wechat', 'wxpusher'],
                                 wechat_account_id='account', wechat_targets='conversation')
        for channel in settings.channels:
            self.assertTrue(await self.connection.send_alert(channel, settings))
        self.connection.notifier.send_message.assert_awaited_once()
        self.connection.dingtalk_notifier.send_text.assert_awaited_once()
        self.connection.wechat_notifier.send_message.assert_awaited_once()
        self.connection.wxpusher_notifier.send_markdown.assert_awaited_once()


class InputChecks(unittest.TestCase):
    def test_only_known_product_destinations(self):
        for url in ['http://item.jd.com/1.html','https://localhost/a','https://item.jd.com.evil.example/a','https://user:pass@item.jd.com/a']:
            with self.assertRaises(ValueError): public_product_url(url)

    def test_cross_origin_mutations_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = FastAPI();install(app, tmp)
            with TestClient(app) as client:
                result = client.post('/api/manmanbuy/login', headers={'Origin': 'https://other.example'})
                self.assertEqual(result.status_code, 403)

    def test_successful_query_snapshot_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = FastAPI()
            db = DatabaseManager(str(Path(tmp) / 'test.db'))
            connection = install(app, tmp, db)
            result = {'source': 'manmanbuy', 'has_history': True, 'product_name': '测试商品',
                      'lowest_price': 69, 'lowest_date': '2026-09-01', 'average_60_days': 80}
            with patch.object(connection, 'query', AsyncMock(return_value=result)):
                with TestClient(app) as client:
                    response = client.post('/api/manmanbuy/query', json={
                        'url': 'https://item.jd.com/5089253.html?tracking=private'})
                    self.assertEqual(response.status_code, 200, response.text)
            check = db.get_historical_price_checks()[0]
            self.assertEqual(check['product_url'], 'https://item.jd.com/5089253.html')
            self.assertEqual(check['lowest_price'], '69')

    def test_alert_settings_default_validation_and_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = FastAPI()
            db = DatabaseManager(str(Path(tmp) / 'test.db'))
            install(app, tmp, db)
            with TestClient(app) as client:
                initial = client.get('/api/manmanbuy/alerts').json()
                self.assertFalse(initial['settings']['enabled'])
                self.assertEqual(initial['settings']['channels'], [])
                invalid = client.put('/api/manmanbuy/alerts', json={
                    'enabled': True, 'channels': ['bark']})
                self.assertEqual(invalid.status_code, 422)
                db.set_config('bark_config', json.dumps({'device_key': 'private-test-key'}))
                saved = client.put('/api/manmanbuy/alerts', json={
                    'enabled': True, 'channels': ['bark']})
                self.assertEqual(saved.status_code, 200)
                readback = client.get('/api/manmanbuy/alerts').json()
                self.assertEqual(readback['settings']['channels'], ['bark'])
                self.assertTrue(readback['settings']['enabled'])
                self.assertNotIn('private-test-key', json.dumps(readback))
                self.assertEqual(client.put('/api/manmanbuy/alerts', json={
                    'enabled': True, 'channels': ['wechat']}).status_code, 422)
