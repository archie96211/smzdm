import asyncio
import os
import tempfile
import unittest
from pathlib import Path

_TMP = tempfile.TemporaryDirectory()
os.environ.update(SMZDM_DATA_DIR=_TMP.name, SMZDM_LOG_DIR=_TMP.name,
                  SMZDM_WECHAT_BRIDGE_ENABLED='false', AUTO_START_MONITOR='false',
                  SMZDM_IMAGE_SERVER_HOST='127.0.0.1', SMZDM_ALLOWED_NETWORKS='192.168.31.0/24')
import aiohttp
from aiohttp import web
from fastapi.testclient import TestClient
from src.monitor import SMZDMMonitor
from src.web_server import app

class FetchChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.monitor = SMZDMMonitor(str(Path(self.tmp.name) / 'test.db'))
        self.code = 200
        self.rows = [{'article_channel_id': '2', 'article_id': '1', 'article_title': '纸巾', 'article_price': '10元'},
                     {'article_channel_id': '11', 'article_id': '2', 'article_title': '文章'}]
        async def handle(request):
            return web.json_response({'error_code': '0', 'data': {'rows': self.rows}}, status=self.code)
        a = web.Application(); a.router.add_get('/', handle)
        self.runner = web.AppRunner(a); await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0); await site.start()
        self.monitor.api_base_url = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/'
        sid = self.monitor.db.create_scheme('test')
        self.monitor.db.add_keyword(sid, '纸巾')
        self.sid = sid; self.kw = self.monitor.db.get_keywords(sid)[0]
    async def asyncTearDown(self):
        await self.runner.cleanup(); self.tmp.cleanup()
    async def test_first_run_dedup_and_new_item(self):
        async with aiohttp.ClientSession() as s:
            self.assertEqual(await self.monitor.monitor_keyword(s, self.sid, self.kw), [])
            self.assertEqual(len(self.monitor.db.get_recent_products(self.sid)), 1)
            self.assertEqual(await self.monitor.monitor_keyword(s, self.sid, self.kw), [])
            self.rows.append(dict(self.rows[0], article_id='3'))
            self.assertEqual(len(await self.monitor.monitor_keyword(s, self.sid, self.kw)), 1)
            self.assertEqual(self.monitor.fetch_metrics['successes'], 3)
    async def test_failure_backoff_and_recovery(self):
        async with aiohttp.ClientSession() as s:
            self.code = 429
            await self.monitor.monitor_keyword(s, self.sid, self.kw)
            await self.monitor.monitor_keyword(s, self.sid, self.kw)
            self.assertEqual(self.monitor.fetch_metrics['requests'], 1)
            self.assertEqual(self.monitor.fetch_metrics['failures'], 1)
            self.monitor.fetch_backoff[self.kw['id']] = (1, 0); self.code = 200
            await self.monitor.monitor_keyword(s, self.sid, self.kw)
            self.assertEqual(self.monitor.fetch_metrics['successes'], 1)
            self.assertFalse(self.monitor.fetch_backoff)

class AccessChecks(unittest.TestCase):
    def test_lan_and_interval_validation(self):
        with TestClient(app, client=('192.168.31.10', 12345)) as c:
            self.assertEqual(c.get('/api/health').status_code, 200)
            self.assertEqual(c.get('/api/wechat/conversations').json()['data'], [])
            self.assertEqual(c.post('/api/wechat/login/start').status_code, 503)
            self.assertEqual(c.post('/api/schemes', json={'name':'bad','keyword':'x','refresh_interval':0}).status_code, 422)
    def test_untrusted_address_denied(self):
        with TestClient(app, client=('203.0.113.5', 12345)) as c:
            self.assertEqual(c.get('/api/schemes').status_code, 403)

if __name__ == '__main__': unittest.main()
