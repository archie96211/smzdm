"""Bounded owned-product candidates and evidence-checked local price arithmetic."""

import re
from difflib import SequenceMatcher
from decimal import Decimal, InvalidOperation

from .deal_groups import identity

CATEGORY_SEARCH_TERMS = ("猫砂", "抽纸", "纸巾", "面巾纸", "卷纸", "罐头", "湿巾")


def candidate_products(offer, products, limit=3):
    """Use confirmed merchant identity first, then a conservative bounded name search."""
    urls = {offer.get("product_url"), offer.get("merchant_item_url")}
    urls.discard(None)
    linked = [item for item in products if any(link["product_url"] in urls for link in item.get("links", []))]
    if linked:
        return linked[:limit]
    title = identity(offer.get("article_title", ""))
    ranked = []
    for item in products:
        name = identity(item["name"])
        if not name or not title:
            continue
        score = SequenceMatcher(None, name, title).ratio()
        if name in title:
            score += 1
        shared_category = any(term in name and term in title for term in CATEGORY_SEARCH_TERMS)
        tissue_family = any(term in name for term in ("抽纸", "纸巾", "面巾纸", "卷纸")) and \
                        any(term in title for term in ("抽纸", "纸巾", "面巾纸", "卷纸"))
        if shared_category or tissue_family:
            score += 0.6
        if score >= 0.38:
            ranked.append((score, item))
    return [item for _, item in sorted(ranked, key=lambda pair: pair[0], reverse=True)[:limit]]


def calculate_verified_price(offer, expression):
    """Check quoted operands against source text, then calculate without eval()."""
    if not isinstance(expression, dict):
        return None
    source = " ".join(str(offer.get(field) or "") for field in
                      ("article_title", "article_price", "article_subtitle", "real_price_title"))

    def operand(value):
        if not isinstance(value, dict):
            raise ValueError("missing operand")
        raw, evidence = value.get("value"), value.get("evidence")
        if not isinstance(raw, (int, float, str)) or isinstance(raw, bool) or not isinstance(evidence, str):
            raise ValueError("invalid operand")
        number = Decimal(str(raw))
        if not number.is_finite() or number < 0 or number > 1_000_000:
            raise ValueError("out-of-range operand")
        if not evidence or evidence not in source:
            raise ValueError("operand lacks source quote")
        tokens = re.findall(r"\d+(?:\.\d+)?", evidence)
        if number not in [Decimal(token) for token in tokens] and not (
            number == 1 and re.search(r"单件|一件|每件|单包|一包|每包|单袋|一袋|每袋", evidence)):
            raise ValueError("operand absent from source quote")
        return number

    try:
        base = operand(expression.get("base_price"))
        discounts = expression.get("discounts", [])
        if not isinstance(discounts, list) or len(discounts) > 4:
            return None
        total = base - sum((operand(value) for value in discounts), Decimal(0))
        packages = operand(expression.get("package_count"))
        if packages <= 0 or packages != packages.to_integral_value() or total <= 0:
            return None
        effective = total / packages
        units = expression.get("units_per_package")
        unit_value = operand(units) if units is not None else None
        unit_price = effective / unit_value if unit_value and unit_value > 0 else None
        return {"total_price": format(total.quantize(Decimal("0.01")), "f"),
                "price_per_package": format(effective.quantize(Decimal("0.0001")), "f"),
                "unit_price": format(unit_price.quantize(Decimal("0.0001")), "f") if unit_price else None}
    except (ValueError, InvalidOperation, TypeError, ZeroDivisionError):
        return None
