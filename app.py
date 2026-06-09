import asyncio
import json
import os
import re
import time
import threading
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

import requests as req_lib
from flask import Flask, render_template, jsonify, request
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup

_stealth = Stealth()

app = Flask(__name__)

HUMOR_URL  = "https://www.fmkorea.com/humor"
PATCH_URL  = "https://www.fmkorea.com/search.php?query=패치노트&st=title&sn=off&ss=on&so=r"
OHMYHUMOR_URL = "http://www.todayhumor.co.kr/board/list.php?table=bestofbest"
REDDIT_URL    = "https://www.reddit.com/r/funny/hot.json"
ARCA_URL      = "https://arca.live/b/humor"

YOUTUBE_CHANNELS = [
    {"handle": "@humor_zoo",  "label": "humor_zoo",  "shorts": True},
    {"handle": "@humorfarm",  "label": "humorfarm",  "shorts": False},
    {"handle": "@puppyd5g",   "label": "puppyd5g",   "shorts": True},
]

FILTER_KEYWORDS = {
    "성적": [
        "야동", "성인", "19금", "야사", "섹스", "원조", "조건",
        "성매매", "몰카", "포르노", "음란",
    ],
    "위해": [
        "자살", "자해", "폭발물", "테러", "마약", "살인", "폭행", "살해",
    ],
    "정치": [
        "선거", "투표", "탄핵", "대선", "총선", "재선거", "보선",
        "여당", "야당", "좌파", "우파", "부정선거", "계엄", "당선",
        "민주당", "국민의힘", "더불어민주", "국힘", "진보당",
        "이재명", "윤석열", "오세훈", "박근혜", "문재인",
        "김부겸", "한동훈", "이준석", "안철수", "대구경북",
        "복위", "503번", "집권", "정권교체", "정권",
    ],
    "군사방산": [
        "방산", "포대", "미사일", "전투기", "천궁", "전쟁기념관",
    ],
    "사회갈등": [
        "젠더", "페미", "반일", "혐오", "노조", "파업",
        "집회", "시위", "2030", "MZ세대", "저출산 대책",
        "청년정책", "인구절벽",
    ],
    "법조수사": [
        "검찰", "재판", "판결", "선고", "구속", "기소",
        "구속영장", "무죄", "유죄", "항소", "상고", "수사",
        "고발", "고소장", "영장",
    ],
    "뉴스기사": [
        "속보", "단독", "사퇴", "사임", "논란", "파문",
        "충격", "경고", "해명", "입장문",
    ],
}

_FILTER_PATTERNS = [
    re.compile(r'[가-힣]\(\d{1,2}\)\s*$'),   # "이유(10)" 뉴스 클릭베이트 형식
    re.compile(r'\.\.\.?\d+\)\s*$'),           # "...이유(3)" 형식
]

SKIP_TITLES = ["전체 삭제", "공지", "규정", "금지", "차단", "신고", "불만글"]
CACHE_TTL = 900

# 필터 카테고리 메타데이터 (프론트에 노출)
FILTER_CATEGORY_META = {
    "정치":    {"label": "정치 용어",     "emoji": "🏛",  "desc": "여당·야당·선거·탄핵 등"},
    "정치인":  {"label": "정치인 이름",   "emoji": "👤",  "desc": "현직·전직 주요 정치인"},
    "법조수사":{"label": "법조·수사",     "emoji": "⚖️",  "desc": "검찰·재판·구속·판결 등"},
    "사회갈등":{"label": "사회 갈등",     "emoji": "🔥",  "desc": "페미·젠더·반일·이념 갈등"},
    "뉴스기사":{"label": "뉴스 기사형",   "emoji": "📰",  "desc": "단독·속보·의혹·사퇴 등"},
    "성적":    {"label": "성인·선정",     "emoji": "🔞",  "desc": "성적 콘텐츠"},
    "위해":    {"label": "위해·혐오",     "emoji": "⛔",  "desc": "자해·폭력·테러·마약"},
    "스포츠":  {"label": "스포츠",        "emoji": "⚽",  "desc": "축구·야구·농구 등"},
    "게임":    {"label": "게임",          "emoji": "🎮",  "desc": "롤·오버워치·배그 등"},
}

_HAS_ENGLISH = re.compile(r'[a-zA-Z]')
_KST = timezone(timedelta(hours=9))


def _relative_time(time_text):
    if not time_text:
        return ""
    try:
        if ":" in time_text and len(time_text) == 5:
            h, m = map(int, time_text.split(":"))
            now = datetime.now(_KST)
            post_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if post_dt > now:
                post_dt -= timedelta(days=1)
            diff_min = int((now - post_dt).total_seconds() / 60)
            if diff_min < 1:
                return "방금 전"
            if diff_min < 60:
                return f"{diff_min}분 전"
            h_ago = diff_min // 60
            return f"{h_ago}시간 전"
        return time_text
    except Exception:
        return time_text

_cache = {}
_thumb_cache = {}
_lock = threading.Lock()

# ─── AI 소재 채점 (shorts_filter) ───────────────────────────
_sf_available = False
_score_fn = None
_score_batch_fn = None
_score_cache: dict = {}
_score_lock = threading.Lock()

