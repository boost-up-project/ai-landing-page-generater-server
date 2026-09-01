# Campaign Knowledge 출력 명세

## 목적

캠페인 전략 PDF에서 근거가 확인된 정보만 8개 고정 항목으로 추출한다.
HTML 웹 컴포넌트와 이미지 자산은 분석하지 않고 캠페인별 디렉터리에 저장한다.

## 분석 항목

1. Campaign Overview: 캠페인 배경 / 추진 목적 / 캠페인 범위
2. Objective: 캠페인 목표 / 핵심 KPI / 기대 성과
3. Campaign Opportunity: 핵심 문제 / 시장 기회 / 캠페인 기회 요소
4. Audience Insight: 핵심 타깃 / 타깃 니즈 / 행동·인식 인사이트
5. Campaign Idea: 캠페인 아이디어 / 핵심 콘셉트 / 크리에이티브 방향
6. Offering: 제품·서비스 가치 / 고객 혜택 / 차별화 요소
7. Communication Strategy: 핵심 메시지 / 메시지 우선순위 / 커뮤니케이션 방향
8. CTA Map: 핵심 CTA / 행동 유도 흐름 / 전환 설계

각 항목은 `content`와 `source_references`를 가진다. 내용이 있으면 실제 PDF
파일명과 페이지 근거가 필요하며, 내용이 없으면 두 값을 모두 비워 둔다.

## API 흐름

- `POST /api/campaigns`: PDF 분석 및 HTML·이미지 저장
- `GET /api/campaigns/{campaign_id}`: Campaign Knowledge 초안 조회
- `PUT /api/campaigns/{campaign_id}/review`: 수정 결과 검토 완료
- `POST /api/campaigns/{campaign_id}/finalize`: `campaign.md` 생성
- `GET /api/campaigns/{campaign_id}/markdown`: 확정 Markdown 조회

## TODO

- 브랜드, 캠페인, 이후 서비스의 저장 경로 통합은 각 기능 개발 완료 후
  `project_id` 기반 플로우 통합 단계에서 처리한다.
