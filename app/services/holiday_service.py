# -*- coding: utf-8 -*-
"""
智能节假日服务模块
支持：自动计算、多API降级、LRU缓存、持久化
"""

import time
import json
import os
import threading
from datetime import datetime, timedelta
from collections import OrderedDict

from app.config import (
    HOLIDAY_API_URLS, 
    HOLIDAY_CACHE_TTL, 
    HOLIDAY_CACHE_DIR,
    MAX_CACHED_YEARS
)
from app.utils.lunar_holiday_calculator import (
    get_holidays_as_set,
    calculate_all_legal_holidays,
    apply_adjustments,
    LUNARDATE_AVAILABLE
)
from app.services.exchange_calendar import get_exchange_holidays
from app.services.exchange_calendar_crawler import (
    fetch_exchange_holidays_with_status,
)


class HolidayCacheManager:
    """
    智能节假日缓存管理器
    - LRU内存缓存（限制最多3年）
    - 持久化存储
    - 定时批量写入
    """
    
    def __init__(self, max_years=3):
        self._max_years = max_years
        self._memory_cache = OrderedDict()  # LRU: {year: {data, source, expires, timestamp, has_adjustments}}
        self._cache_file = os.path.join(HOLIDAY_CACHE_DIR, "holiday_cache.json")
        self._dirty = False  # 是否有未写入的更改
        self._last_save_time = 0
        self._save_interval = 3600  # 1小时写入一次
        self._lock = threading.Lock()
        
        # 启动时加载缓存
        self._load_from_disk()
    
    def _load_from_disk(self):
        """从磁盘加载缓存"""
        if not os.path.exists(self._cache_file):
            return
        
        try:
            with open(self._cache_file, 'r', encoding='utf-8') as f:
                disk_cache = json.load(f)
            
            metadata = disk_cache.get("metadata", {})
            cache_data = disk_cache.get("cache", {})
            
            # 只加载最近的数据
            current_year = datetime.now().year
            for year_str, data in cache_data.items():
                year = int(year_str)
                # 保留当前年份 ±2 年的数据
                if abs(year - current_year) <= 2:
                    self._memory_cache[year] = data
            
            print(f"[节假日缓存] 从磁盘加载了 {len(self._memory_cache)} 年的数据")
            
        except Exception as e:
            print(f"[节假日缓存] 加载失败: {e}")
    
    def save_to_disk(self, force=False):
        """保存缓存到磁盘"""
        with self._lock:
            now = time.time()
            
            # 检查是否需要写入
            if not force and now - self._last_save_time < self._save_interval:
                return
            
            if not self._dirty and not force:
                return
            
            try:
                # 读取现有数据，合并内存缓存
                disk_data = {"metadata": {"version": "2.0"}, "cache": {}}
                
                if os.path.exists(self._cache_file):
                    with open(self._cache_file, 'r', encoding='utf-8') as f:
                        disk_data = json.load(f)
                
                # 更新缓存
                for year, data in self._memory_cache.items():
                    disk_data["cache"][str(year)] = data
                
                # 写入临时文件再原子替换
                temp_file = self._cache_file + ".tmp"
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(disk_data, f, ensure_ascii=False, indent=2)
                
                os.replace(temp_file, self._cache_file)
                
                self._last_save_time = now
                self._dirty = False
                print(f"[节假日缓存] 已保存到磁盘")
                
            except Exception as e:
                print(f"[节假日缓存] 保存失败: {e}")
    
    def get(self, year):
        """获取指定年份的节假日数据"""
        with self._lock:
            if year in self._memory_cache:
                # 移到末尾（LRU）
                self._memory_cache.move_to_end(year)
                data = self._memory_cache[year]
                
                # 检查是否过期
                if data.get("expires", 0) > time.time():
                    return data
                # 内置/计算数据永不过期
                elif data.get("source") in ("builtin", "calculated"):
                    return data
            
            return None
    
    def set(self, year, data):
        """设置缓存"""
        with self._lock:
            # LRU淘汰
            if len(self._memory_cache) >= self._max_years:
                # 移除最旧的
                oldest_year, _ = self._memory_cache.popitem(last=False)
            
            self._memory_cache[year] = data
            self._dirty = True
    
    def mark_dirty(self):
        """标记为脏数据"""
        self._dirty = True


# 全局缓存管理器
_cache_manager = None


