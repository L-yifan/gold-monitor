# -*- coding: utf-8 -*-
"""
交易所交易日历爬虫模块
从上海证券交易所官网获取A股交易日历
"""

import re
import json
import os
import requests
from datetime import datetime, timedelta

from app.config import (
    EXCHANGE_CALENDAR_URL,
    EXCHANGE_CALENDAR_FILE
)


class ExchangeCalendarCrawler:
    """交易所交易日历爬虫"""
    
    def __init__(self):
        self.url = EXCHANGE_CALENDAR_URL
        self.base_url = "https://www.sse.com.cn/"
        self.cache_file = EXCHANGE_CALENDAR_FILE
        self._session = requests.Session()
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        cache_dir = os.path.dirname(self.cache_file)
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            
    def _warm_up(self):
        """访问首页建立 Session/Cookies"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            self._session.get(self.base_url, headers=headers, timeout=5)
            return True
        except:
            return False
    
    def _load_cache(self):
        """从文件加载缓存"""
        if not os.path.exists(self.cache_file):
            return None
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[交易所日历] 加载缓存失败: {e}")
            return None
    
    def _save_cache(self, data):
        """保存到文件"""
        try:
            temp_file = self.cache_file + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, self.cache_file)
            return True
        except Exception as e:
            print(f"[交易所日历] 保存缓存失败: {e}")
            return False
    
    def _fetch_page(self):
        """获取上交所页面内容"""
        # 预热以获取 cookies
        self._warm_up()
        
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": self.base_url
            }
            response = self._session.get(self.url, headers=headers, timeout=10)
            
            # 优先尝试 utf-8，然后尝试 gbk
            content = response.content
            try:
                text = content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    text = content.decode('gbk')
                except UnicodeDecodeError:
                    text = response.text
            
            if len(text) < 1000:
                print(f"[交易所日历] 页面内容异常短 (长度: {len(text)})，可能被拦截")
                
            return text
            
        except Exception as e:
            print(f"[交易所日历] 获取页面失败: {e}")
            return None
    
    def _parse_date_range(self, text, year=2026):
        """解析日期范围文本，返回日期列表"""
        dates = []
        
        # 匹配格式：X月X日（星期X）至X月X日（星期X）
        # 兼容“第二段省略月份”：如“2月15日至23日”
        pattern = r'(\d{1,2})\s*月\s*(\d{1,2})\s*日[^\d]*?(?:至|到|-|—|~)[^\d]*?(?:(\d{1,2})\s*月)?\s*(\d{1,2})\s*日'
        match = re.search(pattern, text)
        
        if match:
            start_month = int(match.group(1))
            start_day = int(match.group(2))
            end_month = int(match.group(3)) if match.group(3) else start_month
            end_day = int(match.group(4))
            
            try:
                start_date = datetime(year, start_month, start_day)
                end_date = datetime(year, end_month, end_day)
                
                current = start_date
                while current <= end_date:
                    dates.append(current.strftime("%Y-%m-%d"))
                    current += timedelta(days=1)
            except Exception as e:
                print(f"[交易所日历] 日期解析错误: {e}")
        else:
            # 尝试匹配单日休市：X月X日休市
            single_pattern = r'(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:（[^）]+）)?\s*休市'
            single_match = re.search(single_pattern, text)
            if single_match:
                sm, sd = int(single_match.group(1)), int(single_match.group(2))
                try:
                    dates.append(datetime(year, sm, sd).strftime("%Y-%m-%d"))
                except:
                    pass
        
        return dates
    
    def _find_first_trading_day(self, text, year=2026):
        """从文本中找到首个交易日"""
        # 匹配格式：X月X日（星期X）起照常开市
        pattern = r'(\d{1,2})\s*月\s*(\d{1,2})\s*日[^\d]*?起(?:照常|恢复)?开市'
        match = re.search(pattern, text)
        
        if match:
            month = int(match.group(1))
            day = int(match.group(2))
            return f"{year}-{month:02d}-{day:02d}"
        
        return None
    
    def parse_year_from_content(self, content, year=2026):
        """解析页面内容，提取指定年份的休市安排"""
        holidays = {}
        first_trading_days = {}
        
        # 使用正则直接搜索内容
        # 先找到包含年份的区块
        # 格式类似：<td>2月15日（星期日）至2月23日（星期一）休市，2月24日（星期二）起照常开市</td>
        
        # 匹配所有包含日期范围的行
        # 格式：X月X日（周X）至X月X日（周X）休市，X月X日（周X）起照常开市
        holiday_names = ['元旦', '春节', '清明节', '劳动节', '端午节', '中秋节', '国庆节']
        
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            
            # 找到所有的行
            for tr in soup.find_all('tr'):
                cells = tr.find_all('td')
                if len(cells) >= 2:
                    td1_text = cells[0].get_text(strip=True)
                    td2_text = cells[1].get_text(strip=True)
                    
                    for name in holiday_names:
                        # 兼容部分乱码情况，如果在原始 td 的 html 里能找到名字也可以
                        if name in td1_text or name in str(cells[0]):
                            # 找到了休市安排说明单元格 td2_text
                            # 示例：1月1日（星期四）至1月3日（星期六）休市，1月5日（星期一）起照常开市
                            
                            # 解析日期范围
                            dates = self._parse_date_range(td2_text, year)
                            if dates:
                                holidays[name] = dates
                            
                            # 查找首个交易日
                            first_day = self._find_first_trading_day(td2_text, year)
                            if first_day:
                                first_trading_days[name] = first_day
                            break
                            
            # 备用方案（如果基于表格解析失败，或者上交所更换了格式，回退到无标签的正文暴搜）
            if not holidays:
                clean_text = soup.get_text()
                pattern = r'(\d{1,2})月(\d{1,2})日[^\d至]*至[^\d]*(?:(\d{1,2})月)?(\d{1,2})日[^\d]*休市'
                for match in re.finditer(pattern, clean_text):
                    try:
                        start_month = int(match.group(1))
                        start_day = int(match.group(2))
                        end_month = int(match.group(3)) if match.group(3) else start_month
                        
                        if start_month == 1: name = '元旦'
                        elif start_month == 2 and start_day >= 14: name = '春节'
                        elif start_month == 4: name = '清明节'
                        elif start_month == 5: name = '劳动节'
                        elif start_month == 6: name = '端午节'
                        elif start_month == 9: name = '中秋节'
                        elif start_month == 10: name = '国庆节'
                        else: continue
                        
                        if name not in holidays:
                            dates = self._parse_date_range(match.group(0), year)
                            if dates:
                                holidays[name] = dates
                    except:
                        continue
        except Exception as e:
            print(f"[交易所日历] bs4 解析异常: {e}")
        
        if not holidays:
            print(f"[交易所日历] 未能解析出任何节假日")
            return None
        
        # 生成所有休市日期
        all_dates = set()
        for dates in holidays.values():
            all_dates.update(dates)
        
        return {
            "year": year,
            "holidays": holidays,
            "first_trading_days": first_trading_days,
            "all_holiday_dates": sorted(all_dates)
        }
    
    def crawl_year(self, year=None):
        """爬取指定年份的交易日历"""
        if year is None:
            year = datetime.now().year
        
        # 优先从缓存加载，避免频繁请求导致的挂起或封禁
        cached = self._load_from_cache(year)
        if cached:
            return cached
            
        # 尝试获取页面
        content = self._fetch_page()
        if not content:
            print(f"[交易所日历] 爬取失败，且无本地缓存")
            return None
        
        # 解析内容
        result = self.parse_year_from_content(content, year)
        if not result:
            return self._load_from_cache(year)
        
        # 更新缓存
        self._update_cache(result)
        
        return result
    
    def _load_from_cache(self, year):
        """从缓存加载"""
        cache = self._load_cache()
        if not cache:
            return None
        
        calendars = cache.get("calendars", {})
        if str(year) in calendars:
            return calendars[str(year)]
        
        # 尝试找最近的年份
        for y in range(year, year - 3, -1):
            if str(y) in calendars:
                print(f"[交易所日历] 使用缓存的 {y} 年数据")
                return calendars[str(y)]
        
        return None
    
    def _update_cache(self, new_data):
        """更新缓存"""
        year = new_data.get("year")
        
        cache = self._load_cache() or {
            "metadata": {
                "version": "3.0",
                "source": "sse_crawler",
                "url": self.url,
                "last_updated": datetime.now().isoformat()
            },
            "calendars": {}
        }
        
        cache["calendars"][str(year)] = new_data
        cache["metadata"]["last_updated"] = datetime.now().isoformat()
        
        self._save_cache(cache)
        print(f"[交易所日历] 已更新 {year} 年数据，共 {len(new_data.get('all_holiday_dates', []))} 天休市")
    
    def get_holidays(self, year=None):
        """获取指定年份的休市日期集合"""
        data = self.crawl_year(year)
        if data:
            return set(data.get("all_holiday_dates", []))
        return set()
    
    def get_first_trading_day(self, holiday_name, year=None):
        """获取指定节假日后的首个交易日"""
        data = self.crawl_year(year)
        if data:
            return data.get("first_trading_days", {}).get(holiday_name)
        return None

    def get_holiday_name_by_date(self, date_str, year=None):
        """获取指定日期所在的节假日名称"""
        if year is None:
            try:
                year = int(date_str.split('-')[0])
            except:
                year = datetime.now().year
        
        data = self.crawl_year(year)
        if data:
            holidays = data.get("holidays", {})
            for name, dates in holidays.items():
                if date_str in dates:
                    return name
        return None
# 全局爬虫实例
_crawler = None


def get_crawler():
    """获取爬虫单例"""
    global _crawler
    if _crawler is None:
        _crawler = ExchangeCalendarCrawler()
    return _crawler


def fetch_exchange_holidays(year=None):
    """获取交易所休市日期（快捷函数）"""
    return get_crawler().get_holidays(year)


def fetch_exchange_holidays_with_status(year=None):
    """
    获取交易所休市日期并返回数据可用状态

    返回:
        tuple(set, bool): (休市日期集合, 是否成功获取到可用日历)
    """
    data = get_crawler().crawl_year(year)
    if data:
        return set(data.get("all_holiday_dates", [])), True
    return set(), False


def get_holiday_name_by_date(date_str, year=None):
    """获取指定日期所在的节假日名称（快捷函数）"""
    return get_crawler().get_holiday_name_by_date(date_str, year)


def get_first_trading_day(holiday_name, year=None):
    """获取指定节假日后的首个交易日（快捷函数）"""
    return get_crawler().get_first_trading_day(holiday_name, year)


def get_exchange_holiday_name_by_date(date_str, year=None):
    """兼容旧命名：获取指定日期所在的节假日名称"""
    return get_holiday_name_by_date(date_str, year)


def get_exchange_first_trading_day_from_crawler(holiday_name, year=None):
    """兼容旧命名：获取指定节假日后的首个交易日"""
    return get_first_trading_day(holiday_name, year)


if __name__ == "__main__":
    # 测试
    print("=== 测试交易所日历爬虫 ===")
    crawler = ExchangeCalendarCrawler()
    
    # 爬取2026年数据
    result = crawler.crawl_year(2026)
    
    if result:
        print(f"\n年份: {result['year']}")
        print(f"\n节假日明细:")
        for name, dates in result.get("holidays", {}).items():
            print(f"  {name}: {dates}")
        
        print(f"\n所有休市日期 ({len(result['all_holiday_dates'])}天):")
        print(result["all_holiday_dates"])
        
        print(f"\n首个交易日:")
        for name, date in result.get("first_trading_days", {}).items():
            print(f"  {name}后: {date}")
    else:
        print("获取失败")
