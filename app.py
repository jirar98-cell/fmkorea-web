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
}

_FILTER_PATTERNS = []

SKIP_TITLES = ["전체 삭제", "공지", "규정", "금지", "차단", "신고", "불만글"]
CACHE_TTL = 300

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
_score_cache: dict = {}
_score_lock = threading.Lock()

try:
    if os.environ.get("GROQ_API_KEY"):
        from shorts_filter import score_material as _score_fn  # type: ignore
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


async def _scrape_page(browser, url, extra_filter=None):
    page = await browser.new_page()
    await _stealth.apply_stealth_async(page)
    async def handle_route(route):
        if route.request.resource_type in ("image", "font", "media", "stylesheet"):
            await route.abort()
        else:
            await route.continue_()
    await page.route("**/*", handle_route)
    await page.goto(url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector("table.bd_lst tr", timeout=5000)
    except Exception:
        pass
    html = await page.content()
    await page.close()

    soup = BeautifulSoup(html, "html.parser")
    results, seen = [], set()
    filtered_count = 0
    for row in soup.select("table.bd_lst tr"):
        title_el = row.select_one("td.title a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
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


async def _ai_filter_posts(posts):
    """AI로 게시물 카테고리 분류. 전부 통과, category 필드 추가."""
    if not _sf_available or not posts:
        return posts, 0

    loop = asyncio.get_event_loop()
    sem = asyncio.Semaphore(10)

    async def _score_one(post):
        async with sem:
            try:
                result = await loop.run_in_executor(
                    None, lambda: _score_fn(title=post["title"])
                )
                return result
            except Exception:
                return {"category": "유머"}

    scores = await asyncio.gather(*[_score_one(p) for p in posts])
    tagged = []
    for post, score in zip(posts, scores):
        post_copy = dict(post)
        post_copy["category"] = score.get("category", "유머")
        tagged.append(post_copy)
    return tagged, 0


async def _scrape(url, extra_filter=None, pages=1):
    browser = await _ensure_browser()
    page_urls = [url if pg == 1 else f"{url}?page={pg}" for pg in range(1, pages + 1)]
    pages_data = await asyncio.gather(*[_scrape_page(browser, u, extra_filter) for u in page_urls])
    results, seen = [], set()
    total_filtered = 0
    for page_result in pages_data:
        page_posts, fc = page_result
        total_filtered += fc
        for post in page_posts:
            if post["url"] not in seen:
                seen.add(post["url"])
                results.append(post)

    # 0개면 봇 감지 가능성 — 잠시 대기 후 첫 페이지만 재시도
    if not results:
        await asyncio.sleep(3)
        retry_posts, retry_fc = await _scrape_page(browser, page_urls[0], extra_filter)
        total_filtered += retry_fc
        for post in retry_posts:
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


def fetch_thumb(post_url):
    if post_url in _thumb_cache:
        return _thumb_cache[post_url]
    try:
        img_url = _run_async(_fetch_thumb_async(post_url))
        _thumb_cache[post_url] = img_url
        return img_url
    except Exception:
        _thumb_cache[post_url] = None
        return None


def _fetch_ohmyhumor():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
    r = req_lib.get(OHMYHUMOR_URL, headers=headers, timeout=10)
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")
    results, seen = [], set()
    for post in soup.select("td.subject a")[:60]:
        title = post.get_text(strip=True)
        href  = post.get("href", "")
        if not title or len(title) < 3 or title in seen:
            continue
        seen.add(title)
        if href and not href.startswith("http"):
            href = "http://www.todayhumor.co.kr" + href
        if is_filtered(title):
            continue
        results.append({"title": title, "url": href, "date": "", "source": "오유"})
        if len(results) >= 40:
            break
    return results


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
    page_urls = [ARCA_URL if pg == 1 else f"{ARCA_URL}?before=9999999&p={pg}" for pg in range(1, pages + 1)]
    pages_data = await asyncio.gather(*[_scrape_arca_page(browser, u) for u in page_urls])
    results, seen = [], set()
    for page_posts in pages_data:
        for post in page_posts:
            if post["url"] not in seen:
                seen.add(post["url"])
                results.append(post)
    return results


def _fetch_reddit():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; fmkorea-web/1.0)"}
    r = req_lib.get(f"{REDDIT_URL}?limit=50", headers=headers, timeout=10)
    data = r.json()
    posts = []
    for item in data.get("data", {}).get("children", []):
        d = item.get("data", {})
        if d.get("stickied") or not d.get("title"):
            continue
        posts.append({
            "title": _translate_ko(d["title"]),
            "url":   "https://www.reddit.com" + d["permalink"],
            "date":  "",
        })
        if len(posts) >= 40:
            break
    return posts


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
    """여러 커뮤니티 소스 합산 피드."""
    import random as _random
    try:
        force = request.args.get("refresh") == "1"
        fm_posts, fetched_at, fm_filtered = get_cached("humor", force=force, async_fn=lambda: _scrape(HUMOR_URL, pages=2))
        udt_posts, _, udt_filtered = get_cached_sync("udt", _fetch_ohmyhumor, force)
        combined = fm_posts + udt_posts
        _random.shuffle(combined)
        total_filtered = fm_filtered + udt_filtered
        return jsonify({"posts": combined, "count": len(combined), "filtered": total_filtered, "fetched_at": fetched_at})
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
    if not url or not url.startswith("https://www.fmkorea.com"):
        return jsonify({"img": None})
    return jsonify({"img": fetch_thumb(url)})


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
    try:
        result = _run_async(_scrape(HUMOR_URL, pages=3))
        posts, filtered = result if isinstance(result, tuple) else (result, 0)
        with _lock:
            _cache["humor"] = {
                "posts": posts,
                "filtered": filtered,
                "timestamp": time.time(),
                "fetched_at": datetime.now().strftime("%H:%M:%S 기준"),
            }
    except Exception:
        pass

threading.Thread(target=_prewarm, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
