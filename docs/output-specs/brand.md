# Brand Knowledge 출력 명세

## 목적

업로드한 브랜드 PDF에서 근거가 확인된 정보만 추출하여, 검토 가능한 구조화
데이터와 최종 `brand.md`를 생성한다.

## 데이터 계약

모델은 Markdown을 직접 작성하지 않는다. `app/brand/schemas.py`의
`BrandKnowledge` JSON Schema에 맞는 구조화 데이터를 반환하며, 서버가 이를
검증한 후 Markdown 템플릿에 렌더링한다.

각 항목은 다음 값을 가진다.

- `content`: PDF에서 확인된 내용. 관련 내용이 없으면 빈 문자열
- `source_references`: 근거 PDF 파일명과 1부터 시작하는 페이지 번호

내용이 있으면 근거가 반드시 하나 이상 있어야 하며, 내용이 없으면 근거도
비어 있어야 한다.

## 고정 출력 순서

1. Brand Identity
   - Brand Overview
   - Brand Philosophy
   - Brand Positioning
   - Brand Target
   - Brand Personality
2. Verbal Guideline
   - Brand Voice
   - Tone of Voice
   - Writing Style
   - Messaging Principles
   - Vocabulary & Expressions
   - Copy Rules
3. Visual Guideline
   - Logo
   - Icon
   - Color
   - Fonts

PDF에 정보가 없는 항목은 `_PDF에서 확인된 정보 없음._`으로 표시한다.

## 변경 기준

- 제목, 섹션 순서, 빈 값 문구는 `app/brand/templates/brand.md`에서 관리한다.
- 추출 기준과 분류 규칙은 `app/brand/prompts/analyze.md`에서 관리한다.
- 필드명과 API 데이터 형식은 `app/brand/schemas.py`에서 관리한다.
- 세 파일 중 하나를 변경하면 관련 테스트와 이 문서도 함께 갱신한다.
