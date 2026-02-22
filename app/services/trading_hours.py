# -*- coding: utf-8 -*-
"""
交易时间服务模块
判断上海黄金交易所 Au99.99 的交易时间状态
"""

import time
from datetime import datetime, timedelta
from app.services.holiday_service import (
    get_holidays,
    is_holiday as holiday_service_is_holiday,
    warmup_cache,
    check_and_save_cache
)


def fetch_holidays(year=None):
    """
    获取中国法定节假日列表（委托给 holiday_service）
    
    参数:
        year: 年份，默认为当前年份
        
    返回:
        set: 节假日日期字符串集合 (格式: "YYYY-MM-DD")
    """
    return get_holidays(year)


def is_holiday(dt=None, market_type="fund"):
    """
    判断指定日期是否为节假日（委托给 holiday_service）
    
    参数:
        dt: datetime 对象，默认为当前时间
        market_type: "fund"(基金/股票) 或 "gold"(黄金)
    
    返回:
        bool: 是否为节假日
    """
    return holiday_service_is_holiday(dt, market_type)


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


def is_trading_day(dt=None, market_type="fund"):
    """
    判断是否为交易日（周一至周五且非节假日）
    
    参数:
        dt: datetime 对象，默认为当前时间
        market_type: "fund"(基金/股票) 或 "gold"(黄金)
    
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
    if is_holiday(dt, market_type):
        return False
    
    return True


def get_trading_status(dt=None):
    """
    获取黄金当前交易状态
    
    参数:
        dt: datetime 对象，默认为当前时间
        
    返回:
        dict: 包含交易状态信息的字典
    """
    if dt is None:
        dt = datetime.now()
    
    current_time = dt.time()
    weekday = get_weekday(dt)
    holiday = is_holiday(dt, "gold")
    holiday_name = None
    if holiday:
        from app.services.exchange_calendar import get_holiday_name_by_date as get_gold_holiday_name_by_date
        holiday_name = get_gold_holiday_name_by_date(dt.strftime("%Y-%m-%d"))
    
    result = {
        "is_trading_time": False,
        "trading_phase": "closed",
        "phase_name": "休市",
        "next_event": None,
        "next_event_time": None,
        "time_until_next": None,
        "is_holiday": holiday,
        "holiday_name": holiday_name,
        "weekday": weekday
    }
    
    # 如果不是交易日，计算下次开盘时间
    if not is_trading_day(dt, "gold"):
        next_trading_day = _find_next_trading_day(dt, "gold")
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

        if yesterday_weekday < 4 and not is_holiday(yesterday, "gold"):
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


def get_fund_trading_status(dt=None):
    """
    获取基金当前交易状态 (核心时段: 9:30-11:30, 13:00-15:00)
    
    参数:
        dt: datetime 对象，默认为当前时间
        
    返回:
        dict: 包含交易状态信息的字典
    """
    if dt is None:
        dt = datetime.now()
    
    current_time = dt.time()
    weekday = get_weekday(dt)
    holiday = is_holiday(dt, "fund")
    holiday_name = None
    if holiday:
        from app.services.exchange_calendar_crawler import get_holiday_name_by_date as get_fund_holiday_name_by_date
        holiday_name = get_fund_holiday_name_by_date(dt.strftime("%Y-%m-%d"))
    
    result = {
        "is_trading_time": False,
        "trading_phase": "closed",
        "phase_name": "休市",
        "next_event": None,
        "next_event_time": None,
        "time_until_next": None,
        "is_holiday": holiday,
        "holiday_name": holiday_name,
        "weekday": weekday
    }
    
    # 定义关键时间点
    t930 = datetime.strptime("09:30", "%H:%M").time()
    t1130 = datetime.strptime("11:30", "%H:%M").time()
    t1300 = datetime.strptime("13:00", "%H:%M").time()
    t1500 = datetime.strptime("15:00", "%H:%M").time()
    
    # 如果不是交易日，计算下次开盘时间
    if not is_trading_day(dt, "fund"):
        next_trading_day = _find_next_trading_day(dt, "fund")
        day_open = datetime.combine(next_trading_day, t930)
        
        result["next_event"] = "market_open"
        result["next_event_time"] = day_open
        result["time_until_next"] = int((day_open - dt).total_seconds())
        return result
    
    # 判断当前交易阶段
    if (current_time >= t930 and current_time < t1130) or \
       (current_time >= t1300 and current_time < t1500):
        result["is_trading_time"] = True
        result["trading_phase"] = "trading"
        result["phase_name"] = "交易中"
        
        if current_time < t1130:
            next_event_time = datetime.combine(dt.date(), t1130)
            result["next_event"] = "lunch_break"
        else:
            next_event_time = datetime.combine(dt.date(), t1500)
            result["next_event"] = "market_close"
            
        result["next_event_time"] = next_event_time
        result["time_until_next"] = int((next_event_time - dt).total_seconds())
        return result
    
    # 非交易时间，计算下一个事件
    if current_time < t930:
        next_event_time = datetime.combine(dt.date(), t930)
        result["next_event"] = "market_open"
    elif current_time < t1300:
        next_event_time = datetime.combine(dt.date(), t1300)
        result["next_event"] = "market_resume"
    else:
        next_trading_day = _find_next_trading_day(dt, "fund")
        next_event_time = datetime.combine(next_trading_day, t930)
        result["next_event"] = "market_open"
        
    result["next_event_time"] = next_event_time
    result["time_until_next"] = int((next_event_time - dt).total_seconds())
    return result


def _calculate_next_event(dt, result):
    """
    计算黄金下一个交易事件（开盘或收盘）
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
            next_trading_day = _find_next_trading_day(dt, "gold")
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
    next_trading_day = _find_next_trading_day(dt, "gold")
    result["next_event"] = "day_open"
    next_time = datetime.combine(next_trading_day, datetime.strptime("09:00", "%H:%M").time())
    result["next_event_time"] = next_time
    result["time_until_next"] = int((next_time - dt).total_seconds())
    
    return result


