"""Offline checks for price evidence, aggregation and durable alert decisions."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.database import DatabaseManager
from src.deal_comparison import calculate_verified_price, candidate_products
from src.deal_pipeline import deal_key, prepare_alerts
from src.merchant_links import canonical_product_url, resolve_jd_affiliate, resolve_merchant_item_url, resolve_offer_product_url, unwrap_location
from src.monitor import SMZDMMonitor


class PriceEvidenceChecks(unittest.TestCase):
    def test_model_numbers_are_calculated_only_from_exact_source_quotes(self):
        offer = {"article_title": "抽纸6包，每包100张", "article_price": "标价30元，满30减6元"}
        expression = {"base_price": {"value": 30, "evidence": "标价30元"},
                      "discounts": [{"value": 6, "evidence": "满30减6元"}],
                      "package_count": {"value": 6, "evidence": "6包"},
                      "units_per_package": {"value": 100, "evidence": "100张"}}
        self.assertEqual(calculate_verified_price(offer, expression),
                         {"total_price": "24.00", "price_per_package": "4.0000", "unit_price": "0.0400"})
        expression["discounts"][0]["evidence"] = "满30减8元"
        self.assertIsNone(calculate_verified_price(offer, expression))

    def test_coupon_and_tracking_links_are_not_item_identity(self):
        self.assertIsNone(canonical_product_url("https://uland.taobao.com/coupon/edetail?id=123456"))
        self.assertEqual(canonical_product_url("https://item.jd.com/5089253.html?tracking=secret"),
                         "https://item.jd.com/5089253.html")
        self.assertEqual(canonical_product_url("http://detail.tmall.com/item.htm?id=12345678&spm=track"),
                         "https://detail.tmall.com/item.htm?id=12345678")
        self.assertEqual(canonical_product_url("http://uland.taobao.com/item/edetail?id=ABCdef012345&skuId=12345678"),
                         "https://uland.taobao.com/item/edetail?id=ABCdef012345&skuId=12345678")
        self.assertIsNone(unwrap_location("http://www.manmanbuy.com/redirectUrl.aspx?tourl=https://uland.taobao.com/a"))

    def test_category_candidate_search_is_bounded_and_not_a_comparability_decision(self):
        products = [{"id": 1, "name": "常用猫砂", "links": []},
                    {"id": 2, "name": "抽纸", "links": []},
                    {"id": 3, "name": "宠物罐头", "links": []}]
        self.assertEqual(candidate_products({"article_title": "另一品牌猫砂 10kg"}, products)[0]["id"], 1)
        self.assertEqual(candidate_products({"article_title": "某品牌面巾纸 6包"}, products)[0]["id"], 2)


class AlertPipelineChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(str(Path(self.tmp.name) / "state.db"))
        self.scheme_id = self.db.create_scheme("aggregation")

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_unchanged_cross_source_offer_skips_alert(self):
        offer = {"article_id": "manmanbuy:new", "article_title": "示例抽纸6包",
                 "article_price": "24元", "article_url": "https://cu.manmanbuy.com/discuxiao_1.aspx"}
        self.db.record_deal_alert(self.scheme_id, deal_key(offer), 2400, "24元")
        with patch("src.deal_pipeline.resolve_offer_product_url", AsyncMock(return_value=None)):
            self.assertEqual(await prepare_alerts(self.db, None, self.scheme_id, [offer]), [])

    async def test_one_alert_for_two_sources_and_restart_dedup(self):
        offers = [
            {"article_id": "manmanbuy:1", "article_title": "示例猫砂10kg", "article_price": "80元",
             "article_url": "https://cu.manmanbuy.com/discuxiao_1.aspx", "source": "manmanbuy", "db_id": 1},
            {"article_id": "smzdm:2", "article_title": "示例猫砂10kg", "article_price": "80元",
             "article_url": "https://www.smzdm.com/p/2/", "source": "smzdm", "db_id": 2},
        ]
        with patch("src.deal_pipeline.resolve_offer_product_url", AsyncMock(return_value=None)):
            first = await prepare_alerts(self.db, None, self.scheme_id, offers)
            self.assertEqual(len(first), 1)
            self.assertEqual(len(first[0]["group_offers"]), 2)
            self.db.save_deal_assessment(self.scheme_id, first[0])
            self.assertEqual(len(DatabaseManager(self.db.db_path).pending_deal_assessments(self.scheme_id)), 1)
            self.db.mark_deal_assessment_sent(self.scheme_id, first[0]["alert_key"])
            self.assertEqual(self.db.pending_deal_assessments(self.scheme_id), [])
            saved = self.db.list_deal_assessments(self.scheme_id)[0]
            self.assertEqual(saved["status"], "sent")
            self.assertEqual(len(saved["assessment"]["group_offers"]), 2)
            self.db.record_deal_alert(self.scheme_id, first[0]["alert_key"],
                                      first[0]["alert_price_cents"], first[0]["alert_terms"])
            self.assertEqual(await prepare_alerts(DatabaseManager(self.db.db_path), None,
                                                  self.scheme_id, offers), [])
            cheaper = [dict(offers[0], article_price="72元")]
            self.assertEqual(len(await prepare_alerts(self.db, None, self.scheme_id, cheaper)), 1)
            dearer = [dict(offers[0], article_price="85元")]
            self.assertEqual(await prepare_alerts(self.db, None, self.scheme_id, dearer), [])

    async def test_background_alert_does_not_query_history_or_model(self):
        offer = {"article_id": "manmanbuy:3", "article_title": "抽纸6包",
                 "article_price": "24元", "article_url": "https://cu.manmanbuy.com/discuxiao_3.aspx",
                 "comparison": {"conclusion": {"judgement": "better"}},
                 "history": {"lowest_price": "1"}}
        history = type("History", (), {"path": Path(self.tmp.name) / "missing.json",
                                        "query": AsyncMock(side_effect=AssertionError("history query"))})()
        with patch("src.deal_pipeline.resolve_offer_product_url",
                   AsyncMock(return_value="https://item.jd.com/5089253.html")):
            ready = await prepare_alerts(self.db, None, self.scheme_id, [offer], history)
        self.assertEqual(len(ready), 1)
        self.assertNotIn("comparison", ready[0])
        self.assertNotIn("history", ready[0])
        history.query.assert_not_awaited()

    async def test_coupon_jump_can_use_logged_in_article_item_link(self):
        class Response:
            def __init__(self, body=b"", status=200, location=""):
                self.status = status
                self.headers = {"content-type": "text/html", "Location": location}
                self.body = body
                self.content = self

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

            async def iter_chunked(self, _):
                middle = len(self.body) // 2
                yield self.body[:middle]
                yield self.body[middle:]

        class Public:
            def head(self, *_args, **_kwargs):
                return Response(status=302, location="http://www.manmanbuy.com/redirectUrl.aspx?tourl=https%3A%2F%2Fuland.taobao.com%2Fcoupon%2Fedetail")

            def get(self, *_args, **_kwargs):
                return Response(status=302, location="https://item.taobao.com/item.htm?id=12345678&spm=tracking")

        class Private:
            def get(self, *_args, **_kwargs):
                return Response(body=b'<script>var myurl = "http://uland.taobao.com/item/edetail?id=ABCdef012345&skuId=12345678";</script>')

        url = await resolve_offer_product_url(Public(),
            {"article_url": "https://cu.manmanbuy.com/discuxiao_591026226.aspx"}, Private())
        self.assertEqual(url, "https://uland.taobao.com/item/edetail?id=ABCdef012345&skuId=12345678")
        self.assertEqual(await resolve_merchant_item_url(Public(), url),
                         "https://item.taobao.com/item.htm?id=12345678")
        self.assertIsNone(await resolve_offer_product_url(Public(),
            {"article_url": "https://cu.manmanbuy.com/discuxiao_591026226.aspx"}))

        class JdPublic:
            def __init__(self):
                self.calls = 0

            def get(self, *_args, **_kwargs):
                self.calls += 1
                location = ("https://jingfen.jd.com/detail/abcdefghijklmnop.html"
                            if self.calls == 1 else "https://item.jd.com/5089253.html?tracking=private")
                return Response(status=302, location=location)

        self.assertEqual(await resolve_jd_affiliate(JdPublic(),
            "http://jingfen.jd.com/detail/abcdefghijklmnop.html"),
            "https://item.jd.com/5089253.html")

    async def test_saved_assessment_retries_after_failed_delivery(self):
        self.db.update_scheme(self.scheme_id, dingtalk_webhook="https://example.test/webhook")
        keyword_id = self.db.add_keyword(self.scheme_id, "测试")
        offer = {"article_id": "test-article", "article_title": "测试抽纸",
                 "article_price": "24元", "article_mall": "测试商城",
                 "article_url": "https://www.smzdm.com/p/12345/", "source": "smzdm"}
        offer["db_id"] = self.db.add_product(self.scheme_id, keyword_id, offer)
        offer.update(alert_key="title:测试抽纸:", alert_price_cents=2400,
                     alert_terms="24元", group_offers=[offer])
        self.db.save_deal_assessment(self.scheme_id, offer)
        monitor = SMZDMMonitor(self.db.db_path)
        monitor.running = True
        monitor.notifier.send_message = AsyncMock(side_effect=[False, True])
        pending = self.db.pending_deal_assessments(self.scheme_id)
        with patch("src.monitor.asyncio.sleep", AsyncMock()):
            await monitor.send_notifications(self.db.get_scheme(self.scheme_id), pending)
            self.assertEqual(len(self.db.pending_deal_assessments(self.scheme_id)), 1)
            await monitor.send_notifications(self.db.get_scheme(self.scheme_id),
                                             self.db.pending_deal_assessments(self.scheme_id))
        self.assertEqual(self.db.pending_deal_assessments(self.scheme_id), [])
        self.assertEqual(self.db.list_deal_assessments(self.scheme_id)[0]["status"], "sent")
        self.assertFalse(self.db.should_send_deal_alert(self.scheme_id, offer["alert_key"], 2400, "24元"))

    async def test_combined_notification_contains_history_purchase_and_source_evidence(self):
        self.db.update_scheme(self.scheme_id, dingtalk_webhook="https://example.test/webhook")
        offer = {"article_id": "manmanbuy:1", "article_title": "示例抽纸6包",
                 "article_price": "24元", "article_mall": "示例商城",
                 "article_url": "https://cu.manmanbuy.com/discuxiao_1.aspx",
                 "source": "manmanbuy", "alert_key": "item:test-paper:6",
                 "alert_price_cents": 2400, "alert_terms": "24元",
                 "history": {"has_history": True, "lowest_price": "22.00",
                             "lowest_date": "2026-09-01T00:00:00"},
                 "history_delta": "2.00",
                 "comparison": {"relation": "category", "owned_name": "已购抽纸",
                                "owned_unit": "张", "unit": "张", "confidence": "verified",
                                "calculated_price": {"total_price": "24.00",
                                                     "price_per_package": "4.0000",
                                                     "unit_price": "0.0400"},
                                "purchase": {"price_per_unit": "0.0500"},
                                "conclusion": {"judgement": "better", "note": "同类单位价格较低"}}}
        keyword_id = self.db.add_keyword(self.scheme_id, "示例抽纸")
        offer["db_id"] = self.db.add_product(self.scheme_id, keyword_id, offer)
        second = {"article_id": "smzdm:2", "article_title": "示例抽纸6包",
                  "article_price": "24元", "source": "smzdm",
                  "article_url": "https://www.smzdm.com/p/2/"}
        second["db_id"] = self.db.add_product(self.scheme_id, keyword_id, second)
        offer["group_offers"] = [offer, second]
        self.db.save_deal_assessment(self.scheme_id, offer)
        monitor = SMZDMMonitor(self.db.db_path)
        monitor.running = True
        monitor.notifier.send_message = AsyncMock(return_value=True)
        with patch("src.monitor.asyncio.sleep", AsyncMock()):
            await monitor.send_notifications(self.db.get_scheme(self.scheme_id),
                                             self.db.pending_deal_assessments(self.scheme_id))

        monitor.notifier.send_message.assert_awaited_once()
        message = monitor.notifier.send_message.call_args.kwargs["message"]
        for expected in ("慢慢买历史低价", "2026-09-01", "¥4.0000/包装",
                         "我买过（同类参考）", "¥0.0500/张", "合并来源**: 2 条报价",
                         "https://cu.manmanbuy.com/discuxiao_1.aspx",
                         "https://www.smzdm.com/p/2/"):
            self.assertIn(expected, message)
        self.assertEqual(self.db.pending_deal_assessments(self.scheme_id), [])