_translate_score_fn = None
try:
    if os.environ.get("GROQ_API_KEY"):
        from shorts_filter import score_material as _score_fn  # type: ignore
        from shorts_filter import score_batch as _score_batch_fn  # type: ignore
        from shorts_filter import translate_and_score_batch as _translate_score_fn  # type: ignore
        _sf_available = True
except Exception as _sf_err:
    pass




def is_filtered(title):
    for skip in SKIP_TITLES:
        if skip in title:
            return True
    for keywords in FILTER_KEYWORDS.values():
        for kw in keywords:
            if kw in title:
                return True
    for pat in _FILTER_PATTERNS:
        if pat.search(title):
            return True
    return False


def filter_reason(title):
    """필터 적용 이유 반환 (디버깅/통계용)"""
    for skip in SKIP_TITLES:
        if skip in title:
            return f"skip:{skip}"
    for cat, keywords in FILTER_KEYWORDS.items():
        for kw in keywords:
            if kw in title:
                return f"{cat}:{kw}"
    for i, pat in enumerate(_FILTER_PATTERNS):
        if pat.search(title):
            return f"pattern:{i}"
    return None


def is_korean_only(title):
    return not _HAS_ENGLISH.search(title)


_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()

_pw = None
_browser = None


async def _ensure_browser():
    global _pw, _browser
    if _browser is not None:
        try:
            if _browser.is_connected():
                return _browser
        except Exception:
            pass
    if _pw:
        try:
            await _pw.stop()
        except Exception:
            pass
    _pw = await async_playwright().start()
    _browser = await _pw.chromium.launch(args=[
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--lang=ko-KR",
    ])
    return _browser


def _run_async(coro):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=60)


