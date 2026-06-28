#!/usr/bin/env python3
"""
什么值得买好价监控系统 - 数据库模块
"""

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Iterator
import os

class DatabaseManager:
    def __init__(self, db_path: str = "smzdm_monitor.db"):
        self.db_path = db_path
        self.init_database()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=15, check_same_thread=False)
        conn.execute("PRAGMA busy_timeout = 15000")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def init_database(self):
        """初始化数据库，创建所有必要的表"""
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            cursor = conn.cursor()
            
            # 监控方案表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS monitor_schemes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    refresh_interval INTEGER DEFAULT 60,
                    dingtalk_webhook TEXT,
                    dingtalk_secret TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            self._ensure_columns(cursor, 'monitor_schemes', {
                'wechat_enabled': 'BOOLEAN DEFAULT 0',
                'wechat_account_id': "TEXT DEFAULT ''",
                'wechat_targets': "TEXT DEFAULT ''",
                'wxpusher_enabled': 'BOOLEAN DEFAULT 0',
                'wxpusher_app_token': "TEXT DEFAULT ''",
                'wxpusher_uid': "TEXT DEFAULT ''",
            })
            
            # 关键词表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scheme_id INTEGER NOT NULL,
                    keyword TEXT NOT NULL,
                    category_id TEXT DEFAULT '',
                    brand_id TEXT DEFAULT '',
                    mall_id TEXT DEFAULT '',
                    order_type TEXT DEFAULT 'time',
                    price_min REAL DEFAULT 0,
                    price_max REAL DEFAULT 999999,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (scheme_id) REFERENCES monitor_schemes (id) ON DELETE CASCADE
                )
            ''')
            
            # 商品历史记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS product_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scheme_id INTEGER NOT NULL,
                    keyword_id INTEGER NOT NULL,
                    article_id TEXT NOT NULL,
                    article_title TEXT NOT NULL,
                    article_price TEXT,
                    article_mall TEXT,
                    article_url TEXT,
                    article_date TEXT,
                    raw_data TEXT,
                    is_notified BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (scheme_id) REFERENCES monitor_schemes (id) ON DELETE CASCADE,
                    FOREIGN KEY (keyword_id) REFERENCES keywords (id) ON DELETE CASCADE,
                    UNIQUE(article_id, keyword_id)
                )
            ''')
            
            # 通知记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notification_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scheme_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    notification_type TEXT DEFAULT 'dingtalk',
                    status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (scheme_id) REFERENCES monitor_schemes (id) ON DELETE CASCADE,
                    FOREIGN KEY (product_id) REFERENCES product_history (id) ON DELETE CASCADE
                )
            ''')

            # 全局配置表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS global_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.executemany('''
                INSERT OR IGNORE INTO global_settings (key, value, description)
                VALUES (?, ?, ?)
            ''', [
                ('image_server_host', '127.0.0.1', '图片服务器主机地址'),
                ('image_server_port', '18080', '图片服务器端口'),
                ('server_port', '18080', '后端服务监听端口'),
                ('dingtalk_webhook', '', '全局钉钉 Webhook URL'),
                ('dingtalk_secret', '', '全局钉钉加签密钥'),
                ('wxpusher_app_token', '', '全局 WxPusher AppToken'),
                ('wxpusher_uid', '', '全局 WxPusher UID'),
            ])
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_keywords_scheme ON keywords(scheme_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_scheme ON product_history(scheme_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_keyword ON product_history(keyword_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_article ON product_history(article_id)')
            
            conn.commit()
    
    # 监控方案管理
    def _ensure_columns(self, cursor: sqlite3.Cursor, table: str, columns: Dict[str, str]) -> None:
        cursor.execute(f'PRAGMA table_info({table})')
        existing = {row[1] for row in cursor.fetchall()}
        for name, definition in columns.items():
            if name not in existing:
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')

    def create_scheme(self, name: str, description: str = "", refresh_interval: int = 60, 
                     dingtalk_webhook: str = "", dingtalk_secret: str = "",
                     wechat_enabled: bool = False, wechat_account_id: str = "",
                     wechat_targets: str = "",
                     wxpusher_enabled: bool = False, wxpusher_app_token: str = "",
                     wxpusher_uid: str = "") -> int:
        """创建监控方案"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO monitor_schemes (
                    name, description, refresh_interval, dingtalk_webhook, dingtalk_secret,
                    wechat_enabled, wechat_account_id, wechat_targets,
                    wxpusher_enabled, wxpusher_app_token, wxpusher_uid
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                name, description, refresh_interval, dingtalk_webhook, dingtalk_secret,
                int(bool(wechat_enabled)), wechat_account_id, wechat_targets,
                int(bool(wxpusher_enabled)), wxpusher_app_token, wxpusher_uid,
            ))
            return cursor.lastrowid
    
    def get_schemes(self) -> List[Dict]:
        """获取所有监控方案"""
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM monitor_schemes ORDER BY created_at DESC')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_scheme(self, scheme_id: int) -> Optional[Dict]:
        """获取单个监控方案"""
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM monitor_schemes WHERE id = ?', (scheme_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_scheme(self, scheme_id: int, **kwargs) -> bool:
        """更新监控方案"""
        if not kwargs:
            return False

        _ALLOWED_SCHEME_COLUMNS = {
            'name', 'description', 'is_active', 'refresh_interval',
            'dingtalk_webhook', 'dingtalk_secret',
            'wechat_enabled', 'wechat_account_id', 'wechat_targets',
            'wxpusher_enabled', 'wxpusher_app_token', 'wxpusher_uid',
            'updated_at',
        }
        for key in kwargs:
            if key not in _ALLOWED_SCHEME_COLUMNS:
                raise ValueError(f'Invalid column name: {key}')

        # 添加更新时间
        kwargs['updated_at'] = datetime.now().isoformat()
        
        set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [scheme_id]
        
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(f'UPDATE monitor_schemes SET {set_clause} WHERE id = ?', values)
            return cursor.rowcount > 0
    
    def delete_scheme(self, scheme_id: int) -> bool:
        """删除监控方案"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM monitor_schemes WHERE id = ?', (scheme_id,))
            return cursor.rowcount > 0
    
    # 关键词管理
    def add_keyword(self, scheme_id: int, keyword: str, **kwargs) -> int:
        """添加关键词"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO keywords (scheme_id, keyword, category_id, brand_id, mall_id, 
                                    order_type, price_min, price_max)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                scheme_id, keyword,
                kwargs.get('category_id', ''),
                kwargs.get('brand_id', ''),
                kwargs.get('mall_id', ''),
                kwargs.get('order_type', 'time'),
                kwargs.get('price_min', 0),
                kwargs.get('price_max', 999999)
            ))
            return cursor.lastrowid
    
    def get_keywords(self, scheme_id: int) -> List[Dict]:
        """获取方案的所有关键词"""
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM keywords WHERE scheme_id = ? AND is_active = 1', (scheme_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def update_keyword(self, keyword_id: int, **kwargs) -> bool:
        """更新关键词"""
        if not kwargs:
            return False

        _ALLOWED_KEYWORD_COLUMNS = {
            'keyword', 'category_id', 'brand_id', 'mall_id',
            'order_type', 'price_min', 'price_max', 'is_active',
        }
        for key in kwargs:
            if key not in _ALLOWED_KEYWORD_COLUMNS:
                raise ValueError(f'Invalid column name: {key}')

        set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [keyword_id]
        
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(f'UPDATE keywords SET {set_clause} WHERE id = ?', values)
            return cursor.rowcount > 0
    
    def delete_keyword(self, keyword_id: int) -> bool:
        """删除关键词"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE keywords SET is_active = 0 WHERE id = ?', (keyword_id,))
            return cursor.rowcount > 0
    
    # 商品历史记录管理
    def add_product(self, scheme_id: int, keyword_id: int, product_data: Dict) -> Optional[int]:
        """添加商品记录"""
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO product_history 
                    (scheme_id, keyword_id, article_id, article_title, article_price, 
                     article_mall, article_url, article_date, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    scheme_id, keyword_id,
                    product_data.get('article_id', ''),
                    product_data.get('article_title', ''),
                    product_data.get('article_price', ''),
                    product_data.get('article_mall', ''),
                    product_data.get('article_url', ''),
                    product_data.get('article_format_date', ''),
                    json.dumps(product_data, ensure_ascii=False)
                ))
                return cursor.lastrowid if cursor.rowcount > 0 else None
        except sqlite3.IntegrityError:
            return None
    
    def get_recent_products(self, scheme_id: int, limit: int = 50) -> List[Dict]:
        """获取最近的商品记录"""
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.*, k.keyword 
                FROM product_history p
                JOIN keywords k ON p.keyword_id = k.id
                WHERE p.scheme_id = ?
                ORDER BY p.created_at DESC
                LIMIT ?
            ''', (scheme_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def has_keyword_history(self, keyword_id: int) -> bool:
        """检查关键词是否已有商品历史。"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM product_history WHERE keyword_id = ? LIMIT 1', (keyword_id,))
            return cursor.fetchone() is not None
    
    def mark_as_notified(self, product_id: int) -> bool:
        """标记商品已通知"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE product_history SET is_notified = 1 WHERE id = ?', (product_id,))
            return cursor.rowcount > 0
    
    # 通知记录管理
    def add_notification_log(self, scheme_id: int, product_id: int, 
                           notification_type: str = 'dingtalk', 
                           status: str = 'success', 
                           error_message: str = '') -> int:
        """添加通知记录"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO notification_logs (scheme_id, product_id, notification_type, status, error_message)
                VALUES (?, ?, ?, ?, ?)
            ''', (scheme_id, product_id, notification_type, status, error_message))
            return cursor.lastrowid
    
    def get_notification_stats(self, scheme_id: int) -> Dict:
        """获取通知统计"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM notification_logs 
                WHERE scheme_id = ? AND DATE(sent_at) = DATE('now')
            ''', (scheme_id,))
            row = cursor.fetchone()
            return {
                'total': row[0] or 0,
                'success': row[1] or 0,
                'failed': row[2] or 0
            }

    # 系统配置管理
    def get_config(self, config_key: str) -> Optional[str]:
        """获取系统配置"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM global_settings WHERE key = ?', (config_key,))
            row = cursor.fetchone()
            if row:
                return row[0]

            # 兼容早期版本的 system_config 表。
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_config'")
            if cursor.fetchone():
                cursor.execute('SELECT config_value FROM system_config WHERE config_key = ?', (config_key,))
                row = cursor.fetchone()
                if row:
                    return row[0]

            return None

    def set_config(self, config_key: str, config_value: str, description: str = '') -> bool:
        """设置系统配置"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO global_settings (key, value, description, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    description = CASE
                        WHEN excluded.description = '' THEN global_settings.description
                        ELSE excluded.description
                    END,
                    updated_at = excluded.updated_at
            ''', (config_key, config_value, description, datetime.now().isoformat()))
            return cursor.rowcount > 0

    def get_global_settings(self) -> Dict[str, Dict[str, str]]:
        """获取所有全局配置"""
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT key, value, description, updated_at FROM global_settings ORDER BY key')
            return {row['key']: dict(row) for row in cursor.fetchall()}

    def update_global_settings(self, settings: Dict[str, str]) -> None:
        """批量更新全局配置"""
        descriptions = {
            'image_server_host': '图片服务器主机地址',
            'image_server_port': '图片服务器端口',
            'server_port': '后端服务监听端口',
            'dingtalk_webhook': '全局钉钉 Webhook URL',
            'dingtalk_secret': '全局钉钉加签密钥',
        }
        for key, value in settings.items():
            self.set_config(key, str(value), descriptions.get(key, ''))
    
    def get_image_server_config(self) -> Dict[str, str]:
        """获取图片服务器配置"""
        host = self.get_config('image_server_host') or 'localhost'
        port = self.get_config('image_server_port') or '18080'
        return {
            'host': host,
            'port': int(port)
        }

if __name__ == "__main__":
    # 测试数据库
    db = DatabaseManager("test.db")
    
    # 创建测试方案
    scheme_id = db.create_scheme(
        name="RTX显卡监控",
        description="监控RTX系列显卡好价",
        refresh_interval=60
    )
    
    # 添加测试关键词
    keyword_id = db.add_keyword(scheme_id, "RTX 4060", order_type="time")
    
    print(f"创建方案ID: {scheme_id}")
    print(f"创建关键词ID: {keyword_id}")
    print("数据库测试完成！")
