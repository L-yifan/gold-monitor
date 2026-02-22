# -*- coding: utf-8 -*-
"""
交易状态路由模块
提供交易时间状态查询接口
"""

from flask import Blueprint, jsonify, request
from app.services.trading_hours import get_trading_status, get_fund_trading_status


trading_bp = Blueprint('trading', __name__)


# 事件名称映射
EVENT_NAMES = {
    # 基金
    "market_open": "开市",
    "market_resume": "开盘",
    "lunch_break": "休市",
    "market_close": "收市",
    # 黄金
    "day_auction": "早市集合竞价",
    "day_open": "早市开盘",
    "day_close": "早市收盘",
    "night_auction": "夜市集合竞价",
    "night_open": "夜市开盘",
    "night_close": "夜市收盘",
}


def _format_status(status):
    """格式化交易状态为 API 响应"""
    # 转换时间为字符串（使用空格分隔，更兼容）
    next_event_time_str = None
    if status["next_event_time"]:
        next_event_time_str = status["next_event_time"].strftime("%Y-%m-%d %H:%M:%S")
    
    # 星期几名称映射
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    
    return {
        "is_trading_time": status["is_trading_time"],
        "trading_phase": status["trading_phase"],
        "phase_name": status["phase_name"],
        "next_event": status["next_event"],
        "next_event_name": EVENT_NAMES.get(status["next_event"], status["next_event"]),
        "next_event_time": next_event_time_str,
        "time_until_next": status["time_until_next"],
        "is_holiday": status["is_holiday"],
        "holiday_name": status.get("holiday_name"),
        "weekday": status["weekday"],
        "weekday_name": weekday_names[status["weekday"]]
    }


@trading_bp.route('/api/trading-status')
def get_trading_status_api():
    """
    获取当前交易状态 (支持 ?type=gold 或 ?type=fund)
    
    返回:
        JSON: 交易状态信息
    """
    try:
        asset_type = request.args.get('type', 'gold').lower()
        
        if asset_type == 'fund':
            status = get_fund_trading_status()
        else:
            status = get_trading_status()
        
        return jsonify({
            "success": True,
            "data": _format_status(status)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"获取交易状态失败: {str(e)}"
        })
