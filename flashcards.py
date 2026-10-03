"""문항 세트 → 플래시카드.

카드: {id, front, back, qid, known: True|False|None, reviews: int}
덱은 학습 공간 세트(kind="flashcards")로 저장하고, markdown 칸에 카드 JSON을 넣는다.
"""
from __future__ import annotations

import json
import re
import uuid

FLASH_MODEL = "gpt-4o-mini"
_MAX_QUESTIONS = 60

_PROMPT = """너는 의과대학생용 암기 플래시카드를 만드는 도구다. 주어진 시험 문항들에서 꼭 외워야 할 핵심 사실을 뽑아 카드로 만들고 JSON으로만 답하라.

규칙
- 문항마다 카드 1장(핵심이 둘이면 최대 2장). 서로 같은 내용의 카드는 만들지 마라.
- front: 짧은 회상 질문 한 줄. 답이나 그 번역·어원을 front에 넣지 마라 (예: ❌ "근육 줄기세포인 위성세포(satellite cell)가 발현하는 인자는?").
- back: 답을 먼저, 이어서 왜 그런지 한 줄. 두 줄을 넘기지 마라.
- 문항의 정답·해설 내용에 근거하고, 문항에 없는 내용은 덧붙이지 마라.
- qid: 근거가 된 문항 번호 (예: "문제 3").
{term_rule}
형식: {{"cards": [{{"front": "", "back": "", "qid": "문제 1"}}]}}"""


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


def make_flashcards(markdown: str, term_rule: str = "", model: str = FLASH_MODEL) -> list[dict]:
    from llm import completion_kwargs, get_client

    items = _card_source(markdown)
    if not items:
        return []
    resp = get_client().chat.completions.create(
        messages=[{"role": "system", "content": _PROMPT.format(
                       term_rule=f"- 의학용어 표기: {term_rule}" if term_rule else "")},
                  {"role": "user", "content": json.dumps({"questions": items}, ensure_ascii=False)}],
        response_format={"type": "json_object"},
        **completion_kwargs(model, max_tokens=8000, temperature=0.3),
    )
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (resp.choices[0].message.content or "").strip())
    cards, seen = [], set()
    for c in json.loads(text).get("cards") or []:
        if not isinstance(c, dict):
            continue
        front, back = " ".join(str(c.get("front") or "").split()), str(c.get("back") or "").strip()
        key = re.sub(r"\W", "", front.lower())
        if not front or not back or key in seen:
            continue
        seen.add(key)
        cards.append(new_card(front, back, str(c.get("qid") or "")))
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
