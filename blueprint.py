"""출제 설계표 — 문항마다 서로 다른 주제·묻는 방식·형식·정답 개수를 미리 정한다.

모델에게 "겹치지 않게 내라"고만 하면 같은 개념(예: MyoD, Duchenne)을 여러 번 묻는다.
그래서 두 단계로 나눈다.
  1) extract_topics(): 강의를 처음부터 끝까지 훑어 서로 겹치지 않는 출제 포인트 목록을 JSON으로 받는다.
  2) make_blueprint(): 그 목록에서 강의 전 구간에 고르게 포인트를 골라 문항에 하나씩 배정하고,
     묻는 방식·선지 형식·정답 개수도 코드가 정해서 반복을 막는다.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass

TOPIC_MODEL = "gpt-4o-mini"      # 주제 뽑기는 저렴한 모델로 충분
_MAX_TOPIC_CHARS = 150_000        # 주제 뽑기 입력 상한 (약 100k 토큰)

ANGLES = ["정의·특징", "기전·원리", "비교·감별", "예외·함정", "원인→결과", "임상 적용", "순서·과정", "수치·기준"]

_TOPIC_PROMPT = """너는 의과대학 시험 출제 위원이다. 주어진 강의를 처음부터 끝까지 읽고, 시험 문항으로 낼 수 있는 출제 포인트를 강의 순서대로 뽑아 JSON으로만 답하라.

