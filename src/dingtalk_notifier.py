#!/usr/bin/env python3
"""
什么值得买好价监控系统 - 钉钉通知模块
"""

import aiohttp
import asyncio
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

class DingTalkNotifier:
    def __init__(self):
        self.session = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取HTTP会话"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    def _generate_sign(self, secret: str, timestamp: str) -> str:
        """生成钉钉加签"""
        string_to_sign = f"{timestamp}\n{secret}"
        string_to_sign_enc = string_to_sign.encode('utf-8')
        secret_enc = secret.encode('utf-8')
        
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        
        return sign
    
    def _build_webhook_url(self, webhook_url: str, secret: Optional[str] = None) -> str:
        """构建带签名的webhook URL"""
        if not secret:
            return webhook_url
        
        timestamp = str(round(time.time() * 1000))
        sign = self._generate_sign(secret, timestamp)
        
        separator = '&' if '?' in webhook_url else '?'
        return f"{webhook_url}{separator}timestamp={timestamp}&sign={sign}"
    
    def _build_text_message(self, content: str, at_mobiles: list = None, is_at_all: bool = False) -> Dict:
        """构建文本消息"""
        message = {
            "msgtype": "text",
            "text": {
                "content": content
            }
        }
        
        if at_mobiles or is_at_all:
            message["at"] = {
                "atMobiles": at_mobiles or [],
                "isAtAll": is_at_all
            }
        
        return message
    
    def _build_markdown_message(self, title: str, text: str, at_mobiles: list = None, is_at_all: bool = False) -> Dict:
        """构建Markdown消息"""
        message = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text
            }
        }
        
        if at_mobiles or is_at_all:
            message["at"] = {
                "atMobiles": at_mobiles or [],
                "isAtAll": is_at_all
            }
        
        return message
    
    def _build_link_message(self, title: str, text: str, message_url: str, pic_url: str = "") -> Dict:
        """构建链接消息"""
        return {
            "msgtype": "link",
            "link": {
                "text": text,
                "title": title,
                "picUrl": pic_url,
                "messageUrl": message_url
            }
        }
    
    def _build_action_card_message(self, title: str, text: str, single_title: str = "", single_url: str = "", 
                                 btn_orientation: str = "0", buttons: list = None) -> Dict:
        """构建ActionCard消息"""
        message = {
            "msgtype": "actionCard",
            "actionCard": {
                "title": title,
                "text": text,
                "btnOrientation": btn_orientation
            }
        }
        
        if single_title and single_url:
            message["actionCard"]["singleTitle"] = single_title
            message["actionCard"]["singleURL"] = single_url
        elif buttons:
            message["actionCard"]["btns"] = buttons
        
        return message
    
    async def send_text(self, webhook_url: str, content: str, secret: str = "", 
                       at_mobiles: list = None, is_at_all: bool = False) -> bool:
        """发送文本消息"""
        try:
            url = self._build_webhook_url(webhook_url, secret)
            message = self._build_text_message(content, at_mobiles, is_at_all)
            
            session = await self._get_session()
            async with session.post(url, json=message, headers={'Content-Type': 'application/json'}) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('errcode') == 0:
                        logger.info("钉钉文本消息发送成功")
                        return True
                    else:
                        logger.error(f"钉钉消息发送失败: {result.get('errmsg', '未知错误')}")
                else:
                    logger.error(f"钉钉消息发送HTTP错误: {response.status}")
                    
        except Exception as e:
            logger.error(f"发送钉钉文本消息异常: {e}")
        
        return False
    
    async def send_markdown(self, webhook_url: str, title: str, text: str, secret: str = "",
                          at_mobiles: list = None, is_at_all: bool = False) -> bool:
        """发送Markdown消息"""
        try:
            url = self._build_webhook_url(webhook_url, secret)
            message = self._build_markdown_message(title, text, at_mobiles, is_at_all)
            
            session = await self._get_session()
            async with session.post(url, json=message, headers={'Content-Type': 'application/json'}) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('errcode') == 0:
                        logger.info("钉钉Markdown消息发送成功")
                        return True
                    else:
                        logger.error(f"钉钉消息发送失败: {result.get('errmsg', '未知错误')}")
                else:
                    logger.error(f"钉钉消息发送HTTP错误: {response.status}")
                    
        except Exception as e:
            logger.error(f"发送钉钉Markdown消息异常: {e}")
        
        return False
    
    async def send_link(self, webhook_url: str, title: str, text: str, message_url: str, 
                       pic_url: str = "", secret: str = "") -> bool:
        """发送链接消息"""
        try:
            url = self._build_webhook_url(webhook_url, secret)
            message = self._build_link_message(title, text, message_url, pic_url)
            
            session = await self._get_session()
            async with session.post(url, json=message, headers={'Content-Type': 'application/json'}) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('errcode') == 0:
                        logger.info("钉钉链接消息发送成功")
                        return True
                    else:
                        logger.error(f"钉钉消息发送失败: {result.get('errmsg', '未知错误')}")
                else:
                    logger.error(f"钉钉消息发送HTTP错误: {response.status}")
                    
        except Exception as e:
            logger.error(f"发送钉钉链接消息异常: {e}")
        
        return False
    
    async def send_action_card(self, webhook_url: str, title: str, text: str, secret: str = "",
                             single_title: str = "", single_url: str = "", 
                             btn_orientation: str = "0", buttons: list = None) -> bool:
        """发送ActionCard消息"""
        try:
            url = self._build_webhook_url(webhook_url, secret)
            message = self._build_action_card_message(title, text, single_title, single_url, btn_orientation, buttons)
            
            session = await self._get_session()
            async with session.post(url, json=message, headers={'Content-Type': 'application/json'}) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('errcode') == 0:
                        logger.info("钉钉ActionCard消息发送成功")
                        return True
                    else:
                        logger.error(f"钉钉消息发送失败: {result.get('errmsg', '未知错误')}")
                else:
                    logger.error(f"钉钉消息发送HTTP错误: {response.status}")
                    
        except Exception as e:
            logger.error(f"发送钉钉ActionCard消息异常: {e}")
        
        return False
    
    async def send_message(self, webhook_url: str, message: str, secret: str = "", 
                          message_type: str = "text", **kwargs) -> bool:
        """通用消息发送方法"""
        if message_type == "text":
            return await self.send_text(webhook_url, message, secret, 
                                      kwargs.get('at_mobiles'), kwargs.get('is_at_all', False))
        elif message_type == "markdown":
            title = kwargs.get('title', '什么值得买好价提醒')
            return await self.send_markdown(webhook_url, title, message, secret,
                                          kwargs.get('at_mobiles'), kwargs.get('is_at_all', False))
        elif message_type == "link":
            return await self.send_link(webhook_url, kwargs.get('title', '好价提醒'), 
                                      message, kwargs.get('message_url', ''), 
                                      kwargs.get('pic_url', ''), secret)
        elif message_type == "actionCard":
            return await self.send_action_card(webhook_url, kwargs.get('title', '好价提醒'), 
                                             message, secret, kwargs.get('single_title', ''),
                                             kwargs.get('single_url', ''), kwargs.get('btn_orientation', '0'),
                                             kwargs.get('buttons'))
        else:
            logger.error(f"不支持的消息类型: {message_type}")
            return False
    
    async def test_webhook(self, webhook_url: str, secret: str = "") -> bool:
        """测试钉钉webhook"""
        try:
            message = {
                "msgtype": "text",
                "text": {
                    "content": "🧪 什么值得买监控系统测试消息\n\n这是一条测试消息，用于验证钉钉机器人配置是否正确。\n\n如果您收到此消息，说明配置成功！"
                }
            }
            
            url = self._build_webhook_url(webhook_url, secret)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=message, timeout=10) as response:
                    result = await response.json()
                    return result.get('errcode') == 0
        except Exception as e:
            logger.error(f"测试webhook失败: {e}")
            return False
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session and not self.session.closed:
            await self.session.close()

# 测试函数
async def test_dingtalk():
    """测试钉钉通知功能"""
    notifier = DingTalkNotifier()
    
    # 这里需要替换为实际的webhook URL和secret
    webhook_url = "https://oapi.dingtalk.com/robot/send?access_token=YOUR_ACCESS_TOKEN"
    secret = "YOUR_SECRET"  # 可选
    
    try:
        # 测试文本消息
        success = await notifier.test_webhook(webhook_url, secret)
        print(f"测试结果: {'成功' if success else '失败'}")
        
        # 测试Markdown消息
        markdown_text = """
## 🔔 什么值得买好价提醒

### 📦 商品信息
- **商品名称**: RTX 4060 Ti 显卡
- **价格**: ¥2999
- **商城**: 京东
- **时间**: 2024-01-01 12:00

[查看详情](https://www.smzdm.com)
        """
        
        success = await notifier.send_markdown(webhook_url, "好价提醒", markdown_text, secret)
        print(f"Markdown消息测试: {'成功' if success else '失败'}")
        
    finally:
        await notifier.close()

if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_dingtalk())