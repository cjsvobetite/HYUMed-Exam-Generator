"""학습 공간 — 과목 노트북·단원·문항 세트·복습 세트 만들기.

  노트북(과목)  {id, name, emoji, units: [{id, name}], created_at}
  세트          {id, notebook_id, unit_id, kind: "exam"|"generated", title, n_questions, created_at, markdown}

세트를 풀면 풀이 기록에 set_id와 문항별 정오(detail)·🚩 문항 표시(flagged)가 남는다.
복습 세트를 풀면 sources({복습 문항 번호: [set_id, 원래 문항 번호]})로 원래 문항에 결과를 되돌려 적는다.
question_status()가 이 기록들을 모아 문항마다 "마지막에 틀렸나 / 한 번이라도 틀렸나 / 🚩" 를 계산한다.
"""
from __future__ import annotations

import json
import random
import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from store import get_store

KIND_LABEL = {"exam": "기출·문제지", "generated": "AI 생성"}
EMOJIS = ["🫀", "🧠", "🫁", "🦴", "🧬", "💊", "🦠", "🩸", "🧪", "🩺", "👁️", "🦷"]

# 복습 출처
SRC_WRONG = "wrong"          # 마지막으로 풀었을 때 틀린 문항
SRC_EVER_WRONG = "ever"      # 한 번이라도 틀린 문항
SRC_FLAGGED = "flagged"      # 🚩 문항 표시
SRC_UNSOLVED = "unsolved"    # 아직 안 푼 문항
SRC_EXAM = "exam"            # 기출·문제지 세트의 모든 문항
SRC_GENERATED = "generated"  # AI 생성 세트의 모든 문항
SOURCE_LABEL = {
    SRC_WRONG: "❌ 틀린 문항 (최근 풀이 기준)",
    SRC_EVER_WRONG: "⚠️ 한 번이라도 틀린 문항",
    SRC_FLAGGED: "🚩 표시한 문항",
    SRC_UNSOLVED: "🆕 아직 안 푼 문항",
    SRC_EXAM: "📄 기출·문제지 문항 전체",
    SRC_GENERATED: "✨ AI 생성 문항 전체",
}

_QHEAD_SUB = re.compile(r"\*\*(?:문제|Q|C)\s*\d+\.?\*\*")


def _id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─── 노트북·단원 ───

def notebooks(uid: str) -> list[dict]:
    return get_store().notebooks(uid)


def create_notebook(uid: str, name: str, emoji: str = "") -> dict:
    existing = notebooks(uid)
    nb = {"id": _id(), "name": name.strip(), "emoji": emoji or EMOJIS[len(existing) % len(EMOJIS)],
          "units": [], "created_at": _now()}
    get_store().save_notebook(uid, nb)
    return nb


def find_or_create_notebook(uid: str, name: str) -> dict:
    name = name.strip()
    for nb in notebooks(uid):
        if nb["name"].strip().lower() == name.lower():
            return nb
    return create_notebook(uid, name)


def add_unit(uid: str, nb: dict, name: str) -> dict:
    name = name.strip()
    for u in nb.get("units", []):
        if u["name"].strip().lower() == name.lower():
            return u
    unit = {"id": _id(), "name": name}
    nb.setdefault("units", []).append(unit)
    get_store().save_notebook(uid, nb)
    return unit


def rename_unit(uid: str, nb: dict, unit_id: str, name: str) -> None:
    for u in nb.get("units", []):
        if u["id"] == unit_id:
            u["name"] = name.strip()
    get_store().save_notebook(uid, nb)


def delete_unit(uid: str, nb: dict, unit_id: str) -> None:
    """단원을 지우면 그 단원의 세트는 '단원 미지정'으로 남긴다."""
    nb["units"] = [u for u in nb.get("units", []) if u["id"] != unit_id]
    get_store().save_notebook(uid, nb)
    for s in get_store().sets(uid, nb["id"], with_markdown=True):
        if s.get("unit_id") == unit_id:
            s["unit_id"] = None
            get_store().save_set(uid, s)


def unit_name(nb: dict, unit_id: str | None) -> str:
    for u in nb.get("units", []):
        if u["id"] == unit_id:
            return u["name"]
    return "단원 미지정"


# ─── 세트 ───

def save_set(uid: str, markdown: str, kind: str, title: str, notebook_id: str, unit_id: str | None) -> dict:
    from cbt import parse_cbt_questions
    st = {"id": _id(), "notebook_id": notebook_id, "unit_id": unit_id, "kind": kind, "title": title.strip(),
          "n_questions": len(parse_cbt_questions(markdown)), "created_at": _now(), "markdown": markdown}
    get_store().save_set(uid, st)
    return st


def move_set(uid: str, set_id: str, notebook_id: str, unit_id: str | None) -> None:
    st = get_store().get_set(uid, set_id)
    if st:
        st["notebook_id"], st["unit_id"] = notebook_id, unit_id
        get_store().save_set(uid, st)


def delete_set(uid: str, set_id: str) -> None:
    get_store().delete_set(uid, set_id)


# ─── 문항별 풀이 상태 ───

@dataclass
class QStatus:
    tries: int = 0
    last_correct: bool | None = None
    ever_wrong: bool = False
    flagged: bool = False


