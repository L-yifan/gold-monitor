# -*- coding: utf-8 -*-
"""
交易状态路由模块
提供交易时间状态查询接口
"""

from flask import Blueprint, jsonify
from app.services.trading_hours import get_trading_status


trading_bp = Blueprint('trading', __name__)


@trading_bp.route('/api/trading-status')
def get_trading_status_api():
    """
    获取当前交易状态
    
    返回:
        JSON: 交易状态信息
        {
            "success": True,
            "data": {
                "is_trading_time": bool,
                "trading_phase": str,
                "phase_name": str,
                "next_event": str,
                "next_event_time": str (ISO格式),
                "time_until_next": int (秒),
                "is_holiday": bool,
                "weekday": int,
                "weekday_name": str
            }
        }
    """
    try:
        status = get_trading_status()
        
        # 转换时间为 ISO 格式字符串
        next_event_time_str = None
        if status["next_event_time"]:
            next_event_time_str = status["next_event_time"].isoformat()
        
        # 星期几名称映射
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        
        return jsonify({
            "success": True,
            "data": {
                "is_trading_time": status["is_trading_time"],
                "trading_phase": status["trading_phase"],
                "phase_name": status["phase_name"],
                "next_event": status["next_event"],
                "next_event_time": next_event_time_str,
                "time_until_next": status["time_until_next"],
                "is_holiday": status["is_holiday"],
                "weekday": status["weekday"],
                "weekday_name": weekday_names[status["weekday"]]
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"获取交易状态失败: {str(e)}"
        })