def _parse_fmkorea_html(html, extra_filter=None):
    """펨코 HTML → 게시물 리스트 파싱."""
    soup = BeautifulSoup(html, "html.parser")
    results, seen = [], set()
    filtered_count = 0
    for row in soup.select("table.bd_lst tr"):
        title_el = row.select_one("td.title a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href  = title_el.get("href", "")
        if not title or len(title) < 3:
            continue
        if href and not href.startswith("http"):
            href = "https://www.fmkorea.com" + href
        if href in seen:
            continue
        seen.add(href)
        if is_filtered(title):
            filtered_count += 1
            continue
        if extra_filter and not extra_filter(title):
            continue
        time_cell = row.select_one("td.time")
        time_text = _relative_time(time_cell.get_text(strip=True)) if time_cell else ""
        views_text = ""
        for td in row.select("td.m_no"):
            if "m_no_voted" not in (td.get("class") or []):
                views_text = td.get_text(strip=True)
                break
        voted_cell = row.select_one("td.m_no_voted")
        voted_text = voted_cell.get_text(strip=True) if voted_cell else ""
        try:
            voted_num = int(voted_text.replace(",", "")) if voted_text else 0
        except ValueError:
            voted_num = 0
        if voted_cell and voted_num < 1:
            continue
        results.append({
            "title": title, "url": href, "date": time_text,
            "views": views_text, "recommend": voted_text,
            "source": "펨코",
        })
    return results, filtered_count


_cffi_session = None

def _get_cffi_session():
    global _cffi_session
    if _cffi_session is None:
        try:
            from curl_cffi import requests as _cffi_lib
            _cffi_session = _cffi_lib.Session(impersonate="chrome124")
        except Exception:
            pass
    return _cffi_session


def _fetch_fmkorea_light(url, extra_filter=None):
    """curl_cffi Chrome 핑거프린트로 펨코 스크래핑 (Playwright 불필요)."""
    session = _get_cffi_session()
    if session is None:
        return [], 0
    try:
        r = session.get(url, headers={"Accept-Language": "ko-KR,ko;q=0.9"}, timeout=15)
        if r.status_code != 200:
            return [], 0
        if "보안시스템" in r.text[:2000]:
            return [], 0
        return _parse_fmkorea_html(r.text, extra_filter)
    except Exception:
        return [], 0


async def _scrape_page(browser, url, extra_filter=None):
    """Playwright fallback scraper (curl_cffi 실패 시 사용)."""
    page = await browser.new_page()
    await _stealth.apply_stealth_async(page)
    async def handle_route(route):
        if route.request.resource_type in ("image", "font", "media", "stylesheet"):
            await route.abort()
        else:
            await route.continue_()
    await page.route("**/*", handle_route)
    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(3000)
    try:
        await page.wait_for_selector("table.bd_lst tr", timeout=5000)
    except Exception:
        pass
    html = await page.content()
    await page.close()
    return _parse_fmkorea_html(html, extra_filter)


async def _ai_filter_posts(posts):
    """AI로 게시물 채점. category + score(0~10) 필드 추가."""
    if not _sf_available or not posts:
        return posts, 0

    loop = asyncio.get_event_loop()
    BATCH = 20
    all_results: list[dict] = []

    for i in range(0, len(posts), BATCH):
        chunk = posts[i:i + BATCH]
        titles = [p["title"] for p in chunk]
        try:
            results = await loop.run_in_executor(None, lambda t=titles: _score_batch_fn(t))
        except Exception:
            results = [{"category": "기타", "score": 0}] * len(chunk)
        all_results.extend(results)

    tagged = []
    for post, result in zip(posts, all_results):
        post_copy = dict(post)
        post_copy["category"] = result["category"]
        post_copy["score"] = result["score"]
        tagged.append(post_copy)
    return tagged, 0


async def _scrape(url, extra_filter=None, pages=1):
    loop = asyncio.get_event_loop()
    page_urls = [url if pg == 1 else f"{url}?page={pg}" for pg in range(1, pages + 1)]
    results, seen = [], set()
    total_filtered = 0

    # 1차: curl_cffi (빠름, Playwright 불필요)
    for i, page_url in enumerate(page_urls):
        if i > 0:
            await asyncio.sleep(1)
        posts, fc = await loop.run_in_executor(
            None, lambda u=page_url: _fetch_fmkorea_light(u, extra_filter)
        )
        total_filtered += fc
        for post in posts:
            if post["url"] not in seen:
                seen.add(post["url"])
                results.append(post)

    # 2차: curl_cffi 실패 시 Playwright fallback
    if not results:
        browser = await _ensure_browser()
        for i, page_url in enumerate(page_urls):
            if i > 0:
                await asyncio.sleep(2)
            posts, fc = await _scrape_page(browser, page_url, extra_filter)
            total_filtered += fc
            for post in posts:
                if post["url"] not in seen:
                    seen.add(post["url"])
                    results.append(post)

    results, ai_dropped = await _ai_filter_posts(results)
    return results, total_filtered + ai_dropped


_refreshing = set()


def _do_refresh_async(key, url, extra_filter, async_fn):
    try:
        if async_fn is not None:
            result = _run_async(async_fn())
        else:
            result = _run_async(_scrape(url, extra_filter))
        posts, filtered = result if isinstance(result, tuple) else (result, 0)
        now = time.time()
        with _lock:
            _cache[key] = {
                "posts": posts,
                "filtered": filtered,
                "timestamp": now,
                "fetched_at": datetime.now().strftime("%H:%M:%S 기준"),
            }
    finally:
        _refreshing.discard(key)


def _do_refresh_sync(key, fetcher):
    try:
        posts = fetcher()
        now = time.time()
        with _lock:
            _cache[key] = {
                "posts": posts,
                "filtered": 0,
                "timestamp": now,
                "fetched_at": datetime.now().strftime("%H:%M:%S 기준"),
            }
    finally:
        _refreshing.discard(key)


def get_cached(key, url=None, force=False, extra_filter=None, async_fn=None):
    with _lock:
        cached = _cache.get(key, {})
        now = time.time()
        fresh = not force and cached.get("timestamp", 0) and now - cached["timestamp"] < CACHE_TTL
        if fresh:
            return cached["posts"], cached["fetched_at"], cached.get("filtered", 0)
        if cached.get("posts") and key not in _refreshing:
            _refreshing.add(key)
            t = threading.Thread(target=_do_refresh_async, args=(key, url, extra_filter, async_fn), daemon=True)
            t.start()
            return cached["posts"], cached["fetched_at"] + " (갱신 중)", cached.get("filtered", 0)
    if async_fn is not None:
        result = _run_async(async_fn())
    else:
        result = _run_async(_scrape(url, extra_filter))
    posts, filtered = result if isinstance(result, tuple) else (result, 0)
    now = time.time()
    with _lock:
        _cache[key] = {
            "posts": posts,
            "filtered": filtered,
            "timestamp": now,
            "fetched_at": datetime.now().strftime("%H:%M:%S 기준"),
        }
        _refreshing.discard(key)
    return posts, _cache[key]["fetched_at"], filtered


def get_cached_sync(key, fetcher, force=False):
    with _lock:
        cached = _cache.get(key, {})
        now = time.time()
        fresh = not force and cached.get("timestamp", 0) and now - cached["timestamp"] < CACHE_TTL
        if fresh:
            return cached["posts"], cached["fetched_at"], cached.get("filtered", 0)
        if cached.get("posts") and key not in _refreshing:
            _refreshing.add(key)
            t = threading.Thread(target=_do_refresh_sync, args=(key, fetcher), daemon=True)
            t.start()
            return cached["posts"], cached["fetched_at"] + " (갱신 중)", cached.get("filtered", 0)
    posts = fetcher()
    now = time.time()
    with _lock:
        _cache[key] = {
            "posts": posts,
            "filtered": 0,
            "timestamp": now,
            "fetched_at": datetime.now().strftime("%H:%M:%S 기준"),
        }
        _refreshing.discard(key)
    return posts, _cache[key]["fetched_at"], 0


async def _fetch_thumb_async(post_url):
    """Playwright로 OG 이미지 또는 첫 번째 본문 이미지 추출."""
    browser = await _ensure_browser()
    page = await browser.new_page()
    await _stealth.apply_stealth_async(page)
    async def handle_route(route):
        if route.request.resource_type in ("font", "stylesheet", "media"):
            await route.abort()
        else:
            await route.continue_()
    await page.route("**/*", handle_route)
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=10000)
        try:
            await page.wait_for_selector(".xe_content img, meta[property='og:image']", timeout=3000)
        except Exception:
            pass
        html = await page.content()
    finally:
        await page.close()

    soup = BeautifulSoup(html, "html.parser")
    og = soup.select_one("meta[property='og:image']")
    if og and og.get("content", "").startswith("http"):
        return og["content"]
    img_el = soup.select_one(".xe_content img, .rd_body img, .document_content img")
    if img_el:
        img_url = (img_el.get("src") or img_el.get("data-src") or "")
        if img_url.startswith("//"):
            img_url = "https:" + img_url
        if img_url.startswith("http"):
            return img_url
    return None


