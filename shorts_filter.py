"""
shorts_filter.py — @puppyd5g 채널 DNA 기반 소재 적합도 채점
Groq llama-3.1-8b-instant (무료 API)

태그 체계 (8개 복수 태그):
- 반전: "이랬는데 알고보니" 예상을 뒤집는 구조
- 의외: 팩트/통계 기반 "이거 실화야?" 놀라움
- 동물: 동물 이야기 전반
- 감동: 따뜻하고 뭉클한
- 유머: 웃기고 공감됨
- 호기심: "굳이 궁금하지 않았는데..." 채널 슬로건 잡학
- 인물: 평범한 사람의 특별한 이야기
- 공감: 누구나 겪는 상황·보편 감정
"""

import json
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
)

MODEL = "llama-3.1-8b-instant"

TAGS = [
    # 반전/충격
    "반전", "의외", "충격", "레전드",
    # 동물
    "동물", "고양이", "강아지", "야생",
    # 지식/잡학
    "잡학", "역사", "과학", "세계",
    # 감정
    "감동", "훈훈", "공감", "힐링",
    # 유머
    "유머", "황당",
    # 인물/사회
    "인물", "직장", "연애", "육아",
    # 생활
    "음식", "여행",
]
TAGS_SET = set(TAGS)

# @puppyd5g 채널 DNA — 135개 영상 전수 분석
_CHANNEL_DNA = """
유튜브 채널 @puppyd5g 쇼츠 소재 채점 기준.

[채널 히트작]
1위: 특이점이 와버린 경마경주 (8M) → 반전
2위: 아빠가 보는 아들과 딸의 차이란 (5.8M) → 공감+반전
3위: 동물들에게 기세는 곧 본능이다 (3.2M) → 야생+반전
4위: 노래는 유명한데 어디사람이여유? (3M) → 잡학+의외
5위: 너무 잘생겨서 문제였던 교수님 (2.7M) → 인물+반전
6위: 평화로운 표범 부부의 일상 (2.4M) → 야생+훈훈
7위: 야생동물 만지지 말랬는데 먼저 다가옴 (1.9M) → 야생+반전

[태그 정의 — 아래 목록 외 단어 사용 금지]
- 반전: "이랬는데 알고보니~" 예상을 완전히 뒤집는 결말
- 의외: 팩트/통계 기반 놀라움 ("실화야?", 이게 사실?)
- 충격: 믿기 어려운 사건/상황 (부정적 뉘앙스)
- 레전드: 두고두고 회자되는 역대급 상황
- 동물: 동물 전반 (구체적 종류 모를 때)
- 고양이: 고양이 이야기
- 강아지: 강아지 이야기
- 야생: 야생동물·자연·생태계
- 잡학: 굳이 몰랐어도 됐을 흥미로운 지식
- 역사: 역사적 사건·인물
- 과학: 과학·의학·신체·기술
- 세계: 세계 각국 문화·나라 비교·국제
- 감동: 뭉클하고 눈물나는 이야기
- 훈훈: 따뜻하고 미소짓게 되는 이야기
- 공감: 누구나 겪는 보편 감정·일상
- 힐링: 마음이 편안해지는 힐링 콘텐츠
- 유머: 웃기고 재밌는 상황
- 황당: 어이없고 황당한 상황
- 인물: 평범한 사람의 특별한 이야기
- 직장: 직장생활·업무·회사
- 연애: 연애·결혼·부부·가족 관계
- 육아: 아이·부모·육아
- 음식: 음식·요리·먹방
- 여행: 여행·나라·해외문화

[채점 기준]
- 반전 구조 명확 + 누구나 궁금해할 소재 → 9~10점
- 반전 or 의외성 있음, 보편 공감 가능 → 7~8점
- 신기하거나 흥미로운 것 → 5~6점
- 어느 정도 흥미 있지만 채널 색깔과 약간 다름 → 4점
- 채널과 잘 안 맞음 → 2~3점
- 정치/선거/K팝/게임/스포츠결과/학술 → 0~1점
"""

_TAG_LIST = "/".join(TAGS)

_BATCH_PROMPT = f"""{_CHANNEL_DNA}
번호:제목 목록의 각 게시물을 채점하라.
출력: [{{"i":0,"tags":["반전","동물"],"s":9}},{{"i":1,"tags":["유머"],"s":5}},...]
- tags: {_TAG_LIST} 중 1~2개 (핵심 특성 순서로, 위 목록 외 단어 사용 금지)
- s: 0~10 정수
JSON 배열만. 설명 금지."""

