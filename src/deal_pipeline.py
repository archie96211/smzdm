"""Prepare lightweight, provenance-preserving alerts without model calls."""

import logging
import re
import sqlite3
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .database import simple_price_cents
from .deal_groups import group_offers, identity, size_tokens
from .merchant_links import resolve_merchant_item_url, resolve_offer_product_url
from .purchase_ledger import present_purchase

logger = logging.getLogger(__name__)


def owned_summaries(db):
    with db.connect() as conn:
        conn.row_factory = sqlite3.Row
        products = [dict(row) for row in conn.execute("SELECT * FROM owned_products ORDER BY name LIMIT 100")]
        for product in products:
            product["links"] = [dict(row) for row in conn.execute(
                "SELECT product_url, variant FROM owned_product_links WHERE product_id=?", (product["id"],))]
            product["purchases"] = [present_purchase(row) for row in conn.execute(
                "SELECT * FROM purchases WHERE product_id=? ORDER BY purchased_on DESC, id DESC LIMIT 2",
                (product["id"],))]
            product["variant_summaries"] = [{"variant": row[0]} for row in conn.execute(
                "SELECT DISTINCT variant FROM purchases WHERE product_id=? AND variant!='' LIMIT 6", (product["id"],))]
        return products


def deal_key(offer):
    merchant_url = offer.get("merchant_item_url") or offer.get("product_url")
    if merchant_url:
        return "merchant:" + merchant_url + ":" + ",".join(size_tokens(offer.get("article_title", "")))
    return "title:" + identity(offer.get("article_title", "")) + ":" + ",".join(size_tokens(offer.get("article_title", "")))


def comparable_price_cents(offer):
    comparison = offer.get("comparison") or {}
    calculation = comparison.get("calculated_price") or {}
    if comparison.get("confidence") == "verified" and calculation.get("total_price"):
        try:
            return int((Decimal(calculation["total_price"]) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, ValueError, TypeError):
            pass
    return simple_price_cents(offer.get("article_price"))


def offer_terms(offer):
    return re.sub(r"\s+", " ", " ".join(str(offer.get(field) or "")
        for field in ("article_price", "article_subtitle", "real_price_title")).strip())[:200]


async def prepare_alerts(db, session, scheme_id, offers, history_connection=None):
    """Resolve bounded item links, group offers and deduplicate before delivery."""
    enriched = []
    link_budget = 8
    private_session = None
    if history_connection and history_connection.path.exists():
        try:
            private_session = await history_connection.get_client()
        except Exception as exc:
            logger.info("Saved ManManBuy session unavailable: %s", type(exc).__name__)
    for original in offers:
        offer = dict(original)
        for field in ("comparison", "history", "history_delta"):
            offer.pop(field, None)
        offer["product_url"] = None
        if link_budget:
            link_budget -= 1
            try:
                offer["product_url"] = await resolve_offer_product_url(session, offer, private_session)
            except Exception as exc:
                logger.info("Merchant item link unavailable: %s", type(exc).__name__)
        offer["merchant_item_url"] = None
        if offer["product_url"]:
            try:
                offer["merchant_item_url"] = await resolve_merchant_item_url(session, offer["product_url"])
            except Exception as exc:
                logger.info("Official merchant item ID unavailable: %s", type(exc).__name__)
        enriched.append(offer)

    # An unchanged previously sent offer cannot produce a new alert even when
    # another source assigns a fresh article ID.
    enriched = [offer for offer in enriched if db.should_send_deal_alert(
        scheme_id, deal_key(offer), None, offer_terms(offer))]
    if not enriched:
        return []

    # Confirmed merchant identity takes precedence over title similarity.
    groups = []
    for offer in enriched:
        group = next((group for group in groups if
                      ((offer.get("merchant_item_url") and
                        group[0].get("merchant_item_url") == offer["merchant_item_url"]) or
                       (offer.get("product_url") and group[0].get("product_url") == offer["product_url"]))
                      and size_tokens(group[0].get("article_title", "")) ==
                      size_tokens(offer.get("article_title", ""))), None)
        if group is None:
            group = next((group for group in groups if
                          (not offer.get("product_url") or not group[0].get("product_url")) and
                          len(group_offers([group[0], offer])) == 1), None)
        if group is None:
            group = []
            groups.append(group)
        group.append(offer)

    ready = []
    for group in groups:
        representative = min(group, key=lambda item: comparable_price_cents(item) or 10**12)
        confirmed = next((item for item in group if item.get("product_url")), None)
        if confirmed and not representative.get("product_url"):
            representative["product_url"] = confirmed["product_url"]
            representative["merchant_item_url"] = confirmed.get("merchant_item_url")
        price_cents = comparable_price_cents(representative)
        terms = offer_terms(representative)
        key = deal_key(representative)
        if not db.should_send_deal_alert(scheme_id, key, price_cents, terms):
            continue
        representative["group_offers"] = group
        representative["alert_key"] = key
        representative["alert_price_cents"] = price_cents
        representative["alert_terms"] = terms
        ready.append(representative)
    return ready
