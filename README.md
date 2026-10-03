# HYUMed-Exam-Generator

Savior for med school — 강의자료·전사본·기출문제로 의대 시험 대비 문항 세트를 만드는 Streamlit 앱 (SaluTerra).

- 강의자료(PDF/PPTX/이미지)와 전사본을 올리면 OpenAI로 문항 세트를 만든다
- 선지 형식(단일/복수정답, 가나다 조합형, 단답·서술형), 내용 형식(개념/응용/케이스), 의학용어 표기(영/한/병기) 선택
- 기출문제를 참고하거나 변형해서 출제하고, 기출문제를 그대로 CBT로 풀 수도 있다
- **OCR**: 스캔 PDF, 사진 찍은 자료, 슬라이드 속 그림 글자까지 추출
- 미리보기(Notion 토글) / CBT(문항별 해설·전체 제출) / PDF(문제지 + 정답·해설 분리)
- 유저별 풀이 기록과 오답 재풀이, 관리자 대시보드

## 파일 구조

```
app.py                  Streamlit 진입점 (로그인, 사이드바 옵션, 생성, 결과·CBT)
auth.py                 회원가입·로그인 (salt + PBKDF2 해시)
config.py               경로·비밀키·폰트 설정
llm.py                  OpenAI 클라이언트, 모델별 파라미터·토큰 한도
question_generator.py   문항 생성 (스트리밍, 이어쓰기, 429 재시도)
prompt_loader.py        시스템/유저 프롬프트 조립
prompts/exam_guide.md   시험 유형별 문항 제작 지침
extractors.py           PDF / PPTX / TXT / 이미지 텍스트 추출 + OCR
cbt.py                  CBT 파싱·화면
history.py              유저별 풀이 기록
pdf_export.py           PDF 생성 (한글 폰트)
storage.py              JSON 저장 (원자적 쓰기 + 잠금)
tests/                  pytest
packages.txt            Streamlit Cloud용 apt 패키지 (Tesseract OCR)
```

실행 중 만들어지는 `data/`(users.json, cbt_history.json, outputs/)와 `fonts/*.ttf`는 Git에 올라가지 않습니다.

## OCR

사이드바 **🔍 OCR**에서 고릅니다.

| 모드 | 동작 |
|---|---|
| 끄기 | 텍스트 레이어만 읽음. 이미지 파일은 건너뜀 |
| 자동 (기본) | 글자를 읽을 수 없는 스캔 PDF 페이지, 이미지 파일, 슬라이드 속 그림만 OCR |
| 모든 PDF 페이지 | PDF 전 페이지 OCR — 그림·도표 속 글자까지 필요할 때 |

| 엔진 | 특징 |
|---|---|
| OpenAI 비전 (`gpt-4o-mini` 기본) | 한글·의학용어·표 인식이 정확. 페이지당 API 비용 발생 |
| Tesseract | 무료. `tesseract-ocr`, `tesseract-ocr-kor`가 설치된 환경에서만 목록에 나타남 |

추출 결과는 파일 내용과 OCR 설정별로 캐시되므로, 버튼을 누를 때마다 OCR을 다시 돌리지 않습니다.

## 로컬 실행

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # 값 채우기
streamlit run app.py
```

- `OPENAI_API_KEY`, `ADMIN_ID`는 환경변수로 넣어도 됩니다.
- Tesseract를 쓰려면: `sudo apt install tesseract-ocr tesseract-ocr-kor` (macOS: `brew install tesseract tesseract-lang`)
- 한글 폰트(NanumGothic)는 첫 실행 때 `fonts/`에 자동으로 내려받고, 실패하면 ReportLab 내장 한글 폰트로 PDF를 만듭니다.

테스트:

```bash
pip install -r requirements-dev.txt
pytest
```

## Streamlit Community Cloud 배포

1. New app → 이 저장소, Main file path `app.py`
2. Advanced settings → Secrets:

```toml
OPENAI_API_KEY = "sk-..."
ADMIN_ID = "관리자로 쓸 아이디"
```

`packages.txt` 덕분에 Tesseract도 자동 설치됩니다.

- API 키는 절대 코드나 GitHub에 올리지 마세요.
- `ADMIN_ID`와 같은 아이디로 로그인하면 관리자 대시보드가 열립니다(지정하지 않으면 `jsdec22`). 다른 사람이 먼저 가입하지 못하도록 배포 직후 그 아이디로 가입해 두세요.
- Streamlit Cloud는 재시작하면 파일이 초기화되어 회원·풀이 기록(`data/`)이 사라집니다. 오래 보관하려면 DB가 필요합니다.

## Colab에서 실행

```python
!git clone https://github.com/cjsvobetite/HYUMed-Exam-Generator.git
%cd HYUMed-Exam-Generator
!apt-get -qq install -y tesseract-ocr tesseract-ocr-kor
!pip install -q -r requirements.txt pyngrok

import os, getpass, subprocess, time
os.environ["OPENAI_API_KEY"] = getpass.getpass("OpenAI API 키: ")
subprocess.Popen(["streamlit", "run", "app.py", "--server.port=8501", "--server.headless=true"])
time.sleep(8)

from pyngrok import ngrok
ngrok.set_auth_token(getpass.getpass("ngrok 토큰: "))
print(ngrok.connect(8501, "http").public_url)
```
