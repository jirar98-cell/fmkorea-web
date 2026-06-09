"""
shorts_filter.py — @puppyd5g 채널 DNA 기반 소재 적합도 채점
Groq llama-3.1-8b-instant (무료 API)

채널 분석: 135개 영상, 최고 8M 뷰
공식: 동물반전(8M) > 인물반전(5.8M) > 동물행동(3.2M) > 잡학호기심(3M)
"""

import json
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
)

MODEL = "llama-3.1-8b-instant"

CATEGORIES = ["동물", "반전", "인물", "잡학", "유머", "감동", "기타"]

_CHANNEL_DNA = """
유튜브 채널 @puppyd5g ("퍼피독 — 굳이 궁금하지 않았던 이야기") 쇼츠 소재 기준.

[실제 고성과 영상 패턴 — 이런 게 잘 됨]
- "특이점이 와버린 경마경주" 8M뷰 → 예상 밖 결말, 반전
- "아빠가 보는 아들과 딸의 차이란" 5.8M뷰 → 보편적 가족 이야기
- "동물들에게 기세는 곧 본능이다" 3.2M뷰 → 동물 행동 관찰
- "노래는 유명한데 어디사람이여유?" 3M뷰 → 잡학 호기심
- "너무 잘생겨서 문제였던 교수님" 2.7M뷰 → 인물 반전
- "평화로운 표범 부부의 일상" 2.4M뷰 → 동물 일상
- "야생동물 만지지 말랬는데 먼저 다가옴" 1.9M뷰 → 동물 반전
- "AI에 똑같은거 100번넘게 시키기" 1.4M뷰 → 실험/호기심
- "지구 역사상 가장 겁없는 동물" 876K뷰 → 동물 사실
- "알파카에 대해 잘 모르는 사실" 448K뷰 → 동물 잡학

[채널 공식]
1. 호기심 갭: 제목만 봐도 "어? 진짜?" 하게 만드는 것
2. 반전/의외성: 예상과 다른 결말, 잘 몰랐던 사실
3. 보편 공감: 나이/성별 상관없이 누구나 흥미로운 것
4. 짧은 만족: 1분 이내에 완결되는 이야기

[높은 점수 (7~10점) 기준]
- 동물의 예상 밖 행동, 잘 모르는 동물 사실
- "했는데 사실은~", "의외로~", "~인 이유" 류의 반전 구조
- 평범한 사람/상황의 의외의 이야기
- 유명한 것의 숨겨진 뒷이야기 (브랜드, 영화, 노래, 역사)
- "이게 실제로?" 싶은 신기한 상황

[낮은 점수 (0~3점) 기준]
- 정치/선거/뉴스/사회이슈/탄핵/갈등
- 게임/e스포츠/롤/오버워치
- K팝/아이돌/연예인 가십/팬덤
- 스포츠 경기 결과/순위/성적
- 전문 학술/기술 내용
- 커뮤니티 내부 용어/밈
- 단순 웃긴 짤 (반전 없는 것)
"""

_BATCH_PROMPT = f"""{_CHANNEL_DNA}
위 기준으로 각 게시물의 쇼츠 소재 적합도를 채점하라.
번호:제목 목록을 보고 아래 JSON 형식으로만 응답.

출력: [{{"i":0,"c":"동물","s":8}},{{"i":1,"c":"기타","s":2}},...]
- c: 카테고리 (동물/반전/인물/잡학/유머/감동/기타 중 하나)
- s: 적합도 점수 0~10 정수
마크다운·설명 절대 금지. JSON 배열만."""


def score_batch(titles: list[str]) -> list[dict]:
    """여러 제목을 한 번의 API 호출로 채점. [{"category": str, "score": int}] 반환."""
    if not titles:
        return []
    numbered = "\n".join(f"{i}:{t}" for i, t in enumerate(titles))
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            max_tokens=min(len(titles) * 25 + 100, 2048),
            messages=[
                {"role": "system", "content": _BATCH_PROMPT},
                {"role": "user",   "content": numbered},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        result = [{"category": "기타", "score": 0}] * len(titles)
        for item in data:
            idx = item.get("i", -1)
            cat = item.get("c", "기타")
            score = item.get("s", 0)
            if isinstance(idx, int) and 0 <= idx < len(titles):
                if cat not in CATEGORIES:
                    cat = "기타"
                result[idx] = {"category": cat, "score": max(0, min(10, int(score)))}
        return result
    except Exception:
        return [{"category": "기타", "score": 0}] * len(titles)


def score_material(title: str, **kwargs) -> dict:
    results = score_batch([title])
    return results[0]


if __name__ == "__main__":
    titles = [
        "표범이 먼저 다가와서 애교부림",
        "경마 결승선에서 생긴 특이점",
        "리바이스 청바지 로고에 숨겨진 뜻",
        "아빠가 보는 아들과 딸의 차이",
        "민주당 의원 발언 논란",
        "롤 패치노트 분석",
    ]
    for t, r in zip(titles, score_batch(titles)):
        print(f"{r['score']:2d}점 [{r['category']}] {t}")
