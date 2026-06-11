# 세션 인수인계 — 퍼피독 소재 피드

> 새 세션 시작 시 이 파일 먼저 읽을 것.
> "가자시발" = 바로 작업 시작. 인사 없이 현황 브리핑 후 다음 할 일 착수.

## 마지막 세션: 2026-06-11

### 오늘 한 것 (전부)

#### AI 업그레이드 (영역전개)
- **Groq llama-3.1-8b-instant → Anthropic claude-fable-5** 로 전면 교체
  - `shorts_filter.py`: `openai.OpenAI` (Groq) → `anthropic.Anthropic`
  - `app.py`: `api_learn_suggest`, `api_title_gen`도 모두 Anthropic으로 전환
  - env 변수: `GROQ_API_KEY` → `ANTHROPIC_API_KEY`
  - `requirements.txt`에 `anthropic` 추가
- **프롬프트 개선**: 4점 기준 명시 ("어느 정도 흥미 있음 → 4점")

#### 버그 수정
- **개드립 메인 피드 누락 버그 수정** — `dogdrip_posts`가 `combined`에 없었음
  - `api_feed()`에 `dogdrip_posts` 추가
  - `total_filtered`에 `dogdrip_filtered` 추가

#### 필터 완화
- **AI 점수 임계값 5→4** (api_feed, api_feed_source 두 곳 모두)

#### 셀렉터 개선
- **인스티즈**: `.issue-list a[href*='/pt/']`, `.pt_list a[href*='/pt/']`, `a[href*='/pt/']` 순서로 fallback 확장
- **개드립**: `.ed-list a`, `article a.ed-link`, 7자리+ 숫자 경로 fallback 추가

### 현재 알려진 이슈

1. **Railway `ANTHROPIC_API_KEY` 미설정** — **즉시 추가 필요**
   - Railway 대시보드 → 서비스 → Variables → `ANTHROPIC_API_KEY` 추가
   - 없으면 AI 채점 전체 비활성화됨 (피드는 뜨지만 점수 없음)
2. **Fable 5 비용** — $10/$50 per MTok (input/output). 하루 5번 전체 새로고침 기준 약 $4~5/일
   - 빈도 낮추려면 CACHE_TTL 더 늘리거나 haiku로 낮출 수 있음
3. **개드립 셀렉터 미검증** — dogdrip.net 403이라 HTML 구조 미확인. 0개일 가능성 있음
4. **인스티즈 셀렉터** — 기존보다 범위 넓혔지만 Railway 결과 확인 필요
5. **fmkorea IP 차단** — 공유기 재시작으로 해결

### 다음에 해야 할 것 (우선순위)

1. **Railway 환경변수 `ANTHROPIC_API_KEY` 추가** ← 가장 급함
2. Railway 로그 확인 — 개드립/인스티즈 실제로 몇 개 나오는지
3. 자료 수 여전히 부족하면:
   - 소스 추가 (클리앙, 뽐뿌 등)
   - 개드립 Playwright fallback 추가 (현재 curl_cffi만)
4. Fable 5 비용이 너무 나오면 `claude-haiku-4-5` 로 다운그레이드 옵션 있음

### 배포
```
./deploy.ps1 "커밋 메시지"
```

### 주요 파일
- `app.py` — Flask 백엔드, 모든 소스 크롤러
- `shorts_filter.py` — Anthropic claude-fable-5 채점 (8개 복수 태그)
- `templates/index.html` — 프론트엔드 전체
- `deploy.ps1` — 배포 스크립트

### 환경변수 (Railway에 반드시 설정)
- `ANTHROPIC_API_KEY` ← **이번 세션에서 Groq에서 교체됨**
- `GROQ_API_KEY`는 더 이상 불필요
