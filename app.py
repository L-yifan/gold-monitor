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
import os
from datetime import datetime
from collections import deque
import threading
from concurrent.futures import ThreadPoolExecutor

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

# 缓存与数据新鲜度配置
CACHE_TTL_SECONDS = 60       # 基金数据缓存有效期（秒）
STALE_THRESHOLD_SECONDS = 30  # 金价数据过期阈值（秒）
MAX_FETCH_WORKERS = 10        # 并发获取数据的线程池大小

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

# 基金自选列表 (存储基金代码)
fund_watchlist = []
# 基金数据缓存 (内存缓存，不持久化详情，只持久化代码列表)
fund_cache = {}

# 数据持久化文件
DATA_FILE = "data.json"

# 预警配置
alert_settings = {
    "high": 0,
    "low": 0,
    "enabled": False
}

# 基金持仓数据 (存储在 data.json 中)
fund_holdings = []  # [{code, name, cost_price, shares, note}, ...]


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
    """将数据保存到 JSON 文件 (原子写入模式)"""
    with lock:
        try:
            # 在保存前执行清理
            cleanup_expired_data()
            
            data = {
                "manual_records": manual_records,
                "price_history": list(price_history),
                "alert_settings": alert_settings,
                "fund_watchlist": fund_watchlist,
                "fund_holdings": fund_holdings
            }
            
            # 使用临时文件进行原子写入
            tmp_file = DATA_FILE + ".tmp"
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())  # 确保数据写入物理磁盘
            
            # 原子替换原文件
            os.replace(tmp_file, DATA_FILE)
        except Exception as e:
            print(f"保存数据失败: {e}")

def load_data():
    """从 JSON 文件加载数据"""
    global manual_records, price_history, alert_settings, fund_watchlist, fund_holdings
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
                # 加载自选基金
                fund_watchlist = data.get("fund_watchlist", [])
                # 加载基金持仓
                fund_holdings = data.get("fund_holdings", [])
            print(f"成功加载数据: {len(manual_records)} 条记录, {len(price_history)} 条历史, {len(fund_watchlist)} 个自选基金, {len(fund_holdings)} 条持仓")
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


def get_24h_summary():
    """计算过去 24 小时的统计数据"""
    with lock:
        if not price_history:
            return None
        
        prices = [p['price'] for p in price_history]
        high = max(prices)
        low = min(prices)
        avg = sum(prices) / len(prices)
        volatility = high - low
        
        return {
            "high_24h": round(high, 2),
            "low_24h": round(low, 2),
            "avg_24h": round(avg, 2),
            "volatility": round(volatility, 2),
            "count": len(prices)
        }


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
            
            # 每 5 秒采集一次（后台不需要太频繁，平衡性能与连续性）
            time.sleep(5)
        except Exception as e:
            print(f"后台抓取异常: {e}")
            time.sleep(30) # 异常后等待较长时间再重试

# ==================== 基金数据获取实现 ====================
def fetch_fund_from_eastmoney(fund_code):
    """
    从天天基金获取估值数据 (主源)
    API: http://fundgz.1234567.com.cn/js/{code}.js
    返回格式: jsonpgz({"fundcode":"...","name":"...","jzrq":"...","dwjz":"...","gsz":"...","gszzl":"...","gztime":"..."});
    """
    try:
        url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js?rt={int(time.time()*1000)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "http://fund.eastmoney.com/"
        }
        response = requests.get(url, headers=headers, timeout=3)
        text = response.text
        
        # 提取 jsonpgz(...) 中的 JSON 内容
        match = re.search(r'jsonpgz\((.*)\);', text)
        if match:
            data = json.loads(match.group(1))
            return {
                "code": data['fundcode'],
                "name": data['name'],
                "price": float(data['gsz']),      # 估算净值
                "change": float(data['gszzl']),   # 估算涨跌幅 (%)
                "time_str": data['gztime'],       # 估值时间
                "timestamp": datetime.now().timestamp(),
                "source": "天天基金"
            }
    except Exception as e:
        # print(f"[天天基金] 获取 {fund_code} 失败: {e}") # 仅调试时开启
        pass
    return None

