# 세션 인수인계 — 퍼피독 소재 피드

> 이 파일을 읽으면 지금 어디까지 왔는지 바로 알 수 있음.
> Claude가 매 세션 끝날 때 여기를 업데이트함.

## 마지막 세션: 2026-06-09

### 완료된 작업
- @puppyd5g 채널 135개 영상 전수 분석
- 채널 DNA 핵심 인사이트: "반전/의외성 구조"가 카테고리보다 중요
- shorts_filter.py: 반전 패턴 기반 0~10점 채점 + BP 번역+채점 단일 Groq 호출
- 소스 추가: 인스티즈, 더쿠 (기존: 루리웹, BoredPanda, fmkorea)
- BP 섹션 6→8개, 섹션당 12→20개
- CACHE_TTL 300→900
- UI: 제목 복사 버튼, 사용됨 표시(localStorage), 소스 필터, 최소 점수 슬라이더, 9-10점 골드 테두리

### 현재 알려진 이슈
- fmkorea: IP 차단 중 (공유기 재시작으로 해결)
- 인스티즈: 셀렉터 확인 필요 (처음 추가, 실제 동작 검증 안 됨)
- Railway 빌드 시간: Playwright 때문에 5~8분 소요

### 다음 해야 할 것
- 인스티즈 크롤러 동작 확인
- BP 번역 품질 확인 (translate_and_score_batch 결과)
- 점수 분포 확인 (너무 많이 걸러지거나 너무 적게 걸러지는지)
- fmkorea IP 풀리면 테스트

### 배포 방법
```
cd "C:\Users\alsdn\OneDrive\바탕 화면\fmkorea_web"
./deploy.ps1 "커밋 메시지"    # 로컬+Railway 동시 배포
```

### 주요 파일
- `app.py` — Flask 백엔드, 소스 크롤러, `/api/feed`
- `shorts_filter.py` — Groq AI 채점 (채널 DNA 포함)
- `templates/index.html` — 프론트엔드
- `deploy.ps1` — 배포 스크립트
