# fmkorea_web — 유튜브 쇼츠 소재 피드

## 프로젝트 목적

유튜브 쇼츠 채널 **@puppyd5g** ("퍼피독 — 굳이 궁금하지 않았던 이야기")의 소재 발굴 도구.
채널 공식: **동물 + 반전/의외성 + 잡학/사실 + 인물 스토리** (경마 반전 8M뷰, 아들/딸 차이 5.8M뷰 등).
이미 반응이 검증된(추천수/포인트 수치 있는) 게시물만 보여주는 것이 핵심이다.

## 폴더 구조

```
C:\Users\alsdn\OneDrive\바탕 화면\fmkorea_web\
├── app.py                  # Flask 백엔드
├── shorts_filter.py        # Groq AI 카테고리 분류
├── requirements.txt
├── templates/
│   └── index.html          # 프론트엔드 (단일 페이지 SPA)
└── CLAUDE.md
```

## 실행

```powershell
cd "C:\Users\alsdn\OneDrive\바탕 화면\fmkorea_web"
python app.py
# http://localhost:5000
```

## 배포 규칙 (절대 준수)

**로컬과 Railway(GitHub)는 항상 1:1로 동일해야 한다.**
코드 변경 후 반드시 `git add → git commit → git push origin master`.

## 현재 소스 구조 (2026-06-09 기준)

| 소스 | URL | 설명 |
|------|-----|------|
| fmkorea | `fmkorea.com/humor` | 현재 IP 차단(49.142.76.174) — 공유기 재시작하면 복구 |
| 루리웹 | `bbs.ruliweb.com/best/board/300148` | 유머 베스트만 (연예게시판 제거) |
| BoredPanda (BP) | 6개 섹션 | 동물/잡학/인물/반전 — 사전 카테고리 분류, 포인트 수치 있음 |

오유(todayhumor)는 **제거됨** — 정치 게시물 과다.

## 피드 필터 정책

- **AI 채점 점수 6 미만 → 제외** (점수 없으면 통과)
- 추천수/포인트 5 미만 → 제외 (수치 없으면 통과)
- 정치/군사/뉴스 키워드 차단 (`FILTER_KEYWORDS` in app.py)

## 채점 시스템 (2026-06-09 개편)

`shorts_filter.py` (Groq llama-3.1-8b-instant) — **@puppyd5g 채널 DNA 기반 0~10점 채점**:
- 반환값: `{"category": "동물", "score": 8}`
- **점수 6 미만은 피드에서 제외**
- **정렬: 점수×2 + log(추천수)** 기준 내림차순
- BoredPanda도 AI 채점 적용 (기존에는 섹션별 사전분류만)

채널 DNA 요약 (135개 영상 분석):
- 최고 성과: 동물반전(8M), 인물반전(5.8M), 동물행동(3.2M), 잡학호기심(3M)
- 고점수: 동물 의외 사실, 반전 구조, 평범한 사람 특별 이야기
- 저점수: 정치/뉴스/게임/K팝/스포츠 결과

## 핵심 기술 결정

- **curl_cffi** (`impersonate="chrome124"`) — 1차 스크래핑 (빠름, Cloudflare 우회)
- **Playwright** — curl_cffi 실패 시 fallback
- **Pillow 이미지 프록시** (`/api/img`) — 외부 이미지 480px JPEG 65% 리사이즈
- **Google Translate free API** — BP 영문 제목 한글 번역
- **TTL 캐시 300s** + `threading.Lock`
- **asyncio** background thread (`_loop`) + `run_coroutine_threadsafe`

## 주요 API

| 경로 | 설명 |
|------|------|
| `GET /api/feed` | 메인 피드 (루리웹+BP+fmkorea 통합, 추천수 정렬) |
| `GET /api/feed?refresh=1` | 캐시 무시하고 강제 갱신 |
| `GET /api/img?url=...` | 이미지 프록시 |
| `GET /api/thumb?url=...` | 게시물 썸네일 추출 |

## 현재 알려진 이슈

1. **fmkorea IP 차단** — 공유기 재시작으로 해결 가능. curl_cffi 코드는 준비됨.
2. **BP 번역 품질** — Google Translate 무료 API라 기계번역 느낌. 수용 가능한 수준.
3. **게시물 수 적음** — 현재 약 47개. 소스 다양화 필요.

## 환경 변수

- `GROQ_API_KEY` — AI 분류용. 없으면 전부 "기타" 처리됨.
