"""문항 생성 프롬프트 조립.

system: 출제 지침(prompts/exam_guide.md) + 출력 형식 + 난이도·용어 규칙
user:   강의 자료 → 기출 참고 → 출제 요청 + 문항별 설계표(blueprint)
"""
from pathlib import Path

GUIDE_PATH = Path(__file__).resolve().parent / "prompts" / "exam_guide.md"

# '전사본에서 언급하지 않은 내용 출제 제외' 옵션 — system·user prompt 양쪽에 넣는다
TRANSCRIPT_ONLY_RULE = (
    "**출제 범위는 강의 전사본에서 실제로 언급된 내용으로 한정한다.**\n"
    "- 모든 문항의 정답 근거가 전사본 안에 있어야 한다. 전사본에 없고 강의 자료(슬라이드)에만 있는 내용, "
    "일반 의학 지식으로만 알 수 있는 내용은 출제하지 말 것.\n"
    "- 강의 자료는 전사본에 나온 내용의 용어·수치·표기를 확인하는 용도로만 쓴다.\n"
    "- 오답 선지도 전사본에 나온 개념들로 구성하고, 해설에는 근거가 된 전사본 구절을 짧게 인용한다.\n"
    "- 전사본 분량이 요청 문항 수에 비해 부족하면 같은 내용을 다른 각도로 묻되, 범위를 넓히지 말 것."
)

DIFFICULTY_RULES = {
    "표준": "강의에서 직접 다룬 사실을 정확히 아는지 묻는다. 함정은 주어 바꿔치기·방향 반전 수준.",
    "높음 (2단계 추론)": "정답을 고르려면 2단계 이상 추론이 필요하게 만든다 (기전 → 결과 → 임상 소견). "
                     "여러 소단원의 개념을 교차 비교하는 선지, 유사 질환 감별 포인트를 늘린다.",
    "황세진 교수 수준": "해부학 교수 스타일. 수업 중 지나가듯 언급한 일화·예외를 노린다 "
                   "(예: 'Microglia만 중배엽 기원', 'B fiber는 preganglionic'). 유사 개념 바꿔치기 함정"
                   "(kinesin↔dynein, Schwann↔oligodendrocyte, radial↔ulnar)을 적극 쓰고, "
                   "'모두 고르시오'는 선지를 5~10개로 늘려도 된다. 해설은 오답 선지만 '- ⑤ X → Y'로 짧게.",
}

_FENCE = "`" * 3

