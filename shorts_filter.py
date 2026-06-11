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

TAGS = ["반전", "의외", "동물", "감동", "유머", "호기심", "인물", "공감"]
TAGS_SET = set(TAGS)

# @puppyd5g 채널 DNA — 135개 영상 전수 분석
_CHANNEL_DNA = """
유튜브 채널 @puppyd5g 쇼츠 소재 채점 기준.

[핵심 원칙 — 카테고리보다 "반전/의외성 구조"가 중요]
1위: 특이점이 와버린 경마경주 (8M) — 스포츠이지만 예상 밖 결말 → 반전
2위: 아빠가 보는 아들과 딸의 차이란 (5.8M) — 보편 공감 + 반전 통찰 → 공감+반전
3위: 동물들에게 기세는 곧 본능이다 (3.2M) — 동물 + '기세' 반전 포인트 → 동물+반전
4위: 노래는 유명한데 어디사람이여유? (3M) — 잡학 + 몰랐던 사실 → 호기심+의외
5위: 너무 잘생겨서 문제였던 교수님 (2.7M) — 인물 + 반전 → 인물+반전
6위: 평화로운 표범 부부의 일상 (2.4M) — 동물 + "표범인데 평화로움" → 동물+의외
7위: 야생동물 만지지 말랬는데 먼저 다가옴 (1.9M) — 동물 + 반전 → 동물+반전

[태그 정의]
- 반전: "이랬는데 알고보니~" / 예상 완전히 뒤집는 구조
- 의외: 팩트/통계/사실 기반 놀라움 ("실화야?")
- 동물: 동물 이야기 (반전 있으면 반전도 함께)
- 감동: 따뜻하고 뭉클한 이야기
- 유머: 웃기고 공감되는 상황
- 호기심: 굳이 몰라도 됐을 잡학, 세상의 이면
- 인물: 평범한 사람의 특별한 이야기
- 공감: 누구나 겪는 보편 감정·상황

[10점짜리 공식]
- 반전 구조 명확 + 누구나 궁금해할 소재 → 9~10점
- 반전 or 의외성 있음, 보편 공감 가능 → 7~8점
- 신기하거나 흥미로운 것, 동물/인물/잡학 → 5~6점
- 어느 정도 흥미 있지만 채널 색깔과 약간 다름 → 4점
- 채널과 잘 안 맞음 → 2~3점
- 뉴스/정치/게임/K팝/스포츠결과/전문학술 → 0~1점

[무조건 낮은 점수 (0~1점)]
- 정치·선거·탄핵·사회갈등
- K팝·아이돌·연예인 가십
- 게임·e스포츠 경기 결과
- 스포츠 경기 스코어·순위
- 전문 기술·학술 내용
- 커뮤니티 내부 밈·용어
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
        return ["호기심"]
    result = [t for t in raw_tags if isinstance(t, str) and t in TAGS_SET]
    return result[:2] if result else ["호기심"]


def score_batch(titles: list[str]) -> list[dict]:
    """국내 소스 제목 채점. [{"tags": [...], "category": str, "score": int}] 반환."""
    if not titles:
        return []
    numbered = "\n".join(f"{i}:{t}" for i, t in enumerate(titles))
    fallback = [{"tags": ["호기심"], "category": "호기심", "score": 0}] * len(titles)
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
        result = [{"tags": ["호기심"], "category": "호기심", "score": 0}] * len(titles)
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
    fallback = [{"title_ko": t, "tags": ["호기심"], "category": "호기심", "score": 0} for t in titles_en]
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
        result = [{"title_ko": t, "tags": ["호기심"], "category": "호기심", "score": 0} for t in titles_en]
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