def fetch_fund_from_sina(fund_code):
    """
    从新浪财经获取基金估值 (备用源)
    API: http://hq.sinajs.cn/list=fu_{code}
    返回格式: var hq_str_fu_000001="华夏成长混合,1.076,3.56,2023-10-27 15:00:00,1.039,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00";
    注意：新浪接口可能不包含实时估值涨幅，主要用于获取名称等基础信息兜底，或尝试其他参数
    修正：新浪开放接口对于某些基金可能数据不全，作为备用方案主要保证代码存在性检查
    """
    try:
        url = f"http://hq.sinajs.cn/list=fu_{fund_code}"
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0"
        }
        response = requests.get(url, headers=headers, timeout=3)
        # 尝试检测编码
        encoding = 'gbk'
        if 'charset' in response.headers.get('Content-Type', ''):
             encoding = response.headers.get('Content-Type', '').split('charset=')[-1]
        response.encoding = encoding
        
        text = response.text
        match = re.search(r'"([^"]+)"', text)
        if match:
            parts = match.group(1).split(',')
            if len(parts) > 1:
                # 新浪接口通常只返回净值，实时估值可能需要额外接口，这里仅作基本的名称获取
                # 如果天天基金挂了，至少能显示名字
                return {
                    "code": fund_code,
                    "name": parts[0],
                    "price": float(parts[1]) if parts[1] else 0,
                    "change": 0, # 新浪此接口可能无实时估值涨幅
                    "time_str": parts[3] if len(parts) > 3 else datetime.now().strftime("%Y-%m-%d"),
                    "timestamp": datetime.now().timestamp(),
                    "source": "新浪财经(仅净值)"
                }
    except Exception as e:
        pass
    return None

def fetch_fund_data(fund_code):
    """多源获取基金数据"""
    # 1. 优先天天基金 (数据最全，含实时估值)
    data = fetch_fund_from_eastmoney(fund_code)
    if data:
        return data
        
    # 2. 备用新浪基金
    data = fetch_fund_from_sina(fund_code)
    if data:
        return data
        
    return None


def fetch_fund_portfolio(fund_code):
    """
    获取基金持仓股票实时数据（含占比和贡献估算）
    1. 从天天基金获取持仓代码和占比（季报数据）
    2. 从新浪财经获取实时行情
    3. 计算每只股票对基金净值的贡献
    """
    try:
        # 1. 获取持仓信息（含占比）- 使用新 API
        url = f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={fund_code}&topline=10"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "http://fundf10.eastmoney.com/"
        }
        response = requests.get(url, headers=headers, timeout=8)
        response.encoding = 'utf-8'
        text = response.text
        
        # 提取报告期（如 "2025年4季度"）
        report_period = ""
        period_match = re.search(r'(\d{4})年(\d)季度', text)
        if period_match:
            report_period = f"{period_match.group(1)}年{period_match.group(2)}季度"
        
        # 解析 HTML 表格：提取 code, name, weight
        # 模式：<td><a...>CODE</a></td><td class='tol'><a...>NAME</a></td>...<td class='tor'>WEIGHT%</td>
        # 注意：第一个表格是最新季度，后面还有历史季度数据，我们只取前10条
        pattern = r"<td><a[^>]*>(\d{6})</a></td>\s*<td class='tol'><a[^>]*>([^<]+)</a></td>.*?<td class='tor'>(\d+\.?\d*)%</td>"
        matches = re.findall(pattern, text, re.DOTALL)
        
        if not matches:
            # 降级：尝试旧 API
            return fetch_fund_portfolio_fallback(fund_code)
        
        # 只取前10条（最新季度）
        holdings_info = {}  # code -> {name, weight}
        for code, name, weight in matches:
            if code not in holdings_info and len(holdings_info) < 10:
                holdings_info[code] = {
                    "name": name,
                    "weight": float(weight)
                }
        
        if not holdings_info:
            return []
        
        # 2. 映射为新浪 API 格式
        sina_codes = []
        code_map = {}  # sina_code -> original_code
        
        for code in holdings_info.keys():
            prefix = ""
            if len(code) == 5:  # 港股
                prefix = "rt_hk"
            elif len(code) == 6:
                if code.startswith('6') or code.startswith('9'):
                    prefix = "sh"
                elif code.startswith('0') or code.startswith('3'):
                    prefix = "sz"
                elif code.startswith('4') or code.startswith('8'):
                    prefix = "bj"
                else:
                    prefix = "sh"
            
            if prefix:
                sina_code = f"{prefix}{code}"
                sina_codes.append(sina_code)
                code_map[sina_code] = code

        if not sina_codes:
            return []
            
        # 3. 批量获取实时行情
        list_str = ",".join(sina_codes)
        hq_url = f"http://hq.sinajs.cn/list={list_str}"
        
        hq_res = requests.get(hq_url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=5)
        encoding = 'gbk'
        if 'charset' in hq_res.headers.get('Content-Type', ''):
            encoding = hq_res.headers.get('Content-Type', '').split('charset=')[-1]
        hq_res.encoding = encoding
        
        hq_text = hq_res.text
        
        portfolio = []
        
        for sina_code in sina_codes:
            pattern = f'var hq_str_{sina_code}="(.*?)";'
            hq_match = re.search(pattern, hq_text)
            
            original_code = code_map[sina_code]
            info = holdings_info.get(original_code, {})
            
            item = {
                "code": original_code,
                "name": info.get("name", "--"),
                "weight": info.get("weight", 0),
                "price": 0,
                "change_percent": 0,
                "contribution": 0,
                "report_period": report_period
            }
            
            if hq_match:
                data_str = hq_match.group(1)
                parts = data_str.split(',')
                
                if "rt_hk" in sina_code:
                    # 港股格式: eng_name, cn_name, open, prev_close, high, low, last, ...
                    if len(parts) > 6:
                        item["name"] = info.get("name") or parts[1]
                        current = float(parts[6]) if parts[6] else 0
                        prev_close = float(parts[3]) if parts[3] else 0
                        item["price"] = current
                        if prev_close > 0:
                            item["change_percent"] = round((current - prev_close) / prev_close * 100, 2)
                else:
                    # A股格式: name, open, prev_close, current, ...
                    if len(parts) > 3:
                        item["name"] = info.get("name") or parts[0]
                        current = float(parts[3]) if parts[3] else 0
                        prev_close = float(parts[2]) if parts[2] else 0
                        item["price"] = current
                        if prev_close > 0:
                            item["change_percent"] = round((current - prev_close) / prev_close * 100, 2)
                
                # 4. 计算贡献：weight * change_percent / 100
                item["contribution"] = round(item["weight"] * item["change_percent"] / 100, 4)
            
            portfolio.append(item)
                
        return portfolio

    except Exception as e:
        print(f"获取持仓失败 {fund_code}: {e}")
        return None


