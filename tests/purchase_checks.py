"""Purchase arithmetic and durable price-history contracts."""

import tempfile
import unittest
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.database import DatabaseManager
from src.purchase_ledger import install
from src.deal_groups import group_offers


class PurchaseChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "ledger.db")
        self.db = DatabaseManager(self.db_path)
        app = FastAPI()
        install(app, self.db)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def test_purchase_units_and_restart(self):
        litter = self.client.post("/api/purchase/products", json={
            "name": "常用猫砂", "measure_unit": "kg", "package_label": "袋"}).json()
        result = self.client.post("/api/purchase/records", json={
            "product_id": litter["id"], "paid_amount": "96", "package_count": 4,
            "units_per_package": "2.4", "purchased_on": "2026-09-20",
            "purchase_channel": "jd", "order_number": "JD-20260920-1", "store": "京东自营"})
        self.assertEqual(result.status_code, 200, result.text)
        record = result.json()["purchases"][0]
        self.assertEqual((record["price_per_package"], record["total_units"], record["price_per_unit"]),
                         ("24", "9.6", "10"))
        self.assertEqual((record["purchase_channel"], record["store"]), ("jd", "京东自营"))
        self.assertEqual(record["order_number"], "JD-20260920-1")
        self.assertEqual(DatabaseManager(self.db_path).db_path, self.db_path)
        self.assertEqual(self.client.get(f"/api/purchase/products/{litter['id']}").json()["purchase_count"], 1)
        changed = self.client.put(f"/api/purchase/records/{record['id']}", json={
            "product_id": litter["id"], "paid_amount": "90", "package_count": 4,
            "units_per_package": "2.4", "store": "京东自营"}).json()["purchases"][0]
        self.assertEqual(changed["purchase_channel"], "jd")
        self.assertEqual(changed["order_number"], "JD-20260920-1")
        self.assertEqual(self.client.post("/api/purchase/records", json={
            "product_id": litter["id"], "paid_amount": "1", "package_count": 1,
            "units_per_package": "1", "purchase_channel": "unknown"}).status_code, 422)

        tissue = self.client.post("/api/purchase/products", json={
            "name": "抽纸", "measure_unit": "张", "package_label": "包"}).json()
        tissue_result = self.client.post("/api/purchase/records", json={
            "product_id": tissue["id"], "paid_amount": "24", "package_count": 6,
            "units_per_package": "100"}).json()
        self.assertEqual(tissue_result["purchases"][0]["price_per_unit"], "0.04")
        self.assertEqual(self.client.post("/api/purchase/records", json={
            "product_id": tissue["id"], "paid_amount": "1.001", "package_count": 1,
            "units_per_package": "1"}).status_code, 422)

    def test_deal_price_change_and_history_query_are_saved(self):
        scheme_id = self.db.create_scheme("prices")
        keyword_id = self.db.add_keyword(scheme_id, "猫砂")
        deal = {"article_id": "deal-1", "article_title": "猫砂", "article_price": "80元"}
        product_id = self.db.add_product(scheme_id, keyword_id, deal)
        self.assertIsNone(self.db.add_product(scheme_id, keyword_id, deal))
        self.db.add_product(scheme_id, keyword_id, dict(deal, article_price="72元"))
        self.db.add_product(scheme_id, keyword_id, dict(deal, article_price="56元+7元淘金币"))
        events = self.client.get(f"/api/purchase/offer-observations/{product_id}").json()
        self.assertEqual([event["price_cents"] for event in events], [None, 7200, 8000])
        self.db.record_historical_price_check("https://item.jd.com/5089253.html?private=unused", {
            "source": "manmanbuy", "has_history": True, "lowest_price": 69,
            "lowest_date": "2026-09-01", "average_60_days": 80, "product_name": "猫砂"})
        checks = self.client.get("/api/purchase/price-checks").json()
        self.assertEqual(checks[0]["product_url"], "https://item.jd.com/5089253.html")

    def test_owned_product_link_is_canonical_and_unique(self):
        product = self.client.post("/api/purchase/products", json={
            "name": "示例抽纸", "measure_unit": "张", "package_label": "包"}).json()
        linked = self.client.post(f"/api/purchase/products/{product['id']}/links", json={
            "product_url": "https://item.taobao.com/item.htm?id=12345678&spm=private", "variant": "S号"})
        self.assertEqual(linked.status_code, 200, linked.text)
        link = linked.json()["links"][0]
        self.assertEqual(link["product_url"], "https://item.taobao.com/item.htm?id=12345678")
        self.assertEqual(self.client.post(f"/api/purchase/products/{product['id']}/links", json={
            "product_url": "https://item.taobao.com/item.htm?id=12345678"}).status_code, 409)
        self.assertEqual(self.client.post(f"/api/purchase/products/{product['id']}/links", json={
            "product_url": "https://uland.taobao.com/coupon/edetail"}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/purchase/products/{product['id']}/links", json={
            "product_url": "https://item.jd.com:bad/5089253.html"}).status_code, 422)
        self.assertEqual(self.client.delete(f"/api/purchase/products/{product['id']}/links/{link['id']}").status_code, 200)

    def test_purchase_variant_edit_and_delete(self):
        product = self.client.post("/api/purchase/products", json={
            "name": "纸巾", "measure_unit": "张", "package_label": "包"}).json()
        record = self.client.post("/api/purchase/records", json={
            "product_id": product["id"], "paid_amount": "30", "package_count": 5,
            "units_per_package": "100", "variant": "S 号"}).json()["purchases"][0]
        self.client.post("/api/purchase/records", json={
            "product_id": product["id"], "paid_amount": "42", "package_count": 5,
            "units_per_package": "200", "variant": "L 号"})
        detail = self.client.get(f"/api/purchase/products/{product['id']}").json()
        self.assertEqual({item["variant"] for item in detail["variant_summaries"]}, {"S 号", "L 号"})
        self.assertIsNone(detail["weighted_price_per_unit"])
        self.assertEqual(self.client.delete(f"/api/purchase/products/{product['id']}").status_code, 409)
        self.assertEqual(self.client.put(f"/api/purchase/products/{product['id']}", json={
            "name": "抽纸", "measure_unit": "kg", "package_label": "包"}).status_code, 409)
        changed = self.client.put(f"/api/purchase/records/{record['id']}", json={
            "product_id": product["id"], "paid_amount": "24", "package_count": 4,
            "units_per_package": "100", "variant": "S 号"}).json()
        self.assertEqual(changed["purchases"][1]["price_per_unit"], "0.06")
        self.assertEqual(self.client.delete(f"/api/purchase/records/{record['id']}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/purchase/records/{record['id']}").status_code, 404)

        box = self.client.post("/api/purchase/products", json={
            "name": "箱装猫砂", "measure_unit": "kg", "package_label": "箱"}).json()
        boxed = self.client.post("/api/purchase/records", json={
            "product_id": box["id"], "paid_amount": "96", "package_count": 1,
            "units_per_package": "9.6", "inner_package_count": 4,
            "inner_package_label": "袋", "variant": "白茶"}).json()["purchases"][0]
        self.assertEqual((boxed["price_per_package"], boxed["price_per_inner_package"], boxed["price_per_unit"]),
                         ("96", "24", "10"))
        self.assertEqual(self.client.post("/api/purchase/records", json={
            "product_id": box["id"], "paid_amount": "96", "package_count": 1,
            "units_per_package": "9.6", "inner_package_count": 4}).status_code, 422)

    def test_offer_grouping_preserves_sources_and_sizes(self):
        rows = [
            {"id": 1, "article_id": "123", "article_title": "维达 抽纸 S号 100抽 6包", "article_price": "20元"},
            {"id": 2, "article_id": "manmanbuy:456", "article_title": "维达抽纸S号100抽6包", "article_price": "18元"},
            {"id": 3, "article_id": "manmanbuy:789", "article_title": "维达抽纸M号100抽6包", "article_price": "17元"},
            {"id": 4, "article_id": "manmanbuy:790", "article_title": "维达抽纸S号200抽6包", "article_price": "17元"},
        ]
        groups = group_offers(rows)
        self.assertEqual([len(group["offers"]) for group in groups], [2, 1, 1])
        self.assertEqual(groups[0]["sources"], ["smzdm", "manmanbuy"])
        long_title = {"article_title": "简芯白茶混合猫砂去味速结团 白茶混合豆腐砂 2.4kg*1 植物原料 销量TOP1"}
        short_title = {"article_title": "简芯 白茶混合豆腐砂 2.4kg*1 植物原料"}
        from src.deal_groups import same_product
        self.assertTrue(same_product(long_title, short_title))
        self.assertFalse(same_product(long_title, {"article_title": "简芯 白茶混合豆腐砂 2.4kg*4 植物原料"}))

    def test_existing_database_gets_empty_channel_without_guessing(self):
        legacy_path = str(Path(self.tmp.name) / "legacy.db")
        with sqlite3.connect(legacy_path) as conn:
            conn.execute("""CREATE TABLE purchases (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL,
                purchased_on DATE, store TEXT NOT NULL DEFAULT '', paid_cents INTEGER NOT NULL,
                package_count INTEGER NOT NULL, units_per_package TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            conn.execute("INSERT INTO purchases (product_id, store, paid_cents, package_count, units_per_package) VALUES (1, '旧店铺', 100, 1, '1')")
        upgraded = DatabaseManager(legacy_path)
        with upgraded.connect() as conn:
            self.assertEqual(conn.execute("SELECT store, purchase_channel, order_number FROM purchases").fetchone(), ("旧店铺", "", ""))


if __name__ == "__main__":
    unittest.main()
