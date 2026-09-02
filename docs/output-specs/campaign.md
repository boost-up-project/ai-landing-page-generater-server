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

각 항목은 `content`와 `source_references`를 가진다. AI 최초 분석 결과에서 내용이
있으면 실제 PDF 파일명과 페이지 근거가 필요하며, 내용이 없으면 두 값을 모두 비워
둔다. 검토 화면에서 사용자가 직접 추가한 내용은 출처 없이 저장할 수 있다.

## API 흐름

- `POST /api/campaigns`: PDF 분석 및 HTML·이미지 저장
- `GET /api/campaigns/{campaign_id}`: Campaign Knowledge 초안 조회
- `PUT /api/campaigns/{campaign_id}/review`: 수정 결과 검토 완료
- `POST /api/campaigns/{campaign_id}/finalize`: `campaign.md` 생성
- `GET /api/campaigns/{campaign_id}/markdown`: 확정 Markdown 조회

엔드포인트 경로는 유지하되, 캠페인 분석 요청에는 브랜드 분석에서 생성된
`project_id`를 `multipart/form-data` 필드로 함께 전달한다.

## 저장 경로

브랜드 진입점에서 생성된 `project_id`를 기준으로 이후 단계 산출물을 같은
프로젝트 디렉터리에 저장한다.

```text
storage/projects/{project_id}/
  project.json
  brand/
    {brand_id}/
      uploads/
      extracted.txt
      analyzed.json
      reviewed.json
      brand.md
      record.json
  campaign/
    {campaign_id}/
      uploads/
      component/
      assets/
      extracted.txt
      analyzed.json
      reviewed.json
      campaign.md
      record.json
```

`brand_id`와 `campaign_id`는 각 단계 record 식별자로 유지하고, 조회 API는
기존처럼 해당 id를 사용한다. 같은 프로젝트에서 단계를 다시 분석해도 이전 id의
산출물은 덮어쓰지 않으며, `project.json`의 `current_brand_id`와
`current_campaign_id`가 현재 활성 산출물을 가리킨다.

동일 PDF 분석 캐시는 프로젝트 내부에서만 검색하며, 사용자가 수정할 수 있는
`record.json` 대신 최초 AI 결과인 `analyzed.json`을 재사용한다.

## 요청 및 응답

`POST /api/brands/analyze` 응답에는 전체 플로우 식별자인 `project_id`가 포함된다.

`POST /api/campaigns` 요청에는 다음 필드를 포함한다.

- `project_id`: 브랜드 분석 응답에서 받은 프로젝트 id
- `strategy_file`: 캠페인 전략 PDF 1개
- `component_files`: HTML 웹 컴포넌트 파일 목록
- `asset_files`: 이미지 파일 목록

Campaign 응답에는 `project_id`, `campaign_id`, `source_checksum`,
`reused_from_campaign_id`가 포함된다.

`POST /api/campaigns/{campaign_id}/finalize` 응답에는 이후 단계 라우팅을 위해
`next_route`로 `/#persona-input`을 포함한다.

## TODO

- Persona 이후 서비스도 동일한
  `storage/projects/{project_id}/{stage}/{item_id}/` 규칙으로 확장한다.