def fetch_fund_portfolio_fallback(fund_code):
    """
    降级方案：使用旧 API（无占比数据）
    """
    try:
        url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "http://fund.eastmoney.com/"
        }
        response = requests.get(url, headers=headers, timeout=5)
        text = response.text
        
        match = re.search(r'stockCodes=\[(.*?)\]', text)
        if not match:
            return None
            
        codes_str = match.group(1)
        if not codes_str:
            return []
            
        codes = [c.strip('"\'') for c in codes_str.split(',')][:10]
        
        sina_codes = []
        code_map = {}
        
        for code in codes:
            prefix = ""
            if len(code) == 5:
                prefix = "rt_hk"
            elif len(code) == 6:
                if code.startswith('6') or code.startswith('9'):
                    prefix = "sh"
                elif code.startswith('0') or code.startswith('3'):
                    prefix = "sz"
                elif code.startswith('4') or code.startswith('8'):
                    prefix = "bj"
                else:
                    prefix = "sh"
            
            if prefix:
                sina_code = f"{prefix}{code}"
                sina_codes.append(sina_code)
                code_map[sina_code] = code

        if not sina_codes:
            return []
            
        list_str = ",".join(sina_codes)
        hq_url = f"http://hq.sinajs.cn/list={list_str}"
        
        hq_res = requests.get(hq_url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=5)
        hq_res.encoding = 'gbk'
        hq_text = hq_res.text
        
        portfolio = []
        
        for sina_code in sina_codes:
            pattern = f'var hq_str_{sina_code}="(.*?)";'
            hq_match = re.search(pattern, hq_text)
            
            if hq_match:
                data_str = hq_match.group(1)
                parts = data_str.split(',')
                
                item = {
                    "code": code_map[sina_code],
                    "name": "--",
                    "weight": 0,
                    "price": 0,
                    "change_percent": 0,
                    "contribution": 0,
                    "report_period": ""
                }
                
                if "rt_hk" in sina_code:
                    if len(parts) > 6:
                        item["name"] = parts[1]
                        current = float(parts[6]) if parts[6] else 0
                        prev_close = float(parts[3]) if parts[3] else 0
                        item["price"] = current
                        if prev_close > 0:
                            item["change_percent"] = round((current - prev_close) / prev_close * 100, 2)
                else:
                    if len(parts) > 3:
                        item["name"] = parts[0]
                        current = float(parts[3]) if parts[3] else 0
                        prev_close = float(parts[2]) if parts[2] else 0
                        item["price"] = current
                        if prev_close > 0:
                            item["change_percent"] = round((current - prev_close) / prev_close * 100, 2)
                
                portfolio.append(item)
                
        return portfolio

    except Exception as e:
        print(f"降级获取持仓失败 {fund_code}: {e}")
        return None

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
            latest = price_history[-1].copy() # 复制一份，避免直接修改缓存
            # 如果缓存数据太老（超过 30 秒），说明后台可能挂了或未运行，尝试实时抓一次
            if time.time() - latest["timestamp"] > STALE_THRESHOLD_SECONDS:
                data = fetch_gold_price()
                if data:
                    price_history.append(data)
                    save_data()
                    latest = data
            
            # 注入 24 小时摘要信息
            summary = get_24h_summary()
            if summary:
                latest.update(summary)
                
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


