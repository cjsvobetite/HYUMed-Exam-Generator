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
    "혼용 (한글·영어 둘 다 출제)":              "both",
}
TERM_LANG_RULE = {
    "english": "의학용어는 영어로 쓴다. 발문·선지에 한글 번역을 괄호로 덧붙이지 않는다. 표준 약어(ACEi, MI, CHF 등)는 그대로 쓴다.",
    "korean":  "의학용어는 한글(대한의사협회 의학용어집 기준)로 쓴다. 발문·선지에 영어 원어를 괄호로 덧붙이지 않는다. "
               "일반화된 약어(DNA, RNA, ATP, MI 등)는 그대로 쓴다.",
    "both":    "학생이 한글 용어와 영어 용어를 둘 다 알아야 하도록 섞어서 출제한다. 어떤 문항은 한글로, 어떤 문항은 영어로 묻고, "
               "발문을 한글로 쓰면 선지는 영어로(또는 그 반대로) 내도 된다. 세트 전체에서 한글·영어 비율이 한쪽으로 쏠리지 않게 한다. "
               "한 용어 옆에 다른 언어 번역을 괄호로 같이 쓰는 '병기'는 발문·선지에서 하지 않는다 — 번역이 곧 힌트가 된다. "
               "해설에서만 '한글 (영어)'로 함께 적어 둘 다 익히게 한다.",
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
