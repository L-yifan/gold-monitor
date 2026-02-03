# -*- coding: utf-8 -*-
"""
基金数据抓取模块
包含基金估值、持仓股抓取和缓存刷新逻辑
"""

import re
import time
import json
import requests
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from app.config import (
    CACHE_TTL_SECONDS, FUND_STALE_TTL_SECONDS,
    HOLDINGS_CACHE_TTL_SECONDS, HOLDINGS_STALE_TTL_SECONDS,
    MAX_FETCH_WORKERS, PORTFOLIO_CACHE_TTL
)
from app.models.state import (
    lock, fund_cache, fund_portfolios, holdings_cache
)
import app.models.state as state
from app.services.persistence import save_data


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
                "dwjz": float(data['dwjz']) if data.get('dwjz') and str(data['dwjz']).strip() else 0,      # 昨日单位净值
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
                # 新浪接口返回: 名称,净值,累计净值,日期
                current_price = float(parts[1]) if parts[1] else 0
                return {
                    "code": fund_code,
                    "name": parts[0],
                    "price": current_price,
                    "dwjz": current_price,  # 新浪接口无昨日净值，使用当前净值作为近似
                    "change": 0,  # 新浪此接口可能无实时估值涨幅
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


def refresh_fund_cache_async(codes):
    """后台刷新基金缓存，避免阻塞接口"""
    if not codes:
        return
    
    with lock:
        if state.fund_refreshing:
            return
        state.fund_refreshing = True

    def _worker():
        try:
            with ThreadPoolExecutor(max_workers=MAX_FETCH_WORKERS) as executor:
                fetched_list = list(executor.map(fetch_fund_data, codes))
            with lock:
                for i, data in enumerate(fetched_list):
                    if data:
                        fund_cache[codes[i]] = data
        finally:
            with lock:
                state.fund_refreshing = False

    threading.Thread(target=_worker, daemon=True).start()


def build_holdings_response(holdings, fund_data_list, cached_map):
    """合并持仓与基金数据，计算盈亏"""
    results = []
    total_cost = 0
    total_value = 0

    for i, holding in enumerate(holdings):
        fund_data = fund_data_list[i] or cached_map.get(holding['code'])

        cost_price = holding.get('cost_price', 0)
        shares = holding.get('shares', 0)
        cost = cost_price * shares
        total_cost += cost

        # 安全获取数值，确保不会是 None（dict.get 在值为 None 时不会返回默认值）
        current_price = (fund_data.get('price') or 0) if fund_data else 0
        change = (fund_data.get('change') or 0) if fund_data else 0
        time_str = fund_data.get('time_str', '--') if fund_data else '--'
        source = fund_data.get('source', '--') if fund_data else '--'

        # 确保数值类型
        try:
            current_price = float(current_price)
            change = float(change)
        except (TypeError, ValueError):
            current_price = 0
            change = 0

        market_value = current_price * shares if current_price > 0 else 0
        total_value += market_value

        profit_amount = market_value - cost if current_price > 0 else 0
        profit_rate = ((current_price - cost_price) / cost_price * 100) if cost_price > 0 and current_price > 0 else 0

        # 计算今日预估盈亏: (当前估值 - 昨日净值) * 持份额
        dwjz = (fund_data.get('dwjz') or 0) if fund_data else 0
        try:
            dwjz = float(dwjz)
        except (TypeError, ValueError):
            dwjz = 0
        
        # 如果 dwjz 不存在但有 change (涨跌幅)，尝试倒推: previous = current / (1 + change/100)
        # 注意: 这种倒推在精确度上可能略有偏差，但作为兜底逻辑可用
        if dwjz <= 0 and current_price > 0 and change != 0:
            try:
                prev_price = current_price / (1 + change / 100)
                dwjz = prev_price
            except (ZeroDivisionError, TypeError, ValueError):
                dwjz = 0

        today_profit = 0
        if dwjz > 0 and current_price > 0:
            today_profit = (current_price - dwjz) * shares

        results.append({
            "code": holding['code'],
            "name": fund_data['name'] if fund_data else holding.get('name', f'基金{holding["code"]}'),
            "cost_price": round(cost_price, 4),
            "shares": round(shares, 2),
            "current_price": round(current_price, 4) if current_price else 0,
            "change": round(change, 2),
            "profit_rate": round(profit_rate, 2),
            "profit_amount": round(profit_amount, 2),
            "today_profit": round(today_profit, 2),
            "market_value": round(market_value, 2),
            "cost": round(cost, 2),
            "time_str": time_str,
            "source": source,
            "note": holding.get('note', ''),
            "data_available": fund_data is not None
        })

    total_profit = total_value - total_cost
    total_profit_rate = (total_profit / total_cost * 100) if total_cost > 0 else 0

    return {
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
    }


def refresh_holdings_cache_async(holdings):
    """后台刷新持仓缓存"""
    if not holdings:
        return
    
    with lock:
        if state.holdings_refreshing:
            return
        state.holdings_refreshing = True

    def _worker():
        try:
            codes = [h['code'] for h in holdings]
            with ThreadPoolExecutor(max_workers=MAX_FETCH_WORKERS) as executor:
                fund_data_list = list(executor.map(fetch_fund_data, codes))

            with lock:
                cached_map = {code: fund_cache.get(code) for code in codes}
                for i, data in enumerate(fund_data_list):
                    if data:
                        fund_cache[codes[i]] = data

            response = build_holdings_response(holdings, fund_data_list, cached_map)
            with lock:
                holdings_cache["timestamp"] = time.time()
                holdings_cache["response"] = response
        finally:
            with lock:
                state.holdings_refreshing = False

    threading.Thread(target=_worker, daemon=True).start()


def build_portfolio_meta(holdings, report_period="", source="", parse_error=None, estimate_mode="none"):
    """构建重仓股贡献估算元数据"""
    weight_coverage = round(
        sum(item.get("weight", 0) for item in holdings if item.get("weight", 0) > 0),
        2
    )
    contribution_total = round(
        sum(
            item.get("contribution", 0)
            for item in holdings
            if isinstance(item.get("contribution"), (int, float))
        ),
        4
    )

    if weight_coverage >= 70:
        confidence_label = "高"
    elif weight_coverage >= 40:
        confidence_label = "中"
    else:
        confidence_label = "低"

    meta = {
        "weight_coverage": weight_coverage,
        "contribution_total": contribution_total,
        "contribution_available": weight_coverage > 0,
        "confidence_label": confidence_label,
        "report_period": report_period,
        "source": source,
        "estimate_mode": estimate_mode
    }
    if parse_error:
        meta["parse_error"] = parse_error
    return meta


def apply_equal_weight_estimate(holdings):
    """对无权重的重仓股使用等权估算贡献"""
    if not holdings:
        return holdings
    weight = round(100 / len(holdings), 2)
    for item in holdings:
        item["weight"] = weight
        if isinstance(item.get("change_percent"), (int, float)):
            item["contribution"] = round(item["weight"] * item["change_percent"] / 100, 4)
        else:
            item["contribution"] = None
    return holdings


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
            return {
                "holdings": [],
                "meta": build_portfolio_meta([], report_period="", source="fallback")
            }
            
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
            return {
                "holdings": [],
                "meta": build_portfolio_meta([], report_period="", source="fallback")
            }
            
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
                    "contribution": None,
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

            return {
                "holdings": portfolio,
                "meta": build_portfolio_meta(portfolio, report_period="", source="fallback")
            }

    except Exception as e:
        print(f"降级获取持仓失败 {fund_code}: {e}")
        return None


def fetch_fund_portfolio(fund_code, force_refresh=False):
    """
    获取基金持仓股票实时数据（含占比和贡献估算）
    1. 检查本地持久化缓存 (24小时有效期)
    2. 若缓存失效，则从天天基金重新获取构成和权重
    3. 从新浪财经获取所有重仓股实时行情
    4. 计算每只股票对基金净值的贡献
    """
    try:
        now_ts = datetime.now().timestamp()
        holdings_info = {}
        report_period = ""
        use_cache = False

        stale_cache_item = None
        # 1. 尝试从持久化缓存获取构成 (有效期 24 小时)
        if not force_refresh:
            with lock:
                if fund_code in fund_portfolios:
                    cache_item = fund_portfolios[fund_code]
                    stale_cache_item = cache_item
                    if now_ts - cache_item.get('timestamp', 0) < PORTFOLIO_CACHE_TTL:
                        holdings_info = cache_item.get('holdings_info', {})
                        report_period = cache_item.get('report_period', "")
                        use_cache = True

        # 2. 如果没有缓存，则从天天基金抓取新数据
        if not use_cache:
            url = f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={fund_code}&topline=10"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "http://fundf10.eastmoney.com/"
            }
            response = requests.get(url, headers=headers, timeout=8)
            if response.status_code != 200:
                return {
                    "holdings": [],
                    "meta": build_portfolio_meta([], report_period=report_period, source="eastmoney", parse_error="请求失败")
                }
            response.encoding = 'utf-8'
            text = response.text

            if not text or len(text) < 200:
                return {
                    "holdings": [],
                    "meta": build_portfolio_meta([], report_period=report_period, source="eastmoney", parse_error="响应内容过短")
                }

            if re.search(r'暂无持仓|暂无数据|无重仓股|未披露', text):
                return {
                    "holdings": [],
                    "meta": build_portfolio_meta([], report_period=report_period, source="eastmoney", parse_error="暂无持仓披露")
                }

            content_match = re.search(r'content\s*:\s*"(.*)"', text, re.S)
            if content_match:
                text = content_match.group(1)
                text = text.replace('\\r', '').replace('\\n', '').replace('\\t', '')
                text = text.replace('\\"', '"')
            
            # 提取报告期（如 "2025年4季度"）
            period_match = re.search(r'(\d{4})年(\d)季度', text)
            if period_match:
                report_period = f"{period_match.group(1)}年{period_match.group(2)}季度"
            
            # 解析 HTML 表格：提取 code, name, weight
            pattern = r"<td[^>]*>\s*<a[^>]*>(\d{5,6})</a>\s*</td>\s*<td[^>]*>\s*<a[^>]*>([^<]+)</a>\s*</td>.*?<td[^>]*>(\d+\.?\d*)%\s*</td>"
            matches = re.findall(pattern, text, re.DOTALL)
            
            if not matches:
                # 先尝试使用过期缓存
                if stale_cache_item and stale_cache_item.get("holdings_info"):
                    holdings_info = stale_cache_item.get("holdings_info", {})
                    report_period = stale_cache_item.get("report_period", report_period)
                    use_cache = True
                else:
                    # 降级：尝试旧 API (旧 API 可能获取不到权重，目前先保持现状)
                    fallback = fetch_fund_portfolio_fallback(fund_code)
                    if fallback and fallback.get("holdings"):
                        holdings = apply_equal_weight_estimate(fallback.get("holdings"))
                        meta = build_portfolio_meta(
                            holdings,
                            report_period=fallback.get("meta", {}).get("report_period", ""),
                            source="fallback",
                            parse_error="解析失败，已使用等权估算",
                            estimate_mode="equal_weight"
                        )
                        meta["contribution_available"] = True
                        return {"holdings": holdings, "meta": meta}
                    return {
                        "holdings": [],
                        "meta": build_portfolio_meta([], report_period=report_period, source="eastmoney", parse_error="解析失败")
                    }
            
            # 构建持仓信息内容
            for code, name, weight in matches:
                if code not in holdings_info and len(holdings_info) < 10:
                    holdings_info[code] = {
                        "name": name,
                        "weight": float(weight)
                    }
            
            if holdings_info:
                # 更新持久化缓存
                with lock:
                    fund_portfolios[fund_code] = {
                        "timestamp": now_ts,
                        "report_period": report_period,
                        "holdings_info": holdings_info
                    }
                # 抓取到新数据后保存到磁盘
                threading.Thread(target=save_data, daemon=True).start()

        if not holdings_info:
            return {
                "holdings": [],
                "meta": build_portfolio_meta([], report_period=report_period, source="eastmoney")
            }
        
        # 3. 映射为新浪 API 格式
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
            return {
                "holdings": [],
                "meta": build_portfolio_meta([], report_period=report_period, source="eastmoney")
            }
            
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
                "contribution": None,
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
                if item["weight"] > 0:
                    item["contribution"] = round(item["weight"] * item["change_percent"] / 100, 4)
            
            portfolio.append(item)
                
        estimate_mode = "none"
        parse_error = None
        if use_cache and stale_cache_item and stale_cache_item.get("holdings_info") and not (now_ts - stale_cache_item.get('timestamp', 0) < PORTFOLIO_CACHE_TTL):
            estimate_mode = "cached_stale"
            parse_error = "使用过期缓存权重估算"
        meta = build_portfolio_meta(
            portfolio,
            report_period=report_period,
            source="eastmoney",
            parse_error=parse_error,
            estimate_mode=estimate_mode
        )
        if estimate_mode != "none":
            meta["contribution_available"] = True
        return {"holdings": portfolio, "meta": meta}

    except Exception as e:
        print(f"获取持仓失败 {fund_code}: {e}")
        return None
