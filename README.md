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

## 브랜드 분석 입력

`POST /api/brands/analyze`는 `multipart/form-data`로 다음 필드를 받는다.

| 필드 | 형식 | 필수 여부 |
| --- | --- | --- |
| `files` | PDF, 최대 10개 | 한 개 이상 필수 |
| `logo_files` | SVG, PNG, JPG, JPEG | 선택 |
| `icon_files` | SVG, PNG, JPG, JPEG | 선택 |
| `font_files` | TTF | 선택 |
| `colors` | `#RRGGBB` 또는 `#RGB` 문자열 | 선택 |

시각 자산은 합쳐서 최대 20개까지 업로드할 수 있다. 직접 업로드한 자산명과
정규화된 색상값은 Gemini가 분석한 Visual Guideline에 합쳐진다.

## 페르소나 생성

`POST /api/personas`는 프로젝트의 `brand.md`와 `campaign.md`를 참고해 1~5개의
자연어 입력을 각각 독립적인 구조화 페르소나로 생성한다. 결과는 Profile,
Situation, Needs, Pain Point, Interest, Behavior와 Appendix의 Purchase Journey,
Dislikes로 구성된다. 검토 확정 후 입력 순서대로 `persona-a.md`부터 최대
`persona-e.md`까지 개별 파일을 생성한다.

세부 요청·응답과 저장 명세는 `docs/output-specs/persona.md`에서 확인할 수 있다.

## 백엔드 실행 방법

백엔드 저장소 루트에서 실행한다. 처음 실행할 때 의존성을 설치한다.

```bash
uv sync
```

`.env` 파일이 없다면 `.env.example`을 복사하고 `GEMINI_API_KEY`에 실제 키를
입력한다.

```bash
cp .env.example .env
```

FastAPI 서버를 실행한다.

```bash
uv run uvicorn app.main:app --reload
```

실행 후 다음 주소에서 확인할 수 있다.

- API 문서: `http://127.0.0.1:8000/docs`
- 상태 확인: `http://127.0.0.1:8000/health`

서버를 종료할 때는 실행 중인 터미널에서 `Ctrl+C`를 누른다.

## Coolify 배포

프런트엔드 `https://blanki.ynana.xyz`의 브라우저 요청을 허용하도록 다음 환경변수를
설정한다.

```env
CORS_ORIGINS=["https://blanki.ynana.xyz"]
```

로컬 프런트엔드도 함께 허용하려면 `.env.example`과 같이 로컬 origin을 목록에
추가한다. 환경변수를 변경한 뒤에는 백엔드를 재배포한다.
