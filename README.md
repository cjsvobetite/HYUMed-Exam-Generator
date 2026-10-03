# HYUMed-Exam-Generator

Savior for med school — 강의자료·전사본·기출문제로 의대 시험 대비 문항 세트를 만드는 Streamlit 앱 (SaluTerra).

메뉴는 세 가지입니다.

| 메뉴 | 하는 일 |
|---|---|
| ✨ AI 문항 생성 | 강의자료(PDF/PPTX/이미지)·전사본으로 문항 세트 생성. 선지 형식·내용 형식·난이도·의학용어 표기 선택, 기출 참고·변형 |
| 📄 문제지 CBT | 문제지·족보·복기 파일(PDF/사진/텍스트)을 올려 CBT로 풀고 해설지 PDF 받기 |
| 📋 복습 기록 | 유저별 풀이 기록, 회차별 오답 재풀이 |

공통: 미리보기(토글) / CBT(문항별 해설·전체 제출) / PDF(문제지 + 정답·해설 분리), 관리자 대시보드.

## 파일 구조

```
app.py                  진입점 (로그인 → 페이지 이동)
views/                  페이지: generate(문항 생성) · exam_cbt(문제지 CBT) · history_view · admin · login
ui.py                   공통 디자인 (헤더, 단계 제목, 배지, 미리보기 렌더)
constants.py            선택지·브랜드 상수
exam_import.py          문제지 → 문항 구조화 · 그림 잘라내기 · 정답/해설 · 마크다운 변환
images.py               문항 그림 저장 (data/images)
extractors.py           PDF / PPTX / TXT / 이미지 텍스트 추출 + OCR
question_generator.py   문항 생성 (스트리밍, 이어쓰기, 429 재시도)
prompt_loader.py        생성 프롬프트 조립 (+ prompts/exam_guide.md 출제 지침)
llm.py                  OpenAI 클라이언트, 모델별 파라미터·토큰 한도
cbt.py                  CBT 파싱·화면
history.py              풀이 기록
pdf_export.py           PDF 생성 (한글 폰트, 그림 포함)
auth.py / storage.py    회원 계정 / JSON 저장 (원자적 쓰기 + 잠금)
tests/                  pytest
packages.txt            Streamlit Cloud용 apt 패키지 (Tesseract OCR)
```

실행 중 만들어지는 `data/`(users.json, cbt_history.json, outputs/, images/)와 `fonts/*.ttf`는 Git에 올라가지 않습니다.

## 문제지 CBT

1. **문제지 올리기** — PDF, 사진(JPG/PNG), 텍스트 파일, 또는 복기 텍스트 붙여넣기. 여러 파일은 올린 순서대로 이어 붙입니다.
2. **읽기** — 비전 모델(기본 gpt-4o)이 페이지마다 문항 번호·발문·선지·정답 표기·그림 위치를 찾습니다. 페이지를 넘어가는 문항은 이어 붙이고, 복기가 덜 된 문항(발문이 잘림, 선지 누락, "기억 안 남" 등)은 **복기 불완전**으로 표시합니다.
3. **해설지 만들기** — 불완전한 문항 처리 방법을 고릅니다.
   - **🛠️ AI가 보완해서 풀기**: 빠진 발문·선지만 출제 의도에 맞게 채우고 `(AI 보완)` 배지와 무엇을 보완했는지 남깁니다.
   - **🏷️ 그대로 두고 표시**: 내용은 손대지 않고 `(문항 복기 불완전)` 배지만 붙입니다. 빠진 선지는 `(복기 안 됨)`으로 자리만 지키고, 판단할 수 없는 문항은 정답 없이 해설만 달고 채점에서 뺍니다.
   - 문제지에 정답이 있으면 그 정답을 쓰고, AI가 다르게 판단하면 해설 끝에 `※ AI 검토`로 남깁니다. "AI 해설 생성"을 끄면 문제지의 정답·해설만으로 바로 풉니다.
4. **풀기** — CBT로 풀고, 해설지 PDF·마크다운을 내려받습니다. 기록은 복습 기록에 `문제지: 파일명`으로 남습니다.

**그림이 있는 문항**: 그림·사진·ECG·영상·조직 슬라이드가 있는 문항은 그림을 잘라 문항에 붙입니다.
PDF 안에 이미지가 들어 있으면 그 이미지 경계 그대로, 스캔본·사진이면 모델이 찾은 그림 영역을 잘라내고, 영역을 못 찾으면 문항 영역(최후에는 페이지 전체)을 붙입니다.
붙인 그림은 CBT·미리보기·해설지 PDF에 모두 나오고, 해설을 만들 때도 모델에게 함께 보여 줍니다.

## OCR (AI 문항 생성의 자료 읽기)

자료 올리기 아래 **🔍 OCR 설정**에서 고릅니다.

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
- Streamlit Cloud는 재시작하면 파일이 초기화되어 회원·풀이 기록·문항 그림(`data/`)이 사라집니다. 오래 보관하려면 DB가 필요합니다.

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
