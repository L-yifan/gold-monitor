# -*- coding: utf-8 -*-
"""
配置常量模块
包含数据源配置、缓存配置、路径配置等
"""

import os

# ==================== 路径配置 ====================
# 获取项目根目录（app包的上级目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

# 数据文件路径
DATA_FILE = os.path.join(DATA_DIR, 'data.json')
# 旧数据文件路径（用于自动迁移）
OLD_DATA_FILE = os.path.join(BASE_DIR, 'data.json')

# ==================== 数据源配置 ====================
# 数据源列表（按优先级排序）
DATA_SOURCES = [
    {
        "name": "东方财富",
        "type": "eastmoney",
        "enabled": True,
        "timeout": 3,
        "fail_count": 0,
        "mute_until": 0
    },
    {
        "name": "腾讯财经",
        "type": "tencent",
        "enabled": True,
        "timeout": 3,
        "fail_count": 0,
        "mute_until": 0
    },
    {
        "name": "网易财经",
        "type": "netease",
        "enabled": True,
        "timeout": 3,
        "fail_count": 0,
        "mute_until": 0
    },
    {
        "name": "新浪财经",
        "type": "sina",
        "enabled": True,
        "timeout": 3,
        "fail_count": 0,
        "mute_until": 0
    }
]

# ==================== 熔断配置 ====================
MAX_FAIL_COUNT = 3  # 连续失败多少次触发熔断
MUTE_DURATION = 60  # 熔断持续时间（秒）

# ==================== 缓存配置 ====================
CACHE_TTL_SECONDS = 60       # 基金数据缓存有效期（秒）
FUND_STALE_TTL_SECONDS = 300  # 基金数据可接受的过期时间（秒）
HOLDINGS_CACHE_TTL_SECONDS = 10  # 持仓汇总缓存有效期（秒）
HOLDINGS_STALE_TTL_SECONDS = 300  # 持仓汇总可接受的过期时间（秒）
STALE_THRESHOLD_SECONDS = 30  # 金价数据过期阈值（秒）
MAX_FETCH_WORKERS = 10        # 并发获取数据的线程池大小

# ==================== 历史数据配置 ====================
MAX_HISTORY_SIZE = 20000  # 存储历史价格数据 (最多保存 20000 条，约 24 小时以上的数据，5秒一条)
HISTORY_KEEP_HOURS = 24   # 数据清理：保留小时数
RECORDS_KEEP_DAYS = 7     # 手动记录保留天数

# ==================== 基金持仓缓存配置 ====================
PORTFOLIO_CACHE_TTL = 86400  # 基金重仓股配置缓存有效期 (24小时)

# ==================== HTTP 请求配置 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
}

# ==================== 交易时间配置 ====================
# 使用百度日历 API 获取节假日（无需 API Key，免费稳定）
HOLIDAY_API_URL = "https://sp0.baidu.com/8aQDcjqpAAV3otqbppnN2DJv/api.php?resource_id=6017&query={year}年节假日"
HOLIDAY_CACHE_TTL = 86400  # 节假日数据缓存有效期（24小时）

# 采集频率配置
FETCH_INTERVAL_TRADING = 5       # 交易时间内采集间隔（秒）
FETCH_INTERVAL_NON_TRADING = 300  # 非交易时间采集间隔（秒）