def _fetch_thumb_cffi(post_url):
    """curl_cffi 기반 fmkorea 썸네일 추출 (빠름)."""
    session = _get_cffi_session()
    if session is None:
        return None
    try:
        r = session.get(post_url, headers={"Accept-Language": "ko-KR"}, timeout=10)
        if r.status_code != 200 or "보안시스템" in r.text[:2000]:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        og = soup.select_one("meta[property='og:image']")
        if og and og.get("content", "").startswith("http"):
            return og["content"]
        img_el = soup.select_one(".xe_content img, .rd_body img, .document_content img")
        if img_el:
            src = img_el.get("src") or img_el.get("data-src") or ""
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith("http"):
                return src
    except Exception:
        pass
    return None


def fetch_thumb(post_url):
    if post_url in _thumb_cache:
        return _thumb_cache[post_url]
    # curl_cffi 먼저 시도 (빠름)
    img_url = _fetch_thumb_cffi(post_url)
    if img_url:
        _thumb_cache[post_url] = img_url
        return img_url
    # fallback: Playwright
    try:
        img_url = _run_async(_fetch_thumb_async(post_url))
        _thumb_cache[post_url] = img_url
        return img_url
    except Exception:
        _thumb_cache[post_url] = None
        return None


def _fetch_thumb_simple(post_url):
    """requests 기반 OG 이미지 추출 — Playwright 불필요한 사이트용."""
    if post_url in _thumb_cache:
        return _thumb_cache[post_url]
    try:
        r = req_lib.get(post_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        }, timeout=5)
        r.encoding = r.apparent_encoding
        soup = BeautifulSoup(r.text, "html.parser")
        og = soup.select_one("meta[property='og:image']")
        img = og["content"] if og and og.get("content", "").startswith("http") else None
        _thumb_cache[post_url] = img
        return img
    except Exception:
        _thumb_cache[post_url] = None
        return None


def _fetch_ohmyhumor():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
    r = req_lib.get(OHMYHUMOR_URL, headers=headers, timeout=10)
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")
    results, seen = [], set()
    for row in soup.select("tr.humor_best_list, tbody tr"):
        subj = row.select_one("td.subject a")
        if not subj:
            continue
        title = subj.get_text(strip=True)
        href  = subj.get("href", "")
        if not title or len(title) < 3 or title in seen:
            continue
        seen.add(title)
        if href and not href.startswith("http"):
            href = "http://www.todayhumor.co.kr" + href
        if is_filtered(title):
            continue
        rec_el = row.select_one("td.oknok")
        rec = rec_el.get_text(strip=True) if rec_el else ""
        results.append({"title": title, "url": href, "date": "", "recommend": rec, "source": "오유"})
        if len(results) >= 40:
            break
    return results


async def _fetch_ohmyhumor_classified():
    """오유 크롤링 + AI 카테고리 분류."""
    loop = asyncio.get_event_loop()
    posts = await loop.run_in_executor(None, _fetch_ohmyhumor)
    tagged, _ = await _ai_filter_posts(posts)
    return tagged, 0


_NOTICE_PAT = re.compile(r'^\[공지\]|^공지|^📢|^◤|체험단|이벤트 참여|이벤트$')
_CRAWL_UA   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _fetch_ruliweb():
    """루리웹 베스트 게시판 크롤링 (requests 기반)."""
    boards = [
        ("https://bbs.ruliweb.com/best/board/300148", "루리웹"),  # 유머
    ]
    headers = {"User-Agent": _CRAWL_UA, "Accept-Language": "ko-KR,ko;q=0.9", "Referer": "https://bbs.ruliweb.com/"}
    results, seen = [], set()
    for url, src in boards:
        try:
            r = req_lib.get(url, headers=headers, timeout=8)
            r.encoding = r.apparent_encoding
            soup = BeautifulSoup(r.text, "html.parser")
            for row in soup.select("tr.table_body"):
                divsn = row.select_one("td.divsn")
                if divsn and "공지" in divsn.get_text():
                    continue
                a = row.select_one("td.subject a.deco")
                if not a:
                    continue
                title = a.get_text(strip=True)
                href  = a.get("href", "")
                if not title or len(title) < 3 or title in seen:
                    continue
                seen.add(title)
                if is_filtered(title) or _NOTICE_PAT.search(title):
                    continue
                rec_el = row.select_one("td.recomd")
                time_el = row.select_one("td.time")
                results.append({
                    "title": title,
                    "url":   href if href.startswith("http") else "https://bbs.ruliweb.com" + href,
                    "date":  time_el.get_text(strip=True) if time_el else "",
                    "recommend": rec_el.get_text(strip=True) if rec_el else "",
                    "source": src,
                })
                if len(results) >= 60:
                    break
        except Exception:
            continue
    return results


