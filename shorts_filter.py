"""
shorts_filter.py  —  Groq 무료 API 기반 게시물 카테고리 분류.
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

CATEGORIES = ["동물", "반전", "인물", "잡학", "유머", "감동", "기타"]

_BATCH_PROMPT = """너는 유튜브 쇼츠 소재 분류 AI다.
번호:제목 형식의 목록을 보고 각 게시물의 카테고리를 골라라.

카테고리 정의:
- 동물: 동물·펫·야생동물·곤충·수중생물 관련 모든 것
- 반전: 예상 못한 결말·반전·놀라운 순간·의외의 상황
- 인물: 특이한 사람·유명인 뒷이야기·인간 관계·사회 현상
- 잡학: 몰랐던 사실·역사·과학·브랜드 비화·통계·기록
- 유머: 웃긴 상황·개그·유머러스한 내용
- 감동: 훈훈·힐링·감동 사연
- 기타: 위 어디에도 맞지 않는 경우

반드시 JSON 배열만 출력. 마크다운·설명 절대 금지.
[{"i":0,"c":"동물"},{"i":1,"c":"반전"},...]"""


def score_batch(titles: list[str]) -> list[str]:
    """여러 제목을 한 번의 API 호출로 분류."""
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
        result = ["기타"] * len(titles)
        for item in data:
            idx = item.get("i", -1)
            cat = item.get("c", "기타")
            if isinstance(idx, int) and 0 <= idx < len(titles) and cat in CATEGORIES:
                result[idx] = cat
        return result
    except Exception:
        return ["기타"] * len(titles)


def score_material(title: str, **kwargs) -> dict:
    cats = score_batch([title])
    return {"category": cats[0]}


if __name__ == "__main__":
    titles = [
        "표범이 먼저 다가와서 애교부림",
        "경마 결승선에서 생긴 특이점",
        "리바이스 청바지 로고에 숨겨진 뜻",
        "아빠가 보는 아들과 딸의 차이",
    ]
    print(score_batch(titles))
