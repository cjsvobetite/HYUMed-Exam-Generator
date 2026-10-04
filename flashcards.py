"""문항 세트·강의 자료 → 플래시카드.

카드: {id, front, back, qid, known: True|False|None, reviews: int}
덱은 학습 공간 세트(kind="flashcards")로 저장하고, markdown 칸에 카드 JSON을 넣는다.

- 요청(instruction)이 없으면: 문항마다 핵심 사실 1~2장.
- 요청이 있으면: 요청을 최우선으로 따른다 (카드 수·앞뒷면 구성 포함).
  강의 자료(material)를 같이 주면 자료를 나눠 읽혀 "강의록의 용어를 빠짐없이" 같은 요청도 처리한다.
"""
from __future__ import annotations

import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor

FLASH_MODEL = "gpt-4o-mini"
EXAMPLE_REQUEST = "이 강의록에 나온 의학용어를 모두 빠짐없이 물어보는 카드로 만들어줘 (앞면: 의학용어, 뒷면: 뜻)"
# (버튼 이름, 요청 문구) — 화면에서 예시 버튼으로 보여 준다
CARD_EXAMPLES = [
    ("의학용어 전부", EXAMPLE_REQUEST),
    ("강조한 핵심만", "교수님이 강조하거나 반복한 핵심 개념만 골라 카드로 만들어줘"),
    ("질환별 정리", "질환마다 원인·증상·진단·치료를 각각 묻는 카드로 만들어줘"),
    ("기출 개념 전부", "기출문제에 나온 개념을 하나도 빠짐없이 카드로 만들어줘"),
]
# 문항 없이 자료만으로 카드를 만들 때 요청이 비어 있으면 쓰는 기본 요청
DEFAULT_MATERIAL_REQUEST = "자료 전체에 걸쳐 시험에 나올 핵심 사실을 빠짐없이 카드로 만들어줘 (앞면: 회상 질문, 뒷면: 답과 한 줄 이유)"
_MAX_QUESTIONS = 60
_MAX_CARDS = 400
_CHUNK = 12_000          # 강의 자료를 이 글자 수 단위로 나눠 카드를 만든다
_WORKERS = 4

_PROMPT = """너는 의과대학생용 암기 플래시카드를 만드는 도구다. 주어진 내용으로 카드를 만들고 JSON으로만 답하라.
{request}
기본 규칙 (사용자 요청과 충돌하면 사용자 요청을 따른다)
- 시험 문항이 주어지면 문항마다 카드 1장(핵심이 둘이면 최대 2장). 서로 같은 내용의 카드는 만들지 마라.
- front: 짧은 회상 질문 한 줄. 답이나 그 번역·어원을 front에 넣지 마라.
- back: 답을 먼저, 이어서 왜 그런지 한 줄. 두 줄을 넘기지 마라.
- 주어진 문항·자료에 근거하고, 없는 내용은 덧붙이지 마라.
- qid: 문항에서 만든 카드면 근거 문항 번호(예: "문제 3"), 강의 자료에서 만든 카드면 "".
{term_rule}
형식: {{"cards": [{{"front": "", "back": "", "qid": ""}}]}}"""


def _card_source(markdown: str) -> list[dict]:
    from cbt import parse_cbt_questions

    out = []
    for q in parse_cbt_questions(markdown)[:_MAX_QUESTIONS]:
        item = {"qid": q["id"], "stem": q["stem"]}
        if q["choices"]:
            item["choices"] = {str(i + 1): c for i, c in enumerate(q["choices"])}
            item["answer"] = [i + 1 for i in q["answers"]]
        else:
            item["answer"] = q.get("answer_text", "")
        item["explanation"] = q["explanation"][:600]
        out.append(item)
    return out


def _chunks(text: str) -> list[str]:
    paras, out, buf = re.split(r"\n\s*\n", text), [], ""
    for p in paras:
        if buf and len(buf) + len(p) > _CHUNK:
            out.append(buf)
            buf = ""
        buf += p + "\n\n"
    if buf.strip():
        out.append(buf)
    return out


def _call(system: str, user: str, model: str) -> list[dict]:
    from llm import completion_kwargs, get_client

    resp = get_client().chat.completions.create(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        **completion_kwargs(model, max_tokens=12000, temperature=0.3),
    )
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (resp.choices[0].message.content or "").strip())
    return [c for c in json.loads(text).get("cards") or [] if isinstance(c, dict)]


def make_flashcards(markdown: str, term_rule: str = "", model: str = FLASH_MODEL,
                    instruction: str = "", material: str = "") -> list[dict]:
    """instruction: 사용자 요청 (예: EXAMPLE_REQUEST). material: 강의 자료·전사본 원문 (선택)."""
    instruction = instruction.strip()
    if not instruction and not markdown and material.strip():
        instruction = DEFAULT_MATERIAL_REQUEST
    system = _PROMPT.format(
        request=f"\n★ 사용자 요청 (최우선 — 카드 수·앞뒷면 구성도 이 요청대로):\n{instruction}\n" if instruction else "",
        term_rule=f"- 의학용어 표기: {term_rule}" if term_rule else "",
    )
    items = _card_source(markdown) if markdown else []

    if instruction and material.strip():
        # 요청이 강의 자료를 대상으로 할 수 있으므로 자료를 나눠 각각 카드를 만들고 합친다
        chunks = _chunks(material)
        payloads = [f"=== 강의 자료 ({i}/{len(chunks)}) ===\n{chunk}" for i, chunk in enumerate(chunks, 1)]
        if items:
            payloads.append("=== 시험 문항 (요청에 해당하는 내용이 있으면 카드로) ===\n"
                            + json.dumps({"questions": items}, ensure_ascii=False))
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            raw = [c for part in pool.map(lambda u: _call(system, u, model), payloads) for c in part]
    elif items:
        raw = _call(system, json.dumps({"questions": items}, ensure_ascii=False), model)
    else:
        return []

    cards, seen = [], set()
    for c in raw:
        front, back = " ".join(str(c.get("front") or "").split()), str(c.get("back") or "").strip()
        key = re.sub(r"\W", "", front.lower())
        if not front or not back or key in seen:
            continue
        seen.add(key)
        cards.append(new_card(front, back, str(c.get("qid") or "")))
        if len(cards) >= _MAX_CARDS:
            break
    return cards


def new_card(front: str, back: str, qid: str = "") -> dict:
    return {"id": uuid.uuid4().hex[:10], "front": front, "back": back, "qid": qid, "known": None, "reviews": 0}


def dumps(cards: list[dict]) -> str:
    return json.dumps({"cards": cards}, ensure_ascii=False)


def loads(text: str) -> list[dict]:
    try:
        return list(json.loads(text or "{}").get("cards") or [])
    except ValueError:
        return []
