"""Offline Bark contract, privacy, migration and monitor integration checks."""

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

_TEMP = tempfile.TemporaryDirectory()
os.environ.update(
    SMZDM_DATA_DIR=_TEMP.name,
    SMZDM_LOG_DIR=_TEMP.name,
    AUTO_START_MONITOR="false",
    SMZDM_IMAGE_SERVER_HOST="127.0.0.1",
)
import aiohttp
from aiohttp import web
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient
from src.bark_notifier import BarkConfig, BarkNotifier, build_payload, merge_config, public_config
from src.database import DatabaseManager
from src.monitor import SMZDMMonitor
from src import web_server


class PayloadChecks(unittest.TestCase):
    def test_link_modes_and_fallback(self):
        url = "https://www.smzdm.com/p/123456/"
        context = {"url": url}
        web = build_payload(BarkConfig(), "t", "b", context)
        self.assertEqual(web["url"], url)
        self.assertEqual(web["body"], "b")
        app = build_payload(BarkConfig(link_mode="app", copy_text="{url}"), "t", "b", context)
        self.assertEqual(app["url"], "smzdm://youhui/123456")
        self.assertIn(url, app["body"])
        self.assertEqual(app["copy"], url)
        for other in ["https://post.smzdm.com/p/abc/", "https://www.smzdm.com.evil.test/p/123/", "https://example.com/p/123/", "https://www.smzdm.com/"]:
            payload = build_payload(BarkConfig(link_mode="app"), "t", "b", {"url": other})
            self.assertEqual(payload["url"], other)
            self.assertEqual(payload["body"], "b")
        disabled = build_payload(BarkConfig(link_mode="app", open_url=False), "t", "b", context)
        self.assertNotIn("url", disabled)
        self.assertEqual(disabled["body"], "b")
        self.assertEqual(disabled["action"], "none")
        with self.assertRaises(ValueError):
            BarkConfig(link_mode="unsupported")

    def test_complete_push_url_and_redaction(self):
        key = "a" * 22
        for url, server in [
            (f"https://example.com/{key}/", "https://example.com"),
            (f"https://example.com/{key}/测试标题/测试正文?group=test", "https://example.com"),
            (f"https://example.com/bark/{key}/", "https://example.com/bark"),
        ]:
            config = merge_config({"push_url": url}, {}, [])
            self.assertEqual(config.server_url, server)
            self.assertEqual(config.device_key, key)
            self.assertNotIn(key, json.dumps(public_config(config)))
            self.assertEqual(merge_config({"push_url": ""}, config.model_dump(), []).device_key, key)
        for url in ["https://example.com/", "https://example.com/push", "https://user:pass@example.com/key"]:
            with self.assertRaises(ValueError):
                merge_config({"push_url": url}, {}, [])


    def test_features_and_zero_ttl(self):
        config = BarkConfig(
            device_key="test-device",
            group="{scheme}/{mall}/{keyword}",
            icon="https://example.com/icon.png?v=2",
            image_enabled=True,
            level="critical",
            volume=7,
            badge=3,
            archive="yes",
            ttl=0,
            sound="minuet",
            auto_copy=True,
            copy_text="{url}",
            call=True,
        )
        payload = build_payload(
            config,
            "标题",
            "正文",
            {
                "scheme": "s",
                "mall": "m",
                "keyword": "k",
                "url": "https://example.com/deal",
            },
            "https://example.com/image.png",
        )
        self.assertEqual(payload["group"], "s/m/k")
        self.assertEqual(payload["ttl"], 0)
        self.assertEqual(payload["isArchive"], "1")
        self.assertEqual(payload["volume"], "7")
        self.assertEqual(payload["badge"], 3)
        self.assertEqual(payload["copy"], payload["url"])
        self.assertEqual(payload["autoCopy"], "1")
        self.assertEqual(payload["call"], "1")
        self.assertIn("image", payload)

    def test_archive_no_omits_ttl_and_default_omits_both(self):
        payload = build_payload(
            BarkConfig(archive="no", ttl=86400, open_url=False), "t", "b", {}
        )
        self.assertEqual(payload["isArchive"], "0")
        self.assertNotIn("ttl", payload)
        self.assertEqual(payload["action"], "none")
        default = build_payload(BarkConfig(), "t", "b", {})
        self.assertNotIn("ttl", default)
        self.assertNotIn("isArchive", default)

    def test_cbc_and_gcm_round_trip_all_key_sizes(self):
        for mode in ("CBC", "GCM"):
            for size in (16, 24, 32):
                with self.subTest(mode=mode, size=size):
                    key = "a" * size
                    config = BarkConfig(
                        device_key="test-device",
                        encryption=mode,
                        encryption_key=key,
                        archive="yes",
                        ttl=3600,
                    )
                    payload = build_payload(
                        config, "私密标题", "私密正文", {"scheme": "私密分组"}
                    )
                    self.assertEqual(set(payload), {"device_key", "iv", "ciphertext"})
                    self.assertNotIn("私密", json.dumps(payload, ensure_ascii=False))
                    data = base64.b64decode(payload["ciphertext"])
                    iv = payload["iv"].encode()
                    if mode == "GCM":
                        plain = AESGCM(key.encode()).decrypt(iv, data, None)
                    else:
                        dec = Cipher(
                            algorithms.AES(key.encode()), modes.CBC(iv)
                        ).decryptor()
                        padded = dec.update(data) + dec.finalize()
                        unpad = padding.PKCS7(128).unpadder()
                        plain = unpad.update(padded) + unpad.finalize()
                    result = json.loads(plain)
                    self.assertEqual(result["body"], "私密正文")
                    self.assertEqual(result["ttl"], 3600)
                    self.assertNotEqual(
                        payload["iv"], build_payload(config, "t", "b", {})["iv"]
                    )

    def test_icon_url_preserves_query_and_trailing_slash(self):
        icon = "https://example.com/icon?version=/"
        self.assertEqual(BarkConfig(icon=icon).icon, icon)

    def test_invalid_key_url_template_and_ranges(self):
        for values in (
            {"encryption": "GCM", "encryption_key": "short"},
            {"ttl": -1},
            {"volume": 11},
            {"group": "{scheme.__class__}"},
            {"server_url": "file:///tmp/key"},
            {"server_url": "https://example.com/push"},
            {"server_url": "https://user:pass@example.com"},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                BarkConfig(**values)


class TransportChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.status = 200
        self.result = {"code": 200}
        self.received = []

        async def handle(request):
            self.received.append(await request.json())
            return web.json_response(self.result, status=self.status)

        app = web.Application()
        app.router.add_post("/push", handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
        self.config = BarkConfig(server_url=self.url, device_key="private-device")
        self.sender = BarkNotifier()

    async def asyncTearDown(self):
        await self.sender.close()
        await self.runner.cleanup()

    async def test_http_and_application_errors(self):
        self.assertTrue(await self.sender.send_message(self.config, "t", "b"))
        self.result = {"code": 400, "message": "private-device secret-body"}
        with self.assertLogs("src.bark_notifier", logging.WARNING) as logs:
            self.assertFalse(await self.sender.send_message(self.config, "t", "b"))
        self.assertNotIn("private-device", " ".join(logs.output))
        self.status = 500
        self.result = {"code": 200}
        self.assertFalse(await self.sender.send_message(self.config, "t", "b"))
        self.status = 302
        self.assertFalse(await self.sender.send_message(self.config, "t", "b"))

    async def test_encrypted_wire_and_size_limit(self):
        cfg = self.config.model_copy(
            update={"encryption": "GCM", "encryption_key": "a" * 16}
        )
        self.assertTrue(await self.sender.send_message(cfg, "私密", "内容"))
        self.assertEqual(set(self.received[0]), {"device_key", "ciphertext", "iv"})
        self.assertFalse(await self.sender.send_message(cfg, "t", "长" * 4000))
        self.assertEqual(len(self.received), 1)
        await self.sender.close()
        self.assertIsNone(self.sender.session)

    async def test_bark_only_monitor_and_notification_log(self):
        with tempfile.TemporaryDirectory() as folder:
            mon = SMZDMMonitor(str(Path(folder) / "db.sqlite"))
            sid = mon.db.create_scheme(
                "only bark", bark_enabled=True, refresh_interval=60
            )
            kid = mon.db.add_keyword(sid, "paper")
            mon.db.set_config("bark_config", self.config.model_dump_json())
            mon.db.add_product(sid, kid, {"article_id": "old", "article_title": "old"})
            mon.fetch_products = AsyncMock(
                return_value=[
                    {
                        "article_channel_id": "2",
                        "article_id": "new",
                        "article_title": "new deal",
                        "article_price": "10元",
                        "article_mall": "shop",
                        "article_url": "https://example.com/deal",
                    }
                ]
            )
            mon.running = True
            mon.tasks[sid] = asyncio.create_task(mon.monitor_scheme(sid))
            try:

                async def received():
                    while True:
                        with mon.db.connect() as conn:
                            if conn.execute(
                                "select count(*) from notification_logs"
                            ).fetchone()[0]:
                                return
                        await asyncio.sleep(0.01)

                await asyncio.wait_for(received(), 2)
                with mon.db.connect() as conn:
                    self.assertEqual(
                        conn.execute(
                            "select notification_type,status from notification_logs"
                        ).fetchall(),
                        [("bark", "success")],
                    )
                self.assertEqual(self.received[0]["title"], "new deal")
                self.assertEqual(len(mon.db.get_recent_products(sid)), 2)
            finally:
                await mon.stop_monitoring()


class SettingsChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(str(Path(self.temp.name) / "db.sqlite"))
        self.sid = self.db.create_scheme("settings")
        self.patch = patch.object(web_server, "db", self.db)
        self.patch.start()
        self.access_patch = patch.object(web_server, "allow_public_api", True)
        self.access_patch.start()
        self.client = TestClient(web_server.app)

    def tearDown(self):
        self.client.close()
        self.access_patch.stop()
        self.patch.stop()
        self.temp.cleanup()

    def save(self, values, suffix=""):
        return self.client.put("/api/bark/settings" + suffix, json=values)

    def test_secret_redaction_preservation_and_clearing(self):
        self.assertEqual(
            self.save(
                {
                    "config": {
                        "device_key": "secret-device",
                        "encryption": "CBC",
                        "encryption_key": "a" * 16,
                    }
                }
            ).status_code,
            200,
        )
        for path in (
            "/api/bark/settings",
            "/api/global-settings",
            "/api/schemes",
            f"/api/schemes/{self.sid}",
        ):
            body = self.client.get(path).text
            self.assertNotIn("secret-device", body)
            self.assertNotIn("a" * 16, body)
        self.assertTrue(
            self.client.get("/api/bark/settings").json()["data"]["config"][
                "has_device_key"
            ]
        )
        self.save(
            {"config": {"device_key": "", "encryption_key": "", "group": "changed"}}
        )
        self.assertEqual(self.db.get_bark_config()["device_key"], "secret-device")
        self.save(
            {
                "config": {"encryption": "none"},
                "clear_secrets": ["device_key", "encryption_key"],
            }
        )
        self.assertEqual(self.db.get_bark_config()["device_key"], "")

    def test_override_inheritance_and_other_settings_preserved(self):
        self.db.set_config("dingtalk_webhook", "existing")
        self.save({"config": {"device_key": "global-key", "group": "global"}})
        suffix = f"?scheme_id={self.sid}"
        self.save({"config": {"group": "local"}, "enabled": True}, suffix)
        self.assertEqual(self.db.get_bark_config(self.sid)["group"], "local")
        self.assertEqual(self.db.get_bark_config(self.sid)["device_key"], "global-key")
        self.save({"use_global": True, "enabled": False}, suffix)
        self.assertEqual(self.db.get_bark_config(self.sid)["group"], "global")
        self.assertFalse(self.db.get_scheme(self.sid)["bark_enabled"])
        self.assertEqual(self.db.get_config("dingtalk_webhook"), "existing")

    def test_invalid_update_is_atomic_and_does_not_echo_secrets(self):
        self.save({"config": {"device_key": "valid"}})
        result = self.save(
            {"config": {"encryption": "GCM", "encryption_key": "sensitive"}}
        )
        self.assertEqual(result.status_code, 422)
        self.assertNotIn("sensitive", result.text)
        self.assertEqual(self.db.get_bark_config()["encryption"], "none")
        self.assertEqual(
            self.save({"enabled": True}, "?scheme_id=999999").status_code, 404
        )

    def test_schema_migration_preserves_existing_scheme(self):
        with self.db.connect() as conn:
            conn.execute("ALTER TABLE monitor_schemes DROP COLUMN bark_enabled")
            conn.execute("ALTER TABLE monitor_schemes DROP COLUMN bark_config")
        upgraded = DatabaseManager(self.db.db_path)
        self.assertEqual(upgraded.get_scheme(self.sid)["name"], "settings")
        self.assertFalse(upgraded.get_scheme(self.sid)["bark_enabled"])
        self.assertEqual(upgraded.get_scheme(self.sid)["bark_config"], "")


if __name__ == "__main__":
    unittest.main()