def _fetch_theqoo():
    """더쿠 hot 크롤링 (requests 기반)."""
    headers = {"User-Agent": _CRAWL_UA, "Accept-Language": "ko-KR,ko;q=0.9", "Referer": "https://theqoo.net/"}
    results, seen = [], set()
    try:
        r = req_lib.get("https://theqoo.net/hot", headers=headers, timeout=8)
        r.encoding = r.apparent_encoding
        soup = BeautifulSoup(r.text, "html.parser")
        for td in soup.select("td.title"):
            a = td.select_one("a")
            if not a:
                continue
            href  = a.get("href", "")
            title = a.get_text(strip=True)
            if href.startswith("/event") or href.startswith("/ad"):
                continue
            if not title or len(title) < 3 or title in seen:
                continue
            if _NOTICE_PAT.search(title):
                continue
            seen.add(title)
            if is_filtered(title):
                continue
            full_href = "https://theqoo.net" + href if href.startswith("/") else href
            tr = td.parent
            rec_el = tr.select_one(".m_no") if tr else None
            results.append({
                "title": title,
                "url":   full_href,
                "date":  "",
                "recommend": rec_el.get_text(strip=True) if rec_el else "",
                "source": "더쿠",
            })
            if len(results) >= 40:
                break
    except Exception:
        pass
    return results


async def _fetch_ruliweb_classified():
    loop = asyncio.get_event_loop()
    posts = await loop.run_in_executor(None, _fetch_ruliweb)
    tagged, _ = await _ai_filter_posts(posts)
    return tagged, 0


async def _fetch_theqoo_classified():
    loop = asyncio.get_event_loop()
    posts = await loop.run_in_executor(None, _fetch_theqoo)
    tagged, _ = await _ai_filter_posts(posts)
    return tagged, 0


def _fetch_instiz():
    """인스티즈 실시간 인기글 크롤링."""
    headers = {"User-Agent": _CRAWL_UA, "Accept-Language": "ko-KR,ko;q=0.9", "Referer": "https://www.instiz.net/"}
    results, seen = [], set()
    try:
        r = req_lib.get("https://www.instiz.net/pt", headers=headers, timeout=8)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a.listsubject"):
            title = a.get_text(strip=True)
            href  = a.get("href", "")
            if not title or len(title) < 3 or title in seen:
                continue
            if _NOTICE_PAT.search(title) or is_filtered(title):
                continue
            seen.add(title)
            full_href = "https://www.instiz.net" + href if href.startswith("/") else href
            tr = a.find_parent("tr")
            rec_el = tr.select_one(".recom") if tr else None
            rec = rec_el.get_text(strip=True) if rec_el else ""
            results.append({
                "title": title, "url": full_href,
                "date": "", "recommend": rec, "source": "인스티즈",
            })
            if len(results) >= 40:
                break
    except Exception:
        pass
    return results


async def _fetch_instiz_classified():
    loop = asyncio.get_event_loop()
    posts = await loop.run_in_executor(None, _fetch_instiz)
    tagged, _ = await _ai_filter_posts(posts)
    return tagged, 0


def _translate_ko(text):
    try:
        r = req_lib.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "ko", "dt": "t", "q": text},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        return r.json()[0][0][0]
    except Exception:
        return text


def _relative_time_iso(dt_str):
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff_min = int((now - dt).total_seconds() / 60)
        if diff_min < 1:   return "방금 전"
        if diff_min < 60:  return f"{diff_min}분 전"
        if diff_min < 1440: return f"{diff_min // 60}시간 전"
        return f"{diff_min // 1440}일 전"
    except Exception:
        return ""


