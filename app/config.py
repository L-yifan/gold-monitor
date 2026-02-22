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
HISTORY_KEEP_HOURS = 24   # 数据清理：保留小时数（注：金价历史已改为按自然日清理，此配置保留供其他用途）
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
# 节假日 API 配置（按优先级排序）
HOLIDAY_API_URLS = [
    # 百度日历 API（主要）
    ("baidu", "https://sp0.baidu.com/8aQDcjqpAAV3otqbppnN2DJv/api.php?resource_id=6017&query={year}年节假日"),
    # timor.tech 免费 API（备用1）
    ("timor", "https://timor.tech/api/holiday/year/{year}"),
    # 聚合数据免费 API（备用2，需要Key，这里保留接口仅供参考）
    ("juhe", "https://api.juhe.cn/calendar/month"),
]

HOLIDAY_API_URL = HOLIDAY_API_URLS[0][1]  # 保留兼容性
HOLIDAY_CACHE_TTL = 86400  # 节假日数据缓存有效期（24小时）

# 智能缓存配置
HOLIDAY_CACHE_DIR = DATA_DIR  # 缓存目录
MAX_CACHED_YEARS = 3  # 内存中最多缓存3年的数据

# ==================== 交易所交易日历配置 ====================
EXCHANGE_CALENDAR_URL = "https://www.sse.com.cn/disclosure/dealinstruc/closed/"  # 上交所休市安排页面
EXCHANGE_CALENDAR_FILE = os.path.join(DATA_DIR, "exchange_calendar.json")  # 缓存文件
EXCHANGE_CALENDAR_CACHE_DIR = DATA_DIR  # 缓存目录
EXCHANGE_CALENDAR_UPDATE_DAY = 1  # 每月1日自动更新

# ==================== 黄金交易所休市安排配置 ====================
SGE_HOLIDAY_URL = "https://www.sge.com.cn/xwzx/ssjg?p=1&focus=%25E4%25BC%2591%25E5%25B8%2582"
SGE_HOLIDAY_CACHE_FILE = os.path.join(DATA_DIR, "sge_holidays.json")
SGE_HOLIDAY_CACHE_TTL = 30 * 24 * 3600  # 30天缓存
 
# 采集频率配置
FETCH_INTERVAL_TRADING = 5       # 交易时间内采集间隔（秒）
FETCH_INTERVAL_NON_TRADING = 300  # 非交易时间采集间隔（秒）