@app.route('/api/funds', methods=['GET'])
def get_funds():
    """获取所有自选基金的实时数据 (并发优化版)"""
    results = []
    
    # 使用线程池并发获取数据
    current_time = time.time()
    
    with lock:
        # 复制列表，避免迭代时修改
        current_watchlist = list(fund_watchlist)
    
    # 1. 分离缓存命中和未命中的代码
    codes_to_fetch = []
    # 用于存储最终结果的临时字典，确保按 watchlist 顺序返回
    temp_results = {}
    
    for code in current_watchlist:
        cache_item = fund_cache.get(code)
        if cache_item and (current_time - cache_item['timestamp'] < CACHE_TTL_SECONDS):
            temp_results[code] = cache_item
        else:
            codes_to_fetch.append(code)
            
    # 2. 并发抓取未命中的数据
    if codes_to_fetch:
        with ThreadPoolExecutor(max_workers=MAX_FETCH_WORKERS) as executor:
            # map 会按照输入顺序返回结果
            fetched_data_list = list(executor.map(fetch_fund_data, codes_to_fetch))
            
        # 3. 处理抓取结果
        with lock: # 保护缓存写入
            for i, data in enumerate(fetched_data_list):
                code = codes_to_fetch[i]
                if data:
                    fund_cache[code] = data
                    temp_results[code] = data
                else:
                    # 抓取失败，尝试使用过期缓存
                    old_cache = fund_cache.get(code)
                    if old_cache:
                        # 标记过期
                        if "(过期)" not in old_cache.get('source', ''):
                             old_cache['source'] = f"{old_cache.get('source', '')}(过期)"
                        temp_results[code] = old_cache
                    else:
                        # 完全失败
                        temp_results[code] = {
                            "code": code,
                            "name": "加载失败",
                            "price": 0,
                            "change": 0,
                            "time_str": "--",
                            "source": "Error"
                        }

    # 4. 按顺序组装最终结果
    results = [temp_results.get(code) for code in current_watchlist if temp_results.get(code)]
    
    return jsonify({"success": True, "data": results})



@app.route('/api/funds/<fund_code>/portfolio')
def get_fund_portfolio(fund_code):
    """获取基金持仓详情"""
    data = fetch_fund_portfolio(fund_code)
    if data is not None:
        return jsonify({"success": True, "data": data})
    return jsonify({"success": False, "message": "获取持仓失败"})


@app.route('/api/funds/add', methods=['POST'])
def add_fund():
    """添加自选基金"""
    req_data = request.get_json()
    code = str(req_data.get('code', '')).strip()
    
    if not code or not code.isdigit() or len(code) != 6:
        return jsonify({"success": False, "message": "无效的基金代码 (需6位数字)"})
        
    with lock:
        if code in fund_watchlist:
            return jsonify({"success": False, "message": "该基金已在列表中"})
    
    # 尝试抓取一次以验证代码有效性
    data = fetch_fund_data(code)
    if not data:
        return jsonify({"success": False, "message": "无法获取该基金数据，请确认代码是否正确"})
        
    with lock:
        fund_watchlist.append(code)
        fund_cache[code] = data # 顺便存入缓存
        
    save_data()
    return jsonify({"success": True, "data": data})


@app.route('/api/funds/<code_to_del>', methods=['DELETE'])
def delete_fund(code_to_del):
    """删除自选基金"""
    with lock:
        if code_to_del in fund_watchlist:
            fund_watchlist.remove(code_to_del)
            # 缓存可以选择不删，反正会自动过期，或者删掉省内存
            if code_to_del in fund_cache:
                del fund_cache[code_to_del]
            save_data()
            return jsonify({"success": True})
            
    return jsonify({"success": False, "message": "未找到该基金"})


