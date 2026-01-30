# -*- coding: utf-8 -*-
"""
国内金价实时监控系统 - 后端服务
数据来源：新浪财经 (上海黄金交易所 Au99.99)
"""

from flask import Flask, render_template, jsonify, request
import requests
import re
import time
import json
from datetime import datetime
from collections import deque
import threading

app = Flask(__name__)

# ==================== 配置 ====================
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

# 熔断配置
MAX_FAIL_COUNT = 3  # 连续失败多少次触发熔断
MUTE_DURATION = 60  # 熔断持续时间（秒）

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
}

# 存储历史价格数据 (最多保存 20000 条，约 24 小时以上的数据，5秒一条)
MAX_HISTORY_SIZE = 20000
price_history = deque(maxlen=MAX_HISTORY_SIZE)

# 数据清理配置
HISTORY_KEEP_HOURS = 24
RECORDS_KEEP_DAYS = 7

# 用户手动记录的价格快照
manual_records = []

# 数据持久化文件
DATA_FILE = "data.json"

# 预警配置
alert_settings = {
    "high": 0,
    "low": 0,
    "enabled": False
}

def cleanup_expired_data():
    """清理过期的数据，保持文件精简"""
    global manual_records
    now_ts = datetime.now().timestamp()
    
    # 1. 清理历史价格 (24小时)
    history_threshold = now_ts - (HISTORY_KEEP_HOURS * 3600)
    # 因为 price_history 是有序的，我们可以直接根据时间戳过滤
    while price_history and price_history[0].get('timestamp', 0) < history_threshold:
        price_history.popleft()
        
    # 2. 清理手动记录 (7天)
    record_threshold = now_ts - (RECORDS_KEEP_DAYS * 86400)
    manual_records = [r for r in manual_records if r.get('timestamp', 0) > record_threshold]

def save_data():
    """将数据保存到 JSON 文件"""
    with lock:
        try:
            # 在保存前执行清理
            cleanup_expired_data()
            
            data = {
                "manual_records": manual_records,
                "price_history": list(price_history),
                "alert_settings": alert_settings
            }
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存数据失败: {e}")

def load_data():
    """从 JSON 文件加载数据"""
    global manual_records, price_history, alert_settings
    import os
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                manual_records = data.get("manual_records", [])
                history = data.get("price_history", [])
                price_history.clear()
                price_history.extend(history)
                # 加载预警配置
                saved_alerts = data.get("alert_settings", {})
                alert_settings.update(saved_alerts)
            print(f"成功加载数据: {len(manual_records)} 条记录, {len(price_history)} 条历史")
        except Exception as e:
            print(f"加载数据失败: {e}")

# 初始化加载数据
load_data()

# 线程锁 (使用 RLock 以支持在持有锁的情况下调用 save_data)
lock = threading.RLock()


# ==================== 数据获取实现 ====================
def fetch_from_eastmoney(source_config):
    """
    从东方财富获取 Au99.99 实时价格
    """
    try:
        url = "https://push2.eastmoney.com/api/qt/stock/get?secid=118.AU9999&fields=f43,f44,f45,f46,f60,f170"
        response = requests.get(url, headers=HEADERS, timeout=source_config.get('timeout', 5))
        data = response.json()
        
        if data.get('data'):
            d = data['data']
            # 东方财富价格单位是分，需要除以100
            current_price = d.get('f43', 0) / 100
            
            if current_price <= 0:
                return None

            open_price = d.get('f46', 0) / 100
            high_price = d.get('f44', 0) / 100
            low_price = d.get('f45', 0) / 100
            yesterday_close = d.get('f60', 0) / 100
            change_percent = d.get('f170', 0) / 100
            
            change = current_price - yesterday_close
            
            now = datetime.now()
            
            return {
                "price": round(current_price, 2),
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "yesterday_close": round(yesterday_close, 2),
                "change": round(change, 2),
                "change_percent": round(change_percent, 2),
                "timestamp": now.timestamp(),
                "time_str": now.strftime("%H:%M:%S"),
                "source": source_config['name']
            }
    except Exception as e:
        print(f"[{source_config['name']}] 获取失败: {e}")
    return None


