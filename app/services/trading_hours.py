# -*- coding: utf-8 -*-
"""
交易时间服务模块
判断上海黄金交易所 Au99.99 的交易时间状态
"""

import time
import requests
from datetime import datetime, timedelta
from app.config import HOLIDAY_API_URL, HOLIDAY_CACHE_TTL

# 缓存节假日数据
_holiday_cache = {
    "timestamp": 0,
    "holidays": set()
}


def fetch_holidays(year=None):
    """
    从 API 获取中国法定节假日列表
    
    参数:
        year: 年份，默认为当前年份
        
    返回:
        set: 节假日日期字符串集合 (格式: "YYYY-MM-DD")
    """
    global _holiday_cache
    
    now = time.time()
    
    # 检查缓存是否有效
    if now - _holiday_cache["timestamp"] < HOLIDAY_CACHE_TTL:
        return _holiday_cache["holidays"]
    
    if year is None:
        year = datetime.now().year
    
    try:
        url = HOLIDAY_API_URL.format(year=year)
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            holidays = set()
            
            # 解析 API 返回的节假日数据
            # 假设 API 返回格式: {"holidays": [{"date": "2024-02-10", "name": "春节"}, ...]}
            if "holidays" in data:
                for holiday in data["holidays"]:
                    date_str = holiday.get("date", "")
                    if date_str:
                        holidays.add(date_str)
            
            _holiday_cache["timestamp"] = now
            _holiday_cache["holidays"] = holidays
            print(f"[节假日] 已更新 {year} 年节假日数据，共 {len(holidays)} 天")
            return holidays
            
    except Exception as e:
        print(f"[节假日] API 获取失败: {e}")
    
    # 如果获取失败，返回缓存的数据（即使已过期）或空集合
    return _holiday_cache.get("holidays", set())


def is_holiday(dt=None):
    """
    判断指定日期是否为节假日
    
    参数:
        dt: datetime 对象，默认为当前时间
        
    返回:
        bool: 是否为节假日
    """
    if dt is None:
        dt = datetime.now()
    
    date_str = dt.strftime("%Y-%m-%d")
    holidays = fetch_holidays(dt.year)
    
    return date_str in holidays


def get_weekday(dt=None):
    """
    获取星期几 (0=周一, 6=周日)
    
    参数:
        dt: datetime 对象，默认为当前时间
        
    返回:
        int: 星期几 (0-6)
    """
    if dt is None:
        dt = datetime.now()
    return dt.weekday()


def is_trading_day(dt=None):
    """
    判断是否为交易日（周一至周五且非节假日）
    
    参数:
        dt: datetime 对象，默认为当前时间
        
    返回:
        bool: 是否为交易日
    """
    if dt is None:
        dt = datetime.now()
    
    weekday = get_weekday(dt)
    
    # 周六周日不是交易日
    if weekday >= 5:
        return False
    
    # 节假日不是交易日
    if is_holiday(dt):
        return False
    
    return True


