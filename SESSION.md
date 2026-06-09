# 세션 인수인계 — 퍼피독 소재 피드

> 이 파일을 읽으면 지금 어디까지 왔는지 바로 알 수 있음.
> Claude가 매 세션 끝날 때 여기를 업데이트함.

## 마지막 세션: 2026-06-10

### 완료된 작업
- **curl_cffi 전체 적용** — 루리웹/더쿠/인스티즈 전부 `_html_cffi()` 헬퍼로 전환 (Railway IP 차단 우회)
  - `_html_cffi(url, referer, timeout)` — curl_cffi 1차, requests fallback 구조
- **인스티즈 셀렉터 이중화** — `a.listsubject` 없으면 `table.board_list a[href*='/pt/']` 시도
- **BP 6섹션 × 10개 복원** — animals/funny/interesting/people/life/arts (60개 → AI 5배치)
- **BP 타임아웃 28초→45초** + 프론트 AbortController 30초→55초
- **이미지 프록시 WebP화** — 480px→380px, JPEG 65%→WebP 50% (fallback JPEG 55%), `Cache-Control: public, max-age=86400`
- **_img_cache 구조 변경** — `bytes` → `tuple[bytes, str]` (data, mimetype) 쌍으로 저장
- **prewarm 빈결과 캐시 방지** — posts=[] 이면 캐시 건너뜀 (900초 동안 0개 반환 버그 수정)
- **썸네일 동시 처리 3→6** (index.html MAX=6)
- **카운트다운 타이머 est 28→45** (BP 예상 시간 반영)

### 현재 알려진 이슈
- **fmkorea IP 차단** — 공유기 재시작으로 해결. curl_cffi 코드 이미 있음.
- **인스티즈 실제 HTML 구조 미검증** — Railway에서 curl_cffi로 접근은 되지만 셀렉터가 맞는지는 실 결과로 확인 필요
- **BP 45초 타임아웃** — Railway Groq API 지연에 따라 AI 채점 일부 누락 가능성 (정상 동작 범위)

### 다음 해야 할 것
1. Railway 로그 확인: 루리웹/더쿠/인스티즈가 이제 몇 개씩 나오는지
2. 인스티즈 셀렉터 결과 확인 — 여전히 0개면 실제 HTML 구조 분석 필요
3. 학습소 → AI 피드백 루프: 즐겨찾기 카테고리 기반 scoring prompt 가중치 조정 (미구현)

### 배포 방법
```
cd "C:\Users\alsdn\OneDrive\바탕 화면\fmkorea_web"
./deploy.ps1 "커밋 메시지"    # 로컬+Railway 동시 배포
```

### 주요 파일
- `app.py` — Flask 백엔드, `_html_cffi()` 헬퍼, 소스 크롤러, `/api/feed/source`, `/api/img`
- `shorts_filter.py` — Groq AI 채점 (채널 DNA 포함)
- `templates/index.html` — 프론트엔드 (피드 + 학습소 탭)
- `deploy.ps1` — 배포 스크립트
