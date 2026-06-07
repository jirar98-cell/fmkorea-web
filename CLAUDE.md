# fmkorea_web — 인생은 개딸깍

## 프로젝트 개요

펨코(에펨코리아) 유머 게시판 큐레이션 웹앱.
정치·성적·위해 게시물을 자동 필터링하고, 썸네일과 함께 깔끔하게 보여준다.
사용자가 직접 제외 키워드를 추가해 커스터마이징도 가능하다.

## 폴더 위치

```
C:\Users\alsdn\OneDrive\바탕 화면\fmkorea_web\
├── app.py                  # Flask 백엔드 (메인 서버)
├── requirements.txt        # Python 의존성
├── patches.json            # 패치노트 데이터
├── suggestions.json        # 사용자 제안 데이터
├── templates/
│   └── index.html          # 프론트엔드 (단일 페이지)
└── .claude/
    └── settings.local.json
```

## 기술 스택

- **백엔드:** Python · Flask · Playwright · BeautifulSoup4
- **프론트엔드:** HTML5 · CSS3 · Vanilla JavaScript
- **데이터 저장:** JSON 파일 (patches.json, suggestions.json) · 브라우저 LocalStorage
- **외부 접속:** cloudflared Tunnel (선택)

## 실행 방법

### 초기 설정 (최초 1회)

```powershell
cd "C:\Users\alsdn\OneDrive\바탕 화면\fmkorea_web"
pip install -r requirements.txt
playwright install chromium
```

### 서버 실행

```powershell
cd "C:\Users\alsdn\OneDrive\바탕 화면\fmkorea_web"
python app.py
```

브라우저에서 `http://localhost:5000` 접속.

### 외부 공개 (cloudflared Tunnel)

```powershell
cloudflared tunnel --url http://localhost:5000
```

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | 메인 페이지 |
| GET | `/api/humor` | 펨코 유머 게시판 크롤링 (최신 40개) |
| GET | `/api/patch` | 펨코 패치노트 검색 (한글 제목만) |
| GET | `/api/search?q=...` | 키워드 검색 |
| GET | `/api/patches` | patches.json 반환 |
| GET | `/api/suggestions` | 사용자 제안 목록 조회 |
| POST | `/api/suggestions` | 새 제안 등록 |
| GET | `/api/thumb?url=...` | 게시물 썸네일 이미지 추출 |

## 구현된 기능

### v0.5 (2026-04-28) — 현재
- **탭 구조 개편:** 유머(펨코) / 패치노트 / 제외 키워드 / 기능제안 4탭
- **속도 2배 향상:** Playwright에서 이미지·폰트·스타일시트 로딩 차단
- **제외 키워드:** 사용자 정의 키워드 실시간 추가/삭제 (LocalStorage 저장)
- **캐싱 시스템:** TTL 300초, threading.Lock으로 스레드 안전 보장

### v0.4 — 썸네일
- 게시물 첫 번째 이미지 자동 추출 및 표시
- 5개씩 배치 로딩 (UX 개선)

### v0.3 — 카테고리·검색 개선
- 카테고리 탭 구조 도입
- 검색 기능 강화

### v0.2 — 검색·UI
- 키워드 검색 기능 추가
- UI 전면 개편

### v0.1 — 최초 출시
- 펨코 유머 게시판 크롤링
- 정치·성적·위해 키워드 자동 필터링
- 한글 전용 필터 (영문 포함 게시물 제외)

## 핵심 로직 (app.py)

### 콘텐츠 필터링

`is_filtered()` — 차단 키워드 3개 카테고리로 자동 필터링:
- 정치 관련 키워드
- 성적 키워드
- 위해/혐오 키워드

`is_korean_only()` — 영문이 포함된 제목 제외 옵션.

### 스크래핑

Playwright로 동적 페이지 접근 → BeautifulSoup으로 HTML 파싱.
User-Agent 스푸핑으로 차단 우회.
비동기(asyncio) 코루틴을 threading으로 래핑해 Flask와 통합.

### 데이터 소스

- 유머 게시판: `https://www.fmkorea.com/best`
- 패치노트 검색: `https://www.fmkorea.com/search.php?query=패치노트`

## 주의사항

- `suggestions.json`과 `patches.json`은 직접 편집 가능하지만, 서버 재시작 없이 반영됨.
- 캐시 TTL이 5분이라 크롤링 결과는 최대 5분 지연될 수 있음.
- Playwright가 설치되지 않으면 크롤링 API 전체가 500 에러 반환.
