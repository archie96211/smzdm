"""Discount-source parsing and monitoring contracts; no external requests."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.manmanbuy_deals import DealParser
from src.monitor import SMZDMMonitor


CARD = '''<div class="DiscountItemPC_box__sample"><div>
<a href="https://cu.manmanbuy.com/discuxiao_123.aspx"><img src="https://example.org/item.jpg"/></a>
<div class="DiscountItemPC_itemTitle__sample"><a>猫砂 2.4kg</a></div>
<div class="DiscountItemPC_itemSubTitle__sample"><a>18.5元</a></div>
<span class="DiscountItemPC_itemTime__sample">09-23 10:00</span>
<span class="DiscountItemPC_itemMall__sample">京东自营</span>
</div></div>'''


class ParserChecks(unittest.TestCase):
    def test_normalized_card_and_rejected_external_link(self):
        parser = DealParser()
        parser.feed(CARD + CARD.replace("cu.manmanbuy.com", "evil.example"))
        self.assertEqual(len(parser.deals), 1)
        self.assertEqual(parser.deals[0]["article_id"], "manmanbuy:123")
        self.assertEqual(parser.deals[0]["article_price"], "18.5元")


class MonitorChecks(unittest.IsolatedAsyncioTestCase):
    async def test_new_source_baselines_existing_keyword_then_only_new_deal_notifies(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = SMZDMMonitor(str(Path(directory) / "test.db"))
            scheme_id = monitor.db.create_scheme("source-test")
            keyword_id = monitor.db.add_keyword(scheme_id, "猫砂", source="manmanbuy")
            keyword = monitor.db.get_keywords(scheme_id)[0]
            row = {"article_id": "manmanbuy:123", "article_title": "猫砂 2.4kg",
                   "article_price": "18.5元", "article_url": "https://cu.manmanbuy.com/discuxiao_123.aspx",
                   "article_mall": "京东自营", "source": "manmanbuy"}
            with patch("src.monitor.fetch_manmanbuy_deals", new_callable=AsyncMock) as fetch:
                fetch.return_value = [row.copy()]
                self.assertEqual(await monitor.monitor_keyword(None, scheme_id, keyword), [])
                self.assertEqual(len(monitor.db.get_recent_products(scheme_id)), 1)
                fetch.return_value = [row.copy(), dict(row, article_id="manmanbuy:124")]
                fresh = await monitor.monitor_keyword(None, scheme_id, keyword)
                self.assertEqual([item["article_id"] for item in fresh], ["manmanbuy:124"])
                self.assertEqual(await monitor.monitor_keyword(None, scheme_id, keyword), [])
