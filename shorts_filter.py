"""
shorts_filter.py
크롤링한 자료를 쇼츠 소재로 쓸지 AI가 점수 매겨서 거르는 모듈.

쓰는 법:
    from shorts_filter import score_material, filter_batch

    result = score_material(title="...", content="...", url="...")
    # result -> dict: hook_score / tone_fit / fact_confidence / verdict / one_liner

Groq 무료 API 사용 (https://groq.com → API Keys)
환경변수: GROQ_API_KEY
"""

import json
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
)

# 무료 · 빠름 · 품질 충분. 더 빠르게 하려면 "llama-3.1-8b-instant"
MODEL_FAST = "llama-3.1-8b-instant"

SYSTEM_PROMPT = """너는 한국 유머 커뮤니티 피드의 게시물 필터 AI다.
게시물 제목을 읽고 맥락을 파악해서 판단해라.

[drop — 명확히 걸러야 할 것]
- 현직·전직 정치인 이름이 등장하는 글
- 시위·집회·탄핵·계엄 등 현재 정치 사건을 다루는 글
- 정당·선거·법조·수사 관련 뉴스성 글
- 젠더갈등·이념대립 등 사회갈등 글

[pass — 통과시킬 것]
- 일상 유머, 웃긴 에피소드, 의외의 상황
- 동물, 음식, 여행, 취미, 스포츠, 게임
- 영화·드라마·애니·음악 관련 콘텐츠
- 흥미로운 사실, 신기한 이야기

중요: 애매하거나 확실하지 않으면 무조건 pass.
정치성이 명확할 때만 drop.

예) "KBS도 탱크 보도하네" → 시위 맥락 → drop
예) "올공이 특정집단에게 먹힌다면" → 유머 → pass
예) "어제 올림픽공원 현장 카메라로 담아봤습니다" → 일상 → pass

반드시 아래 JSON만 출력. 다른 말, 마크다운 절대 금지.
{"verdict": "pass" or "drop", "reason": "<한 줄>"}"""


def score_material(title: str, content: str = "", url: str | None = None,
                   use_search: bool = False) -> dict:
    """제목을 읽고 pass/drop 판정 반환."""
    user_text = f"제목: {title}"

    resp = client.chat.completions.create(
        model=MODEL_FAST,
        max_tokens=128,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_text},
        ],
    )

    raw = (resp.choices[0].message.content or "").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"verdict": "pass", "reason": "parse_failed"}

    if data.get("verdict") not in ("pass", "drop"):
        data["verdict"] = "pass"
    return data


def filter_batch(items: list[dict], **kwargs) -> dict:
    """
    items: [{"title": ..., "content": ..., "url": ...}, ...]
    반환: {"pass": [...], "review": [...], "drop": [...]}
    """
    buckets: dict = {"pass": [], "review": [], "drop": []}
    for item in items:
        scored = score_material(
            title=item.get("title", ""),
            content=item.get("content", ""),
            url=item.get("url"),
        )
        scored["_source"] = item
        buckets.setdefault(scored.get("verdict", "review"), []).append(scored)
    return buckets


if __name__ == "__main__":
    sample = {
        "title": "엘리베이터에 갇힌 택배기사가 한 행동",
        "content": "",
        "url": "https://example.com/post/123",
    }
    print(json.dumps(score_material(**sample), ensure_ascii=False, indent=2))