def _find_next_trading_day(start_dt, market_type="fund"):
    """
    查找下一个交易日
    
    参数:
        start_dt: 开始日期时间
        market_type: "fund" (基金) 或 "gold" (黄金)
        
    返回:
        date: 下一个交易日的日期
    """
    date_str = start_dt.strftime("%Y-%m-%d")
    
    # 尝试直接获取节后首个交易日
    if market_type == "fund":
        from app.services.exchange_calendar_crawler import (
            get_holiday_name_by_date as get_fund_holiday_name_by_date,
            get_first_trading_day as get_fund_first_trading_day
        )
        holiday_name = get_fund_holiday_name_by_date(date_str)
        if holiday_name:
            first_day_str = get_fund_first_trading_day(holiday_name, start_dt.year)
            if first_day_str:
                try:
                    candidate_date = datetime.strptime(first_day_str, "%Y-%m-%d").date()
                    if candidate_date > start_dt.date():
                        return candidate_date
                except Exception:
                    pass
    else:
        from app.services.exchange_calendar import get_holiday_name_by_date, get_exchange_first_trading_day
        holiday_name = get_holiday_name_by_date(date_str)
        if holiday_name:
            first_day_str = get_exchange_first_trading_day(holiday_name, start_dt.year)
            if first_day_str:
                try:
                    candidate_date = datetime.strptime(first_day_str, "%Y-%m-%d").date()
                    if candidate_date > start_dt.date():
                        return candidate_date
                except Exception:
                    pass
                
    current_date = start_dt.date() + timedelta(days=1)
    
    # 最多查找 30 天
    for _ in range(30):
        dt_check = datetime.combine(current_date, datetime.min.time())
        if is_trading_day(dt_check, market_type):
            return current_date
        current_date += timedelta(days=1)
    
    # 如果 30 天内没找到，返回当前日期（异常情况）
    return start_dt.date()


def get_fetch_interval(asset_type="gold", dt=None):
    """
    获取当前应该使用的数据采集间隔
    
    参数:
        asset_type: 资产类型 ("gold" or "fund")
        dt: datetime 对象，默认为当前时间
        
    返回:
        int: 采集间隔秒数（交易时间较短，非交易时间 300 秒）
    """
    if asset_type == "fund":
        status = get_fund_trading_status(dt)
        if status["is_trading_time"]:
            return 15  # 基金更新稍慢，15秒一次
        else:
            return 300
    else:
        status = get_trading_status(dt)
        if status["is_trading_time"]:
            return 5  # 黄金交易：5 秒
        else:
            return 300  # 非交易时间：5 分钟


def check_trading_events(asset_type="gold", last_status=None):
    """
    检查是否触发了交易事件（开盘或收盘）
    
    参数:
        asset_type: 资产类型 ("gold" or "fund")
        last_status: 上一次的交易状态
        
    返回:
        dict or None: 如果有事件触发，返回事件信息
    """
    if asset_type == "fund":
        current_status = get_fund_trading_status()
    else:
        current_status = get_trading_status()
    
    if last_status is None:
        return None
    
    # 检测状态变化
    last_phase = last_status.get("trading_phase", "closed")
    current_phase = current_status["trading_phase"]
    
    if asset_type == "gold":
        event_map = {
            ("day_auction", "day_session"): ("day_open", "日间交易开始"),
            ("day_session", "closed"): ("day_close", "日间交易结束"),
            ("night_auction", "night_session"): ("night_open", "夜间交易开始"),
            ("night_session", "closed"): ("night_close", "夜间交易结束"),
        }
    else: # fund
        event_map = {
            ("closed", "trading"): ("market_open", "基金市场开盘"),
            ("trading", "closed"): ("market_close", "基金市场收盘"),
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
