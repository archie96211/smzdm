"""Automation contract and safety checks without live notifications."""
import os
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

_TEMP = tempfile.TemporaryDirectory()
os.environ.setdefault('SMZDM_DATA_DIR', _TEMP.name)
os.environ['AUTO_START_MONITOR'] = 'false'
os.environ['SMZDM_WECHAT_BRIDGE_ENABLED'] = 'false'
from fastapi.testclient import TestClient
from src import web_server as server
from src.database import DatabaseManager
from src.automation_api import install


class AutomationChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database = DatabaseManager(self.tmp.name + '/test.db')
        with self.database.connect() as conn:
            conn.execute('CREATE TABLE automation_requests (request_id TEXT PRIMARY KEY, digest TEXT, scheme_id INTEGER)')
        self.patches = [patch.object(server, 'db', self.database),
                        patch.object(server, '_sync_scheme_monitor_state', AsyncMock()),
                        patch.dict(os.environ, {'SMZDM_API_TOKEN': 'test-api-token', 'SMZDM_API_TOKEN_FILE': ''})]
        for p in self.patches: p.start()
        self.client = TestClient(server.app, client=('127.0.0.1', 12345))
        self.headers = {'Authorization': 'Bearer test-api-token', 'Idempotency-Key': 'test-request-1'}
        self.spec = {'name': 'Storage', 'keywords': [{'keyword': 'SSD 2TB', 'price_max': 800}], 'enabled': False}

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def create(self, **changes):
        return self.client.post('/api/v1/monitors', json={**self.spec, **changes}, headers=self.headers)

    def test_auth_and_transactional_idempotency(self):
        self.assertEqual(self.client.get('/api/v1/monitors').status_code, 401)
        first = self.create()
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()['monitor']['is_active'])
        self.assertEqual(first.json()['monitor']['keywords'][0]['price_max'], 800)
        again = self.create()
        self.assertFalse(again.json()['changed'])
        self.assertEqual(len(self.database.get_schemes()), 1)
        self.assertEqual(self.create(name='Different').status_code, 409)
        other_headers = {**self.headers, 'Idempotency-Key': 'test-request-2'}
        self.assertEqual(self.client.post('/api/v1/monitors', json=self.spec, headers=other_headers).status_code, 409)

    def test_validation_and_missing_bark_do_not_create(self):
        self.assertEqual(self.create(keywords=[{'keyword': 'x', 'price_min': 20, 'price_max': 10}]).status_code, 422)
        self.assertEqual(self.create(refresh_interval=1).status_code, 422)
        self.assertEqual(self.create(bark_enabled=True).status_code, 422)
        self.assertEqual(self.database.get_schemes(), [])

    def test_patch_preserves_fields_and_redacts(self):
        scheme_id = self.create().json()['monitor']['id']
        self.database.update_scheme(scheme_id, dingtalk_secret='private-secret')
        response = self.client.patch(f'/api/v1/monitors/{scheme_id}', json={'description': 'new'}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['refresh_interval'], 300)
        self.assertNotIn('private-secret', response.text)
        self.database.set_config('dingtalk_secret', 'private-global', '')
        self.client.patch('/api/v1/settings', json={'image_server_port': 19000}, headers=self.headers)
        self.assertEqual(self.database.get_global_settings()['dingtalk_secret']['value'], 'private-global')
        self.assertNotIn('private-global', self.client.get('/api/v1/settings', headers=self.headers).text)

    def test_keyword_add_replace_and_disabled_readback(self):
        scheme_id = self.create().json()['monitor']['id']
        path = f'/api/v1/monitors/{scheme_id}/keywords'
        body = {'keyword': 'NVMe', 'price_max': 700, 'is_active': False}
        first = self.client.post(path, json=body, headers=self.headers)
        self.assertEqual(first.status_code, 200, first.text)
        again = self.client.post(path, json=body, headers=self.headers)
        self.assertFalse(again.json()['changed'])
        detail = self.client.get(f'/api/v1/monitors/{scheme_id}', headers=self.headers).json()
        self.assertEqual(len(detail['keywords']), 2)
        self.assertFalse(detail['keywords'][1]['is_active'])
        result = self.client.put(f"/api/v1/keywords/{first.json()['id']}", json={**body, 'price_max': 600}, headers=self.headers)
        self.assertEqual(result.json()['keywords'][1]['price_max'], 600)

    def test_aggregated_source_round_trip(self):
        result = self.create(keywords=[{'keyword': '猫砂', 'source': 'both'}])
        self.assertEqual(result.status_code, 200, result.text)
        keyword = result.json()['monitor']['keywords'][0]
        self.assertEqual(keyword['source'], 'both')
        readback = self.client.get(f"/api/v1/monitors/{result.json()['monitor']['id']}", headers=self.headers)
        self.assertEqual(readback.json()['keywords'][0]['source'], 'both')
        self.assertEqual(self.create(keywords=[{'keyword': '猫砂', 'source': 'unknown'}]).status_code, 422)

    def test_private_purchase_read_requires_token(self):
        with self.database.connect() as conn:
            product = conn.execute("INSERT INTO owned_products (name, measure_unit, package_label) VALUES ('猫砂', 'kg', '袋')").lastrowid
            conn.execute("INSERT INTO purchases (product_id, paid_cents, package_count, units_per_package) VALUES (?, 9600, 4, '2.4')", (product,))
        self.assertEqual(self.client.get('/api/v1/purchases').status_code, 401)
        records = self.client.get('/api/v1/purchases', headers=self.headers).json()
        self.assertEqual(records[0]['price_per_unit'], '10')
        self.assertEqual(records[0]['product_name'], '猫砂')

    def test_private_purchase_pagination_and_exact_lookup(self):
        with self.database.connect() as conn:
            product = conn.execute("INSERT INTO owned_products (name, measure_unit, package_label) VALUES ('抽纸', '张', '包')").lastrowid
            conn.executemany("""INSERT INTO purchases
                (product_id, purchased_on, order_number, paid_cents, package_count, units_per_package)
                VALUES (?, '2026-01-01', ?, 100, 1, '100')""",
                [(product, 'shared-order' if index in (0, 1) else '') for index in range(205)])
        first = self.client.get('/api/v1/purchases', headers=self.headers).json()
        last = self.client.get('/api/v1/purchases?limit=200&offset=200', headers=self.headers).json()
        self.assertEqual((len(first), len(last)), (200, 5))
        self.assertFalse({item['id'] for item in first} & {item['id'] for item in last})
        self.assertEqual(self.client.get('/api/v1/purchases?limit=201', headers=self.headers).status_code, 422)
        record_id = last[-1]['id']
        self.assertEqual(self.client.get(f'/api/v1/purchases/{record_id}', headers=self.headers).json()['id'], record_id)
        self.assertEqual(self.client.get('/api/v1/purchases/99999', headers=self.headers).status_code, 404)
        self.assertEqual(self.client.post('/api/v1/purchases/search', headers=self.headers,
            json={'order_number': 'shared-order'}).status_code, 200)
        matches = self.client.post('/api/v1/purchases/search', headers=self.headers,
            json={'order_number': 'shared-order'}).json()
        self.assertEqual(len(matches), 2)
        self.assertEqual([item['id'] for item in matches], sorted(item['id'] for item in matches))
        self.assertEqual(self.client.post('/api/v1/purchases/search', headers=self.headers,
            json={'order_number': 'missing'}).json(), [])
        self.assertEqual(self.client.post('/api/v1/purchases/search', json={
            'order_number': 'shared-order'}).status_code, 401)

    def test_private_purchase_management(self):
        self.assertEqual(self.client.post('/api/v1/owned-products', json={
            'name': '罐头', 'measure_unit': 'g', 'package_label': '罐'}).status_code, 401)
        product = self.client.post('/api/v1/owned-products', headers=self.headers, json={
            'name': '罐头', 'measure_unit': 'g', 'package_label': '罐'}).json()
        self.assertEqual(self.client.get('/api/v1/owned-products', headers=self.headers).json()[0]['name'], '罐头')
        record = self.client.post('/api/v1/purchases', headers=self.headers, json={
            'product_id': product['id'], 'paid_amount': '48', 'package_count': 6,
            'units_per_package': '85', 'variant': '鸡肉味', 'purchase_channel': 'jd',
            'order_number': 'JD-ORDER-1', 'store': '自营店'}).json()
        self.assertEqual(record['total_units'], '510')
        self.assertEqual(record['purchase_channel'], 'jd')
        self.assertEqual(record['order_number'], 'JD-ORDER-1')
        self.assertIsNone(record['price_per_inner_package'])
        self.assertEqual(self.client.put(f"/api/v1/owned-products/{product['id']}", headers=self.headers,
            json={'name': '猫罐头', 'measure_unit': 'kg', 'package_label': '罐'}).status_code, 409)
        updated = self.client.put(f"/api/v1/purchases/{record['id']}", headers=self.headers, json={
            'product_id': product['id'], 'paid_amount': '42', 'package_count': 6,
            'units_per_package': '85', 'variant': '鸡肉味'}).json()
        self.assertEqual(updated['paid_amount'], '42')
        self.assertEqual(updated['purchase_channel'], 'jd')
        self.assertEqual(updated['order_number'], 'JD-ORDER-1')
        self.assertEqual(self.client.delete(f"/api/v1/purchases/{record['id']}", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/v1/owned-products/{product['id']}", headers=self.headers).status_code, 200)

    def test_deal_context_is_authenticated_cached_and_excludes_purchase_notes(self):
        item_url = 'https://item.jd.com/5089253.html'
        with self.database.connect() as conn:
            product = conn.execute("INSERT INTO owned_products (name, measure_unit, package_label) VALUES ('猫砂', 'kg', '袋')").lastrowid
            conn.execute("INSERT INTO owned_product_links (product_id, product_url, variant) VALUES (?, ?, '')",
                         (product, item_url))
            conn.execute("""INSERT INTO purchases
                (product_id, paid_cents, package_count, units_per_package, store, note, order_number)
                VALUES (?, 9600, 4, '2.4', 'private store', 'private note', 'private-order-123')""", (product,))
        session_path = Path(self.tmp.name) / 'session.json'
        session_path.touch()
        history = {"source": "manmanbuy", "queried_at": 100, "has_history": True,
                   "product_name": "猫砂", "lowest_price": "90", "lowest_date": "2026-09-01",
                   "average_60_days": "100"}
        connection = type("Connection", (), {"path": session_path, "lock": asyncio.Lock(),
                     "query": AsyncMock(return_value=history)})()
        with patch.object(server, 'manmanbuy_connection', connection):
            self.assertEqual(self.client.post('/api/v1/deal-context', json={'url': item_url}).status_code, 401)
            first = self.client.post('/api/v1/deal-context', headers=self.headers,
                json={'url': item_url, 'title': '猫砂 4袋', 'advertised_price': '80元'})
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()['history']['status'], 'queried')
            self.assertEqual(first.json()['owned_candidates'][0]['recent_purchases'][0]['price_per_unit'], '10')
            self.assertNotIn('private store', first.text)
            self.assertNotIn('private note', first.text)
            self.assertNotIn('private-order-123', first.text)
            second = self.client.post('/api/v1/deal-context', headers=self.headers,
                json={'url': item_url, 'title': '猫砂 4袋'})
            self.assertEqual(second.json()['history']['status'], 'cached')
            connection.query.assert_awaited_once()

    def test_deal_context_rejects_unknown_and_coupon_urls(self):
        for url in ('http://127.0.0.1/private', 'https://uland.taobao.com/coupon/edetail?id=1',
                    'https://example.com/item/1', 'https://cu.manmanbuy.com/discuxiao_1.aspx?x=1#fragment'):
            response = self.client.post('/api/v1/deal-context', headers=self.headers, json={'url': url})
            self.assertEqual(response.status_code, 422, response.text)

    def test_title_only_context_has_no_claimed_history(self):
        with self.database.connect() as conn:
            conn.execute("INSERT INTO owned_products (name, measure_unit, package_label) VALUES ('抽纸', '张', '包')")
        response = self.client.post('/api/v1/deal-context', headers=self.headers,
                                    json={'title': '抽纸6包', 'advertised_price': '24元'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['history']['status'], 'item_unconfirmed')
        self.assertIsNone(response.json()['product_url'])
        self.assertEqual(response.json()['owned_candidates'][0]['name'], '抽纸')

    def test_price_verification_uses_source_quotes(self):
        request = {'title': '抽纸6包', 'advertised_price': '标价30元，满30减6元',
                   'expression': {'base_price': {'value': 30, 'evidence': '标价30元'},
                                  'discounts': [{'value': 6, 'evidence': '满30减6元'}],
                                  'package_count': {'value': 6, 'evidence': '6包'}}}
        result = self.client.post('/api/v1/verify-price', headers=self.headers, json=request)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['calculation']['price_per_package'], '4.0000')
        request['expression']['discounts'][0]['evidence'] = '满30减8元'
        self.assertFalse(self.client.post('/api/v1/verify-price', headers=self.headers,
                                          json=request).json()['verified'])


if __name__ == '__main__': unittest.main()
