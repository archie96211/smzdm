"""Resolve known deal redirects to a verifiable merchant product URL."""

import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit


JD_ITEM = re.compile(r"^/(\d{5,20})\.html$")
JD_MOBILE_ITEM = re.compile(r"^/product/(\d{5,20})\.html$")
MMB_ARTICLE = re.compile(r"^/discuxiao_(\d+)\.aspx$")
SMZDM_ARTICLE = re.compile(r"^/p/\d+/?$")
MMB_MYURL = re.compile(r'''\bvar\s+myurl\s*=\s*["'](https?://[^"']{1,2048})["']''', re.I)


async def read_limited(response, limit=400_000):
    chunks = []
    size = 0
    async for chunk in response.content.iter_chunked(65_536):
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def canonical_product_url(value):
    """Return a stable product URL; coupons, shops and search pages have no item identity."""
    try:
        parsed = urlsplit(value or "")
        unsafe = parsed.username or parsed.password or parsed.port or parsed.fragment
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or unsafe:
        return None
    host = (parsed.hostname or "").lower()
    if host == "uland.taobao.com" and parsed.path == "/item/edetail":
        parameters = parse_qs(parsed.query)
        item = parameters.get("id", [])
        sku = parameters.get("skuId", [])
        if len(item) == len(sku) == 1 and re.fullmatch(r"[A-Za-z0-9_-]{10,120}", item[0]) and \
                re.fullmatch(r"\d{5,20}", sku[0]):
            return "https://uland.taobao.com/item/edetail?" + urlencode({"id": item[0], "skuId": sku[0]})
        return None
    if host == "item.jd.com":
        match = JD_ITEM.fullmatch(parsed.path)
        return f"https://item.jd.com/{match.group(1)}.html" if match else None
    if host == "item.m.jd.com":
        match = JD_MOBILE_ITEM.fullmatch(parsed.path)
        return f"https://item.jd.com/{match.group(1)}.html" if match else None
    if host in {"item.taobao.com", "detail.tmall.com"} and parsed.path == "/item.htm":
        item_ids = parse_qs(parsed.query).get("id", [])
        if len(item_ids) == 1 and re.fullmatch(r"\d{5,20}", item_ids[0]):
            return f"https://{host}/item.htm?{urlencode({'id': item_ids[0]})}"
    return None


def unwrap_location(value):
    """Inspect a redirect header without following arbitrary destinations."""
    direct = canonical_product_url(value)
    if direct:
        return direct
    parsed = urlsplit(value or "")
    if parsed.hostname == "www.manmanbuy.com" and parsed.path == "/redirectUrl.aspx":
        targets = parse_qs(parsed.query).get("tourl", [])
        if len(targets) == 1:
            return canonical_product_url(targets[0])
    return None


class BuyLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buy_link = None

    def handle_starttag(self, tag, attrs):
        if tag != "a" or self.buy_link:
            return
        attrs = dict(attrs)
        href = attrs.get("href", "")
        parsed = urlsplit(href)
        if parsed.scheme == "https" and parsed.hostname == "go.smzdm.com" and "go-buy" in attrs.get("class", "").split():
            self.buy_link = href


async def resolve_offer_product_url(session, offer, manmanbuy_session=None):
    """Perform at most two public requests with no cookies and no redirect following."""
    article_url = offer.get("article_url", "")
    direct = canonical_product_url(article_url)
    if direct:
        return direct
    parsed = urlsplit(article_url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        return None
    if parsed.hostname == "cu.manmanbuy.com" and MMB_ARTICLE.fullmatch(parsed.path):
        deal_id = MMB_ARTICLE.fullmatch(parsed.path).group(1)
        jump = f"https://cu.manmanbuy.com/goto_{deal_id}.aspx"
    elif parsed.hostname == "www.smzdm.com" and SMZDM_ARTICLE.fullmatch(parsed.path):
        async with session.get(article_url, allow_redirects=False) as response:
            if response.status != 200 or "text/html" not in response.headers.get("content-type", ""):
                return None
            body = await read_limited(response)
            if body is None:
                return None
        parser = BuyLinkParser()
        parser.feed(body.decode("utf-8", errors="replace"))
        jump = parser.buy_link
    else:
        return None
    if not jump:
        return None
    async with session.head(jump, allow_redirects=False) as response:
        if response.status in {301, 302, 303, 307, 308}:
            direct = unwrap_location(response.headers.get("Location", ""))
            if direct:
                return direct
    if parsed.hostname == "cu.manmanbuy.com" and manmanbuy_session is not None:
        async with manmanbuy_session.get(article_url, allow_redirects=False) as response:
            if response.status != 200 or "text/html" not in response.headers.get("content-type", ""):
                return None
            body = await read_limited(response)
            if body is None:
                return None
        match = MMB_MYURL.search(body.decode("utf-8", errors="replace"))
        if match:
            embedded = match.group(1).replace("\\/", "/")
            direct = canonical_product_url(embedded)
            if direct:
                return direct
            return await resolve_jd_affiliate(session, embedded)
    return None


async def resolve_jd_affiliate(session, value):
    """Follow at most two JD-owned affiliate hops to a verified JD item page."""
    try:
        parsed = urlsplit(value or "")
        unsafe = parsed.username or parsed.password or parsed.port
    except ValueError:
        return None
    if parsed.hostname != "jingfen.jd.com" or parsed.scheme not in {"http", "https"} or \
            unsafe or not re.fullmatch(r"/detail/[A-Za-z0-9_-]{10,120}\.html", parsed.path):
        return None
    current = parsed._replace(scheme="https").geturl()
    for _ in range(2):
        async with session.get(current, allow_redirects=False) as response:
            if response.status not in {301, 302, 303, 307, 308}:
                return None
            location = response.headers.get("Location", "")
        destination = urljoin(current, location)
        direct = canonical_product_url(destination)
        if direct and urlsplit(direct).hostname == "item.jd.com":
            return direct
        parsed = urlsplit(destination)
        if parsed.scheme != "https" or parsed.hostname != "jingfen.jd.com" or parsed.username or parsed.password or parsed.port:
            return None
        current = destination
    return None


async def resolve_merchant_item_url(session, product_url):
    """One safe redirect hop from a Taobao SKU affiliate page to its official item ID."""
    direct = canonical_product_url(product_url)
    if not direct:
        return None
    if urlsplit(direct).hostname != "uland.taobao.com":
        return direct
    async with session.get(direct, allow_redirects=False) as response:
        if response.status not in {301, 302, 303, 307, 308}:
            return None
        destination = canonical_product_url(response.headers.get("Location", ""))
        return destination if destination and urlsplit(destination).hostname == "item.taobao.com" else None
