# 세션 인수인계 — 퍼피독 소재 피드

> 이 파일을 읽으면 지금 어디까지 왔는지 바로 알 수 있음.
> Claude가 매 세션 끝날 때 여기를 업데이트함.

## 마지막 세션: 2026-06-10

### 완료된 작업
- 소스별 프로그레시브 로딩 구현 (`/api/feed/source?src=ruli|theqoo|instiz|bp`)
- 예상 완료 카운트다운 (28초 기준, 남은 시간 역산 표시)
- 진행률 바 (헤더 하단 파란 바)
- ❤️ 즐겨찾기 버튼 (카드 hover 시 나타남)
- 📊 학습소 탭: 즐겨찾기 목록 + 카테고리 성향 분석 + 인사이트 텍스트
- AI 채점 실패 시 score=None → 필터 통과 (핵심 버그 수정)
- BP 하드 타임아웃: 스크래핑 12초 + 전체 28초
- 프론트 30초 AbortController 타임아웃
- 정치/사회 필터 키워드 강화 (사회갈등, 법조수사 카테고리 추가)
- 이미지 16:9 비율 고정

### 현재 알려진 이슈
- **루리웹 0개** — Railway IP에서 루리웹 차단 추정. curl_cffi 적용 고려
- **인스티즈 0개** — 셀렉터 `a.listsubject` 확인 필요
- **BP 타임아웃** — 28초 이내 완료 안 될 경우 빈 배열 반환 (정상 동작)
- fmkorea IP 차단 (공유기 재시작으로 해결, curl_cffi 준비됨)

### 다음 해야 할 것
1. 루리웹 curl_cffi 적용 (현재 plain requests → Railway에서 차단될 수 있음)
2. 인스티즈 셀렉터 확인 (실제 HTML 구조 체크)
3. 학습소 → AI 피드백 루프: 즐겨찾기한 카테고리 기반으로 scoring prompt 조정

### 배포 방법
```
cd "C:\Users\alsdn\OneDrive\바탕 화면\fmkorea_web"
./deploy.ps1 "커밋 메시지"    # 로컬+Railway 동시 배포
```

### 주요 파일
- `app.py` — Flask 백엔드, 소스 크롤러, `/api/feed/source`, `/api/feed`
- `shorts_filter.py` — Groq AI 채점 (채널 DNA 포함)
- `templates/index.html` — 프론트엔드 (피드 + 학습소 탭)
- `deploy.ps1` — 배포 스크립트
