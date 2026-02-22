# -*- coding: utf-8 -*-
"""
上海黄金交易所交易日历服务模块
支持爬虫自动获取 + 内置数据备用（独立缓存）
"""

import json
import os
from datetime import datetime

from app.config import SGE_HOLIDAY_CACHE_FILE
from app.services.sge_holiday_crawler import fetch_sge_holiday_data


# 内置2026年休市数据（来自上交所官网）
BUILTIN_EXCHANGE_HOLIDAYS = {
    2026: {
        "source": "builtin_2026",
        "holidays": {
            "元旦": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "春节": ["2026-02-15", "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-21", "2026-02-22", "2026-02-23"],
            "清明节": ["2026-04-04", "2026-04-05", "2026-04-06"],
            "劳动节": ["2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05"],
            "端午节": ["2026-06-19", "2026-06-20", "2026-06-21"],
            "中秋节": ["2026-09-25", "2026-09-26", "2026-09-27"],
            "国庆节": ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07"],
        },
        "first_trading_days": {
            "元旦": "2026-01-05",
            "春节": "2026-02-24",
            "清明节": "2026-04-07",
            "劳动节": "2026-05-06",
            "端午节": "2026-06-22",
            "中秋节": "2026-09-28",
            "国庆节": "2026-10-08",
        }
    }
}


class ExchangeCalendarService:
    """交易所交易日历服务"""
    
    def __init__(self):
        self.cache_file = SGE_HOLIDAY_CACHE_FILE
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self):
        cache_dir = os.path.dirname(self.cache_file)
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
    
    def _load_cache(self):
        if not os.path.exists(self.cache_file):
            return None
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    
    def _save_cache(self, data):
        try:
            temp_file = self.cache_file + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, self.cache_file)
            return True
        except:
            return False
    
    def get_holidays(self, year=None):
        """获取指定年份的休市日期集合"""
        if year is None:
            year = datetime.now().year
        
        # 1. 优先使用内置数据
        if year in BUILTIN_EXCHANGE_HOLIDAYS:
            data = BUILTIN_EXCHANGE_HOLIDAYS[year]
            all_dates = set()
            for dates in data.get("holidays", {}).values():
                all_dates.update(dates)
            return all_dates
        
        # 2. 尝试使用SGE爬虫获取
        try:
            sge_data = fetch_sge_holiday_data(year)
            if sge_data:
                all_dates = set(sge_data.get("all_holiday_dates", []))
                if all_dates:
                    return all_dates
        except Exception as e:
            print(f"[交易所日历] SGE爬虫调用失败: {e}")
        
        # 3. 尝试从本地缓存读取
        cache = self._load_cache()
        if cache:
            calendars = cache.get("calendars", {})
            if str(year) in calendars:
                data = calendars[str(year)]
                all_dates = set()
                for dates in data.get("holidays", {}).values():
                    all_dates.update(dates)
                return all_dates
        
        return set()
    
    def get_first_trading_day(self, holiday_name, year=None):
        """获取指定节假日后的首个交易日"""
        if year is None:
            year = datetime.now().year
        
        # 优先使用内置数据
        if year in BUILTIN_EXCHANGE_HOLIDAYS:
            return BUILTIN_EXCHANGE_HOLIDAYS[year].get("first_trading_days", {}).get(holiday_name)
        
        # 尝试SGE爬虫数据
        try:
            sge_data = fetch_sge_holiday_data(year)
            if sge_data:
                result = sge_data.get("first_trading_days", {}).get(holiday_name)
                if result:
                    return result
        except Exception:
            pass
        
        # 尝试从缓存读取
        cache = self._load_cache()
        if cache:
            calendars = cache.get("calendars", {})
            if str(year) in calendars:
                return calendars[str(year)].get("first_trading_days", {}).get(holiday_name)
        
        return None
    
    def get_holiday_name_by_date(self, date_str):
        """根据日期获取节日名称"""
        date = datetime.strptime(date_str, "%Y-%m-%d")
        year = date.year
        
        # 1. 内置数据
        if year in BUILTIN_EXCHANGE_HOLIDAYS:
            holidays = BUILTIN_EXCHANGE_HOLIDAYS[year].get("holidays", {})
            for name, dates in holidays.items():
                if date_str in dates:
                    return name
        
        # 2. SGE爬虫数据
        try:
            sge_data = fetch_sge_holiday_data(year)
            if sge_data:
                for name, dates in sge_data.get("holidays", {}).items():
                    if date_str in dates:
                        return name
        except Exception:
            pass

        # 3. 本地缓存兜底（仅 SGE 独立缓存）
        cache = self._load_cache()
        if cache:
            calendars = cache.get("calendars", {})
            if str(year) in calendars:
                holidays = calendars[str(year)].get("holidays", {})
                for name, dates in holidays.items():
                    if date_str in dates:
                        return name

        return None


# 全局服务实例
_service = None


def get_service():
    global _service
    if _service is None:
        _service = ExchangeCalendarService()
    return _service


def get_exchange_holidays(year=None):
    """获取交易所休市日期集合"""
    return get_service().get_holidays(year)


def get_exchange_first_trading_day(holiday_name, year=None):
    """获取节假日后首个交易日"""
    return get_service().get_first_trading_day(holiday_name, year)


def get_holiday_name_by_date(date_str):
    """根据日期获取节日名称"""
    return get_service().get_holiday_name_by_date(date_str)


if __name__ == "__main__":
    # 测试
    print("=== 测试交易所日历服务 ===")
    
    service = get_service()
    
    # 2026年测试
    holidays = service.get_holidays(2026)
    print(f"\n2026年休市日期 ({len(holidays)}天):")
    print(sorted(holidays))
    
    print(f"\n首个交易日:")
    for name in ["元旦", "春节", "清明节", "劳动节", "端午节", "中秋节", "国庆节"]:
        day = service.get_first_trading_day(name, 2026)
        print(f"  {name}: {day}")
    
    # 测试日期查询
    print(f"\n日期对应的节日:")
    test_dates = ["2026-02-16", "2026-02-20", "2026-02-24", "2026-10-01"]
    for d in test_dates:
        name = service.get_holiday_name_by_date(d)
        print(f"  {d}: {name}")