_BP_COMBO_PROMPT = f"""{_CHANNEL_DNA}
영문 제목을 한국어로 번역하고 채점하라.
번역 스타일: @puppyd5g 채널 느낌 — 짧고 호기심 유발, 직역 금지.
예) "Dog Refuses To Leave Owner's Side During Surgery" → "수술 내내 곁을 지킨 개"

번호:영문제목 형식 →
출력: [{{"i":0,"t":"한국어 제목","tags":["동물","감동"],"s":8}},...]
- t: 자연스러운 한국어 (채널 스타일)
- tags: {_TAG_LIST} 중 1~2개
- s: 0~10 정수
JSON 배열만. 마크다운 금지."""


def _parse_tags(raw_tags) -> list[str]:
    """AI 반환 tags 파싱 + 유효성 검증."""
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    if not isinstance(raw_tags, list):
        return ["잡학"]
    result = [t for t in raw_tags if isinstance(t, str) and t in TAGS_SET]
    return result[:2] if result else ["잡학"]


def score_batch(titles: list[str]) -> list[dict]:
    """국내 소스 제목 채점. [{"tags": [...], "category": str, "score": int}] 반환."""
    if not titles:
        return []
    numbered = "\n".join(f"{i}:{t}" for i, t in enumerate(titles))
    fallback = [{"tags": ["잡학"], "category": "잡학", "score": None} for _ in titles]
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            max_tokens=min(len(titles) * 30 + 100, 2048),
            messages=[
                {"role": "system", "content": _BATCH_PROMPT},
                {"role": "user",   "content": numbered},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        result = [{"tags": ["잡학"], "category": "잡학", "score": None} for _ in titles]
        for item in data:
            idx = item.get("i", -1)
            if not (isinstance(idx, int) and 0 <= idx < len(titles)):
                continue
            tags = _parse_tags(item.get("tags", []))
            score = max(0, min(10, int(item.get("s", 0))))
            result[idx] = {"tags": tags, "category": tags[0], "score": score}
        return result
    except Exception:
        return fallback


def translate_and_score_batch(titles_en: list[str]) -> list[dict]:
    """BP용: 영문 제목 번역 + 채점. [{"title_ko", "tags", "category", "score"}] 반환."""
    if not titles_en:
        return []
    numbered = "\n".join(f"{i}:{t}" for i, t in enumerate(titles_en))
    # score None → 피드 필터 통과 (rate limit 시 영문 제목이라도 살림)
    fallback = [{"title_ko": t, "tags": ["잡학"], "category": "잡학", "score": None} for t in titles_en]
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            max_tokens=min(len(titles_en) * 45 + 100, 2048),
            messages=[
                {"role": "system", "content": _BP_COMBO_PROMPT},
                {"role": "user",   "content": numbered},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        result = [{"title_ko": t, "tags": ["잡학"], "category": "잡학", "score": None} for t in titles_en]
        for item in data:
            idx = item.get("i", -1)
            if not (isinstance(idx, int) and 0 <= idx < len(titles_en)):
                continue
            tags = _parse_tags(item.get("tags", []))
            score = max(0, min(10, int(item.get("s", 0))))
            title_ko = item.get("t") or titles_en[idx]
            result[idx] = {"title_ko": title_ko, "tags": tags, "category": tags[0], "score": score}
        return result
    except Exception:
        return fallback


def score_material(title: str, **kwargs) -> dict:
    results = score_batch([title])
    return results[0]


if __name__ == "__main__":
    print("=== 국내 소스 채점 (복수 태그) ===")
    ko_titles = [
        "특이점이 와버린 경마경주",
        "민주당 의원 설전",
        "표범이 먼저 다가옴",
        "아빠가 보는 아들과 딸의 차이",
        "잘생겨서 문제였던 교수",
    ]
    for t, r in zip(ko_titles, score_batch(ko_titles)):
        print(f"{r['score']:2d}점 [{'+'.join(r['tags'])}] {t}")

    print("\n=== BP 번역+채점 ===")
    en_titles = [
        "Dog Refuses To Leave Owner During Surgery",
        "Horse Makes Unexpected Move At Finish Line",
        "This Professor Was Too Handsome To Work",
    ]
    for r in translate_and_score_batch(en_titles):
        print(f"{r['score']:2d}점 [{'+'.join(r['tags'])}] {r['title_ko']}")
