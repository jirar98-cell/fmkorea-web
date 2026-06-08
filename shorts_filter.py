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

CATEGORIES = ["유머", "감동", "드라마", "영화", "스포츠", "정치", "아이돌"]

SYSTEM_PROMPT = f"""너는 한국 커뮤니티 게시물 분류 AI다.
게시물 제목을 보고 가장 적합한 카테고리 하나를 선택해라.

카테고리 정의:
- 유머: 웃긴 상황, 짤, 움짤, 어이없는 일, 동물 유머
- 감동: 훈훈한 이야기, 감동 사연, 선행, 힐링
- 드라마: 드라마틱한 반전, 충격 실화, 갈등·분쟁 스토리
- 영화: 영화·드라마·애니·웹툰·게임 콘텐츠
- 스포츠: 스포츠 경기·선수·하이라이트·기록
- 정치: 정치·사회이슈·시사·뉴스
- 아이돌: 아이돌·연예인·K-POP·팬덤

반드시 아래 JSON만 출력. 다른 말, 마크다운 절대 금지.
{{"category": "유머|감동|드라마|영화|스포츠|정치|아이돌"}}"""


def score_material(title: str, content: str = "", url: str | None = None,
                   use_search: bool = False) -> dict:
    """제목을 읽고 카테고리 분류 반환."""
    resp = client.chat.completions.create(
        model=MODEL_FAST,
        max_tokens=64,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"제목: {title}"},
        ],
    )

    raw = (resp.choices[0].message.content or "").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"category": "유머"}

    if data.get("category") not in CATEGORIES:
        data["category"] = "유머"
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