def fetch_from_sina(source_config):
    """
    从新浪财经获取 Au99.99 实时价格
    """
    try:
        url = "https://hq.sinajs.cn/list=gds_au9999"
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=source_config.get('timeout', 5))
        
        # 处理编码
        content_type = response.headers.get('Content-Type', '').lower()
        if 'charset' in content_type:
             response.encoding = content_type.split('charset=')[-1]
        else:
             response.encoding = 'gbk' # 默认GBK

        text = response.text
        
        match = re.search(r'"([^"]+)"', text)
        if not match:
            return None
        
        data_str = match.group(1)
        parts = data_str.split(',')
        
        if len(parts) < 8:
            return None
        
        current_price = float(parts[1]) if parts[1] else 0
        
        if current_price <= 0:
            return None

        yesterday_close = float(parts[2]) if parts[2] else current_price
        open_price = float(parts[3]) if parts[3] else current_price
        high_price = float(parts[4]) if parts[4] else current_price
        low_price = float(parts[5]) if parts[5] else current_price
            
        change = current_price - yesterday_close
        change_percent = (change / yesterday_close * 100) if yesterday_close else 0
        
        now = datetime.now()
        
        return {
            "price": round(current_price, 2),
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "yesterday_close": round(yesterday_close, 2),
            "change": round(change, 2),
            "change_percent": round(change_percent, 2),
            "timestamp": now.timestamp(),
            "time_str": now.strftime("%H:%M:%S"),
            "source": source_config['name']
        }
    except Exception as e:
        print(f"[{source_config['name']}] 获取失败: {e}")
    return None

def fetch_from_tencent(source_config):
    """
    从腾讯财经获取 Au99.99 实时价格
    """
    try:
        url = "http://qt.gtimg.cn/q=s_shau9999"
        response = requests.get(url, headers=HEADERS, timeout=source_config.get('timeout', 3))
        text = response.text
        
        # 格式: v_s_shau9999="1~黄金Au9999~shau9999~550.45~0.12~0.02~...~";
        match = re.search(r'"([^"]+)"', text)
        if not match:
            return None
            
        parts = match.group(1).split('~')
        if len(parts) < 6:
            return None
            
        current_price = float(parts[3])
        change = float(parts[4])
        change_percent = float(parts[5])
        
        # 腾讯简版不含最高最低，尝试使用全版以获取更全数据
        full_url = "http://qt.gtimg.cn/q=shau9999"
        full_res = requests.get(full_url, headers=HEADERS, timeout=2)
        full_match = re.search(r'"([^"]+)"', full_res.text)
        
        open_price = current_price
        high_price = current_price
        low_price = current_price
        yesterday_close = current_price - change
        
        if full_match:
            f_parts = full_match.group(1).split('~')
            if len(f_parts) > 34:
                yesterday_close = float(f_parts[4])
                open_price = float(f_parts[5])
                high_price = float(f_parts[33])
                low_price = float(f_parts[34])

        now = datetime.now()
        return {
            "price": round(current_price, 2),
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "yesterday_close": round(yesterday_close, 2),
            "change": round(change, 2),
            "change_percent": round(change_percent, 2),
            "timestamp": now.timestamp(),
            "time_str": now.strftime("%H:%M:%S"),
            "source": source_config['name']
        }
    except Exception as e:
        print(f"[{source_config['name']}] 获取失败: {e}")
    return None