def get_cache_manager():
    """获取缓存管理器单例"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = HolidayCacheManager(MAX_CACHED_YEARS)
    return _cache_manager


def fetch_holidays_from_api(year):
    """
    从多个API获取节假日数据
    
    返回: (holidays_set, adjustments_dict, source_name) 或 (None, None, None)
    """
    holidays = set()
    adjustments = {}
    source = None
    
    for api_name, api_url in HOLIDAY_API_URLS:
        try:
            url = api_url.format(year=year)
            import requests
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                # 解析节假日数据
                if "data" in data and data["data"]:
                    item = data["data"][0]
                    
                    # 解析 holiday 字段
                    if "holiday" in item:
                        for holiday in item["holiday"]:
                            if "date" in holiday:
                                holidays.add(holiday["date"])
                    
                    # 解析 holidays 字段
                    elif "holidays" in item:
                        for holiday in item["holidays"]:
                            if "date" in holiday:
                                holidays.add(holiday["date"])
                    
                    # 解析调休数据 (如果有)
                    if "list" in item:
                        for entry in item["list"]:
                            if entry.get("is_down") == "true":
                                adjustments.setdefault("holidays", []).append(entry.get("date", ""))
                            elif entry.get("is_down") == "false":
                                adjustments.setdefault("workdays", []).append(entry.get("date", ""))
                
                if holidays:
                    source = api_name
                    print(f"[节假日] 从 {api_name} 获取 {year} 年数据成功，共 {len(holidays)} 天")
                    break
                    
        except Exception as e:
            print(f"[节假日] {api_name} 获取失败: {e}")
            continue
    
    if not holidays:
        return None, None, None
    
    return holidays, adjustments, source


def calculate_holidays(year):
    """
    自动计算法定节假日（不含调休）
    
    返回: (holidays_set, source)
    """
    holidays = get_holidays_as_set(year)
    source = "calculated"
    
    if holidays:
        print(f"[节假日] 自动计算 {year} 年法定节假日，共 {len(holidays)} 天")
    else:
        print(f"[节假日] 自动计算失败")
    
    return holidays, source


def get_holidays(year=None):
    """
    获取指定年份的节假日集合
    
    优先级:
    1. 内存缓存命中且未过期
    2. 持久化缓存命中且未过期
    3. 年份 >= 2026: 尝试API获取 -> 自动计算
    4. 使用上一年数据估算
    
    返回: set(["2026-01-01", ...])
    """
    if year is None:
        year = datetime.now().year
    
    cache_mgr = get_cache_manager()
    
    # 1. 检查内存缓存
    cached = cache_mgr.get(year)
    if cached:
        return set(cached["data"])
    
    # 2. 尝试获取新数据
    holidays = None
    adjustments = None
    source = None
    source_name = None
    
    if year >= 2026:
        # 2.1 尝试API获取（含调休）
        holidays, adjustments, api_source = fetch_holidays_from_api(year)
        
        if holidays:
            source = "api"  # 统一为api，便于过期判断
            source_name = api_source  # 记录实际来源
            # 应用调休
            if adjustments:
                holidays = apply_adjustments(holidays, adjustments)
        else:
            # 2.2 自动计算
            holidays, calc_source = calculate_holidays(year)
            source = calc_source
    else:
        # 2025及以前使用内置数据（略过，这里不处理）
        holidays = set()
    
    # 3. 如果都失败，使用上一年数据估算
    if not holidays:
        print(f"[节假日] 警告: {year} 年数据获取失败，尝试使用 {year-1} 年数据估算")
        prev_holidays = get_holidays(year - 1)
        if prev_holidays:
            # 简单平移（不一定准确）
            holidays = set()
            for d in prev_holidays:
                try:
                    old_date = datetime.strptime(d, "%Y-%m-%d")
                    new_date = old_date.replace(year=year)
                    holidays.add(new_date.strftime("%Y-%m-%d"))
                except:
                    pass
            source = "fallback"
    
    # 4. 缓存结果
    if holidays:
        # 根据来源设置不同的过期时间
        if source == "api":
            expires = time.time() + 30 * 24 * 3600  # 30天
        elif source == "calculated":
            expires = time.time() + 90 * 24 * 3600  # 90天
        elif source == "fallback":
            expires = time.time() + 7 * 24 * 3600  # 7天
        else:
            expires = time.time() + float('inf')
        
        cache_data = {
            "data": list(holidays),
            "source": source,
            "source_name": source_name if source == "api" else None,
            "expires": expires,
            "timestamp": time.time(),
            "has_adjustments": bool(adjustments)
        }
        cache_mgr.set(year, cache_data)
        cache_mgr.mark_dirty()
    
    return holidays if holidays else set()


def is_holiday(dt=None, market_type="fund"):
    """
    判断指定日期是否为节假日
    
    参数:
        dt: datetime 对象，默认为当前时间
        market_type: 市场类型 "fund"(基金/股票) 或 "gold"(黄金)
    
    返回:
        bool: 是否为节假日
    """
    if dt is None:
        dt = datetime.now()
    
    date_str = dt.strftime("%Y-%m-%d")
    
    if market_type == "fund":
        # 基金/股票使用上交所日历爬虫
        holidays, has_calendar = fetch_exchange_holidays_with_status(dt.year)
        if not holidays and not has_calendar:
            # 爬虫失败且无缓存时，回退到本地节假日服务避免误判开市
            holidays = get_holidays(dt.year)
    else:
        # 黄金使用上金所（SGE）混合日历
        holidays = get_exchange_holidays(dt.year)
    
    return date_str in holidays


def check_and_save_cache():
    """定时保存缓存（可由外部调用）"""
    cache_mgr = get_cache_manager()
    cache_mgr.save_to_disk()


# 启动时预热缓存
def warmup_cache():
    """预热缓存：加载当前年份及前后年份"""
    current_year = datetime.now().year
    
    for year in range(current_year - 1, current_year + 2):
        if year >= 2026:
            get_holidays(year)
    
    # 尝试保存
    get_cache_manager().save_to_disk(force=True)
    print(f"[节假日] 缓存预热完成")


if __name__ == "__main__":
    # 测试
    print("=== 测试节假日获取 ===")
    
    # 预热
    warmup_cache()
    
    # 测试
    for year in [2025, 2026, 2027, 2028]:
        holidays = get_holidays(year)
        print(f"\n{year}年: {len(holidays)} 天")
        print(sorted(holidays)[:10], "...")
    
    # 测试日期判断
    print("\n=== 测试日期判断 ===")
    test_dates = [
        datetime(2026, 1, 1),
        datetime(2026, 2, 16),
        datetime(2026, 4, 4),
        datetime(2026, 5, 1),
        datetime(2026, 10, 1),
        datetime(2026, 10, 6),
        datetime(2026, 3, 15),  # 周六
    ]
    
    for dt in test_dates:
        print(f"{dt.strftime('%Y-%m-%d %A')}: {'节假日' if is_holiday(dt) else '工作日'}")
