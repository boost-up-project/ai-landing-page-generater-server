# Persona 출력 명세

## 목적

사용자가 입력한 1~5개의 자연어 설명을 각각 독립적인 페르소나로 분류하고,
현재 프로젝트의 `brand.md`와 `campaign.md`를 참고해 합리적인 추론을 더한다.
원문과 추론은 결과에서 따로 표시하지 않고 자연스러운 한국어로 통합한다.

## 분석 항목

1. Profile: 어떤 사람인지 보여 주는 기본 특성
2. Situation: 현재 상황과 제품·서비스가 필요한 맥락
3. Needs: 이루고 싶은 목표와 원하는 변화
4. Pain Point: 현재 겪는 문제와 불편
5. Interest: 취향, 관심사, 중요하게 생각하는 가치
6. Behavior: 제품·서비스를 탐색, 비교, 구매하는 방식
7. Appendix
   - Purchase Journey: 인지부터 구매까지의 여정
   - Dislikes: 피하고 싶어 하는 경험과 조건

AI는 각 페르소나에 짧은 한국어 이름을 생성한다. 각 항목은 검토 화면에서
불릿 목록으로 편집할 수 있도록 문자열 배열로 반환한다.

## API 흐름

- `POST /api/personas`: 1~5개의 자연어 입력 분석
- `GET /api/personas/{persona_id}`: Persona 초안 조회
- `PUT /api/personas/{persona_id}/review`: 수정 결과 검토 완료
- `POST /api/personas/{persona_id}/finalize`: 페르소나별 Markdown 생성
- `GET /api/personas/{persona_id}/markdown`: 확정 Markdown 조회

`POST /api/personas` 요청 예시는 다음과 같다.

```json
{
  "project_id": "프로젝트 UUID",
  "inputs": [
    "작은 집으로 이사해 공간 활용 가구를 찾는 직장인"
  ]
}
```

## 저장 경로

```text
storage/projects/{project_id}/persona/{persona_id}/
  inputs.json
  analyzed.json
  reviewed.json
  persona-a.md
  persona-b.md
  record.json
```

Markdown은 입력 순서대로 `persona-a.md`부터 최대 `persona-e.md`까지 생성한다.
Persona 이후 단계의 경로가 정해지지 않았으므로 확정 응답의 `next_route`는
현재 `null`이다.
