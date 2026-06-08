"""
shorts_filter.py  —  Groq 무료 API 기반 커뮤니티 게시물 카테고리 분류.
환경변수: GROQ_API_KEY
"""

import json
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
)

MODEL_FAST = "llama-3.1-8b-instant"

CATEGORIES = ["유머", "감동", "드라마", "영화", "스포츠", "정치", "아이돌"]

_BATCH_PROMPT = """너는 한국 커뮤니티 게시물 분류 AI다.
번호:제목 형식의 목록을 보고 각 게시물의 카테고리를 골라라.

카테고리 정의:
- 유머: 웃긴 상황·짤·움짤·어이없는 일·동물 유머·개그
- 감동: 훈훈한 이야기·감동 사연·선행·힐링·칭찬받은 일
- 드라마: 반전·충격 실화·갈등·분쟁·사건사고·이슈 스토리
- 영화: 영화·드라마·애니·웹툰·게임 콘텐츠 소개·리뷰
- 스포츠: 스포츠 경기·선수·하이라이트·기록 (축구·야구·농구·e스포츠 포함)
- 정치: 정치·사회이슈·시사·뉴스·정당·선거·집회
- 아이돌: 아이돌·연예인·K-POP·팬덤·배우·예능

반드시 JSON 배열만 출력. 마크다운·설명 금지.
[{"i":0,"c":"유머"},{"i":1,"c":"감동"},...]"""


def score_batch(titles: list[str]) -> list[str]:
    """여러 제목을 한 번의 API 호출로 분류. 반환: 카테고리 문자열 리스트."""
    if not titles:
        return []
    numbered = "\n".join(f"{i}:{t}" for i, t in enumerate(titles))
    try:
        resp = client.chat.completions.create(
            model=MODEL_FAST,
            max_tokens=min(len(titles) * 15 + 50, 1024),
            messages=[
                {"role": "system", "content": _BATCH_PROMPT},
                {"role": "user",   "content": numbered},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        result = ["유머"] * len(titles)
        for item in data:
            idx = item.get("i", -1)
            cat = item.get("c", "유머")
            if isinstance(idx, int) and 0 <= idx < len(titles) and cat in CATEGORIES:
                result[idx] = cat
        return result
    except Exception:
        return ["유머"] * len(titles)


def score_material(title: str, content: str = "", url: str | None = None,
                   use_search: bool = False) -> dict:
    """단일 제목 분류 (하위 호환용)."""
    cats = score_batch([title])
    return {"category": cats[0]}


if __name__ == "__main__":
    titles = [
        "엘리베이터에 갇힌 택배기사가 한 행동",
        "손흥민 오늘 해트트릭 달성",
        "이재명 대표 오늘 기자회견",
    ]
    print(score_batch(titles))