def get_trading_status(dt=None):
    """
    获取当前交易状态
    
    参数:
        dt: datetime 对象，默认为当前时间
        
    返回:
        dict: 包含交易状态信息的字典
        {
            "is_trading_time": bool,      # 是否处于交易时间
            "trading_phase": str,         # 交易阶段: "day_session", "night_session", 
                                          #          "day_auction", "night_auction", "closed"
            "phase_name": str,            # 阶段中文名称
            "next_event": str,            # 下一个事件: "day_open", "day_close", "night_open", "night_close"
            "next_event_time": datetime,  # 下一个事件时间
            "time_until_next": int,       # 距离下一个事件的秒数
            "is_holiday": bool,           # 今天是否为节假日
            "weekday": int                # 星期几
        }
    """
    if dt is None:
        dt = datetime.now()
    
    current_time = dt.time()
    weekday = get_weekday(dt)
    holiday = is_holiday(dt)
    
    result = {
        "is_trading_time": False,
        "trading_phase": "closed",
        "phase_name": "休市",
        "next_event": None,
        "next_event_time": None,
        "time_until_next": None,
        "is_holiday": holiday,
        "weekday": weekday
    }
    
    # 如果不是交易日，计算下次开盘时间
    if not is_trading_day(dt):
        next_trading_day = _find_next_trading_day(dt)
        day_open = datetime.combine(next_trading_day, datetime.strptime("09:00", "%H:%M").time())
        
        result["next_event"] = "day_open"
        result["next_event_time"] = day_open
        result["time_until_next"] = int((day_open - dt).total_seconds())
        return result
    
    # 判断当前交易阶段
    # 早市集合竞价: 08:50-08:59
    if current_time >= datetime.strptime("08:50", "%H:%M").time() and \
       current_time < datetime.strptime("08:59", "%H:%M").time():
        result["is_trading_time"] = True
        result["trading_phase"] = "day_auction"
        result["phase_name"] = "早市集合竞价"
        result["next_event"] = "day_open"
        day_open = datetime.combine(dt.date(), datetime.strptime("09:00", "%H:%M").time())
        result["next_event_time"] = day_open
        result["time_until_next"] = int((day_open - dt).total_seconds())
        return result
    
    # 日间交易: 09:00-15:30
    if current_time >= datetime.strptime("09:00", "%H:%M").time() and \
       current_time < datetime.strptime("15:30", "%H:%M").time():
        result["is_trading_time"] = True
        result["trading_phase"] = "day_session"
        result["phase_name"] = "日间交易"
        result["next_event"] = "day_close"
        day_close = datetime.combine(dt.date(), datetime.strptime("15:30", "%H:%M").time())
        result["next_event_time"] = day_close
        result["time_until_next"] = int((day_close - dt).total_seconds())
        return result
    
    # 夜市集合竞价: 19:50-19:59 (仅周一至周四)
    if weekday < 4 and \
       current_time >= datetime.strptime("19:50", "%H:%M").time() and \
       current_time < datetime.strptime("19:59", "%H:%M").time():
        result["is_trading_time"] = True
        result["trading_phase"] = "night_auction"
        result["phase_name"] = "夜市集合竞价"
        result["next_event"] = "night_open"
        night_open = datetime.combine(dt.date(), datetime.strptime("20:00", "%H:%M").time())
        result["next_event_time"] = night_open
        result["time_until_next"] = int((night_open - dt).total_seconds())
        return result
    
    # 夜间交易: 20:00-次日02:30 (仅周一至周四)
    # 注意：周五没有夜市
    if weekday < 4:
        # 20:00-23:59:59
        if current_time >= datetime.strptime("20:00", "%H:%M").time():
            result["is_trading_time"] = True
            result["trading_phase"] = "night_session"
            result["phase_name"] = "夜间交易"
            result["next_event"] = "night_close"
            # 次日 02:30
            next_day = dt.date() + timedelta(days=1)
            night_close = datetime.combine(next_day, datetime.strptime("02:30", "%H:%M").time())
            result["next_event_time"] = night_close
            result["time_until_next"] = int((night_close - dt).total_seconds())
            return result
    
    # 检查是否是凌晨的夜间交易 (02:30 前)
    if current_time < datetime.strptime("02:30", "%H:%M").time():
        # 检查昨天是否是周一至周四（有夜市）
        yesterday = dt.date() - timedelta(days=1)
        yesterday_weekday = yesterday.weekday()
        
        if yesterday_weekday < 4 and not is_holiday(yesterday):
            result["is_trading_time"] = True
            result["trading_phase"] = "night_session"
            result["phase_name"] = "夜间交易"
            result["next_event"] = "night_close"
            night_close = datetime.combine(dt.date(), datetime.strptime("02:30", "%H:%M").time())
            result["next_event_time"] = night_close
            result["time_until_next"] = int((night_close - dt).total_seconds())
            return result
    
    # 非交易时间，计算下一个事件
    result = _calculate_next_event(dt, result)
    return result