async def _scrape_arca_page(browser, url):
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="ko-KR",
    )
    page = await ctx.new_page()
    await _stealth.apply_stealth_async(page)
    async def handle_route(route):
        if route.request.resource_type in ("image", "font", "media", "stylesheet"):
            await route.abort()
        else:
            await route.continue_()
    await page.route("**/*", handle_route)
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(1500)
    html = await page.content()
    await ctx.close()

    soup = BeautifulSoup(html, "html.parser")
    results, seen = [], set()
    for row in soup.select("a.vrow.column:not(.notice)"):
        title_el = row.select_one("span.title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = row.get("href", "")
        if not title or len(title) < 3:
            continue
        if not href.startswith("http"):
            href = "https://arca.live" + href
        if href in seen:
            continue
        seen.add(href)
        if is_filtered(title):
            continue

        time_el = row.select_one("time[datetime]")
        date_text = _relative_time_iso(time_el["datetime"]) if time_el else ""

        views_el = row.select_one("span.vcol.col-view")
        views = views_el.get_text(strip=True) if views_el else ""

        rate_el = row.select_one("span.vcol.col-rate")
        recommend = rate_el.get_text(strip=True) if rate_el else ""

        results.append({"title": title, "url": href, "date": date_text,
                        "views": views, "recommend": recommend, "source": "아카"})
    return results


async def _scrape_arca(pages=2):
    browser = await _ensure_browser()
    page_urls = [ARCA_URL if pg == 1 else f"{ARCA_URL}?p={pg}" for pg in range(1, pages + 1)]
    pages_data = await asyncio.gather(*[_scrape_arca_page(browser, u) for u in page_urls])
    results, seen = [], set()
    for page_posts in pages_data:
        for post in page_posts:
            if post["url"] not in seen:
                seen.add(post["url"])
                results.append(post)
    return results


async def _scrape_arca_classified(pages=1):
    """아카라이브 크롤링 + AI 카테고리 분류."""
    results = await _scrape_arca(pages)
    tagged, _ = await _ai_filter_posts(results)
    return tagged, 0


def _parse_rec(rec_str) -> int:
    try:
        return int(str(rec_str).replace(",", "").replace("+", "").strip())
    except Exception:
        return 0


# BoredPanda 섹션 — 반전/인물/잡학 강화, 동물 균형 조정
_BP_SECTIONS = [
    ("https://www.boredpanda.com/animals/",      "동물"),
    ("https://www.boredpanda.com/nature/",        "동물"),
    ("https://www.boredpanda.com/funny/",         "반전"),
    ("https://www.boredpanda.com/wtf/",           "반전"),
    ("https://www.boredpanda.com/interesting/",   "잡학"),
    ("https://www.boredpanda.com/history/",       "잡학"),
    ("https://www.boredpanda.com/people/",        "인물"),
    ("https://www.boredpanda.com/science/",       "잡학"),
]

def _fetch_boredpanda_section(url, pre_cat):
    """BP 섹션 크롤링 — 영문 제목 그대로 반환 (번역은 AI에서 일괄처리)."""
    headers = {"User-Agent": _CRAWL_UA, "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = req_lib.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for article in soup.select("article"):
            h2 = article.select_one("h2")
            a  = article.select_one("a[href]")
            if not h2 or not a:
                continue
            title_en = h2.get_text(strip=True)
            href     = a.get("href", "").split("?")[0]
            if not title_en or not href.startswith("https://www.boredpanda.com/"):
                continue
            pts_el = article.select_one(".points-only-digits")
            pts = pts_el.get_text(strip=True) if pts_el else ""
            img_el = article.select_one("img")
            img_src = img_el.get("src", "") if img_el else ""
            results.append({
                "title":     title_en,   # 영문 — 나중에 AI가 번역
                "url":       href,
                "date":      "",
                "recommend": pts,
                "img":       img_src,
                "source":    "BP",
                "category":  pre_cat,
            })
            if len(results) >= 20:
                break
        return results
    except Exception:
        return []


async def _fetch_boredpanda():
    """BoredPanda 여러 섹션 병렬 크롤링."""
    loop = asyncio.get_event_loop()
    batches = await asyncio.gather(*[
        loop.run_in_executor(None, lambda u=u, c=c: _fetch_boredpanda_section(u, c))
        for u, c in _BP_SECTIONS
    ])
    results, seen = [], set()
    for batch in batches:
        for p in batch:
            if p["url"] not in seen:
                seen.add(p["url"])
                results.append(p)
    return results


async def _fetch_boredpanda_classified():
    """BP 크롤링 → AI 번역+채점 단일 호출로 처리."""
    posts = await _fetch_boredpanda()
    if not posts:
        return [], 0

    if not _sf_available or _translate_score_fn is None:
        # AI 없으면 영문 그대로
        return posts, 0

    loop = asyncio.get_event_loop()
    BATCH = 15
    titles_en = [p["title"] for p in posts]
    all_results: list[dict] = []

    for i in range(0, len(titles_en), BATCH):
        chunk = titles_en[i:i + BATCH]
        try:
            res = await loop.run_in_executor(None, lambda c=chunk: _translate_score_fn(c))
        except Exception:
            res = [{"title_ko": t, "category": "기타", "score": 0} for t in chunk]
        all_results.extend(res)

    tagged = []
    for post, result in zip(posts, all_results):
        post_copy = dict(post)
        post_copy["title"]    = result["title_ko"] or post["title"]
        post_copy["category"] = result["category"]
        post_copy["score"]    = result["score"]
        tagged.append(post_copy)

    return tagged, 0


_MANIFEST = {
    "name": "인생은 개딸깍",
    "short_name": "개딸깍",
    "description": "펨코·오유·아카라이브 유머 큐레이션",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0f0f0f",
    "theme_color": "#0f0f0f",
    "orientation": "portrait-primary",
    "categories": ["entertainment", "news"],
    "lang": "ko",
}


@app.route("/manifest.json")
def serve_manifest():
    from flask import Response
    return Response(json.dumps(_MANIFEST, ensure_ascii=False), mimetype="application/manifest+json")


@app.route("/sw.js")
def serve_sw():
    return app.send_static_file("sw.js")


@app.route("/api/health")
def api_health():
    with _lock:
        cache_info = {
            k: {"count": len(v.get("posts", [])), "age_sec": int(time.time() - v.get("timestamp", 0))}
            for k, v in _cache.items()
        }
    return jsonify({"status": "ok", "cache": cache_info, "ts": datetime.now().isoformat()})


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/humor")
def api_humor():
    try:
        force = request.args.get("refresh") == "1"
        posts, fetched_at, filtered = get_cached("humor", force=force, async_fn=lambda: _scrape(HUMOR_URL, pages=2))
        return jsonify({"posts": posts, "count": len(posts), "filtered": filtered, "fetched_at": fetched_at})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/feed")
def api_feed():
    """소재 피드 — BoredPanda(동물/잡학/인물/반전) + 국내 커뮤니티."""
    try:
        force = request.args.get("refresh") == "1"
        fm_posts,   fetched_at, fm_filtered  = get_cached("humor",   force=force, async_fn=lambda: _scrape(HUMOR_URL, pages=2))
        ruli_posts, _, ruli_filtered         = get_cached("ruli",    force=force, async_fn=_fetch_ruliweb_classified)
        bp_posts,   _, bp_filtered           = get_cached("bp",      force=force, async_fn=_fetch_boredpanda_classified)
        import math
        theqoo_posts,  _, theqoo_filtered  = get_cached("theqoo",  force=force, async_fn=_fetch_theqoo_classified)
        instiz_posts,  _, instiz_filtered  = get_cached("instiz",  force=force, async_fn=_fetch_instiz_classified)
        combined = fm_posts + ruli_posts + bp_posts + theqoo_posts + instiz_posts
        # 채널 DNA 점수 6 미만 제외 (점수 없으면 통과)
        combined = [p for p in combined if p.get("score", 6) >= 6]
        # 낮은 반응 제외 (수치 없으면 통과)
        combined = [p for p in combined if _parse_rec(p.get("recommend", 0)) >= 5 or not p.get("recommend")]
        # URL 중복 제거
        seen_urls, deduped = set(), []
        for p in combined:
            if p["url"] not in seen_urls:
                seen_urls.add(p["url"])
                deduped.append(p)
        # 점수(×2) + log(반응수) 기반 정렬
        deduped.sort(
            key=lambda p: p.get("score", 5) * 2 + math.log10(_parse_rec(p.get("recommend", 0)) + 10),
            reverse=True,
        )
        total_filtered = fm_filtered + ruli_filtered + bp_filtered + theqoo_filtered + instiz_filtered
        return jsonify({"posts": deduped, "count": len(deduped), "filtered": total_filtered, "fetched_at": fetched_at})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/udt")
def api_udt():
    try:
        force = request.args.get("refresh") == "1"
        posts, fetched_at, filtered = get_cached_sync("udt", _fetch_ohmyhumor, force)
        return jsonify({"posts": posts, "count": len(posts), "filtered": filtered, "fetched_at": fetched_at})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dc")
def api_dc():
    try:
        force = request.args.get("refresh") == "1"
        posts, fetched_at, filtered = get_cached("dc", force=force, async_fn=_scrape_arca)
        return jsonify({"posts": posts, "count": len(posts), "filtered": filtered, "fetched_at": fetched_at})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reddit")
def api_reddit():
    try:
        force = request.args.get("refresh") == "1"
        posts, fetched_at, filtered = get_cached_sync("reddit", _fetch_reddit, force)
        return jsonify({"posts": posts, "count": len(posts), "filtered": filtered, "fetched_at": fetched_at})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/api/patch")
def api_patch():
    try:
        force = request.args.get("refresh") == "1"
        posts, fetched_at, filtered = get_cached("patch", PATCH_URL, force, extra_filter=is_korean_only)
        return jsonify({"posts": posts, "count": len(posts), "filtered": filtered, "fetched_at": fetched_at})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "검색어를 입력해주세요."}), 400
    try:
        url = f"https://www.fmkorea.com/search.php?query={quote(query)}&st=title&sn=off&ss=on&so=r"
        result = _run_async(_scrape(url))
        posts, filtered = result if isinstance(result, tuple) else (result, 0)
        return jsonify({"posts": posts, "count": len(posts), "filtered": filtered, "query": query})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/patches")