OUTPUT_FORMAT = f"""## 출력 형식 (앱이 이 형식을 읽어 CBT·PDF로 만든다 — 정확히 지킬 것)
- 문항마다 아래 구조. 번호는 `**문제 N.**` (N은 1부터 차례대로). 다른 번호 체계(Q1, S1, C1) 쓰지 말 것.
- 선지는 줄마다 ①②③… 원문자로 시작. 증례·보기 진술·표 같은 발문 보충 내용은 `> `로 시작하는 줄에 쓴다.
- 정답·해설은 안쪽 토글 안에. 정답 줄은 `✅ **정답: …**`, 해설은 `💡 **해설:** …`로 시작.
- 문항 사이 다른 텍스트(메타 정보, 소제목, 설명)는 쓰지 말 것. 마지막에만 전체 정답표 토글을 둔다.
- 설계표의 묻는 방식 이름("(예외·함정)" 등)·형식·정답 개수를 발문에 쓰지 말 것.
- 전체 출력을 {_FENCE} 코드블록으로 감싸지 말 것.

예시 1 — 한 개 고르기
<details>
<summary>**문제 1.** Myotome에서 유래한 근육 전구세포가 사지로 이동하는 데 필요한 전사인자는?</summary>

   ① MyoD
   ② Pax3
   ③ Myf5
   ④ Myogenin
   ⑤ Sonic hedgehog

<details>
<summary>✅ 정답 확인</summary>

✅ **정답: ②**
💡 **해설:** Pax3는 dermomyotome 가장자리의 전구세포가 사지싹으로 이동하는 데 필요하다(전사본: "Pax3 없으면 팔다리 근육이 안 생긴다").
- ① MyoD — 이동이 아니라 분화 결정 인자.
- ③ Myf5 — 축상(epaxial) 근육 계열 결정에 관여.
- ④ Myogenin — myoblast 융합·말단 분화 단계.
- ⑤ Shh — notochord·신경관에서 분비되는 신호 분자이지 근육 전구세포 내 전사인자가 아님.

</details>
</details>

예시 2 — 조합형 (보기 진술은 `> (가)`로, 선지는 조합)
<details>
<summary>**문제 2.** Duchenne 근이영양증에 대한 설명으로 옳은 것을 모두 고른 것은?</summary>

> (가) X-연관 열성으로 유전된다.
> (나) Dystrophin 유전자의 결손으로 생긴다.
> (다) 혈청 CK는 정상이다.
> (라) Gower sign이 관찰된다.

   ① 가, 나
   ② 가, 다
   ③ 나, 라
   ④ 가, 나, 라
   ⑤ 나, 다, 라

<details>
<summary>✅ 정답 확인</summary>

✅ **정답: ④**
💡 **해설:** (가)(나)(라)가 옳다.
- (다) 근섬유 파괴로 CK는 초기부터 크게 상승한다.

</details>
</details>

예시 3 — 케이스형 / 모두 고르시오 (증례는 `> ` 줄)
<details>
<summary>**문제 3.** 다음 증례에 대한 설명으로 옳은 것을 모두 고르시오.</summary>

> 4세 남아가 계단을 오르기 힘들어하고 자주 넘어져 내원했다. 종아리가 비대하고, 바닥에서 일어날 때 손으로 허벅지를 짚는다. 혈청 CK 12,000 U/L.

   ① 종아리 비대는 지방·섬유조직 침착에 의한 가성비대이다.
   ② 근생검에서 dystrophin 염색이 정상으로 보일 것이다.
   ③ 같은 질환의 경증형은 Becker 근이영양증이다.
   ④ 어머니는 보인자일 가능성이 있다.
   ⑤ 근력 약화는 원위부 근육에서 먼저 시작된다.

<details>
<summary>✅ 정답 확인</summary>

✅ **정답: ①, ③, ④**
💡 **해설:** Duchenne 근이영양증의 전형적 증례.
- ② dystrophin이 거의 없어 염색되지 않는다.
- ⑤ 근위부(골반·대퇴)부터 약해진다.

</details>
</details>

예시 4 — 단답형·약술형·서술형 (선지 없음, 정답 줄에 답을 쓴다)
<details>
<summary>**문제 4.** 성체 골격근이 손상되었을 때 재생을 담당하는 근육 줄기세포의 이름은?</summary>

<details>
<summary>✅ 정답 확인</summary>

✅ **정답: 위성세포 (satellite cell)**
💡 **해설:** 기저막과 근섬유막 사이에 있으며 Pax7을 발현한다.

</details>
</details>

마지막 — 전체 정답표
<details>
<summary>전체 정답표</summary>

| 문항 | 정답 |
|---|---|
| 1 | ② |

</details>
"""


def load_exam_guide() -> str:
    if not GUIDE_PATH.exists():
        raise FileNotFoundError(f"{GUIDE_PATH} 파일이 없습니다.")
    return GUIDE_PATH.read_text(encoding="utf-8")


def build_system_prompt(extra: str = "", answer_formats=None, term_lang_rule: str = "",
                        transcript_only: bool = False, difficulty: str = "") -> str:
    parts = ["너는 한국 의과대학 시험 문항 출제 위원이다. 아래 지침과 출력 형식을 엄격히 따르고, 모든 출력은 한국어로 한다."]
    rules = []
    if term_lang_rule.strip():
        rules.append(f"- 의학용어 표기: {term_lang_rule} (발문·선지·해설·정답표 전부)")
    if transcript_only:
        rules.append("- 출제 범위 제한:\n" + TRANSCRIPT_ONLY_RULE)
    if difficulty in DIFFICULTY_RULES:
        rules.append(f"- 난이도 ({difficulty}): {DIFFICULTY_RULES[difficulty]}")
    if answer_formats:
        rules.append("- 이번 요청에서 쓸 수 있는 선지 형식은 설계표에 배정된 것뿐이다: "
                     + ", ".join(answer_formats))
    if extra.strip():
        rules.append(f"- 사용자 추가 지시 (지침보다 우선): {extra.strip()}")
    if rules:
        parts.append("## 이번 요청의 최우선 규칙\n" + "\n".join(rules))
    parts.append(load_exam_guide())
    parts.append(OUTPUT_FORMAT)
    return "\n\n".join(parts)