규칙
- 포인트는 약 {n}개. 강의의 앞·중간·끝을 고르게 덮어라. 앞부분만 촘촘하고 뒤를 빼먹으면 안 된다.
- 포인트끼리 겹치지 않게 하라. 같은 개념을 말만 바꿔 두 개로 쪼개지 마라.
- point는 "무엇을 묻는지" 구체적인 한 문장으로 (나쁜 예: "MyoD", 좋은 예: "MyoD는 myoblast 분화를 결정하는 근육 특이 전사인자이며 Myf5와 중복 기능을 가진다").
- section: 그 포인트가 속한 강의 소단원·주제 (짧게).
- emphasis: 교수가 강조·반복하거나 "시험에 나온다"고 한 내용이면 2, 일반 설명 1, 지나가는 언급 0.
- has_sequence: 시간 순서·단계가 있는 내용이면 true.
- clinical: 질환·증례·임상 적용과 연결되는 내용이면 true.
{scope_rule}
형식: {{"topics": [{{"section": "", "point": "", "emphasis": 1, "has_sequence": false, "clinical": false}}]}}"""


@dataclass
class Topic:
    section: str
    point: str
    emphasis: int = 1
    has_sequence: bool = False
    clinical: bool = False


@dataclass
class Slot:
    number: int
    answer_format: str
    content_type: str
    angle: str
    topic: Topic | None = None
    n_answers: int | None = None      # '모두 고르시오' 정답 개수
    repeat: bool = False              # 포인트가 모자라 같은 포인트를 다른 측면으로 다시 쓰는 경우
    region: str = ""                  # 주제 목록이 없을 때 쓰는 강의 구간


def extract_topics(transcript: str, lecture: str, num_questions: int, transcript_only: bool = False,
                   model: str = TOPIC_MODEL) -> list[Topic]:
    from llm import completion_kwargs, get_client

    n = max(10, min(120, round(num_questions * 1.5)))
    if transcript_only and transcript.strip():
        scope = "- 출제 범위는 전사본에 실제로 언급된 내용뿐이다. 강의 자료에만 있는 내용은 포인트로 뽑지 마라."
        material = f"=== 강의 전사본 ===\n{transcript}\n\n=== 강의 자료 (참고용) ===\n{lecture}"
    else:
        scope = "- 전사본이 있으면 전사본 내용을 우선하고, 강의 자료로 보충하라."
        material = "\n\n".join(filter(None, [
            f"=== 강의 전사본 ===\n{transcript}" if transcript.strip() else "",
            f"=== 강의 자료 ===\n{lecture}" if lecture.strip() else "",
        ]))
    resp = get_client().chat.completions.create(
        messages=[{"role": "system", "content": _TOPIC_PROMPT.format(n=n, scope_rule=scope)},
                  {"role": "user", "content": material[:_MAX_TOPIC_CHARS]}],
        response_format={"type": "json_object"},
        **completion_kwargs(model, max_tokens=8000, temperature=0.2),
    )
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (resp.choices[0].message.content or "").strip())
    raw = json.loads(text).get("topics") or []
    topics, seen = [], set()
    for t in raw:
        if not isinstance(t, dict) or not str(t.get("point") or "").strip():
            continue
        point = " ".join(str(t["point"]).split())
        key = re.sub(r"\W", "", point.lower())[:40]
        if key in seen:
            continue
        seen.add(key)
        try:
            emphasis = max(0, min(2, int(t.get("emphasis", 1))))
        except (TypeError, ValueError):
            emphasis = 1
        topics.append(Topic(section=str(t.get("section") or "").strip(), point=point, emphasis=emphasis,
                            has_sequence=bool(t.get("has_sequence")), clinical=bool(t.get("clinical"))))
    return topics


def _pick_topics(topics: list[Topic], n: int) -> list[tuple[Topic, bool]]:
    """강의 순서를 n개 구간으로 나눠 구간마다 강조도가 가장 높은 포인트를 고른다.
    포인트가 n개보다 적으면 한 바퀴 돈 뒤 '다른 측면'으로 다시 쓴다."""
    if not topics:
        return []
    if len(topics) >= n:
        picked = []
        for i in range(n):
            lo, hi = len(topics) * i // n, len(topics) * (i + 1) // n
            bucket = topics[lo:max(hi, lo + 1)]
            picked.append((max(bucket, key=lambda t: t.emphasis), False))
        return picked
    return [(topics[i % len(topics)], i >= len(topics)) for i in range(n)]


def _short(label: str) -> str:
    return label.split(" (", 1)[0].split(") ", 1)[-1] if label else label


def _is_select_all(fmt: str) -> bool:
    return "모두 고르시오" in fmt


def _choice_count(fmt: str) -> int:
    return 7 if "칠지" in fmt else 5


def make_blueprint(num_questions: int, answer_formats: list[str], content_types: list[str],
                   topics: list[Topic] | None = None, seed: int | None = None) -> list[Slot]:
    rng = random.Random(seed)
    n = num_questions
    # 선지·내용 형식: 고르게 돌리되 같은 조합이 연달아 나오지 않게 내용 형식을 한 칸씩 어긋나게
    slots = []
    for i in range(n):
        af = answer_formats[i % len(answer_formats)]
        ct = content_types[(i // len(answer_formats) + i) % len(content_types)]
        slots.append(Slot(number=i + 1, answer_format=af, content_type=ct, angle=""))

    # 주제 배정
    picks = _pick_topics(topics or [], n)
    regions = ["전반부 (0~25%)", "중반부-1 (25~50%)", "중반부-2 (50~75%)", "후반부 (75~100%)"]
    for i, s in enumerate(slots):
        if picks:
            s.topic, s.repeat = picks[i]
        else:
            s.region = regions[i * 4 // max(n, 1)]

    # 묻는 방식: 문항마다 돌리고, 케이스형은 임상 적용, 순서 정보가 있으면 순서형도 허용
    offset = rng.randrange(len(ANGLES))
    usable = [a for a in ANGLES if a != "순서·과정"]
    for i, s in enumerate(slots):
        if "케이스" in s.content_type:
            s.angle = "임상 적용 (증례)"
        elif s.topic and s.topic.has_sequence and i % 3 == 0:
            s.angle = "순서·과정"
        else:
            s.angle = usable[(offset + i * 3) % len(usable)]
        if s.repeat and s.topic:
            # 같은 포인트를 다시 쓸 때는 앞에서 쓴 방식과 겹치지 않게
            first = next(x for x in slots if x.topic is s.topic and not x.repeat)
            if s.angle == first.angle:
                s.angle = usable[(usable.index(first.angle) + 4) % len(usable)] \
                    if first.angle in usable else usable[0]

    # '모두 고르시오' 정답 개수: 1~k를 고르게 섞어 배정 (연속 같은 개수 피함)
    for fmt in {s.answer_format for s in slots if _is_select_all(s.answer_format)}:
        group = [s for s in slots if s.answer_format == fmt]
        k = _choice_count(fmt)
        pool = [(j % k) + 1 for j in range(len(group))]
        rng.shuffle(pool)
        for a in range(1, len(pool)):
            if pool[a] == pool[a - 1]:
                for b in range(a + 1, len(pool)):
                    if pool[b] != pool[a - 1]:
                        pool[a], pool[b] = pool[b], pool[a]
                        break
        for s, cnt in zip(group, pool):
            s.n_answers = cnt
    return slots


def render_blueprint(slots: list[Slot]) -> str:
    rows = ["| 문항 | 선지 형식 | 내용 형식 | 출제 포인트 | 묻는 방식 |", "|---|---|---|---|---|"]
    for s in slots:
        fmt = _short(s.answer_format)
        if s.n_answers:
            fmt += f" (정답 {s.n_answers}개)"
        if s.topic:
            point = f"[{s.topic.section}] {s.topic.point}" if s.topic.section else s.topic.point
            if s.repeat:
                point += " — 앞 문항과 다른 측면으로"
        else:
            point = f"강의 {s.region}에서 다른 문항과 겹치지 않는 포인트"
        rows.append(f"| 문제 {s.number} | {fmt} | {_short(s.content_type)} | {point} | {s.angle} |")
    return "\n".join(rows)
