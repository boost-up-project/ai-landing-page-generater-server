# ai-landing-page-generater-server

## 실행 방법
### 1. uv가 설치되어 있는지 확인


```
uv--version
```

### (설치되어있지 않을 경우) 1-2. uv 설치

hombrew:
```
brew install uv
```

또는 uv 공식 설치 방식:

```
curl-LsSf https://astral.sh/uv/install.sh |sh
```


### 2. 프로젝트 의존성 설치

```
uv sync
```

실행.

**명령어 역할**

① `.venv` 생성

없으면:

```
.venv/
```

자동 생성
-> 따로 가상 환경 설치할 필요 없음. 

② `uv.lock` 확인

③ 패키지 설치


### 3. FastAPI 서버 실행

```
uv run uvicorn app.main:app --reload
```

## 버전 정보
개발 환경 및 버전

### Runtime

| 항목 | 버전 |
| --- | --- |
| Python | 3.10.20 |
| uv | `uv --version`으로 확인 |
| FastAPI | >= 0.141.1 |
| Uvicorn | >= 0.52.4 |

### 주요 Dependencies

| Library | Version | 용도 |
| --- | --- | --- |
| fastapi | >= 0.141.1 | REST API 서버 |
| uvicorn | >= 0.52.4 | ASGI 서버 |
| pydantic-settings | >= 2.15.0 | 환경 변수 및 설정 관리 |
| python-multipart | >= 0.0.32 | PDF 등 파일 업로드 |
| pymupdf | uv.lock 기준 | PDF 파싱 |
| httpx | uv.lock 기준 | 외부 API / AI API 호출 |
| tenacity | uv.lock 기준 | API 호출 재시도 처리 |

### Development Dependencies

| Library | 용도 |
| --- | --- |
| pytest | 테스트 |
| pytest-asyncio | 비동기 API 테스트 |
| ruff | Python Lint / Format |

## Commit 메시지 규칙
| **타입**       | **설명**                          |
|----------------|-----------------------------------|
| feat         | 	새로운 기능 추가                  |
| fix | 버그 수정                         |
| docs           | 문서 수정                         |
|style| 코드 스타일 수정 (기능 변경 없음) |
| refactor         | 	코드 구조 개선                    |
| test | 테스트 코드 추가                  |
| chore           | 기타 작업 (빌드 설정 등)          |

## 브랜치명 규칙
1. 이슈를 만든다. 
2. `<해당 브랜치 기능>/#<이슈번호>/<간단한기능설명단어>`
ex) feat/#1/brand_identity

## 백엔드 구조

백엔드는 기술 계층이 아니라 도메인을 기준으로 구성한다.

```text
app/
├── brand/       # 브랜드 분석 API, 스키마, 서비스, 프롬프트, MD 템플릿
├── campaign/    # 캠페인 생성 도메인
├── persona/     # 페르소나 생성 도메인
├── common/      # 도메인 공통 기능(PDF 파싱 등)
├── core/        # 설정 및 애플리케이션 전역 관심사
└── workflows/   # brand → campaign → persona 같은 전체 흐름 조정
```

Gemini가 반환하는 값은 Pydantic 스키마로 검증한 후 각 도메인의 고정 Markdown
템플릿으로 렌더링한다. 기획 출력 명세는 `docs/output-specs/`에서 관리한다.
`GEMINI.md`는 Gemini CLI가 참고하는 개발 규칙이며 런타임 프롬프트나 결과
템플릿을 저장하는 곳으로 사용하지 않는다.