def build_user_prompt(lecture_text, transcript_text,
                      answer_formats, content_types,
                      num_mcq, num_short, difficulty,
                      term_lang_rule: str = "",
                      past_exam_text: str = "",
                      variation_mode: str = "",
                      transcript_only: bool = False,
                      blueprint: str = "") -> str:
    """blueprint: blueprint.render_blueprint() 결과 (문항별 주제·묻는 방식·형식·정답 개수).
    없으면 강의를 4구간으로 나눠 고르게 출제하라는 지시로 대신한다."""
    parts = []

    # ── 강의 자료 ──
    if transcript_only and transcript_text.strip():
        parts.append(f"=== 강의 전사본 (유일한 출제 범위 — 여기 언급된 내용만 출제) ===\n{transcript_text}")
        if lecture_text.strip():
            parts.append("=== 강의 자료 (용어·수치 확인용 — 전사본에 없는 내용은 출제 금지) ===\n"
                         f"{lecture_text}")
    elif transcript_text.strip() and lecture_text.strip():
        parts.append(f"=== 강의 전사본 (주 출제 범위) ===\n{transcript_text}")
        parts.append(f"=== 강의 자료 (보조 참고용) ===\n{lecture_text}")
    elif transcript_text.strip():
        parts.append(f"=== 강의 전사본 (출제 범위) ===\n{transcript_text}")
    elif lecture_text.strip():
        parts.append(f"=== 강의 자료 (출제 범위) ===\n{lecture_text}")

    # ── 기출 ──
    if past_exam_text.strip():
        vm_desc = {
            "유사 변형": "수치·고유명사·임상 조건만 바꾸고 출제 개념·구조는 유지",
            "적당한 변형": "출제 개념은 같되 시나리오·선지 배열·함정 위치를 새로 설계",
            "창의적 변형": "같은 범위에서 완전히 새로운 발문·선지. 기출의 난이도·출제 감각만 참고",
        }
        if variation_mode:
            parts.append(f"=== 참고 기출문제 — 변형 출제 ({variation_mode}: {vm_desc.get(variation_mode, '')}) ===\n"
                         "기출 문항을 그대로 옮기지 말 것.\n" f"{past_exam_text[:10000]}")
        else:
            parts.append("=== 참고 기출문제 (출제 범위·스타일 참고용, 그대로 옮기지 말 것) ===\n"
                         f"{past_exam_text[:10000]}")

    # ── 요청 ──
    total = num_mcq + num_short
    req = ["=== 출제 요청 ===",
           f"- 문항 수: 정확히 {total}문항 (문제 1 ~ 문제 {total}). 토큰이 부족하면 해설을 줄이고 문항 수는 줄이지 말 것.",
           f"- 난이도: {difficulty}"]
    if term_lang_rule.strip():
        req.append(f"- 의학용어 표기: {term_lang_rule}")
    if blueprint:
        req += ["", "=== 문항별 설계표 (반드시 이대로 출제) ===",
                "각 문항은 배정된 출제 포인트를, 배정된 묻는 방식으로, 배정된 선지 형식·정답 개수로 출제한다. "
                "다른 문항의 포인트를 다시 묻지 말 것.", "", blueprint]
    else:
        req += ["- 사용할 선지 형식: " + ", ".join(answer_formats),
                "- 사용할 내용 형식: " + ", ".join(content_types),
                "- 강의를 길이 기준 4구간(0~25 / 25~50 / 50~75 / 75~100%)으로 나눠 구간마다 고르게 출제하고, "
                "문항마다 서로 다른 핵심 개념을 묻는다."]
    req += ["", "선지 형식별 정답 개수: '하나만 고르시오'·조합형은 정확히 1개, '모두 고르시오'는 설계표의 개수, "
            "단답·약술·서술형은 정답 줄에 답 텍스트.",
            "힌트 차단: 발문에 정답·그 번역·어원·파생어를 쓰지 말고, 정답 선지만 길거나 자세하게 쓰지 말 것 "
            "(출제 후 자동 점검으로 걸러 다시 쓰게 된다)."]
    parts.append("\n".join(req))
    return "\n\n".join(parts)