def question_status(uid: str) -> dict[tuple[str, str], QStatus]:
    """(set_id, 문항 번호) → 풀이 상태. 풀이 기록을 오래된 것부터 차례로 반영한다."""
    status: dict[tuple[str, str], QStatus] = {}
    for rec in get_store().attempts(uid):
        set_id = rec.get("set_id")
        sources = rec.get("sources") or {}
        if not set_id and not sources:
            continue

        def key(qid):
            if sources:
                src = sources.get(qid)
                return tuple(src) if src else None
            return (set_id, qid)

        detail = rec.get("detail") or {}
        for qid, ok in detail.items():
            k = key(qid)
            if not k:
                continue
            s = status.setdefault(k, QStatus())
            s.tries += 1
            s.last_correct = bool(ok)
            s.ever_wrong = s.ever_wrong or not ok
        for qid in rec.get("seen_ids") or []:
            k = key(qid)
            if k and qid not in detail:       # 주관식·정답 없는 문항: 풀이 횟수만
                status.setdefault(k, QStatus()).tries += 1
        for qid in rec.get("flagged_ids") or []:
            k = key(qid)
            if k:
                status.setdefault(k, QStatus()).flagged = True
        for qid in rec.get("unflagged_ids") or []:
            k = key(qid)
            if k and k in status:
                status[k].flagged = False
    return status


def notebook_stats(uid: str, nb: dict, status=None) -> dict:
    status = status if status is not None else question_status(uid)
    sets = get_store().sets(uid, nb["id"])
    ids = {s["id"] for s in sets}
    wrong = sum(1 for (sid, _), st in status.items() if sid in ids and st.last_correct is False)
    flagged = sum(1 for (sid, _), st in status.items() if sid in ids and st.flagged)
    return {"sets": len(sets), "questions": sum(s.get("n_questions", 0) for s in sets),
            "wrong": wrong, "flagged": flagged}


# ─── 복습 세트 ───

def build_review(uid: str, nb: dict, unit_ids: list | None, sources: list[str], limit: int,
                 shuffle: bool = True, seed: int | None = None) -> tuple[str, dict, int]:
    """조건에 맞는 문항을 모아 새 마크다운을 만든다.
    반환: (마크다운, {복습 문항 번호: [set_id, 원래 번호]}, 조건에 맞은 전체 문항 수)"""
    from quality import split_blocks

    status = question_status(uid)
    picked = []          # (set_id, qid, block)
    for s in get_store().sets(uid, nb["id"], with_markdown=True):
        if unit_ids is not None and s.get("unit_id") not in unit_ids:
            continue
        lines = s["markdown"].split("\n")
        for qid, (a, b) in split_blocks(s["markdown"]).items():
            st = status.get((s["id"], qid), QStatus())
            ok = (
                (SRC_WRONG in sources and st.last_correct is False)
                or (SRC_EVER_WRONG in sources and st.ever_wrong)
                or (SRC_FLAGGED in sources and st.flagged)
                or (SRC_UNSOLVED in sources and st.tries == 0)
                or (SRC_EXAM in sources and s.get("kind") == "exam")
                or (SRC_GENERATED in sources and s.get("kind") == "generated")
            )
            if ok:
                picked.append((s["id"], qid, "\n".join(lines[a:b + 1])))
    total = len(picked)
    if shuffle:
        random.Random(seed).shuffle(picked)
    picked = picked[:limit] if limit else picked

    blocks, mapping = [], {}
    for n, (set_id, qid, block) in enumerate(picked, 1):
        blocks.append(_QHEAD_SUB.sub(f"**문제 {n}.**", block, count=1))
        mapping[f"문제 {n}"] = [set_id, qid]
    return "\n\n".join(blocks), mapping, total


# ─── 자동 분류 ───

def suggest_classification(uid: str, markdown: str, model: str = "gpt-4o-mini") -> dict:
    """세트 내용과 기존 노트북·단원 목록을 보고 {"subject", "unit", "title"}을 추천한다."""
    from cbt import parse_cbt_questions
    from llm import completion_kwargs, get_client

    stems = [q["stem"].split("\n")[0][:120] for q in parse_cbt_questions(markdown)][:25]
    existing = [{"과목": nb["name"], "단원": [u["name"] for u in nb.get("units", [])]} for nb in notebooks(uid)]
    prompt = (
        "의과대학 시험 문항 세트를 학습 노트에 분류한다. 아래 문항 발문들을 보고 과목(subject)과 단원(unit)을 정하라.\n"
        "- 기존 과목·단원 중 맞는 것이 있으면 그 이름을 글자 그대로 쓰고, 없으면 새 이름을 짧게 지어라 "
        "(과목 예: 발생학, 생리학, 병리학 / 단원 예: 근골격계 발생).\n"
        "- title: 이 세트를 알아보기 쉬운 짧은 제목.\n"
        '형식(JSON): {"subject": "", "unit": "", "title": ""}\n\n'
        f"기존 노트: {json.dumps(existing, ensure_ascii=False)}\n\n발문:\n" + "\n".join(f"- {s}" for s in stems)
    )
    resp = get_client().chat.completions.create(
        messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"},
        **completion_kwargs(model, max_tokens=300, temperature=0),
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    return {k: str(data.get(k) or "").strip() for k in ("subject", "unit", "title")}
