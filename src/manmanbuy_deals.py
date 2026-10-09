"""Read ManManBuy's public discount search without a browser runtime."""

import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

import aiohttp

SEARCH_URL = "https://s.manmanbuy.com/pc/search/result"
DETAIL_HOST = "cu.manmanbuy.com"
DETAIL_PATH = re.compile(r"^/discuxiao_(\d+)\.aspx$")


class DealParser(HTMLParser):
    """Extract only visible discount cards from the server-rendered search page."""

    FIELDS = {
        "DiscountItemPC_itemTitle__": "article_title",
        "DiscountItemPC_itemSubTitle__": "article_price",
        "DiscountItemPC_itemTime__": "article_format_date",
        "DiscountItemPC_itemMall__": "article_mall",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.item_depth = None
        self.fields = []
        self.current = None
        self.deals = []

    def handle_starttag(self, tag, attrs):
        self.depth += 1
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "div" and any(c.startswith("DiscountItemPC_box__") for c in classes):
            self.item_depth = self.depth
            self.current = {"source": "manmanbuy"}
        if self.current is None:
            return
        for prefix, field in self.FIELDS.items():
            if any(c.startswith(prefix) for c in classes):
                self.fields.append((self.depth, field))
        if tag == "img" and not self.current.get("article_pic"):
            self.current["article_pic"] = attrs.get("src", "")
        if tag == "a":
            href = attrs.get("href", "")
            parsed = urlsplit(href)
            match = DETAIL_PATH.fullmatch(parsed.path)
            if parsed.scheme == "https" and parsed.netloc == DETAIL_HOST and match:
                self.current.setdefault("article_url", href)
                self.current.setdefault("article_id", "manmanbuy:" + match.group(1))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        if self.current is not None and self.fields:
            field = self.fields[-1][1]
            self.current[field] = self.current.get(field, "") + data

    def handle_endtag(self, tag):
        if self.current is not None:
            while self.fields and self.fields[-1][0] == self.depth:
                self.fields.pop()
            if self.depth == self.item_depth:
                if all(self.current.get(key) for key in ("article_id", "article_title", "article_url")):
                    self.deals.append({key: value.strip() if isinstance(value, str) else value
                                       for key, value in self.current.items()})
                self.current = None
                self.item_depth = None
                self.fields.clear()
        self.depth = max(0, self.depth - 1)


async def fetch_deals(session: aiohttp.ClientSession, keyword: str, limit: int = 20):
    """Return latest discount cards; fail closed if the page becomes a challenge."""
    async with session.get(SEARCH_URL, params={"c": "discount", "keyword": keyword,
                                               "orderby": "new", "pageId": 1},
                           allow_redirects=False) as response:
        if response.status != 200 or response.url.host != "s.manmanbuy.com":
            raise RuntimeError("慢慢买好价搜索暂时不可用")
        if "text/html" not in response.headers.get("content-type", ""):
            raise RuntimeError("慢慢买好价搜索返回格式变化")
        body = await response.content.read(2_000_001)
        if len(body) > 2_000_000:
            raise RuntimeError("慢慢买好价页面超出大小限制")
        html = body.decode("utf-8", errors="replace")
    parser = DealParser()
    parser.feed(html)
    if not parser.deals:
        if "DiscountItemPC_box__" in html or "verify.html" in html:
            raise RuntimeError("慢慢买好价页面变化或需要验证")
        if "暂无相关" not in html and "没有找到" not in html:
            raise RuntimeError("慢慢买好价列表未返回可识别内容")
    needle = re.sub(r"\s+", "", keyword).casefold()
    return [deal for deal in parser.deals
            if needle in re.sub(r"\s+", "", deal["article_title"]).casefold()][:limit]