# ==================== 持仓管理 API ====================
@app.route('/api/holdings', methods=['GET'])
def get_holdings():
    """
    获取持仓数据，并结合实时净值计算盈亏
    """
    with lock:
        holdings = list(fund_holdings)
    
    if not holdings:
        return jsonify({
            "success": True,
            "data": [],
            "summary": {"total_cost": 0, "total_value": 0, "total_profit": 0, "total_profit_rate": 0, "count": 0},
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    
    # 获取所有持仓基金的实时数据
    codes = [h['code'] for h in holdings]
    
    # 并发获取实时数据
    with ThreadPoolExecutor(max_workers=MAX_FETCH_WORKERS) as executor:
        fund_data_list = list(executor.map(fetch_fund_data, codes))
    
    # 合并数据并计算盈亏
    results = []
    total_cost = 0
    total_value = 0
    
    for i, holding in enumerate(holdings):
        fund_data = fund_data_list[i]
        
        cost_price = holding.get('cost_price', 0)
        shares = holding.get('shares', 0)
        cost = cost_price * shares
        total_cost += cost
        
        # 实时数据
        current_price = fund_data['price'] if fund_data else 0
        change = fund_data['change'] if fund_data else 0
        time_str = fund_data.get('time_str', '--') if fund_data else '--'
        source = fund_data.get('source', '--') if fund_data else '--'
        
        # 计算盈亏
        market_value = current_price * shares if current_price > 0 else 0
        total_value += market_value
        
        profit_amount = market_value - cost if current_price > 0 else 0
        profit_rate = ((current_price - cost_price) / cost_price * 100) if cost_price > 0 and current_price > 0 else 0
        
        results.append({
            "code": holding['code'],
            "name": fund_data['name'] if fund_data else holding.get('name', f'基金{holding["code"]}'),
            "cost_price": round(cost_price, 4),
            "shares": round(shares, 2),
            "current_price": round(current_price, 4) if current_price else 0,
            "change": round(change, 2),
            "profit_rate": round(profit_rate, 2),
            "profit_amount": round(profit_amount, 2),
            "market_value": round(market_value, 2),
            "cost": round(cost, 2),
            "time_str": time_str,
            "source": source,
            "note": holding.get('note', ''),
            "data_available": fund_data is not None
        })
    
    # 计算汇总
    total_profit = total_value - total_cost
    total_profit_rate = (total_profit / total_cost * 100) if total_cost > 0 else 0
    
    return jsonify({
        "success": True,
        "data": results,
        "summary": {
            "total_cost": round(total_cost, 2),
            "total_value": round(total_value, 2),
            "total_profit": round(total_profit, 2),
            "total_profit_rate": round(total_profit_rate, 2),
            "count": len(results)
        },
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route('/api/holdings', methods=['POST'])
def add_or_update_holding():
    """
    添加或更新持仓记录
    请求体: { code, cost_price, shares, note? }
    """
    global fund_holdings
    req_data = request.get_json()
    code = str(req_data.get('code', '')).strip()
    
    if not code or not code.isdigit() or len(code) != 6:
        return jsonify({"success": False, "message": "无效的基金代码 (需6位数字)"})
    
    try:
        cost_price = float(req_data.get('cost_price', 0))
        shares = float(req_data.get('shares', 0))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "成本价或份额格式无效"})
    
    note = str(req_data.get('note', '')).strip()
    
    if cost_price <= 0 or shares <= 0:
        return jsonify({"success": False, "message": "成本价和份额必须大于0"})
    
    # 尝试获取基金名称
    fund_data = fetch_fund_data(code)
    name = fund_data['name'] if fund_data else f'基金{code}'
    
    with lock:
        # 检查是否已存在
        existing = next((h for h in fund_holdings if h['code'] == code), None)
        if existing:
            # 更新
            existing['cost_price'] = cost_price
            existing['shares'] = shares
            existing['note'] = note
            existing['name'] = name
        else:
            # 新增
            fund_holdings.append({
                'code': code,
                'name': name,
                'cost_price': cost_price,
                'shares': shares,
                'note': note
            })
    
    save_data()
    return jsonify({"success": True, "message": "持仓已保存"})


@app.route('/api/holdings/<code_to_del>', methods=['DELETE'])
def delete_holding(code_to_del):
    """删除持仓记录"""
    global fund_holdings
    with lock:
        original_len = len(fund_holdings)
        fund_holdings = [h for h in fund_holdings if h['code'] != code_to_del]
        if len(fund_holdings) < original_len:
            save_data()
            return jsonify({"success": True, "message": "持仓已删除"})
    
    return jsonify({"success": False, "message": "未找到该持仓"})



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
