# -*- coding: utf-8 -*-
"""
后台任务模块
包含后台定时采集任务（金价、基金数据等）
"""

import time

from app.models.state import lock, price_history
from app.services.gold_fetcher import fetch_gold_price
from app.services.persistence import save_data
from app.services.trading_hours import get_fetch_interval, check_trading_events


def background_fetch_loop():
    """后台持续采集任务线程，负责金价和基金数据的定时更新"""
    print("后台抓取线程启动...")
    
    last_trading_status = None
    
    while True:
        try:
            # 获取当前应使用的采集间隔
            interval = get_fetch_interval("gold")
            
            # 检查是否触发交易事件（开收盘）
            event = check_trading_events("gold", last_trading_status)
            if event:
                print(f"[交易事件] {event['event_name']} 已触发！")
                # TODO: 在这里可以添加通知逻辑
            
            # 更新交易状态
            from app.services.trading_hours import get_trading_status
            last_trading_status = get_trading_status()
            
            # 只在交易时间内打印状态
            if last_trading_status["is_trading_time"]:
                print(f"[后台采集] {last_trading_status['phase_name']} - 采集间隔: {interval}秒")
            
            # 获取金价数据
            data, _ = fetch_gold_price()
            if data:
                with lock:
                    # 添加到历史记录
                    price_history.append(data)
                # 记录成功后保存数据（内部包含清理逻辑）
                save_data()
            
            # 按计算出的间隔休眠
            time.sleep(interval)
        except Exception as e:
            print(f"后台抓取异常: {e}")
            time.sleep(30) # 异常后等待较长时间再重试
