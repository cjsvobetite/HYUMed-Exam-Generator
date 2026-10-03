"""화면에서 쓰는 선택지·브랜드 상수."""

BRAND = "SaluTerra"
TAGLINE = "강의에서 시험 문항까지 — 조용히, 정확하게"

ANSWER_FORMATS = [
    "1) 오지선다 하나만 고르시오 (단일정답)",
    "2) 가나다라 조합형 (가/가나/가다 식 복합 선지)",
    "3) 오지선다 모두 고르시오 (복수정답)",
    "4) 칠지선다 모두 고르시오 (심화 7선지)",
    "5) 단답형 (1단어~1줄)",
    "6) 약술형 (2~4줄 기전 서술)",
    "7) 서술형 (한 문단 이상)",
]
DEFAULT_ANSWER_FORMATS = {0, 1, 2, 4}

CONTENT_TYPES = [
    "기본개념형 (정의·분류·단순 기전)",
    "응용개념형 (2단계 추론·교차 비교)",
    "케이스형 (임상 시나리오 통합)",
]

DIFFICULTIES = ["표준", "높음 (2단계 추론)", "황세진 교수 수준"]

TERM_LANG_OPTIONS = {
    "영어 (myocardial infarction)":            "english",
    "한글 (심근경색)":                          "korean",
    "병기 (심근경색 (myocardial infarction))": "both",
}
TERM_LANG_RULE = {
    "english": "**의학용어는 영어로만 표기**. 한글 번역 병기 금지. 발문·선지·해설 모두 적용. 표준 약어(ACEi, MI, CHF 등) 허용.",
    "korean":  "**의학용어는 한글로만 표기** (KMA 의학용어집 기준). 괄호 안 영문 병기조차 금지. 단, 표준 약자(DNA, RNA, ATP 등 일반화된 것)는 허용.",
    "both":    "**의학용어는 한글(영문) 형태로 병기**. 첫 등장 시 한글 → 괄호 안 영문, 같은 문항 내 반복 시 한글만. 약자(ACEi, MI 등)는 영문 그대로 사용 가능.",
}

OCR_MODE_OPTIONS = {
    "끄기": "off",
    "자동 (텍스트 없는 곳만)": "auto",
    "모든 PDF 페이지": "always",
}

VIEW_PREVIEW = "📖 미리보기"
VIEW_CBT_PER_Q = "🎯 CBT · 문항별 해설"
VIEW_CBT_SUBMIT = "📝 CBT · 전체 제출 후 해설"
VIEW_MODES = [VIEW_PREVIEW, VIEW_CBT_PER_Q, VIEW_CBT_SUBMIT]
CBT_MODES = [VIEW_CBT_PER_Q, VIEW_CBT_SUBMIT]


def cbt_mode_value(label: str) -> str:
    return "per_q" if label == VIEW_CBT_PER_Q else "submit_all"
