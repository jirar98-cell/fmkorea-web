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
MODEL_FAST = "llama-3.3-70b-versatile"

# 통과 기준 (네 맘대로 조절)
THRESHOLDS = {
    "hook_min": 6,        # 훅이 이거보다 낮으면 버림
    "tone_min": 5,        # 채널 톤 안 맞으면 버림
    "fact_review": 7,     # 사실관계 점수가 이거보다 낮으면 "사람이 확인" 표시
}

# 네 채널 정체성을 여기 박아넣음. 채널 방향 바뀌면 이 텍스트만 수정.
CHANNEL_BRIEF = """
[채널 정체성]
- 컨셉: '예상 못한 실제 사건' 중심의 에버그린 쇼츠. 트렌드 타이밍보다 언제 봐도 먹히는 소재.
- 핵심 무기: 첫 3초 안에 시각적으로 강한 훅. "어? 뭐야 이거" 하고 멈추게 만드는 장면.
- 톤(민욱 톤 2.0): 친구한테 썰 풀듯 짧고 캐주얼. 첫 컷에 결론 반쯤 던져서 끝까지 보게 함.
  과한 설명 없이 1~2줄 호흡, 가벼운 피식 포인트.
- 피하는 것: 흔한 밈 재탕, 톤 안 맞는 정치/심각한 시사, 출처 불명 낚시성 가짜 사건.
"""

SYSTEM_PROMPT = f"""너는 한 쇼츠 채널의 소재 선별 담당이다.
{CHANNEL_BRIEF}

주어진 자료를 아래 3개 축으로 0~10점 채점해라.

1) hook_score: 쇼츠로 떡상할 '훅' 잠재력. 첫 3초에 멈추게 할 시각적/내용적 임팩트와 의외성.
2) tone_fit: 위 채널 톤·주제에 맞는 정도. 톤 안 맞으면 낮게.
3) fact_confidence: 사실관계 신뢰도. 진짜 일어난 사건일 확률.
   - 확인 가능한 출처/근거가 있으면 높게.
   - 출처 불명·과장·낚시 냄새가 나면 낮게.

반드시 아래 JSON 형식만 출력. 다른 말, 마크다운, 코드펜스 절대 금지.
{{
  "hook_score": <0-10 정수>,
  "hook_reason": "<한 줄>",
  "tone_fit": <0-10 정수>,
  "tone_reason": "<한 줄>",
  "fact_confidence": <0-10 정수>,
  "fact_reason": "<한 줄>",
  "one_liner": "<이 소재 쇼츠 훅으로 쓸 첫 컷 한 줄, 민욱 톤>"
}}"""


def score_material(title: str, content: str, url: str | None = None,
                   use_search: bool = False) -> dict:
    """자료 하나를 채점해서 dict 반환. verdict 는 여기서 계산해 붙인다."""
    user_text = f"제목: {title}"
    if content:
        user_text += f"\n\n본문:\n{content}"
    if url:
        user_text += f"\n\n출처 URL: {url}"

    resp = client.chat.completions.create(
        model=MODEL_FAST,
        max_tokens=1024,
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
        return {"verdict": "review", "error": "parse_failed", "raw": raw}

    data["verdict"] = _decide(data)
    return data


def _decide(d: dict) -> str:
    """점수 보고 pass / review / drop 결정."""
    hook = d.get("hook_score", 0)
    tone = d.get("tone_fit", 0)
    fact = d.get("fact_confidence", 0)

    if hook < THRESHOLDS["hook_min"] or tone < THRESHOLDS["tone_min"]:
        return "drop"
    if fact < THRESHOLDS["fact_review"]:
        return "review"
    return "pass"


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
