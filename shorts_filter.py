"""
shorts_filter.py — @puppyd5g 채널 DNA 기반 소재 적합도 채점
Groq llama-3.1-8b-instant (무료 API)

핵심 인사이트 (135개 영상 전수 분석):
- 1위 경마반전(8M): 동물 아님, 반전 구조
- 2위 아들딸차이(5.8M): 동물 아님, 보편 공감+반전
- 동물 콘텐츠도 반전 있어야 터짐 (표범이 먼저 다가옴, 겁없는 동물)
- 카테고리보다 '반전/의외성 요소'가 성패를 결정
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

# @puppyd5g 채널 DNA — 135개 영상 전수 분석, 반전 패턴 중심
_CHANNEL_DNA = """
유튜브 채널 @puppyd5g 쇼츠 소재 채점 기준.

[핵심 원칙 — 카테고리보다 "반전/의외성 구조"가 중요]
1위: 특이점이 와버린 경마경주 (8M) — 스포츠이지만 예상 밖 결말
2위: 아빠가 보는 아들과 딸의 차이란 (5.8M) — 보편 공감 + 반전 통찰
3위: 동물들에게 기세는 곧 본능이다 (3.2M) — 동물이지만 '기세' 반전 포인트
4위: 노래는 유명한데 어디사람이여유? (3M) — 잡학 + 모르던 사실
5위: 너무 잘생겨서 문제였던 교수님 (2.7M) — 인물 + 반전 (잘생긴 게 문제)
6위: 평화로운 표범 부부의 일상 (2.4M) — 동물 + "표범인데 평화로움" 반전
7위: 야생동물 만지지 말랬는데 먼저 다가옴 (1.9M) — 동물 + "먼저 다가옴" 반전

[10점짜리 공식]
- "이랬는데 알고보니~" / "의외로~" / "했는데 먼저~" 구조 → 최고점
- 누구나 아는 것의 숨겨진 이야기 → 높은 점수
- 평범한 사람/동물/상황의 예상 밖 행동 → 높은 점수
- 보편적으로 공감되는 인간 관계·감정 → 높은 점수

[점수 기준]
9~10점: 반전 구조 명확 + 누구나 궁금해할 소재
7~8점: 반전 or 의외성 있음, 보편 공감 가능
5~6점: 반전 없어도 신기하거나 흥미로운 것
3~4점: 흥미는 있지만 채널 공식과 약간 다름
0~2점: 뉴스/정치/게임/K팝/스포츠결과/전문학술

[카테고리별 가중치 (반전 요소 있을 때 +2점)]
- 동물: 반전 있으면 8~10점, 단순 동물 영상은 5~6점
- 반전/특이점: 기본 8점 이상
- 인물: 반전+공감 있으면 8~10점
- 잡학: 몰랐던 사실이면 7~9점
- 유머: 반전 있으면 7점, 단순 개그는 4~5점

[무조건 낮은 점수 (0~3점)]
- 정치·선거·탄핵·사회갈등
- K팝·아이돌·연예인 가십
- 게임·e스포츠 경기 결과
- 스포츠 경기 스코어·순위
- 전문 기술·학술 내용
- 커뮤니티 내부 밈·용어
"""

_BATCH_PROMPT = f"""{_CHANNEL_DNA}
번호:제목 목록의 각 게시물을 채점하라.
출력: [{{"i":0,"c":"반전","s":9}},{{"i":1,"c":"기타","s":2}},...]
- c: 동물/반전/인물/잡학/유머/감동/기타 중 하나
- s: 0~10 정수
JSON 배열만. 설명 금지."""

_BP_COMBO_PROMPT = f"""{_CHANNEL_DNA}
영문 제목을 한국어로 번역하고 채점하라.
번역 스타일: @puppyd5g 채널 느낌 — 짧고 호기심 유발, 직역 금지.
예) "Dog Refuses To Leave Owner's Side During Surgery" → "수술 내내 곁을 지킨 개"

번호:영문제목 형식 →
출력: [{{"i":0,"t":"한국어 제목","c":"동물","s":8}},...]
- t: 자연스러운 한국어 (채널 스타일)
- c: 동물/반전/인물/잡학/유머/감동/기타 중 하나
- s: 0~10 정수
JSON 배열만. 마크다운 금지."""


def score_batch(titles: list[str]) -> list[dict]:
    """국내 소스 제목 채점. [{"category": str, "score": int}] 반환."""
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


def translate_and_score_batch(titles_en: list[str]) -> list[dict]:
    """BP용: 영문 제목 번역 + 채점 단일 호출. [{"title_ko", "category", "score"}] 반환."""
    if not titles_en:
        return []
    numbered = "\n".join(f"{i}:{t}" for i, t in enumerate(titles_en))
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            max_tokens=min(len(titles_en) * 40 + 100, 2048),
            messages=[
                {"role": "system", "content": _BP_COMBO_PROMPT},
                {"role": "user",   "content": numbered},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        result = [{"title_ko": t, "category": "기타", "score": 0} for t in titles_en]
        for item in data:
            idx = item.get("i", -1)
            title_ko = item.get("t", "")
            cat = item.get("c", "기타")
            score = item.get("s", 0)
            if isinstance(idx, int) and 0 <= idx < len(titles_en):
                if cat not in CATEGORIES:
                    cat = "기타"
                result[idx] = {
                    "title_ko": title_ko or titles_en[idx],
                    "category": cat,
                    "score": max(0, min(10, int(score))),
                }
        return result
    except Exception:
        return [{"title_ko": t, "category": "기타", "score": 0} for t in titles_en]


def score_material(title: str, **kwargs) -> dict:
    results = score_batch([title])
    return results[0]


if __name__ == "__main__":
    print("=== 국내 소스 채점 ===")
    ko_titles = [
        "특이점이 와버린 경마경주",
        "민주당 의원 설전",
        "표범이 먼저 다가옴",
        "롤 패치노트 분석",
        "잘생겨서 문제였던 교수",
    ]
    for t, r in zip(ko_titles, score_batch(ko_titles)):
        print(f"{r['score']:2d}점 [{r['category']}] {t}")

    print("\n=== BP 번역+채점 ===")
    en_titles = [
        "Dog Refuses To Leave Owner During Surgery",
        "Horse Makes Unexpected Move At Finish Line",
        "This Professor Was Too Handsome To Work",
    ]
    for r in translate_and_score_batch(en_titles):
        print(f"{r['score']:2d}점 [{r['category']}] {r['title_ko']}")
