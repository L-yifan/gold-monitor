# -*- coding: utf-8 -*-
"""
Shanghai Gold Exchange (SGE) holiday crawler module
Scrapes closure schedules from www.sge.com.cn
"""

import re
import time
import json
import os
import random
import requests
from datetime import datetime, timedelta

from app.config import (
    SGE_HOLIDAY_URL,
    SGE_HOLIDAY_CACHE_FILE,
    SGE_HOLIDAY_CACHE_TTL,
)


class SgeHolidayCrawler:
    """SGE holiday schedule crawler"""

    MAX_RETRIES = 2
    LIST_TIMEOUT = 20
    DETAIL_TIMEOUT = 30

    def __init__(self):
        self.list_url = SGE_HOLIDAY_URL
        self.base_url = "https://www.sge.com.cn"
        self.cache_file = SGE_HOLIDAY_CACHE_FILE
        self._session = None
        self._ensure_cache_dir()

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _ensure_cache_dir(self):
        cache_dir = os.path.dirname(self.cache_file)
        if cache_dir and not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

    def _load_cache(self):
        if not os.path.exists(self.cache_file):
            return None
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[SGE爬虫] 加载缓存失败: {e}")
            return None

    def _save_cache(self, data):
        try:
            temp = self.cache_file + ".tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp, self.cache_file)
            return True
        except Exception as e:
            print(f"[SGE爬虫] 保存缓存失败: {e}")
            return False

    def _is_cache_valid(self, cache_data, year):
        """Check if cached data for *year* is still fresh."""
        if not cache_data:
            return False
        calendars = cache_data.get("calendars", {})
        entry = calendars.get(str(year))
        if not entry:
            return False
        cached_ts = entry.get("timestamp", 0)
        return (time.time() - cached_ts) < SGE_HOLIDAY_CACHE_TTL

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get_session(self):
        """Lazy-init a requests.Session with browser-like headers."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Connection": "keep-alive",
                "Referer": "https://www.sge.com.cn/",
            })
            # Warm up: visit the home page first to get cookies
            try:
                self._session.get(
                    self.base_url, timeout=self.LIST_TIMEOUT, verify=False,
                )
            except Exception:
                pass  # best-effort
        return self._session

    def _fetch_url(self, url, timeout=None):
        """GET *url* with retry logic.  Returns text or None."""
        if timeout is None:
            timeout = self.LIST_TIMEOUT
        session = self._get_session()
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                resp = session.get(
                    url, timeout=timeout, verify=False,
                )
                if resp.status_code == 200:
                    # Handle common encoding problems
                    content = resp.content
                    try:
                        text = content.decode("utf-8")
                    except UnicodeDecodeError:
                        try:
                            text = content.decode("gbk")
                        except UnicodeDecodeError:
                            text = resp.text
                    return text
                else:
                    print(
                        f"[SGE爬虫] HTTP {resp.status_code} "
                        f"(attempt {attempt + 1})"
                    )
            except Exception as e:
                print(
                    f"[SGE爬虫] 请求失败 (attempt {attempt + 1}): {e}"
                )
            if attempt < self.MAX_RETRIES:
                time.sleep(random.uniform(1, 3))
        return None

    # ------------------------------------------------------------------
    # List page parsing
    # ------------------------------------------------------------------

    def _parse_list_page(self, html):
        """Extract announcement entries from the SGE search results page.

        The actual HTML structure is:
          <a class="... nob" href="/jjsnotice/10007108">
            关于2026年度部分节假日<font color='red'>休市</font>安排的公告
          </a>
          ...
          <p class="fr">2025-12-22 15:31:14</p>

        Returns a list of dicts: [{"title": ..., "url": ..., "date": ...}]
        """
        entries = []

        # Strip HTML tags for title matching, but keep original for href
        # Pattern: find <a> tags whose inner text (after stripping tags)
        #          contains "休市"
        # Each search result block: <div class="searchContList ...">
        blocks = re.split(r'searchContList', html)

        for block in blocks[1:]:  # skip the first split (before first match)
            # Extract href from <a> tag
            href_match = re.search(
                r'<a[^>]+href="([^"]*)"[^>]*>(.*?)</a>',
                block, re.DOTALL,
            )
            if not href_match:
                continue

            href = href_match.group(1).strip()
            raw_title = href_match.group(2).strip()
            # Strip all HTML tags from title
            title = re.sub(r'<[^>]+>', '', raw_title).strip()

            if "休市" not in title:
                continue

            # Extract date from <p class="fr">
            date_match = re.search(
                r'<p\s+class="fr"\s*>\s*(\d{4}-\d{2}-\d{2})',
                block,
            )
            date_str = date_match.group(1) if date_match else ""

            full_url = (
                href if href.startswith("http")
                else self.base_url + href
            )
            entries.append({
                "title": title,
                "url": full_url,
                "date": date_str,
            })

        if entries:
            print(f"[SGE爬虫] 找到 {len(entries)} 条休市公告")

        return entries

    # ------------------------------------------------------------------
    # Detail page parsing
    # ------------------------------------------------------------------

    def _parse_holiday_detail(self, html, year):
        """Parse a single announcement detail page.

        Returns dict or None:
        {
            "holidays": {"春节": ["2026-02-15", ...], ...},
            "first_trading_days": {"春节": "2026-02-24", ...},
        }
        """
        holidays = {}
        first_trading_days = {}

        holiday_names = [
            "元旦", "春节", "清明节", "劳动节",
            "端午节", "中秋节", "国庆节",
        ]

        # Strategy A – named sections like "一、春节：..."
        for name in holiday_names:
            # Step 1: Find the section for this holiday
            # SGE format: "一、元旦：...二、春节：..." or with HTML tags
            # Extract text from this holiday name to the next numbered section
            section_pat = re.compile(
                rf'{name}[：:](.*?)(?=[一二三四五六七八九十]+[、.．]|$)',
                re.DOTALL,
            )
            section_m = section_pat.search(html)
            if not section_m:
                continue

            section_text = section_m.group(1)
            # Strip HTML tags for cleaner matching
            clean_text = re.sub(r'<[^>]+>', '', section_text)

            # Step 2: Find closure date range (X月X日至X月X日休市)
            closure_pat = re.compile(
                r'(\d{1,2})\s*月\s*(\d{1,2})\s*日'
                r'[^至]*?至[^月]*?'
                r'(\d{1,2})\s*月\s*(\d{1,2})\s*日'
                r'[^休]*?休市',
            )
            closure_m = closure_pat.search(clean_text)
            if not closure_m:
                continue

            sm, sd = int(closure_m.group(1)), int(closure_m.group(2))
            em, ed = int(closure_m.group(3)), int(closure_m.group(4))
            dates = self._expand_date_range(year, sm, sd, em, ed)
            if dates:
                holidays[name] = dates

            # Step 3: Find first trading day – the date immediately
            #         before "开市" (e.g. "1月5日（星期一）起照常开市")
            ft_pat = re.compile(
                r'(\d{1,2})\s*月\s*(\d{1,2})\s*日[^月]*?(?:起照常|恢复)?开市',
            )
            ft_m = ft_pat.search(clean_text)
            if ft_m:
                ftm, ftd = int(ft_m.group(1)), int(ft_m.group(2))
                first_trading_days[name] = (
                    f"{year}-{ftm:02d}-{ftd:02d}"
                )

        # Strategy B – fallback: unnamed date ranges
        if not holidays:
            pat = re.compile(
                r'(\d{1,2})\s*月\s*(\d{1,2})\s*日'
                r'[^至]*?至[^月]*?'
                r'(\d{1,2})\s*月\s*(\d{1,2})\s*日'
                r'[^休]*?休市'
            )
            for m in pat.finditer(html):
                sm, sd = int(m.group(1)), int(m.group(2))
                em, ed = int(m.group(3)), int(m.group(4))
                name = self._guess_holiday_name(sm, sd)
                if name and name not in holidays:
                    dates = self._expand_date_range(year, sm, sd, em, ed)
                    if dates:
                        holidays[name] = dates

        if not holidays:
            return None

        return {
            "holidays": holidays,
            "first_trading_days": first_trading_days,
        }

    # ------------------------------------------------------------------
    # Date helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _expand_date_range(year, sm, sd, em, ed):
        """Expand month/day range into a list of YYYY-MM-DD strings."""
        try:
            start = datetime(year, sm, sd)
            end = datetime(year, em, ed)
            dates = []
            cur = start
            while cur <= end:
                dates.append(cur.strftime("%Y-%m-%d"))
                cur += timedelta(days=1)
            return dates
        except Exception as e:
            print(f"[SGE爬虫] 日期解析错误: {e}")
            return []

    @staticmethod
    def _guess_holiday_name(month, day):
        """Heuristically guess the holiday name from start date."""
        if month == 1:
            return "元旦"
        if month == 2 and day >= 10:
            return "春节"
        if month == 4 and day <= 7:
            return "清明节"
        if month == 5 and day <= 5:
            return "劳动节"
        if month == 6 and 15 <= day <= 25:
            return "端午节"
        if month == 9 and day >= 20:
            return "中秋节"
        if month == 10 and day <= 7:
            return "国庆节"
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def crawl_holidays(self, year=None):
        """Crawl SGE holiday schedule for *year*.

        Returns dict or None:
        {
            "year": 2026,
            "source": "sge_crawler",
            "holidays": {...},
            "first_trading_days": {...},
            "all_holiday_dates": [...],
            "timestamp": ...,
        }
        """
        if year is None:
            year = datetime.now().year

        # 1. Check cache first
        cache = self._load_cache()
        if self._is_cache_valid(cache, year):
            print(f"[SGE爬虫] 使用 {year} 年缓存数据")
            return cache["calendars"][str(year)]

        # 2. Fetch the listing page
        print(f"[SGE爬虫] 开始爬取 {year} 年休市安排...")
        list_html = self._fetch_url(self.list_url)
        if not list_html:
            print("[SGE爬虫] 列表页获取失败，尝试使用缓存")
            return self._get_from_cache(cache, year)

        # 3. Parse listing to find matching announcement
        entries = self._parse_list_page(list_html)
        if not entries:
            print("[SGE爬虫] 未在列表页找到休市公告")
            return self._get_from_cache(cache, year)

        # Find the entry for the target year
        target_entry = None
        for entry in entries:
            if str(year) in entry.get("title", ""):
                target_entry = entry
                break
        # Fallback: use newest entry if year not explicitly matched
        if not target_entry and entries:
            target_entry = entries[0]

        if not target_entry:
            return self._get_from_cache(cache, year)

        print(f"[SGE爬虫] 找到公告: {target_entry['title']}")

        # 4. Fetch and parse detail page
        time.sleep(random.uniform(0.5, 1.5))  # polite delay
        detail_html = self._fetch_url(target_entry["url"], timeout=self.DETAIL_TIMEOUT)
        if not detail_html:
            print("[SGE爬虫] 详情页获取失败")
            return self._get_from_cache(cache, year)

        parsed = self._parse_holiday_detail(detail_html, year)
        if not parsed:
            print("[SGE爬虫] 详情页解析失败")
            return self._get_from_cache(cache, year)

        # 5. Build result
        all_dates = set()
        for dates in parsed["holidays"].values():
            all_dates.update(dates)

        result = {
            "year": year,
            "source": "sge_crawler",
            "holidays": parsed["holidays"],
            "first_trading_days": parsed["first_trading_days"],
            "all_holiday_dates": sorted(all_dates),
            "timestamp": time.time(),
        }

        # 6. Update cache
        self._update_cache(result)
        count = len(result["all_holiday_dates"])
        print(f"[SGE爬虫] 成功获取 {year} 年数据，共 {count} 天休市")
        return result

    def get_holidays(self, year=None):
        """Return a set of holiday date strings for *year*."""
        data = self.crawl_holidays(year)
        if data:
            return set(data.get("all_holiday_dates", []))
        return set()

    def get_first_trading_day(self, holiday_name, year=None):
        """Get the first trading day after *holiday_name*."""
        data = self.crawl_holidays(year)
        if data:
            return data.get("first_trading_days", {}).get(holiday_name)
        return None

    # ------------------------------------------------------------------
    # Internal cache helpers
    # ------------------------------------------------------------------

    def _get_from_cache(self, cache, year):
        """Return cached data for *year* regardless of TTL, or None."""
        if not cache:
            return None
        calendars = cache.get("calendars", {})
        entry = calendars.get(str(year))
        if entry:
            print(f"[SGE爬虫] 使用过期缓存 {year} 年数据")
            return entry
        return None

    def _update_cache(self, result):
        year = result.get("year")
        cache = self._load_cache() or {
            "metadata": {
                "version": "1.0",
                "source": "sge_crawler",
                "last_updated": datetime.now().isoformat(),
            },
            "calendars": {},
        }
        cache["calendars"][str(year)] = result
        cache["metadata"]["last_updated"] = datetime.now().isoformat()
        self._save_cache(cache)


# ------------------------------------------------------------------
# Module-level convenience API
# ------------------------------------------------------------------

_crawler = None


def get_crawler():
    global _crawler
    if _crawler is None:
        _crawler = SgeHolidayCrawler()
    return _crawler


def fetch_sge_holidays(year=None):
    """Quick helper – returns a set of date strings."""
    return get_crawler().get_holidays(year)


def fetch_sge_holiday_data(year=None):
    """Quick helper – returns full result dict or None."""
    return get_crawler().crawl_holidays(year)


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")

    print("=== SGE Holiday Crawler Test ===\n")
    crawler = SgeHolidayCrawler()

    result = crawler.crawl_holidays(2026)
    if result:
        print(f"\nYear: {result['year']}")
        print(f"Source: {result['source']}")
        print(f"\nHoliday details:")
        for name, dates in result.get("holidays", {}).items():
            print(f"  {name}: {dates}")
        cnt = len(result.get("all_holiday_dates", []))
        print(f"\nTotal closure days: {cnt}")
        print(result.get("all_holiday_dates"))
        print(f"\nFirst trading days:")
        for name, d in result.get("first_trading_days", {}).items():
            print(f"  After {name}: {d}")
    else:
        print("Crawl returned None (website may be unreachable).")
