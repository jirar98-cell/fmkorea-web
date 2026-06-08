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

SYSTEM_PROMPT = """너는 유튜브 쇼츠/릴스 소재를 선별하는 AI 큐레이터다.
펨코 게시물 제목을 보고 유튜브에서 클릭·공유될 만한 소재인지 판단해라.

[pass — 유튜브 소재로 좋은 것]
유머류: 웃긴 상황, 예상치 못한 반전, 충격적인 장면, 귀여운 동물/사람, 어이없는 상황
정보류: 놀라운 사실, 신기한 통계, 흥미로운 발견, "실화냐?" 반응 나올 내용
비주얼: 이미지·영상·짤이 있을 것 같고 눈길 끌 만한 것

[drop — 소재로 안 되는 것]
- 정치, 시위, 탄핵, 계엄, 뉴스, 사회이슈
- "오늘 ~했다", "친구가 ~함" 식 평범한 개인 에피소드
- 질문글, 일반 잡담, 공지, 평범한 일상 이야기
- 텍스트만 있는 커뮤니티 논쟁

판정 기준: 유튜브 알고리즘에서 클릭/공유될 것 같으면 pass. 아니면 drop.

반드시 아래 JSON만 출력. 다른 말, 마크다운 절대 금지.
{"verdict": "pass" or "drop", "type": "humor" or "info", "reason": "<한 줄>"}

type 규칙 (verdict가 pass일 때만 의미 있음):
- humor: 웃긴 상황·반응·귀여운 것
- info: 놀라운 사실·정보·신기한 내용"""


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
