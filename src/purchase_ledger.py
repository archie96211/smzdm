"""Private purchase ledger and saved price observations."""

import sqlite3
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from .merchant_links import canonical_product_url


class OwnedProduct(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    measure_unit: str = Field(min_length=1, max_length=12)
    package_label: str = Field(min_length=1, max_length=12)


class ProductLink(BaseModel):
    product_url: str = Field(min_length=1, max_length=2048)
    variant: str = Field(default="", max_length=120)


class Purchase(BaseModel):
    product_id: int = Field(gt=0)
    purchased_on: Optional[date] = None
    purchase_channel: Optional[Literal["", "jd", "taobao", "tmall", "pdd", "douyin",
                                       "wechat", "offline", "other"]] = None
    order_number: Optional[str] = Field(default=None, max_length=120)
    store: str = Field(default="", max_length=100)
    paid_amount: Decimal = Field(ge=0, le=1000000, allow_inf_nan=False)
    package_count: int = Field(gt=0, le=100000)
    units_per_package: Decimal = Field(gt=0, le=1000000, allow_inf_nan=False)
    note: str = Field(default="", max_length=1000)
    variant: str = Field(default="", max_length=120)
    inner_package_count: Optional[int] = Field(default=None, gt=0, le=100000)
    inner_package_label: str = Field(default="", max_length=12)

    @model_validator(mode="after")
    def valid_money(self):
        if self.paid_amount.as_tuple().exponent < -2:
            raise ValueError("实付金额最多保留两位小数")
        if bool(self.inner_package_count) != bool(self.inner_package_label.strip()):
            raise ValueError("内包装数量和单位需同时填写")
        return self


def amount(value):
    return format(Decimal(value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP).normalize(), "f")


def present_purchase(row):
    item = dict(row)
    total_units = Decimal(item["package_count"]) * Decimal(item["units_per_package"])
    paid = Decimal(item["paid_cents"]) / 100
    item["paid_amount"] = amount(paid)
    item["total_units"] = amount(total_units)
    item["price_per_package"] = amount(paid / item["package_count"])
    item["price_per_unit"] = amount(paid / total_units)
    item["price_per_inner_package"] = (amount(paid / (item["package_count"] * item["inner_package_count"]))
                                         if item["inner_package_count"] else None)
    item.pop("paid_cents")
    return item


def install(app, database):
    async def same_origin(request: Request):
        origin = request.headers.get("origin")
        if request.method != "GET" and origin and urlsplit(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, "请从本服务页面操作")

    router = APIRouter(prefix="/api/purchase", dependencies=[Depends(same_origin)])

    def product_row(conn, product_id):
        row = conn.execute('SELECT * FROM owned_products WHERE id = ?', (product_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "商品档案不存在")
        return dict(row)

    def summary(conn, product_id):
        product = product_row(conn, product_id)
        rows = list(conn.execute('''
            SELECT * FROM purchases WHERE product_id = ? ORDER BY purchased_on DESC, id DESC
        ''', (product_id,)))
        purchases = [present_purchase(row) for row in rows]
        total_cents = sum(row["paid_cents"] for row in rows)
        total_units = sum(row["package_count"] * Decimal(row["units_per_package"]) for row in rows)
        product["purchases"] = purchases
        product["links"] = [dict(row) for row in conn.execute('''
            SELECT id, product_url, variant FROM owned_product_links
            WHERE product_id = ? ORDER BY id
        ''', (product_id,))]
        product["purchase_count"] = len(purchases)
        product["latest_price_per_unit"] = purchases[0]["price_per_unit"] if purchases else None
        product["best_price_per_unit"] = min((p["price_per_unit"] for p in purchases),
                                              key=Decimal, default=None)
        product["weighted_price_per_unit"] = amount(Decimal(total_cents) / 100 / total_units) if total_units else None
        variants = {}
        for row in rows:
            label = row["variant"] or "通用规格"
            item = variants.setdefault(label, {"variant": label, "purchase_count": 0,
                                               "total_cents": 0, "total_units": Decimal(0),
                                               "best_price_per_unit": None})
            item["purchase_count"] += 1
            item["total_cents"] += row["paid_cents"]
            item["total_units"] += row["package_count"] * Decimal(row["units_per_package"])
            price = Decimal(row["paid_cents"]) / 100 / (row["package_count"] * Decimal(row["units_per_package"]))
            if item["best_price_per_unit"] is None or price < item["best_price_per_unit"]:
                item["best_price_per_unit"] = price
        product["variant_summaries"] = [{"variant": item["variant"],
            "purchase_count": item["purchase_count"],
            "weighted_price_per_unit": amount(Decimal(item["total_cents"]) / 100 / item["total_units"]),
            "best_price_per_unit": amount(item["best_price_per_unit"])} for item in variants.values()]
        if len(variants) > 1:
            product["latest_price_per_unit"] = None
            product["best_price_per_unit"] = None
            product["weighted_price_per_unit"] = None
        return product

    @router.get("/products")
    async def list_products():
        with database.connect() as conn:
            conn.row_factory = sqlite3.Row
            ids = [row[0] for row in conn.execute('SELECT id FROM owned_products ORDER BY name')]
            return [summary(conn, item_id) for item_id in ids]

    @router.post("/products")
    async def add_product(data: OwnedProduct):
        name = data.name.strip()
        if not name or not data.measure_unit.strip() or not data.package_label.strip():
            raise HTTPException(422, "商品名称和单位不能为空")
        try:
            with database.connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    INSERT INTO owned_products (name, measure_unit, package_label) VALUES (?, ?, ?)
                ''', (name, data.measure_unit.strip(), data.package_label.strip()))
                return summary(conn, cursor.lastrowid)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "这个商品档案已存在") from None

    @router.get("/products/{product_id}")
    async def get_product(product_id: int):
        with database.connect() as conn:
            conn.row_factory = sqlite3.Row
            return summary(conn, product_id)

    @router.put("/products/{product_id}")
    async def update_product(product_id: int, data: OwnedProduct):
        name = data.name.strip()
        measure_unit = data.measure_unit.strip()
        package_label = data.package_label.strip()
        if not all((name, measure_unit, package_label)):
            raise HTTPException(422, "商品名称和单位不能为空")
        try:
            with database.connect() as conn:
                conn.row_factory = sqlite3.Row
                old = product_row(conn, product_id)
                if (old["measure_unit"] != measure_unit or old["package_label"] != package_label) and conn.execute(
                    'SELECT 1 FROM purchases WHERE product_id = ? LIMIT 1', (product_id,)).fetchone():
                    raise HTTPException(409, "已有购买记录，不能修改计价单位或包装单位")
                conn.execute('''
                    UPDATE owned_products SET name = ?, measure_unit = ?, package_label = ? WHERE id = ?
                ''', (name, measure_unit, package_label, product_id))
                return summary(conn, product_id)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "这个商品档案已存在") from None

    @router.delete("/products/{product_id}")
    async def delete_product(product_id: int):
        with database.connect() as conn:
            if conn.execute('SELECT 1 FROM purchases WHERE product_id = ? LIMIT 1', (product_id,)).fetchone():
                raise HTTPException(409, "请先处理此商品的购买记录")
            cursor = conn.execute('DELETE FROM owned_products WHERE id = ?', (product_id,))
            if not cursor.rowcount:
                raise HTTPException(404, "商品档案不存在")
            return {"deleted": True}

    @router.post("/products/{product_id}/links")
    async def add_product_link(product_id: int, data: ProductLink):
        product_url = canonical_product_url(data.product_url)
        if not product_url:
            raise HTTPException(422, "请填写京东、淘宝或天猫的商品详情链接")
        try:
            with database.connect() as conn:
                conn.row_factory = sqlite3.Row
                product_row(conn, product_id)
                conn.execute('''
                    INSERT INTO owned_product_links (product_id, variant, product_url)
                    VALUES (?, ?, ?)
                ''', (product_id, data.variant.strip(), product_url))
                return summary(conn, product_id)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "这个商品链接已经关联其他档案") from None

    @router.delete("/products/{product_id}/links/{link_id}")
    async def delete_product_link(product_id: int, link_id: int):
        with database.connect() as conn:
            conn.row_factory = sqlite3.Row
            product_row(conn, product_id)
            cursor = conn.execute('''
                DELETE FROM owned_product_links WHERE id = ? AND product_id = ?
            ''', (link_id, product_id))
            if not cursor.rowcount:
                raise HTTPException(404, "商品链接不存在")
            return summary(conn, product_id)

    @router.post("/records")
    async def add_purchase(data: Purchase):
        with database.connect() as conn:
            conn.row_factory = sqlite3.Row
            product_row(conn, data.product_id)
            cursor = conn.execute('''
                INSERT INTO purchases (product_id, purchased_on, purchase_channel, order_number, store, paid_cents,
                    package_count, units_per_package, note, variant,
                    inner_package_count, inner_package_label) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (data.product_id, data.purchased_on.isoformat() if data.purchased_on else None,
                  (data.purchase_channel or "").strip(), (data.order_number or "").strip(),
                  data.store.strip(), int(data.paid_amount * 100), data.package_count,
                  str(data.units_per_package), data.note.strip(), data.variant.strip(),
                  data.inner_package_count, data.inner_package_label.strip()))
            return summary(conn, data.product_id) | {"new_record_id": cursor.lastrowid}

    @router.put("/records/{record_id}")
    async def replace_purchase(record_id: int, data: Purchase):
        with database.connect() as conn:
            conn.row_factory = sqlite3.Row
            product_row(conn, data.product_id)
            cursor = conn.execute('''
                UPDATE purchases SET product_id = ?, purchased_on = ?, purchase_channel = COALESCE(?, purchase_channel),
                    order_number = COALESCE(?, order_number), store = ?, paid_cents = ?,
                    package_count = ?, units_per_package = ?, note = ?, variant = ?,
                    inner_package_count = ?, inner_package_label = ? WHERE id = ?
            ''', (data.product_id, data.purchased_on.isoformat() if data.purchased_on else None,
                  data.purchase_channel.strip() if data.purchase_channel is not None else None,
                  data.order_number.strip() if data.order_number is not None else None,
                  data.store.strip(), int(data.paid_amount * 100), data.package_count,
                  str(data.units_per_package), data.note.strip(), data.variant.strip(),
                  data.inner_package_count, data.inner_package_label.strip(), record_id))
            if not cursor.rowcount:
                raise HTTPException(404, "购买记录不存在")
            return summary(conn, data.product_id)

    @router.delete("/records/{record_id}")
    async def delete_purchase(record_id: int):
        with database.connect() as conn:
            cursor = conn.execute('DELETE FROM purchases WHERE id = ?', (record_id,))
            if not cursor.rowcount:
                raise HTTPException(404, "购买记录不存在")
            return {"deleted": True}

    @router.get("/price-checks")
    async def price_checks(limit: int = 30):
        return database.get_historical_price_checks(limit)

    @router.get("/offer-observations/{product_id}")
    async def offer_observations(product_id: int):
        return database.get_price_observations(product_id)

    app.include_router(router)
