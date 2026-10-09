"""Conservative presentation grouping for offers from separate sources."""

import re
from difflib import SequenceMatcher
from html import unescape


def identity(title):
    clean = re.sub(r"<[^>]*>", "", unescape(title or "")).lower()
    clean = re.sub(r"^(?:好价|限时|京东自营|天猫超市|[【\[].*?[】\]])[:：\s]*", "", clean)
    clean = re.sub(r"[\s\W_]+", "", clean, flags=re.UNICODE)
    return clean


def size_tokens(title):
    """A changed size, pack count, or model number must prevent grouping."""
    clean = re.sub(r"<[^>]*>", "", unescape(title or "")).lower()
    quantities = [re.sub(r"\s+", "", value) for value in re.findall(
        r"\d+(?:\.\d+)?\s*(?:kg|g|ml|l|包|袋|罐|片|张|抽|件|盒|箱)", clean)]
    multipliers = [re.sub(r"\s+", "", value).replace("×", "*").replace("x", "*")
                   for value in re.findall(r"\d+(?:\.\d+)?\s*(?:kg|g|ml|l|包|袋|罐|片|张|抽|件|盒|箱)\s*[*x×]\s*\d+", clean)]
    models = re.findall(r"(?:xxl|xl|s|m|l)号|(?<![a-z])[a-z]{1,2}\d{1,4}(?![a-z])", clean)
    variants = re.findall(r"原味|奶香|绿茶|白茶|薰衣草|樱花|鸡肉|牛肉|鱼肉|无香|香草|黑色|白色|蓝色|红色", clean)
    return sorted(set(quantities + multipliers + models + variants))


def same_product(left, right):
    a, b = identity(left["article_title"]), identity(right["article_title"])
    if not a or not b or size_tokens(left["article_title"]) != size_tokens(right["article_title"]):
        return False
    if a == b:
        return True
    if min(len(a), len(b)) < 12 or a[:2] != b[:2]:
        return False
    match = SequenceMatcher(None, a, b)
    longest = match.find_longest_match(0, len(a), 0, len(b)).size
    return match.ratio() >= 0.96 or longest / min(len(a), len(b)) >= 0.85


def group_offers(offers):
    """Keep every offer and its source link while grouping matching listings."""
    groups = []
    for offer in offers:
        source = "manmanbuy" if str(offer.get("article_id", "")).startswith("manmanbuy:") else "smzdm"
        group = next((item for item in groups if same_product(item["offers"][0], offer)), None)
        if group is None:
            group = {"title": offer["article_title"], "sources": [], "offers": []}
            groups.append(group)
        if source not in group["sources"]:
            group["sources"].append(source)
        group["offers"].append(offer)
    return groups