def fetch_from_netease(source_config):
    """
    从网易财经获取 Au99.99 实时价格
    """
    try:
        # 网易接口，118AU9999 是 SGE Au99.99 的代码
        url = "http://api.money.126.net/data/feed/118AU9999,money.api"
        response = requests.get(url, headers=HEADERS, timeout=source_config.get('timeout', 3))
        
        # 网易返回的是 _ntes_quote_callback({...});
        text = response.text
        match = re.search(r'\((.*)\)', text)
        if not match:
            return None
            
        data = json.loads(match.group(1))
        d = data.get('118AU9999')
        if not d:
            return None
            
        current_price = d.get('price', 0)
        if current_price <= 0:
            return None
            
        open_price = d.get('open', current_price)
        high_price = d.get('high', current_price)
        low_price = d.get('low', current_price)
        yesterday_close = d.get('yestclose', current_price)
        change = d.get('updown', 0)
        change_percent = d.get('percent', 0) * 100
        
        now = datetime.now()
        return {
            "price": round(current_price, 2),
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "yesterday_close": round(yesterday_close, 2),
            "change": round(change, 2),
            "change_percent": round(change_percent, 2),
            "timestamp": now.timestamp(),
            "time_str": now.strftime("%H:%M:%S"),
            "source": source_config['name']
        }
    except Exception as e:
        print(f"[{source_config['name']}] 获取失败: {e}")
    return None


# 数据源处理函数映射
SOURCE_HANDLERS = {
    "eastmoney": fetch_from_eastmoney,
    "sina": fetch_from_sina,
    "tencent": fetch_from_tencent,
    "netease": fetch_from_netease
}

def fetch_gold_price():
    """
    从配置的数据源列表中循环获取价格，包含熔断机制
    """
    now_ts = time.time()
    for source in DATA_SOURCES:
        # 检查是否被手动禁用或处于熔断期
        if not source.get('enabled', False):
            continue
            
        if source.get('mute_until', 0) > now_ts:
            continue
            
        handler = SOURCE_HANDLERS.get(source['type'])
        if not handler:
            continue
            
        # 尝试获取数据
        data = handler(source)
        if data:
            # 成功获取，重置失败计数
            source['fail_count'] = 0
            source['mute_until'] = 0
            return data
        else:
            # 失败处理：增加计数并检查是否触发熔断
            source['fail_count'] = source.get('fail_count', 0) + 1
            if source['fail_count'] >= MAX_FAIL_COUNT:
                print(f"!!! [熔断] {source['name']} 连续失败 {MAX_FAIL_COUNT} 次，进入 {MUTE_DURATION}s 冷却期")
                source['mute_until'] = now_ts + MUTE_DURATION
                source['fail_count'] = 0 # 触发后重置，等待冷却后重新开始
            
    print("所有可用数据源均获取失败")
    return None


def calculate_target_prices(buy_price, fee_rate=0.005):
    """
    计算多个盈利目标的卖出价格
    
    公式: 目标卖出价 = 买入价 × (1 + 利润率) / (1 - 手续费率)
    
    参数:
        buy_price: 买入价格
        fee_rate: 卖出手续费率 (默认 0.5%)
    
    返回:
        多个盈利目标对应的卖出价格列表
    """
    targets = [5, 10, 15, 20, 30]  # 盈利目标百分比
    results = []
    
    for target in targets:
        profit_rate = target / 100
        # 目标卖出价 = 买入价 × (1 + 利润率) / (1 - 手续费率)
        sell_price = buy_price * (1 + profit_rate) / (1 - fee_rate)
        results.append({
            "target_percent": target,
            "sell_price": round(sell_price, 2),
            "profit_amount": round(buy_price * profit_rate, 2),
            "actual_multiplier": round(sell_price / buy_price, 4)
        })
    
    return results


def calculate_current_profit(buy_price, current_price, fee_rate=0.005):
    """
    计算当前价格卖出后的实际收益率 (扣除手续费)
    
    公式: 实际收益率 = (当前价 × (1 - 手续费率) - 买入价) / 买入价 × 100%
    """
    if buy_price <= 0:
        return 0
    
    actual_receive = current_price * (1 - fee_rate)
    profit_rate = (actual_receive - buy_price) / buy_price * 100
    return round(profit_rate, 2)


