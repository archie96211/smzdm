"""Authenticated, transactional management API for external automation."""
import hashlib
import hmac
import json
import os
import sqlite3
import asyncio
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlsplit

import aiohttp

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .purchase_ledger import OwnedProduct, ProductLink, Purchase, present_purchase
from .merchant_links import MMB_ARTICLE, SMZDM_ARTICLE, canonical_product_url
from .merchant_links import resolve_merchant_item_url, resolve_offer_product_url
from .deal_comparison import calculate_verified_price, candidate_products
from .deal_pipeline import owned_summaries


class Keyword(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    keyword: str = Field(min_length=1, max_length=200)
    source: Literal["smzdm", "manmanbuy", "both"] = "smzdm"
    category_id: str = ""
    brand_id: str = ""
    mall_id: str = ""
    order_type: Literal["time", "price_asc", "price_desc", "rating"] = "time"
    price_min: float = Field(default=0, ge=0, allow_inf_nan=False)
    price_max: float = Field(default=999999, ge=0, allow_inf_nan=False)
    is_active: bool = True

    @model_validator(mode="after")
    def prices(self):
        if self.price_min > self.price_max:
            raise ValueError("price_min must not exceed price_max")
        return self


class MonitorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    refresh_interval: int = Field(default=300, ge=60, le=86400)
    enabled: bool = False
    bark_enabled: bool = False
    keywords: list[Keyword] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_keywords(self):
        keys = [json.dumps(k.model_dump(), sort_keys=True) for k in self.keywords]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate keyword rules")
        return self


class MonitorPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    refresh_interval: Optional[int] = Field(default=None, ge=60, le=86400)
    bark_enabled: Optional[bool] = None
    enabled: Optional[bool] = None


class DealContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    url: str = Field(default="", max_length=2048)
    title: str = Field(default="", max_length=200)
    advertised_price: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def has_identity(self):
        if not self.url and not self.title:
            raise ValueError("Provide a deal URL or title")
        return self


class PriceVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(default="", max_length=200)
    advertised_price: str = Field(default="", max_length=200)
    price_details: str = Field(default="", max_length=400)
    real_price_title: str = Field(default="", max_length=200)
    expression: dict


SENSITIVE = {"device_key", "encryption_key", "bark_config", "push_url", "dingtalk_webhook",
             "dingtalk_secret", "wxpusher_app_token", "wxpusher_uid", "wechat_targets",
             "wechat_account_id", "raw_data"}


def redact(value):
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {key: (bool(item) if key in SENSITIVE else redact(item))
                for key, item in value.items()}
    return value


def install(app, host):
    """Reuse the service's scheduler and notification implementations."""
    def authorize(authorization: str = Header(default="")):
        token = os.getenv("SMZDM_API_TOKEN", "")
        path = os.getenv("SMZDM_API_TOKEN_FILE")
        if path:
            try:
                token = Path(path).read_text().strip()
            except OSError:
                token = ""
        if not token:
            raise HTTPException(503, "Automation API token is not configured")
        if not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(401, "Invalid API credentials")

    router = APIRouter(prefix="/api/v1", dependencies=[Depends(authorize)])
    with host.db.connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS automation_requests (
            request_id TEXT PRIMARY KEY, digest TEXT NOT NULL, scheme_id INTEGER NOT NULL)""")

    def detail(scheme_id):
        item = host.db.get_scheme(scheme_id)
        if item is None:
            raise HTTPException(404, "Monitor not found")
        with host.db.connect() as conn:
            conn.row_factory = sqlite3.Row
            item["keywords"] = [dict(r) for r in conn.execute("SELECT * FROM keywords WHERE scheme_id=?", (scheme_id,))]
        item["task_running"] = scheme_id in host.monitor.tasks and not host.monitor.tasks[scheme_id].done()
        item["notification_stats"] = host.db.get_notification_stats(scheme_id)
        return redact(item)

    @router.get("/capabilities")
    async def capabilities():
        return {"api_version": "1", "minimum_interval": 60,
                "features": ["atomic_create", "idempotency", "patch", "bark", "keywords", "products", "deliveries", "manmanbuy_deals", "purchase_ledger", "purchase_management", "purchase_channels", "purchase_order_numbers", "purchase_pagination", "purchase_exact_lookup", "offer_groups", "saved_price_checks", "on_demand_deal_context", "price_verification"],
                "purchase_channels": ["jd", "taobao", "tmall", "pdd", "douyin", "wechat", "offline", "other"],
                "background_model_calls": False,
                "metadata_lookup": False, "preview": False,
                "first_run": "baseline_only", "monitor_schema": MonitorSpec.model_json_schema()}

    @router.get("/status")
    async def status():
        return {"monitor": host.monitor.get_status(), "fetch": host.monitor.fetch_metrics}

    @router.get("/monitors")
    async def monitors():
        return [detail(item["id"]) for item in host.db.get_schemes()]

    @router.get("/monitors/{scheme_id}")
    async def get_monitor(scheme_id: int):
        return detail(scheme_id)

    @router.post("/monitors")
    async def create(spec: MonitorSpec, idempotency_key: str = Header(min_length=8, max_length=128)):
        digest = hashlib.sha256(spec.model_dump_json().encode()).hexdigest()
        reused = False
        try:
            with host.db.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                old = conn.execute("SELECT digest, scheme_id FROM automation_requests WHERE request_id=?", (idempotency_key,)).fetchone()
                if old:
                    if old[0] != digest:
                        raise HTTPException(409, "Idempotency key already used with a different request")
                    scheme_id = old[1]
                    reused = True
                else:
                    if spec.bark_enabled and not host.db.get_bark_config().get("device_key"):
                        raise HTTPException(422, "Configure Bark before enabling notifications")
                    cur = conn.execute("""INSERT INTO monitor_schemes
                        (name, description, refresh_interval, is_active, bark_enabled)
                        VALUES (?, ?, ?, ?, ?)""", (spec.name, spec.description, spec.refresh_interval, int(spec.enabled), int(spec.bark_enabled)))
                    scheme_id = cur.lastrowid
                    for kw in spec.keywords:
                        conn.execute("""INSERT INTO keywords (scheme_id, keyword, source, category_id, brand_id,
                            mall_id, order_type, price_min, price_max, is_active)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (scheme_id, *kw.model_dump().values()))
                    conn.execute("INSERT INTO automation_requests VALUES (?, ?, ?)", (idempotency_key, digest, scheme_id))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Monitor name already exists") from None
        detail(scheme_id)
        if not reused:
            await host._sync_scheme_monitor_state(scheme_id, {"is_active": spec.enabled})
        return {"changed": not reused, "monitor": detail(scheme_id)}

    @router.patch("/monitors/{scheme_id}")
    async def patch_monitor(scheme_id: int, patch: MonitorPatch):
        detail(scheme_id)
        data = patch.model_dump(exclude_none=True)
        if "enabled" in data:
            data["is_active"] = data.pop("enabled")
        if data.get("bark_enabled") and not host.db.get_bark_config(scheme_id).get("device_key"):
            raise HTTPException(422, "Configure Bark before enabling notifications")
        try:
            host.db.update_scheme(scheme_id, **data)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Monitor name already exists") from None
        if data:
            await host._sync_scheme_monitor_state(scheme_id, data)
        return detail(scheme_id)

    @router.delete("/monitors/{scheme_id}")
    async def delete(scheme_id: int):
        detail(scheme_id)
        return await host.delete_scheme(scheme_id)

    @router.post("/monitors/{scheme_id}/refresh")
    async def refresh(scheme_id: int):
        if not detail(scheme_id)["is_active"]:
            raise HTTPException(409, "Enable the monitor first")
        return await host.restart_scheme_monitor(scheme_id)

    @router.post("/monitors/{scheme_id}/keywords")
    async def add_keyword(scheme_id: int, keyword: Keyword):
        detail(scheme_id)
        existing = detail(scheme_id)["keywords"]
        for item in existing:
            if all(item.get(k) == v for k, v in keyword.model_dump().items()):
                return {"changed": False, "id": item["id"]}
        data = keyword.model_dump()
        with host.db.connect() as conn:
            cur = conn.execute("""INSERT INTO keywords (scheme_id, keyword, source, category_id, brand_id,
                mall_id, order_type, price_min, price_max, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (scheme_id, *data.values()))
            key_id = cur.lastrowid
        await host._sync_scheme_monitor_state(scheme_id, {})
        return {"changed": True, "id": key_id}

    @router.put("/keywords/{keyword_id}")
    async def set_keyword(keyword_id: int, keyword: Keyword):
        with host.db.connect() as conn:
            row = conn.execute("SELECT scheme_id FROM keywords WHERE id=?", (keyword_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Keyword not found")
        host.db.update_keyword(keyword_id, **keyword.model_dump())
        await host._sync_scheme_monitor_state(row[0], {})
        return detail(row[0])

    @router.delete("/keywords/{keyword_id}")
    async def delete_keyword(keyword_id: int):
        return await host.delete_keyword(keyword_id)

    @router.get("/monitors/{scheme_id}/products")
    async def products(scheme_id: int, limit: int = Query(default=30, ge=1, le=100)):
        detail(scheme_id)
        return redact(host.db.get_recent_products(scheme_id, limit))

    @router.get("/monitors/{scheme_id}/product-groups")
    async def product_groups(scheme_id: int, limit: int = Query(default=50, ge=1, le=100)):
        from .deal_groups import group_offers
        detail(scheme_id)
        return redact(group_offers(host.db.get_recent_products(scheme_id, limit)))

    @router.post("/deal-context")
    async def deal_context(request: DealContextRequest):
        """Resolve one user-selected deal and return evidence without calling a model."""
        direct = canonical_product_url(request.url) if request.url else None
        article_host = ""
        if not request.url:
            source_url = ""
        elif direct:
            source_url = direct
        else:
            try:
                parts = urlsplit(request.url)
                valid = parts.scheme == "https" and not (parts.username or parts.password or parts.port or parts.fragment)
            except ValueError:
                valid = False
            if not valid or not ((parts.hostname == "cu.manmanbuy.com" and MMB_ARTICLE.fullmatch(parts.path)) or
                                 (parts.hostname == "www.smzdm.com" and SMZDM_ARTICLE.fullmatch(parts.path))):
                raise HTTPException(422, "Use a supported deal article or merchant item URL")
            source_url = f"https://{parts.hostname}{parts.path}"
            article_host = parts.hostname

        with host.db.connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""SELECT article_id, article_title, article_price, article_mall, raw_data
                FROM product_history WHERE article_url=? ORDER BY id DESC LIMIT 1""", (source_url,)).fetchone()
        saved = dict(row) if row else {}
        try:
            raw = json.loads(saved.get("raw_data") or "{}")
        except (ValueError, TypeError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        title = request.title or saved.get("article_title") or ""
        advertised_price = request.advertised_price or saved.get("article_price") or ""
        offer = {"article_url": source_url, "article_title": title,
                 "article_price": advertised_price}
        connection = host.manmanbuy_connection
        private_session = None
        if article_host == "cu.manmanbuy.com" and connection.path.exists():
            try:
                private_session = await connection.get_client()
            except (aiohttp.ClientError, OSError):
                pass
        product_url = direct
        merchant_item_url = direct
        if source_url:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                    product_url = direct or await resolve_offer_product_url(session, offer, private_session)
                    merchant_item_url = (await resolve_merchant_item_url(session, product_url)) if product_url else None
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                product_url = direct
                merchant_item_url = direct

        history = {"status": "item_unconfirmed", "data": None}
        if product_url:
            cached = host.db.recent_historical_price(product_url)
            if cached:
                history = {"status": "cached", "data": cached}
            elif not connection.path.exists():
                history = {"status": "login_required", "data": None}
            else:
                try:
                    async with connection.lock:
                        result = await connection.query(product_url)
                    host.db.record_historical_price_check(product_url, result)
                    history = {"status": "queried", "data": result}
                except HTTPException as exc:
                    history = {"status": "login_required" if exc.status_code == 409 else "unavailable",
                               "data": None}
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    history = {"status": "unavailable", "data": None}

        candidates = candidate_products({"article_title": title, "product_url": product_url,
                                         "merchant_item_url": merchant_item_url}, owned_summaries(host.db))
        owned = [{"id": item["id"], "name": item["name"], "measure_unit": item["measure_unit"],
                  "package_label": item["package_label"],
                  "variants": [variant["variant"] for variant in item["variant_summaries"]],
                  "recent_purchases": [{key: purchase.get(key) for key in
                      ("variant", "purchased_on", "purchase_channel", "paid_amount", "package_count", "units_per_package",
                       "inner_package_count", "inner_package_label", "price_per_package",
                       "price_per_inner_package", "price_per_unit")}
                      for purchase in item["purchases"]]}
                 for item in candidates]
        return {"source_url": source_url, "title": title, "advertised_price": advertised_price,
                "price_details": str(raw.get("article_subtitle") or "")[:400],
                "real_price_title": str(raw.get("real_price_title") or "")[:200],
                "mall": saved.get("article_mall") or "", "product_url": product_url,
                "merchant_item_url": merchant_item_url, "history": history,
                "owned_candidates": owned}

    @router.post("/verify-price")
    async def verify_price(request: PriceVerificationRequest):
        """Verify model-selected quoted operands and calculate with Decimal locally."""
        offer = {"article_title": request.title, "article_price": request.advertised_price,
                 "article_subtitle": request.price_details, "real_price_title": request.real_price_title}
        calculation = calculate_verified_price(offer, request.expression)
        return {"verified": calculation is not None, "calculation": calculation}

    @router.get("/monitors/{scheme_id}/deliveries")
    async def deliveries(scheme_id: int, limit: int = Query(default=30, ge=1, le=100)):
        detail(scheme_id)
        with host.db.connect() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT id, product_id, notification_type, status, sent_at FROM notification_logs WHERE scheme_id=? ORDER BY id DESC LIMIT ?", (scheme_id, limit))]

    @router.get("/monitors/{scheme_id}/assessments")
    async def assessments(scheme_id: int, limit: int = Query(default=30, ge=1, le=100)):
        detail(scheme_id)
        return host.db.list_deal_assessments(scheme_id, limit)

    @router.get("/purchases")
    async def purchases(limit: int = Query(default=200, ge=1, le=200),
                        offset: int = Query(default=0, ge=0)):
        """Page through the user's own purchases in stable date and ID order."""
        from .purchase_ledger import present_purchase
        with host.db.connect() as conn:
            conn.row_factory = sqlite3.Row
            return [present_purchase(row) for row in conn.execute('''
                SELECT p.*, o.name AS product_name, o.measure_unit, o.package_label
                FROM purchases p JOIN owned_products o ON o.id = p.product_id
                ORDER BY p.purchased_on DESC, p.id DESC LIMIT ? OFFSET ?
            ''', (limit, offset))]

    @router.get("/purchases/{record_id}")
    async def get_purchase(record_id: int):
        from .purchase_ledger import present_purchase
        with host.db.connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('''
                SELECT p.*, o.name AS product_name, o.measure_unit, o.package_label
                FROM purchases p JOIN owned_products o ON o.id = p.product_id
                WHERE p.id = ?
            ''', (record_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "Purchase not found")
            return present_purchase(row)

    class PurchaseOrderSearch(BaseModel):
        order_number: str = Field(min_length=1, max_length=120)

    @router.post("/purchases/search")
    async def search_purchases(data: PurchaseOrderSearch):
        """Find every item of one order without putting its number in a URL."""
        from .purchase_ledger import present_purchase
        order_number = data.order_number.strip()
        if not order_number:
            raise HTTPException(422, "Order number is required")
        with host.db.connect() as conn:
            conn.row_factory = sqlite3.Row
            return [present_purchase(row) for row in conn.execute('''
                SELECT p.*, o.name AS product_name, o.measure_unit, o.package_label
                FROM purchases p JOIN owned_products o ON o.id = p.product_id
                WHERE p.order_number = ? ORDER BY p.id
            ''', (order_number,))]

    @router.get("/owned-products")
    async def owned_products():
        with host.db.connect() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(
                "SELECT * FROM owned_products ORDER BY name")]

    @router.post("/owned-products")
    async def create_owned_product(data: OwnedProduct):
        values = (data.name.strip(), data.measure_unit.strip(), data.package_label.strip())
        if not all(values):
            raise HTTPException(422, "Product name and units are required")
        try:
            with host.db.connect() as conn:
                cursor = conn.execute("INSERT INTO owned_products (name, measure_unit, package_label) VALUES (?, ?, ?)", values)
                return {"id": cursor.lastrowid, "name": values[0], "measure_unit": values[1], "package_label": values[2]}
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Product already exists") from None

    @router.put("/owned-products/{product_id}")
    async def update_owned_product(product_id: int, data: OwnedProduct):
        values = (data.name.strip(), data.measure_unit.strip(), data.package_label.strip())
        if not all(values):
            raise HTTPException(422, "Product name and units are required")
        try:
            with host.db.connect() as conn:
                old = conn.execute("SELECT measure_unit, package_label FROM owned_products WHERE id=?", (product_id,)).fetchone()
                if old is None:
                    raise HTTPException(404, "Product not found")
                if (old[0], old[1]) != values[1:] and conn.execute(
                    "SELECT 1 FROM purchases WHERE product_id=? LIMIT 1", (product_id,)).fetchone():
                    raise HTTPException(409, "Cannot change units after purchases exist")
                cursor = conn.execute("UPDATE owned_products SET name=?, measure_unit=?, package_label=? WHERE id=?", (*values, product_id))
                if not cursor.rowcount:
                    raise HTTPException(404, "Product not found")
                return {"id": product_id, "name": values[0], "measure_unit": values[1], "package_label": values[2]}
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Product already exists") from None

    @router.delete("/owned-products/{product_id}")
    async def delete_owned_product(product_id: int):
        with host.db.connect() as conn:
            if conn.execute("SELECT 1 FROM purchases WHERE product_id=? LIMIT 1", (product_id,)).fetchone():
                raise HTTPException(409, "Delete purchase records first")
            cursor = conn.execute("DELETE FROM owned_products WHERE id=?", (product_id,))
            if not cursor.rowcount:
                raise HTTPException(404, "Product not found")
            return {"deleted": True}

    @router.get("/owned-products/{product_id}/links")
    async def owned_product_links(product_id: int):
        with host.db.connect() as conn:
            if not conn.execute("SELECT 1 FROM owned_products WHERE id=?", (product_id,)).fetchone():
                raise HTTPException(404, "Product not found")
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(
                "SELECT id, product_url, variant FROM owned_product_links WHERE product_id=? ORDER BY id", (product_id,))]

    @router.post("/owned-products/{product_id}/links")
    async def create_owned_product_link(product_id: int, data: ProductLink):
        product_url = canonical_product_url(data.product_url)
        if not product_url:
            raise HTTPException(422, "A supported merchant item URL is required")
        try:
            with host.db.connect() as conn:
                if not conn.execute("SELECT 1 FROM owned_products WHERE id=?", (product_id,)).fetchone():
                    raise HTTPException(404, "Product not found")
                cursor = conn.execute("INSERT INTO owned_product_links (product_id, variant, product_url) VALUES (?, ?, ?)",
                                      (product_id, data.variant.strip(), product_url))
                return {"id": cursor.lastrowid, "product_id": product_id,
                        "product_url": product_url, "variant": data.variant.strip()}
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Product URL is already linked") from None

    @router.delete("/owned-products/{product_id}/links/{link_id}")
    async def delete_owned_product_link(product_id: int, link_id: int):
        with host.db.connect() as conn:
            cursor = conn.execute("DELETE FROM owned_product_links WHERE product_id=? AND id=?", (product_id, link_id))
            if not cursor.rowcount:
                raise HTTPException(404, "Product URL not found")
            return {"deleted": True}

    @router.post("/purchases")
    async def create_purchase(data: Purchase):
        with host.db.connect() as conn:
            conn.row_factory = sqlite3.Row
            if not conn.execute("SELECT 1 FROM owned_products WHERE id=?", (data.product_id,)).fetchone():
                raise HTTPException(404, "Product not found")
            cursor = conn.execute('''INSERT INTO purchases (product_id, purchased_on, purchase_channel, order_number, store, paid_cents,
                package_count, units_per_package, note, variant, inner_package_count,
                inner_package_label) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (data.product_id, data.purchased_on.isoformat() if data.purchased_on else None,
                 (data.purchase_channel or "").strip(), (data.order_number or "").strip(),
                 data.store.strip(), int(data.paid_amount * 100), data.package_count,
                 str(data.units_per_package), data.note.strip(), data.variant.strip(),
                 data.inner_package_count, data.inner_package_label.strip()))
            return present_purchase(conn.execute("SELECT * FROM purchases WHERE id=?", (cursor.lastrowid,)).fetchone())

    @router.put("/purchases/{record_id}")
    async def update_purchase(record_id: int, data: Purchase):
        with host.db.connect() as conn:
            conn.row_factory = sqlite3.Row
            if not conn.execute("SELECT 1 FROM owned_products WHERE id=?", (data.product_id,)).fetchone():
                raise HTTPException(404, "Product not found")
            cursor = conn.execute('''UPDATE purchases SET product_id=?, purchased_on=?, purchase_channel=COALESCE(?, purchase_channel),
                order_number=COALESCE(?, order_number), store=?, paid_cents=?,
                package_count=?, units_per_package=?, note=?, variant=?, inner_package_count=?,
                inner_package_label=? WHERE id=?''',
                (data.product_id, data.purchased_on.isoformat() if data.purchased_on else None,
                 data.purchase_channel.strip() if data.purchase_channel is not None else None,
                 data.order_number.strip() if data.order_number is not None else None,
                 data.store.strip(), int(data.paid_amount * 100), data.package_count,
                 str(data.units_per_package), data.note.strip(), data.variant.strip(),
                 data.inner_package_count, data.inner_package_label.strip(), record_id))
            if not cursor.rowcount:
                raise HTTPException(404, "Purchase not found")
            return present_purchase(conn.execute("SELECT * FROM purchases WHERE id=?", (record_id,)).fetchone())

    @router.delete("/purchases/{record_id}")
    async def delete_purchase(record_id: int):
        with host.db.connect() as conn:
            cursor = conn.execute("DELETE FROM purchases WHERE id=?", (record_id,))
            if not cursor.rowcount:
                raise HTTPException(404, "Purchase not found")
            return {"deleted": True}

    @router.get("/historical-price-checks")
    async def historical_price_checks(limit: int = Query(default=30, ge=1, le=100)):
        return host.db.get_historical_price_checks(limit)

    @router.get("/bark")
    async def bark(scheme_id: Optional[int] = None):
        return (await host.get_bark_settings(scheme_id))["data"]

    @router.patch("/bark")
    async def update_bark(request: host.BarkSettingsRequest, scheme_id: Optional[int] = None):
        await host.save_bark_settings(request, scheme_id)
        return (await host.get_bark_settings(scheme_id))["data"]

    @router.post("/bark/test")
    async def test_bark(request: host.BarkSettingsRequest, scheme_id: Optional[int] = None):
        return await host.test_bark(request, scheme_id)

    @router.get("/settings")
    async def settings():
        return {key: ({"configured": bool(value.get("value"))} if key in SENSITIVE else value)
                for key, value in host.db.get_global_settings().items() if key != "bark_config"}

    @router.patch("/settings")
    async def patch_settings(values: dict):
        allowed = set(host.GlobalSettingsUpdate.model_fields) - {"server_port"}
        if not values or not set(values) <= allowed:
            raise HTTPException(422, "Unsupported settings; server port must be changed in the UI")
        try:
            data = host.GlobalSettingsUpdate.model_validate(values).model_dump(exclude_unset=True)
        except ValueError:
            raise HTTPException(422, "Invalid settings") from None
        host.db.update_global_settings(data)
        return await settings()

    @router.patch("/monitors/{scheme_id}/notifications")
    async def patch_notifications(scheme_id: int, values: dict):
        detail(scheme_id)
        allowed = {"dingtalk_webhook", "dingtalk_secret", "wechat_enabled", "wechat_account_id",
                   "wechat_targets", "wxpusher_enabled", "wxpusher_app_token", "wxpusher_uid", "bark_enabled"}
        if not values or not set(values) <= allowed:
            raise HTTPException(422, "Unsupported notification fields")
        try:
            request = host.SchemeUpdate.model_validate(values)
        except ValueError:
            raise HTTPException(422, "Invalid notification settings") from None
        await host.update_scheme(scheme_id, request)
        return detail(scheme_id)

    app.include_router(router)
