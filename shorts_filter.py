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

SYSTEM_PROMPT = """너는 SNS 쇼츠/릴스 소재를 찾는 큐레이터 AI다.
펨코 게시물 제목을 읽고, 이미지·영상 기반의 비주얼 컨텐츠인지 판단해라.

[pass — 소재가 될 것]
- 이미지·사진·영상·짤·움짤이 있을 것 같은 유머 게시물
- 충격적이거나 재밌는 상황 사진 or 영상
- 동물, 음식, 일상, 스포츠 하이라이트, 게임 영상
- 유머러스한 상황이나 반응 컷

[drop — 소재가 안 됨]
- 정치, 시위, 탄핵, 계엄, 뉴스, 사회이슈
- "~한다고 함", "~인듯", "~해봄" 등 텍스트 에피소드만 있을 것 같은 글
- 일반 커뮤니티 잡담, 질문글, 본인 이야기

중요: 애매하면 pass. 명확히 텍스트 에피소드거나 정치글일 때만 drop.

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