# ==================== 后台抓取线程 ====================
def background_fetch_loop():
    """后台持续抓取金价线程，确保即使网页关闭也能记录数据"""
    print("后台抓取线程启动...")
    while True:
        try:
            data = fetch_gold_price()
            if data:
                with lock:
                    # 添加到历史记录
                    price_history.append({
                        "price": data["price"],
                        "timestamp": data["timestamp"],
                        "time_str": data["time_str"]
                    })
                # 记录成功后保存数据（内部包含清理逻辑）
                save_data()
            
            # 每 10 秒采集一次（后台不需要太频繁，平衡性能与连续性）
            time.sleep(10)
        except Exception as e:
            print(f"后台抓取异常: {e}")
            time.sleep(30) # 异常后等待较长时间再重试

# ==================== 路由 ====================
@app.route('/')
def index():
    """首页"""
    return render_template('index.html')


@app.route('/api/price')
def get_price():
    """获取当前金价 (改为从缓存获取，不再实时去抓取，提高响应速度)"""
    with lock:
        if price_history:
            latest = price_history[-1]
            # 如果缓存数据太老（超过 30 秒），说明后台可能挂了或未运行，尝试实时抓一次
            if time.time() - latest["timestamp"] > 30:
                data = fetch_gold_price()
                if data:
                    price_history.append(data)
                    save_data()
                    return jsonify({"success": True, "data": data})
            
            # 正常情况下直接返回最后一条历史数据
            # 注意：这里需要补全最高价最低价等全量信息，后台线程存储的是精简版
            # 为了简单起见，这里直接返回最新的历史记录
            return jsonify({"success": True, "data": latest})
        else:
            # 没历史记录时去抓一次
            data = fetch_gold_price()
            if data:
                with lock:
                    price_history.append(data)
                save_data()
                return jsonify({"success": True, "data": data})
            
    return jsonify({"success": False, "message": "获取数据失败"})



@app.route('/api/history')
def get_history():
    """获取历史价格数据"""
    with lock:
        history_list = list(price_history)
    return jsonify({"success": True, "data": history_list})


@app.route('/api/calculate', methods=['POST'])
def calculate():
    """计算盈利目标"""
    req_data = request.get_json()
    buy_price = req_data.get('buy_price', 0)
    current_price = req_data.get('current_price', 0)
    
    if buy_price <= 0:
        return jsonify({"success": False, "message": "买入价格必须大于0"})
    
    targets = calculate_target_prices(buy_price)
    current_profit = calculate_current_profit(buy_price, current_price)
    
    return jsonify({
        "success": True,
        "targets": targets,
        "current_profit": current_profit
    })


@app.route('/api/record', methods=['POST'])
def add_record():
    """添加手动记录"""
    req_data = request.get_json()
    record = {
        "price": req_data.get('price'),
        "buy_price": req_data.get('buy_price'),
        "profit": req_data.get('profit'),
        "timestamp": datetime.now().timestamp(),
        "time_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": req_data.get('note', '')
    }
    
    with lock:
        manual_records.append(record)
    
    save_data()
    return jsonify({"success": True, "record": record})


@app.route('/api/records')
def get_records():
    """获取所有手动记录"""
    with lock:
        records = list(manual_records)
    return jsonify({"success": True, "data": records})


@app.route('/api/records/clear', methods=['POST'])
def clear_records():
    """清空手动记录"""
    with lock:
        manual_records.clear()
    save_data()
    return jsonify({"success": True})


@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    """获取或更新预警设置"""
    global alert_settings
    if request.method == 'POST':
        req_data = request.get_json()
        with lock:
            alert_settings["high"] = float(req_data.get('high', 0))
            alert_settings["low"] = float(req_data.get('low', 0))
            alert_settings["enabled"] = bool(req_data.get('enabled', False))
        save_data()
        return jsonify({"success": True, "settings": alert_settings})
    
    return jsonify({"success": True, "settings": alert_settings})


# ==================== 启动 ====================
if __name__ == '__main__':
    print("=" * 50)
    print("  国内金价实时监控系统")
    print("  数据来源: 上海黄金交易所 Au99.99")
    print("  访问地址: http://localhost:5000")
    print("=" * 50)
    
    # 启动后台抓取线程
    t = threading.Thread(target=background_fetch_loop, daemon=True)
    t.start()
    
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True, use_reloader=False)
