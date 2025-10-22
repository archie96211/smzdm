#!/usr/bin/env python3
"""
什么值得买好价监控系统 - 图片缓存模块
"""

import os
import hashlib
import aiohttp
import asyncio
from urllib.parse import urlparse
from pathlib import Path
import logging
from typing import Optional
from . import runtime

logger = logging.getLogger(__name__)

class ImageCache:
    def __init__(self, cache_dir: str = None, db_path: str = None):
        """
        初始化图片缓存
        
        Args:
            cache_dir: 缓存目录路径
        """
        self.cache_dir = Path(cache_dir) if cache_dir else runtime.get_images_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = None
        self._db = None
        self.db_path = db_path or str(runtime.get_database_path())
    
    def _get_db(self):
        """获取数据库实例"""
        if self._db is None:
            from .database import DatabaseManager
            self._db = DatabaseManager(self.db_path)
        return self._db
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取HTTP会话"""
        if self.session is None or self.session.closed:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session
    
    def _get_cache_filename(self, url: str) -> str:
        """
        根据URL生成缓存文件名
        
        Args:
            url: 图片URL
            
        Returns:
            缓存文件名
        """
        # 使用URL的MD5哈希作为文件名
        url_hash = hashlib.md5(url.encode()).hexdigest()
        
        # 尝试从URL中提取文件扩展名
        parsed_url = urlparse(url)
        path = parsed_url.path.lower()
        
        # 常见图片扩展名
        extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
        ext = '.jpg'  # 默认扩展名
        
        for extension in extensions:
            if extension in path:
                ext = extension
                break
        
        return f"{url_hash}{ext}"
    
    def _get_cache_path(self, url: str) -> Path:
        """
        获取缓存文件路径
        
        Args:
            url: 图片URL
            
        Returns:
            缓存文件路径
        """
        filename = self._get_cache_filename(url)
        return self.cache_dir / filename
    
    async def download_image(self, url: str) -> Optional[Path]:
        """
        下载图片到本地缓存
        
        Args:
            url: 图片URL
            
        Returns:
            缓存文件路径，如果下载失败返回None
        """
        try:
            cache_path = self._get_cache_path(url)
            
            # 如果文件已存在，直接返回路径
            if cache_path.exists():
                logger.info(f"图片已缓存: {url} -> {cache_path}")
                return cache_path
            
            session = await self._get_session()
            
            logger.info(f"开始下载图片: {url}")
            
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.read()
                    
                    # 写入缓存文件
                    with open(cache_path, 'wb') as f:
                        f.write(content)
                    
                    logger.info(f"图片下载成功: {url} -> {cache_path}")
                    return cache_path
                else:
                    logger.error(f"图片下载失败: {url}, 状态码: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"下载图片时出错: {url}, 错误: {e}")
            return None
    
    def get_cached_image_path(self, url: str) -> Optional[Path]:
        """
        获取已缓存的图片路径
        
        Args:
            url: 图片URL
            
        Returns:
            缓存文件路径，如果不存在返回None
        """
        cache_path = self._get_cache_path(url)
        return cache_path if cache_path.exists() else None
    
    def _build_public_base_url(self, server_host: str = "localhost", server_port: int = 18080) -> str:
        host = str(server_host or "localhost").strip().rstrip("/")
        if "://" in host:
            parsed = urlparse(host)
        else:
            parsed = urlparse(f"//{host}", scheme="http")

        scheme = parsed.scheme or "http"
        netloc = parsed.netloc or parsed.path
        path = parsed.path if parsed.netloc else ""

        if server_port and ":" not in netloc.rsplit("@", 1)[-1]:
            default_port = 443 if scheme == "https" else 80
            if int(server_port) != default_port:
                netloc = f"{netloc}:{int(server_port)}"

        return f"{scheme}://{netloc}{path.rstrip('/')}"

    def get_local_url(self, url: str, server_host: str = "localhost", server_port: int = 18080) -> str:
        """
        获取图片的本地访问URL
        
        Args:
            url: 原始图片URL
            server_host: 服务器主机地址
            server_port: 服务器端口
            
        Returns:
            本地访问URL
        """
        filename = self._get_cache_filename(url)
        return f"{self._build_public_base_url(server_host, server_port)}/images/{filename}"

    async def cache_and_get_local_url(self, url: str, server_host: str = None, server_port: int = None) -> Optional[str]:
        """
        缓存图片并返回本地访问URL
        
        Args:
            url: 原始图片URL
            server_host: 服务器主机地址（可选，从全局配置获取）
            server_port: 服务器端口（可选，从全局配置获取）
            
        Returns:
            本地访问URL，如果缓存失败返回None
        """
        # 如果没有提供服务器配置，从全局配置获取
        if server_host is None or server_port is None:
            db = self._get_db()
            config = db.get_image_server_config()
            server_host = config['host']
            server_port = config['port']
        
        cache_path = await self.download_image(url)
        if cache_path:
            return self.get_local_url(url, server_host, server_port)
        return None

    async def cache_and_get_path(self, url: str) -> Optional[Path]:
        """Cache an image and return the local file path."""
        return await self.download_image(url)
    
    def clear_cache(self):
        """清空缓存目录"""
        try:
            for file_path in self.cache_dir.glob("*"):
                if file_path.is_file():
                    file_path.unlink()
            logger.info("缓存清空成功")
        except Exception as e:
            logger.error(f"清空缓存时出错: {e}")
    
    def get_cache_size(self) -> int:
        """
        获取缓存大小（字节）
        
        Returns:
            缓存大小
        """
        total_size = 0
        try:
            for file_path in self.cache_dir.glob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except Exception as e:
            logger.error(f"计算缓存大小时出错: {e}")
        return total_size
    
    def get_cache_count(self) -> int:
        """
        获取缓存文件数量
        
        Returns:
            缓存文件数量
        """
        try:
            return len(list(self.cache_dir.glob("*")))
        except Exception as e:
            logger.error(f"计算缓存文件数量时出错: {e}")
            return 0
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session and not self.session.closed:
            await self.session.close()

# 全局图片缓存实例
image_cache = ImageCache()

async def test_image_cache():
    """测试图片缓存功能"""
    test_urls = [
        "http://y.zdmimg.com/202510/27/68ff28dca89ef5581.png_d320.jpg",
        "https://gimg2.baidu.com/image_search/src=http%3A%2F%2Fimage109.360doc.com%2FDownloadImg%2F2025%2F04%2F0321%2F296122601_4_20250403090445718&refer=http%3A%2F%2Fimage109.360doc.com&app=2002&size=f9999,10000&q=a80&n=0&g=0n&fmt=auto?sec=1764143176&t=184e57ca29793a2188ca33d29ade2b8f"
    ]
    
    cache = ImageCache()
    
    for url in test_urls:
        print(f"测试缓存图片: {url}")
        local_url = await cache.cache_and_get_local_url(url)
        if local_url:
            print(f"✅ 缓存成功，本地URL: {local_url}")
        else:
            print(f"❌ 缓存失败")
        print("-" * 50)
    
    print(f"缓存统计:")
    print(f"- 文件数量: {cache.get_cache_count()}")
    print(f"- 缓存大小: {cache.get_cache_size() / 1024:.2f} KB")
    
    await cache.close()

if __name__ == "__main__":
    asyncio.run(test_image_cache())