def api_patches():
    path = os.path.join(os.path.dirname(__file__), "patches.json")
    with open(path, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/filter_meta")
def api_filter_meta():
    """필터 카테고리 메타데이터 + 현재 적용 중인 키워드 수 반환"""
    result = []
    for cat, meta in FILTER_CATEGORY_META.items():
        kws = FILTER_KEYWORDS.get(cat, [])
        result.append({
            "id":      cat,
            "label":   meta["label"],
            "emoji":   meta["emoji"],
            "desc":    meta["desc"],
            "count":   len(kws),
            "keywords": kws,
        })
    result.append({
        "id":      "pattern",
        "label":   "패턴 탐지",
        "emoji":   "🔍",
        "desc":    "뉴스 헤드라인 구조 자동 탐지 (regex)",
        "count":   len(_FILTER_PATTERNS),
        "keywords": [],
    })
    return jsonify(result)


_SUGGEST_PATH = os.path.join(os.path.dirname(__file__), "suggestions.json")
_suggest_lock = threading.Lock()


def _load_suggestions():
    if not os.path.exists(_SUGGEST_PATH):
        return []
    with open(_SUGGEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_suggestions(data):
    with open(_SUGGEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/api/suggestions", methods=["GET"])
def api_suggestions_get():
    with _suggest_lock:
        return jsonify(_load_suggestions())


@app.route("/api/suggestions", methods=["POST"])
def api_suggestions_post():
    body = request.json or {}
    name    = (body.get("name", "") or "").strip()
    content = (body.get("content", "") or "").strip()
    if not name or not content:
        return jsonify({"error": "이름과 내용을 모두 입력해주세요."}), 400
    entry = {
        "id": int(time.time() * 1000),
        "name": name,
        "content": content,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    with _suggest_lock:
        data = _load_suggestions()
        data.insert(0, entry)
        _save_suggestions(data)
    return jsonify(entry), 201


@app.route("/api/score_available")
def api_score_available():
    return jsonify({"available": _sf_available})


@app.route("/api/score")
def api_score():
    title = request.args.get("title", "").strip()
    url   = request.args.get("url",   "").strip()
    use_search = request.args.get("search", "0") == "1"
    if not _sf_available:
        return jsonify({"error": "GROQ_API_KEY 미설정 — AI 채점 불가"}), 503
    if not title:
        return jsonify({"error": "title 필요"}), 400
    cache_key = f"{title}|{use_search}"
    with _score_lock:
        if cache_key in _score_cache:
            return jsonify(_score_cache[cache_key])
    try:
        result = _score_fn(title=title, content="", url=url or None, use_search=use_search)
        with _score_lock:
            _score_cache[cache_key] = result
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/thumb")
def api_thumb():
    url = request.args.get("url", "")
    if not url or not url.startswith("http"):
        return jsonify({"img": None})
    if "fmkorea.com" in url:
        return jsonify({"img": fetch_thumb(url)})
    return jsonify({"img": _fetch_thumb_simple(url)})


_img_cache: dict[str, bytes] = {}

@app.route("/api/img")
def api_img():
    """이미지 프록시 — 원본 URL을 받아 480px JPEG 65%로 압축해 반환."""
    from flask import Response
    url = request.args.get("url", "")
    if not url or not url.startswith("http"):
        return "", 404
    if url in _img_cache:
        return Response(_img_cache[url], mimetype="image/jpeg")
    try:
        from PIL import Image
        import io as _io
        r = req_lib.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": url,
        }, timeout=8)
        r.raise_for_status()
        img = Image.open(_io.BytesIO(r.content)).convert("RGB")
        w, h = img.size
        max_w = 480
        if w > max_w:
            img = img.resize((max_w, int(h * max_w / w)), Image.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, "JPEG", quality=65, optimize=True)
        data = buf.getvalue()
        if len(_img_cache) < 300:
            _img_cache[url] = data
        return Response(data, mimetype="image/jpeg")
    except Exception:
        return "", 404


_YT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _fetch_yt_channel(ch):
    handle = ch["handle"]
    url = f"https://www.youtube.com/{handle}"
    try:
        r = req_lib.get(url, headers=_YT_HEADERS, timeout=10)
        text = r.text

        m = re.search(r'"channelMetadataRenderer":\{"title":"([^"]+)"', text)
        name = m.group(1) if m else ch["label"]

        m = re.search(r'"subscriberCountText":\{"simpleText":"([^"]+)"', text)
        subs = m.group(1) if m else ""

        m = re.search(r'"videosCountText":\{"runs":\[\{"text":"(\d[\d,]*)"', text)
        videos = m.group(1) + "개" if m else ""

        m = re.search(r'"avatar":\{"thumbnails":\[\{"url":"(https://yt3[^"]+)"', text)
        avatar = m.group(1) if m else None

        m = re.search(r'"description":"((?:[^"\\]|\\.){0,200})"', text)
        desc = m.group(1).replace("\\n", " ").replace('\\"', '"')[:100] if m else ""

        return {
            "handle": handle, "name": name, "subscribers": subs,
            "videos": videos, "avatar": avatar, "description": desc,
            "url": url,
            "shorts_url": f"https://www.youtube.com/{handle}/shorts" if ch["shorts"] else url,
            "shorts": ch["shorts"],
        }
    except Exception as e:
        return {
            "handle": handle, "name": ch["label"], "subscribers": "", "videos": "",
            "avatar": None, "description": "", "url": url,
            "shorts_url": f"https://www.youtube.com/{handle}/shorts",
            "shorts": ch["shorts"], "error": str(e),
        }


def _fetch_all_yt():
    return [_fetch_yt_channel(ch) for ch in YOUTUBE_CHANNELS]


@app.route("/api/yt_channels")
def api_yt_channels():
    try:
        force = request.args.get("refresh") == "1"
        channels, fetched_at, _ = get_cached_sync("yt_channels", _fetch_all_yt, force)
        return jsonify({"channels": channels, "fetched_at": fetched_at})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _prewarm():
    time.sleep(1)
    tasks = [
        ("humor",  lambda: _run_async(_scrape(HUMOR_URL, pages=2))),
        ("ruli",   lambda: _run_async(_fetch_ruliweb_classified())),
        ("bp",     lambda: _run_async(_fetch_boredpanda_classified())),
        ("theqoo", lambda: _run_async(_fetch_theqoo_classified())),
        ("instiz", lambda: _run_async(_fetch_instiz_classified())),
    ]
    for key, fn in tasks:
        try:
            result = fn()
            posts, filtered = result if isinstance(result, tuple) else (result, 0)
            with _lock:
                _cache[key] = {
                    "posts": posts,
                    "filtered": filtered,
                    "timestamp": time.time(),
                    "fetched_at": datetime.now().strftime("%H:%M:%S 기준"),
                }
        except Exception:
            pass

if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    threading.Thread(target=_prewarm, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, use_reloader=True, reloader_type="stat")
