#!/usr/bin/env python3
"""
??????????????????- ??????
"""

import asyncio
import aiohttp
import time
import re
import logging
import os
from datetime import datetime
from html import unescape
from typing import List, Dict, Optional
from urllib.parse import urlparse
from .database import DatabaseManager
from .dingtalk_notifier import DingTalkNotifier
from .image_cache import ImageCache
from .network_utils import is_public_host as host_is_public, is_public_url as url_is_public
from .wechat_notifier import WeChatNotifier
from .wxpusher_notifier import WxPusherNotifier
from . import runtime

logger = logging.getLogger(__name__)

class SMZDMMonitor:
    def __init__(self, db_path: str = None, notifier: DingTalkNotifier = None):
        db_path = db_path or str(runtime.get_database_path())
        self.db = DatabaseManager(db_path)
        self.notifier = notifier or DingTalkNotifier()
        self.wechat_notifier = WeChatNotifier(
            bridge_url=os.getenv("WECHAT_BRIDGE_URL", "http://127.0.0.1:18012"),
            token=os.getenv("WECHAT_BRIDGE_TOKEN", ""),
        )
        self.wxpusher_notifier = WxPusherNotifier()
        self.image_cache = ImageCache(db_path=db_path)
        self.api_base_url = os.getenv("SMZDM_API_BASE_URL", "https://api.smzdm.com/v1/list")
        self.running = False
        self.tasks = {}
        self._wechat_alert_sent = False
        try:
            self.max_concurrency = max(1, int(os.getenv("SMZDM_MONITOR_CONCURRENCY", "3")))
        except ValueError:
            self.max_concurrency = 3
        self.keyword_semaphore: Optional[asyncio.Semaphore] = None
        
    async def fetch_products(self, session: aiohttp.ClientSession, keyword: str, **params) -> List[Dict]:
        """?????????"""
        try:
            # ?????????
            api_params = {
                'keyword': keyword,
                'category_id': params.get('category_id', ''),
                'brand_id': params.get('brand_id', ''),
                'mall_id': params.get('mall_id', ''),
                'order': params.get('order_type', 'time'),
                'limit': params.get('limit', 20),
                'offset': params.get('offset', 0)
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Referer': 'https://search.smzdm.com/'
            }
            
            async with session.get(self.api_base_url, params=api_params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if str(data.get('error_code', '1')) == '0':
                        rows = data.get('data', {}).get('rows', [])
                        faxian_rows = [r for r in rows if str(r.get('article_channel_id', '')) == '2']
                        if len(faxian_rows) < len(rows):
                            logger.info("Filtered %d non-faxian results (articles/etc), kept %d deals", len(rows) - len(faxian_rows), len(faxian_rows))
                        return faxian_rows
                    else:
                        logger.error(f"API???: {data.get('error_msg', '??????')}")
                else:
                    logger.error(f"HTTP???: {response.status}")
                    
        except Exception as e:
            logger.error(f"????????????: {e}")
        
        return []
    
    def clean_price(self, price_str: str) -> float:
        """??????????????????"""
        if not price_str:
            return 0.0
        
        # ???HTML???
        clean_str = re.sub(r'<[^>]+>', '', price_str)
        # ??????
        numbers = re.findall(r'\d+\.?\d*', clean_str)
        if numbers:
            return float(numbers[0])
        return 0.0

    def _clean_display_text(self, value, default: str = "") -> str:
        if value is None:
            return default
        text = unescape(re.sub(r"<[^>]+>", "", str(value))).strip()
        text = re.sub(r"\s+", " ", text)
        return text or default

    def format_price_text(self, product: Dict) -> str:
        for field in ("article_price", "article_subtitle", "real_price_title", "price"):
            price = self._clean_display_text(product.get(field))
            if price:
                return price
        return "???"

    def format_product_time(self, product: Dict) -> str:
        timestamp_text = ""
        timestamp = product.get("publish_date_lt") or product.get("article_publish_time")
        if timestamp:
            try:
                ts = int(float(timestamp))
                if ts > 10_000_000_000:
                    ts = ts // 1000
                timestamp_text = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            except (TypeError, ValueError, OSError):
                logger.debug("Unable to parse product timestamp: %r", timestamp)

        for field in ("article_format_date", "article_date", "pubdate", "date"):
            product_time = self._clean_display_text(product.get(field))
            if product_time:
                if timestamp_text and re.fullmatch(r"\d{1,2}:\d{2}", product_time):
                    return timestamp_text
                return product_time

        return timestamp_text

    def get_product_image_url(self, product: Dict) -> str:
        for field in ("article_pic", "focus_pic_url", "article_image", "image_url", "pic_url"):
            image_url = self._clean_display_text(product.get(field))
            if image_url:
                return image_url
        return ""

    def normalize_image_url(self, image_url: str) -> str:
        image_url = self._clean_display_text(image_url)
        if not image_url:
            return ""
        if image_url.startswith("//"):
            return f"https:{image_url}"

        parsed = urlparse(image_url)
        hostname = parsed.hostname or ""
        if parsed.scheme == "http" and hostname.endswith(("zdmimg.com", "smzdm.com")):
            return "https://" + image_url[len("http://"):]
        if parsed.scheme in ("http", "https"):
            return image_url
        return ""

    def is_public_host(self, host: str) -> bool:
        return host_is_public(host)

    def is_public_url(self, url: str) -> bool:
        return url_is_public(url)

    async def get_dingtalk_image_url(self, image_url: str) -> str:
        source_image_url = self.normalize_image_url(image_url)
        if not source_image_url:
            return ""

        image_config = self.db.get_image_server_config()
        if self.is_public_host(str(image_config.get("host", ""))):
            try:
                local_url = await self.image_cache.cache_and_get_local_url(
                    source_image_url,
                    server_host=image_config["host"],
                    server_port=image_config["port"],
                )
                if local_url:
                    logger.info("DingTalk product image cached to public URL: %s", local_url)
                    return local_url
            except Exception as exc:
                logger.warning("Failed to cache product image for DingTalk: %s", exc)

            if self.is_public_url(source_image_url):
                logger.info(
                    "Falling back to source image URL after local public cache failed: %s",
                    source_image_url,
                )
                return source_image_url

            return ""

        if self.is_public_url(source_image_url):
            logger.info(
                "image_server_host is not public (%s); use source image URL for DingTalk: %s",
                image_config.get("host"),
                source_image_url,
            )
            return source_image_url

        logger.info(
            "Skip DingTalk image because neither image_server_host nor source image URL is public: %s",
            image_config.get("host"),
        )
        return ""

    async def get_wechat_image_path(self, image_url: str) -> str:
        source_image_url = self.normalize_image_url(image_url)
        if not source_image_url:
            return ""
        try:
            cache_path = await self.image_cache.cache_and_get_path(source_image_url)
            return str(cache_path) if cache_path else ""
        except Exception as exc:
            logger.warning("Failed to cache product image for WeChat: %s", exc)
            return ""
    
    def filter_by_price(self, products: List[Dict], price_min: float, price_max: float) -> List[Dict]:
        """????????????"""
        if price_min <= 0 and price_max >= 999999:
            return products
        
        filtered = []
        for product in products:
            price = self.clean_price(product.get('article_price', ''))
            if price_min <= price <= price_max:
                filtered.append(product)
        
        return filtered
    
    async def monitor_keyword(self, session: aiohttp.ClientSession, scheme_id: int, keyword_data: Dict) -> List[Dict]:
        """Monitor one keyword."""
        try:
            is_initial_run = not self.db.has_keyword_history(keyword_data['id'])
            if self.keyword_semaphore is None:
                self.keyword_semaphore = asyncio.Semaphore(self.max_concurrency)

            async with self.keyword_semaphore:
                products = await self.fetch_products(
                    session,
                    keyword_data['keyword'],
                    category_id=keyword_data.get('category_id', ''),
                    brand_id=keyword_data.get('brand_id', ''),
                    mall_id=keyword_data.get('mall_id', ''),
                    order_type=keyword_data.get('order_type', 'time'),
                    limit=20
                )

            # ??????
            filtered_products = self.filter_by_price(
                products,
                keyword_data.get('price_min', 0),
                keyword_data.get('price_max', 999999)
            )

            new_products = []
            for product in filtered_products:
                product_id = self.db.add_product(
                    scheme_id,
                    keyword_data['id'],
                    product
                )
                if product_id:
                    product['db_id'] = product_id
                    new_products.append(product)
                    logger.info(f"???????? {product.get('article_title', '')[:50]}...")

            if is_initial_run:
                logger.info(
                    "Keyword '%s' initial run saved %s product(s); skip product notifications until future changes.",
                    keyword_data['keyword'],
                    len(new_products),
                )
                return []

            return new_products
                
        except Exception as e:
            logger.error(f"????????'{keyword_data['keyword']}' ???: {e}")
            return []
    async def monitor_scheme(self, scheme_id: int):
        """Monitor one scheme."""
        scheme = self.db.get_scheme(scheme_id)
        if not scheme or not scheme['is_active']:
            return

        logger.info("Start monitoring scheme: %s", scheme['name'])

        timeout = aiohttp.ClientTimeout(total=25, connect=8, sock_read=15)
        connector = aiohttp.TCPConnector(limit=self.max_concurrency, limit_per_host=self.max_concurrency)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            while self.running and scheme_id in self.tasks:
                try:
                    if not self.running or scheme_id not in self.tasks:
                        break

                    keywords = self.db.get_keywords(scheme_id)
                    if not keywords:
                        logger.warning("Scheme %s has no active keywords", scheme['name'])
                        await asyncio.sleep(scheme['refresh_interval'])
                        continue

                    if not self.running or scheme_id not in self.tasks:
                        break

                    tasks = [self.monitor_keyword(session, scheme_id, keyword) for keyword in keywords]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    if not self.running or scheme_id not in self.tasks:
                        break

                    all_new_products = []
                    for result in results:
                        if isinstance(result, Exception):
                            logger.error("Keyword monitor error: %s", result)
                            continue
                        if result:
                            all_new_products.extend(result)

                    if not self.running or scheme_id not in self.tasks:
                        break

                    if all_new_products and (scheme.get('dingtalk_webhook') or scheme.get('wechat_enabled') or scheme.get('wxpusher_enabled')):
                        await self.send_notifications(scheme, all_new_products)

                    if not self.running or scheme_id not in self.tasks:
                        break

                    self.db.update_scheme(scheme_id, updated_at=datetime.now().isoformat())
                    logger.info("Scheme %s monitor cycle complete; new_products=%s", scheme['name'], len(all_new_products))

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error("Monitor scheme %s failed: %s", scheme['name'], e)

                for _ in range(scheme['refresh_interval']):
                    if not self.running or scheme_id not in self.tasks:
                        break
                    await asyncio.sleep(1)

    async def send_notifications(self, scheme: Dict, products: List[Dict]):
        """Send configured DingTalk and WeChat notifications."""
        global_webhook = self.db.get_config('dingtalk_webhook') or ''
        global_wxpusher_token = self.db.get_config('wxpusher_app_token') or ''
        global_wxpusher_uid = self.db.get_config('wxpusher_uid') or ''
        has_dingtalk = scheme.get('dingtalk_webhook') or global_webhook
        has_wxpusher = scheme.get('wxpusher_enabled') and (scheme.get('wxpusher_app_token') or global_wxpusher_token) and (scheme.get('wxpusher_uid') or global_wxpusher_uid)
        if not has_dingtalk and not scheme.get('wechat_enabled') and not has_wxpusher:
            return

        try:
            if not products:
                return

            logger.info("Preparing %s notification(s) for scheme %s", len(products), scheme.get('name'))

            for product in products:
                if not self.running:
                    logger.info("Notification loop stopped because monitor is stopping")
                    break

                try:
                    product_title = self._clean_display_text(product.get('article_title'), 'No title')[:80]
                    price_text = self.format_price_text(product)
                    mall = self._clean_display_text(product.get('article_mall'), 'Unknown mall')
                    product_time = self.format_product_time(product)
                    sent_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    article_url = product.get('article_url', '')
                    pic_url = self.get_product_image_url(product)

                    card_title = f"{scheme['name']} 发现新好价"
                    message_parts = [
                        f"### {product_title}",
                        "",
                        f"- **价格**: {price_text}",
                        f"- **商城**: {mall}",
                    ]
                    if product_time:
                        message_parts.append(f"- **SMZDM时间**: {product_time}")
                    message_parts.append(f"- **发送时间**: {sent_time}")
                    message_parts.append("")

                    public_image_url = ""
                    wechat_image_path = ""
                    if pic_url:
                        public_image_url = await self.get_dingtalk_image_url(pic_url)
                        if public_image_url:
                            logger.info("Product image public URL: %s", public_image_url)
                            message_parts.append(f"![商品图片]({public_image_url})")
                            message_parts.append("")

                    if pic_url and scheme.get('wechat_enabled'):
                        wechat_image_path = await self.get_wechat_image_path(pic_url)
                        if wechat_image_path:
                            logger.info("Product image cached for WeChat: %s", wechat_image_path)

                    card_text = "\n".join(message_parts)
                    sent_success = False

                    webhook = scheme.get('dingtalk_webhook') or global_webhook
                    if webhook:
                        secret = scheme.get('dingtalk_secret') or self.db.get_config('dingtalk_secret') or ''
                        success = await self.notifier.send_message(
                            webhook_url=webhook,
                            message=card_text,
                            secret=secret,
                            message_type='actionCard',
                            title=card_title,
                            single_title='查看商品详情',
                            single_url=article_url if article_url else "https://www.smzdm.com",
                        )
                        self.db.add_notification_log(
                            scheme['id'],
                            product.get('db_id'),
                            'dingtalk',
                            'success' if success else 'failed',
                            '' if success else 'send failed',
                        )
                        sent_success = sent_success or success

                    if scheme.get('wechat_enabled'):
                        wechat_text = "\n".join([
                            product_title,
                            f"价格: {price_text}",
                            f"商城: {mall}",
                            f"SMZDM时间: {product_time}" if product_time else "",
                            f"发送时间: {sent_time}",
                            f"链接: {article_url}" if article_url else "",
                        ]).strip()
                        success = await self.wechat_notifier.send_message(
                            conversation_id=str(scheme.get('wechat_targets') or ''),
                            text=wechat_text,
                            media_path=wechat_image_path,
                        )
                        self.db.add_notification_log(
                            scheme['id'],
                            product.get('db_id'),
                            'wechat',
                            'success' if success else 'failed',
                            '' if success else 'send failed',
                        )
                        sent_success = sent_success or success

                        if not success and not self._wechat_alert_sent:
                            self._wechat_alert_sent = True
                            webhook = scheme.get('dingtalk_webhook') or global_webhook
                            if webhook:
                                secret = scheme.get('dingtalk_secret') or self.db.get_config('dingtalk_secret') or ''
                                try:
                                    await self.notifier.send_text(
                                        webhook_url=webhook,
                                        content="⚠️ 微信通知已失效，请重新扫码登录微信clawbot",
                                        secret=secret,
                                    )
                                except Exception:
                                    logger.debug("Failed to send DingTalk alert for WeChat failure", exc_info=True)
                        elif success:
                            self._wechat_alert_sent = False

                    if scheme.get('wxpusher_enabled'):
                        wxpusher_token = scheme.get('wxpusher_app_token') or global_wxpusher_token
                        wxpusher_uid = scheme.get('wxpusher_uid') or global_wxpusher_uid
                        if wxpusher_token and wxpusher_uid:
                            wxpusher_markdown = "\n".join(message_parts)
                            wxpusher_summary = f"{product_title} {price_text}"
                            success = await self.wxpusher_notifier.send_markdown(
                                app_token=wxpusher_token,
                                title=card_title,
                                text=wxpusher_markdown,
                                uid=wxpusher_uid,
                                url=article_url if article_url else "",
                            )
                            self.db.add_notification_log(
                                scheme['id'],
                                product.get('db_id'),
                                'wxpusher',
                                'success' if success else 'failed',
                                '' if success else 'send failed',
                            )
                            sent_success = sent_success or success

                    if sent_success:
                        self.db.mark_as_notified(product.get('db_id'))
                        logger.info("Product notification sent: %s", product_title[:30])
                    else:
                        logger.error("Product notification failed: %s", product_title[:30])

                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error("Single product notification failed: %s", e)
                    continue

        except Exception as e:
            logger.error("Send notifications failed: %s", e)

    async def start_monitoring(self):
        """Start all active scheme tasks."""
        self.running = True
        self.keyword_semaphore = asyncio.Semaphore(self.max_concurrency)
        logger.info("Monitor system started")

        schemes = self.db.get_schemes()
        active_schemes = [s for s in schemes if s['is_active']]

        if not active_schemes:
            logger.warning("No active schemes found")
            self.running = False
            return

        for scheme in active_schemes:
            task = asyncio.create_task(self.monitor_scheme(scheme['id']))
            self.tasks[scheme['id']] = task
            logger.info("Started scheme monitor: %s", scheme['name'])

        try:
            while self.running and self.tasks:
                done, _pending = await asyncio.wait(
                    self.tasks.values(),
                    timeout=1.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    for scheme_id, scheme_task in list(self.tasks.items()):
                        if scheme_task == task:
                            self.tasks.pop(scheme_id, None)
                            break
                if not self.running:
                    break
        finally:
            await self.stop_monitoring()

    async def stop_monitoring(self):
        """Stop all scheme tasks and close resources."""
        if not self.running and not self.tasks:
            logger.debug("stop_monitoring called but already stopped; skipping")
            return
        self.running = False
        logger.info("Stopping monitor system")

        for task in self.tasks.values():
            task.cancel()

        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

        self.tasks.clear()
        await self.notifier.close()
        await self.wechat_notifier.close()
        await self.image_cache.close()
        logger.info("Monitor system stopped")

    async def restart_scheme(self, scheme_id: int):
        """Restart one scheme task."""
        old_task = self.tasks.pop(scheme_id, None)
        if old_task and not old_task.done():
            old_task.cancel()
            await asyncio.gather(old_task, return_exceptions=True)

        if self.running:
            task = asyncio.create_task(self.monitor_scheme(scheme_id))
            self.tasks[scheme_id] = task
            logger.info("Restarted scheme monitor: %s", scheme_id)

    def get_status(self) -> Dict:
        """Return monitor status."""
        schemes = self.db.get_schemes()
        status = {
            'running': self.running,
            'total_schemes': len(schemes),
            'active_schemes': len([s for s in schemes if s['is_active']]),
            'running_tasks': len(self.tasks),
            'schemes': []
        }

        for scheme in schemes:
            scheme_status = {
                'id': scheme['id'],
                'name': scheme['name'],
                'is_active': scheme['is_active'],
                'is_running': scheme['id'] in self.tasks,
                'keywords_count': len(self.db.get_keywords(scheme['id'])),
                'notification_stats': self.db.get_notification_stats(scheme['id'])
            }
            status['schemes'].append(scheme_status)

        return status

async def main():
    """Run monitor from CLI."""
    monitor = SMZDMMonitor()
    
    try:
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        logger.info("monitor interrupted")
    except Exception as e:
        logger.error(f"??????: {e}")
    finally:
        await monitor.stop_monitoring()

if __name__ == "__main__":
    asyncio.run(main())