def _calculate_next_event(dt, result):
    """
    计算下一个交易事件（开盘或收盘）
    """
    current_time = dt.time()
    weekday = get_weekday(dt)
    
    # 如果当前在日间交易前（08:50 前）
    if current_time < datetime.strptime("08:50", "%H:%M").time():
        result["next_event"] = "day_auction"
        next_time = datetime.combine(dt.date(), datetime.strptime("08:50", "%H:%M").time())
        result["next_event_time"] = next_time
        result["time_until_next"] = int((next_time - dt).total_seconds())
        return result
    
    # 如果当前在日间收盘后到夜市前
    if current_time >= datetime.strptime("15:30", "%H:%M").time() and \
       current_time < datetime.strptime("19:50", "%H:%M").time():
        # 检查今天是否有夜市（周一至周四）
        if weekday < 4:
            result["next_event"] = "night_auction"
            next_time = datetime.combine(dt.date(), datetime.strptime("19:50", "%H:%M").time())
            result["next_event_time"] = next_time
            result["time_until_next"] = int((next_time - dt).total_seconds())
        else:
            # 周五没有夜市，等下周一
            next_trading_day = _find_next_trading_day(dt)
            result["next_event"] = "day_open"
            next_time = datetime.combine(next_trading_day, datetime.strptime("09:00", "%H:%M").time())
            result["next_event_time"] = next_time
            result["time_until_next"] = int((next_time - dt).total_seconds())
        return result
    
    # 如果当前在夜市收盘后（02:30 后到次日 08:50）
    if current_time >= datetime.strptime("02:30", "%H:%M").time() and \
       current_time < datetime.strptime("08:50", "%H:%M").time():
        result["next_event"] = "day_open"
        next_time = datetime.combine(dt.date(), datetime.strptime("09:00", "%H:%M").time())
        result["next_event_time"] = next_time
        result["time_until_next"] = int((next_time - dt).total_seconds())
        return result
    
    # 默认情况下找下一个交易日
    next_trading_day = _find_next_trading_day(dt)
    result["next_event"] = "day_open"
    next_time = datetime.combine(next_trading_day, datetime.strptime("09:00", "%H:%M").time())
    result["next_event_time"] = next_time
    result["time_until_next"] = int((next_time - dt).total_seconds())
    
    return result


def _find_next_trading_day(start_dt):
    """
    查找下一个交易日
    
    参数:
        start_dt: 开始日期时间
        
    返回:
        date: 下一个交易日的日期
    """
    current_date = start_dt.date() + timedelta(days=1)
    
    # 最多查找 30 天
    for _ in range(30):
        dt_check = datetime.combine(current_date, datetime.min.time())
        if is_trading_day(dt_check):
            return current_date
        current_date += timedelta(days=1)
    
    # 如果 30 天内没找到，返回当前日期（异常情况）
    return start_dt.date()


def get_fetch_interval(dt=None):
    """
    获取当前应该使用的数据采集间隔
    
    参数:
        dt: datetime 对象，默认为当前时间
        
    返回:
        int: 采集间隔秒数（交易时间 5 秒，非交易时间 300 秒）
    """
    status = get_trading_status(dt)
    
    if status["is_trading_time"]:
        return 5  # 交易时间：5 秒
    else:
        return 300  # 非交易时间：5 分钟


def check_trading_events(last_status=None):
    """
    检查是否触发了交易事件（开盘或收盘）
    
    参数:
        last_status: 上一次的交易状态（用于检测状态变化）
        
    返回:
        dict or None: 如果有事件触发，返回事件信息；否则返回 None
        {
            "event": str,        # 事件类型: "day_open", "day_close", "night_open", "night_close"
            "event_name": str,   # 事件中文名称
            "timestamp": float   # 事件时间戳
        }
    """
    current_status = get_trading_status()
    
    if last_status is None:
        return None
    
    # 检测状态变化
    last_phase = last_status.get("trading_phase", "closed")
    current_phase = current_status["trading_phase"]
    
    event_map = {
        ("day_auction", "day_session"): ("day_open", "日间交易开始"),
        ("day_session", "closed"): ("day_close", "日间交易结束"),
        ("night_auction", "night_session"): ("night_open", "夜间交易开始"),
        ("night_session", "closed"): ("night_close", "夜间交易结束"),
    }
    
    key = (last_phase, current_phase)
    if key in event_map:
        event_type, event_name = event_map[key]
        return {
            "event": event_type,
            "event_name": event_name,
            "timestamp": time.time()
        }
    
    return None
