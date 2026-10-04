"""학습 공간 — 과목 노트북·단원·문항 세트·복습 세트 만들기.

  노트북(과목)  {id, name, emoji, units: [{id, name}], created_at}
  세트          {id, notebook_id, unit_id, kind: "exam"|"generated"|"flashcards", title, n_questions, created_at, markdown}
                플래시카드 덱(kind="flashcards")은 markdown 칸에 카드 JSON을 넣는다 (flashcards.py).

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

import srs
from store import get_store

KIND_LABEL = {"exam": "기출·문제지", "generated": "AI 생성", "flashcards": "🃏 플래시카드"}
FLASH = "flashcards"
EMOJIS = ["🫀", "🧠", "🫁", "🦴", "🧬", "💊", "🦠", "🩸", "🧪", "🩺", "👁️", "🦷"]

# 복습 출처
SRC_WRONG = "wrong"          # 마지막으로 풀었을 때 틀린 문항
SRC_EVER_WRONG = "ever"      # 한 번이라도 틀린 문항
SRC_FLAGGED = "flagged"      # 🚩 문항 표시
SRC_UNSOLVED = "unsolved"    # 아직 안 푼 문항
SRC_EXAM = "exam"            # 기출·문제지 세트의 모든 문항
SRC_GENERATED = "generated"  # AI 생성 세트의 모든 문항
SRC_DUE = "due"              # 간격 반복: 오늘 복습할 차례가 된 문항
SOURCE_LABEL = {
    SRC_DUE: "📅 오늘 복습할 문항 (간격 반복)",
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


def save_deck(uid: str, cards: list[dict], title: str, notebook_id: str, unit_id: str | None,
              source_set_id: str | None = None) -> dict:
    import flashcards
    st = {"id": _id(), "notebook_id": notebook_id, "unit_id": unit_id, "kind": FLASH, "title": title.strip(),
          "n_questions": len(cards), "created_at": _now(), "source_set_id": source_set_id,
          "markdown": flashcards.dumps(cards)}
    get_store().save_set(uid, st)
    return st


def deck_cards(uid: str, deck_id: str) -> list[dict]:
    import flashcards
    st = get_store().get_set(uid, deck_id)
    return flashcards.loads(st["markdown"]) if st and st.get("kind") == FLASH else []


def rate_card(uid: str, deck_id: str, card_id: str, known: bool) -> None:
    """플래시카드 '알아요/몰라요' 결과를 덱에 기록한다."""
    import flashcards
    st = get_store().get_set(uid, deck_id)
    if not st or st.get("kind") != FLASH:
        return
    cards = flashcards.loads(st["markdown"])
    for c in cards:
        if c["id"] == card_id:
            srs.rate(c, known)
    st["markdown"] = flashcards.dumps(cards)
    get_store().save_set(uid, st)


def update_deck_cards(uid: str, deck_id: str, rows: list[dict]) -> int:
    """편집한 카드 목록으로 덱을 바꾼다. rows: [{id?, front, back}] — id가 같은 카드는 학습 기록을 그대로 둔다."""
    import flashcards
    st = get_store().get_set(uid, deck_id)
    if not st or st.get("kind") != FLASH:
        return 0
    old = {c["id"]: c for c in flashcards.loads(st["markdown"])}
    cards = []
    text = lambda v: v.strip() if isinstance(v, str) else ""      # 표 편집기의 빈 칸은 None/NaN으로 온다
    for r in rows:
        front, back = text(r.get("front")), text(r.get("back"))
        if not front or not back:
            continue
        c = old.get(text(r.get("id")))
        if c:
            c = dict(c, front=front, back=back)
        else:
            c = flashcards.new_card(front, back)
        cards.append(c)
    st["markdown"], st["n_questions"] = flashcards.dumps(cards), len(cards)
    get_store().save_set(uid, st)
    return len(cards)


def question_block(markdown: str, qid: str) -> str:
    from quality import split_blocks
    span = split_blocks(markdown).get(qid)
    if not span:
        return ""
    return "\n".join(markdown.split("\n")[span[0]:span[1] + 1])


def update_question(uid: str, set_id: str, qid: str, block: str | None) -> str | None:
    """세트의 문항 하나를 고친다 (block=None이면 삭제). 성공하면 None, 실패하면 오류 메시지.
    문항 번호는 바꾸지 않는다 — 풀이 기록이 번호로 이어져 있다."""
    from cbt import parse_cbt_questions
    from quality import split_blocks

    st = get_store().get_set(uid, set_id)
    if not st or st.get("kind") == FLASH:
        return "세트를 찾을 수 없습니다."
    span = split_blocks(st["markdown"]).get(qid)
    if not span:
        return f"{qid}을(를) 찾을 수 없습니다."
    lines = st["markdown"].split("\n")
    if block is not None:
        head = _QHEAD_SUB.search("\n".join(lines[span[0]:span[1] + 1]))
        block = _QHEAD_SUB.sub(lambda _: head.group(0), block.strip(), count=1) if head else block.strip()
        parsed = parse_cbt_questions(block)
        if len(parsed) != 1:
            return "문항 형식이 깨졌습니다. <details>·<summary>**문제 N.** 줄과 정답 확인 블록을 그대로 두세요."
    lines[span[0]:span[1] + 1] = block.split("\n") if block is not None else []
    st["markdown"] = "\n".join(lines).strip() + "\n"
    st["n_questions"] = len(parse_cbt_questions(st["markdown"]))
    if block is None and st.get("q_units"):
        st["q_units"].pop(qid, None)
    get_store().save_set(uid, st)
    return None


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
    streak: int = 0              # 연속으로 맞힌 횟수 (틀리면 0)
    last_day: str = ""           # 마지막으로 채점된 날 "YYYY-MM-DD"

    @property
    def due(self):
        return srs.question_due_date(self.streak, self.last_correct, srs.to_date(self.last_day))

    def is_due(self, on=None) -> bool:
        d = self.due
        return d is not None and d <= (on or srs.today())


def question_status(uid: str) -> dict[tuple[str, str], QStatus]:
    """(set_id, 문항 번호) → 풀이 상태. 풀이 기록을 오래된 것부터 차례로 반영한다."""
    status: dict[tuple[str, str], QStatus] = {}
    for rec in get_store().attempts(uid, with_text=False):
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
            s.streak = s.streak + 1 if ok else 0
            s.last_day = (rec.get("ts") or "")[:10]
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
    all_sets = get_store().sets(uid, nb["id"])
    sets = [s for s in all_sets if s.get("kind") != FLASH]
    decks = [s for s in all_sets if s.get("kind") == FLASH]
    ids = {s["id"] for s in sets}
    wrong = sum(1 for (sid, _), st in status.items() if sid in ids and st.last_correct is False)
    flagged = sum(1 for (sid, _), st in status.items() if sid in ids and st.flagged)
    return {"sets": len(sets), "questions": sum(s.get("n_questions", 0) for s in sets),
            "wrong": wrong, "flagged": flagged,
            "decks": len(decks), "cards": sum(s.get("n_questions", 0) for s in decks)}


# ─── 문항별 단원 ───

def question_unit(st: dict, qid: str) -> str | None:
    """문항별로 분류해 두었으면 그 단원, 아니면 세트의 단원."""
    q_units = st.get("q_units") or {}
    return q_units[qid] if qid in q_units else st.get("unit_id")


def unit_question_counts(st: dict) -> dict:
    """{unit_id: 문항 수} — 문항별 분류(q_units)가 있으면 그것을 따른다."""
    q_units = st.get("q_units") or {}
    out: dict = {}
    for unit_id in q_units.values():
        out[unit_id] = out.get(unit_id, 0) + 1
    rest = st.get("n_questions", 0) - len(q_units)
    if rest > 0:
        out[st.get("unit_id")] = out.get(st.get("unit_id"), 0) + rest
    return out


def classify_questions(uid: str, nb: dict, set_id: str, model: str = "gpt-4o-mini") -> dict:
    """세트의 문항마다 노트북 단원을 정한다 (없는 단원은 새로 만든다). 반환: {qid: unit_id}"""
    from cbt import parse_cbt_questions
    from llm import completion_kwargs, get_client

    st = get_store().get_set(uid, set_id)
    qs = parse_cbt_questions(st["markdown"]) if st else []
    if not qs:
        return {}
    units = [u["name"] for u in nb.get("units", [])]
    prompt = (
        f"의과대학 '{nb['name']}' 과목 문항을 단원별로 나눈다. 문항마다 단원 이름 하나를 정하라.\n"
        "- 기존 단원 중 맞는 것이 있으면 글자 그대로 쓰고, 없으면 새 단원 이름을 짧게 지어라 (교과서 장 제목 수준).\n"
        "- 비슷한 문항은 같은 단원으로 묶고, 단원을 지나치게 잘게 쪼개지 마라.\n"
        '형식(JSON): {"units": {"문제 1": "단원 이름", ...}}\n\n'
        f"기존 단원: {json.dumps(units, ensure_ascii=False)}\n\n문항:\n"
        + "\n".join(f"- {q['id']}: {q['stem'][:160]}" for q in qs)
    )
    resp = get_client().chat.completions.create(
        messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"},
        **completion_kwargs(model, max_tokens=4000, temperature=0),
    )
    names = json.loads(resp.choices[0].message.content or "{}").get("units") or {}
    q_units = {}
    for q in qs:
        name = str(names.get(q["id"]) or "").strip()
        if name:
            q_units[q["id"]] = add_unit(uid, nb, name)["id"]
    st = get_store().get_set(uid, set_id)
    st["q_units"] = q_units
    get_store().save_set(uid, st)
    return q_units


# ─── 복습 세트 ───

def _blocks(st: dict):
    from quality import split_blocks
    lines = st["markdown"].split("\n")
    for qid, (a, b) in split_blocks(st["markdown"]).items():
        yield qid, "\n".join(lines[a:b + 1])


def _compose(picked) -> tuple[str, dict]:
    """[(set_id, qid, block)] → 문항 번호를 1부터 다시 매긴 마크다운과 {새 번호: [set_id, 원래 번호]}"""
    blocks, mapping = [], {}
    for n, (set_id, qid, block) in enumerate(picked, 1):
        blocks.append(_QHEAD_SUB.sub(f"**문제 {n}.**", block, count=1))
        mapping[f"문제 {n}"] = [set_id, qid]
    return "\n\n".join(blocks), mapping


def build_review(uid: str, nb: dict | None, unit_ids: list | None, sources: list[str], limit: int,
                 shuffle: bool = True, seed: int | None = None, only: set | None = None) -> tuple[str, dict, int]:
    """조건에 맞는 문항을 모아 새 마크다운을 만든다. nb=None이면 모든 노트북에서 모은다.
    only: {(set_id, 문항 번호)} — 주면 그 문항만 (검색 결과로 복습).
    반환: (마크다운, {복습 문항 번호: [set_id, 원래 번호]}, 조건에 맞은 전체 문항 수)"""
    status = question_status(uid)
    today = srs.today()
    picked = []          # (set_id, qid, block)
    for s in get_store().sets(uid, nb["id"] if nb else None, with_markdown=True):
        if s.get("kind") == FLASH:
            continue
        for qid, block in _blocks(s):
            if unit_ids is not None and question_unit(s, qid) not in unit_ids:
                continue
            if only is not None:
                if (s["id"], qid) in only:
                    picked.append((s["id"], qid, block))
                continue
            st = status.get((s["id"], qid), QStatus())
            ok = (
                (SRC_DUE in sources and st.is_due(today))
                or (SRC_WRONG in sources and st.last_correct is False)
                or (SRC_EVER_WRONG in sources and st.ever_wrong)
                or (SRC_FLAGGED in sources and st.flagged)
                or (SRC_UNSOLVED in sources and st.tries == 0)
                or (SRC_EXAM in sources and s.get("kind") == "exam")
                or (SRC_GENERATED in sources and s.get("kind") == "generated")
            )
            if ok:
                picked.append((s["id"], qid, block))
    total = len(picked)
    if shuffle:
        random.Random(seed).shuffle(picked)
    picked = picked[:limit] if limit else picked
    md, mapping = _compose(picked)
    return md, mapping, total


def compose_from_sources(uid: str, sources: dict) -> str:
    """복습 풀이 기록({복습 번호: [set_id, 원래 번호]})의 문항을 저장된 세트에서 다시 모은다."""
    cache: dict = {}
    picked = []
    for new_qid in sorted(sources, key=lambda q: int(re.sub(r"\D", "", q) or 0)):
        set_id, qid = sources[new_qid]
        if set_id not in cache:
            st = get_store().get_set(uid, set_id)
            cache[set_id] = dict(_blocks(st)) if st else {}
        block = cache[set_id].get(qid)
        if not block:           # 지워진 문항이 있으면 번호가 기록과 어긋나므로 다시 만들지 않는다
            return ""
        picked.append((set_id, qid, block))
    return _compose(picked)[0]


def attempt_markdown(uid: str, rec: dict) -> str:
    """풀이 기록의 문항 마크다운. 세트에 저장된 문항은 기록에 원문을 따로 남기지 않으므로 세트에서 읽는다."""
    if rec.get("full_text"):
        return rec["full_text"]
    if rec.get("set_id"):
        st = get_store().get_set(uid, rec["set_id"])
        return st["markdown"] if st and st.get("kind") != FLASH else ""
    if rec.get("sources"):
        return compose_from_sources(uid, rec["sources"])
    return ""


# ─── 오늘 복습할 것 ───

def due_cards(uid: str, nb: dict | None = None) -> tuple[list, int]:
    """복습일이 된 카드 [(deck_id, card)]와 아직 안 본 카드 수."""
    import flashcards
    pool, new = [], 0
    today = srs.today()
    for d in get_store().sets(uid, nb["id"] if nb else None, with_markdown=True):
        if d.get("kind") != FLASH:
            continue
        for c in flashcards.loads(d["markdown"]):
            if srs.card_due(c, today):
                pool.append((d["id"], c))
            elif not c.get("reviews"):
                new += 1
    return pool, new


def due_question_count(uid: str, status=None) -> int:
    status = status if status is not None else question_status(uid)
    alive = {s["id"] for s in get_store().sets(uid) if s.get("kind") != FLASH}
    today = srs.today()
    return sum(1 for (sid, _), q in status.items() if sid in alive and q.is_due(today))


# ─── 검색 ───

def search(uid: str, nb: dict | None, query: str, limit: int = 200) -> tuple[list, list]:
    """발문·선지·해설과 카드 앞뒷면에서 찾는다. 공백으로 나눈 낱말이 모두 들어 있어야 한다.
    반환: ([{set_id, qid, title, stem, unit_id}], [(deck_id, deck_title, card)])"""
    from cbt import parse_cbt_questions
    import flashcards

    words = [w.lower() for w in query.split() if w.strip()]
    if not words:
        return [], []
    hit = lambda text: all(w in text.lower() for w in words)
    questions, cards = [], []
    for s in get_store().sets(uid, nb["id"] if nb else None, with_markdown=True):
        if s.get("kind") == FLASH:
            for c in flashcards.loads(s["markdown"]):
                if hit(f"{c['front']}\n{c['back']}"):
                    cards.append((s["id"], s["title"], c))
            continue
        for q in parse_cbt_questions(s["markdown"]):
            text = "\n".join([q["stem"], *q["choices"], q["explanation"]])
            if hit(text):
                questions.append({"set_id": s["id"], "qid": q["id"], "title": s["title"], "stem": q["stem"],
                                  "unit_id": question_unit(s, q["id"])})
    return questions[:limit], cards[:limit]


# ─── 공유 ───

_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"     # 헷갈리는 0/O, 1/I 제외


def can_share(st: dict) -> bool:
    """직접 만든 문항·카드만 공유한다 (기출·문제지 세트, 남에게 받은 세트는 제외)."""
    return st.get("kind") in ("generated", FLASH) and not st.get("shared_from")


def share_set(uid: str, set_id: str) -> str | None:
    """세트를 복사해 공유 코드를 만든다. 공유 이후의 편집·학습 기록은 따라가지 않는다."""
    import flashcards
    st = get_store().get_set(uid, set_id)
    if not st or not can_share(st):
        return None
    markdown = st["markdown"]
    if st.get("kind") == FLASH:      # 내 학습 기록은 빼고 보낸다
        markdown = flashcards.dumps([flashcards.new_card(c["front"], c["back"], c.get("qid", ""))
                                     for c in flashcards.loads(markdown)])
    data = {"kind": st["kind"], "title": st["title"], "n_questions": st.get("n_questions", 0),
            "markdown": markdown, "owner": uid, "created_at": _now()}
    for _ in range(10):
        code = "".join(random.SystemRandom().choice(_CODE_CHARS) for _ in range(8))
        if get_store().put_share(code, uid, data):
            return code
    return None


def get_share(code: str) -> dict | None:
    code = re.sub(r"[^A-Z0-9]", "", (code or "").upper())
    return get_store().get_share(code) if len(code) == 8 else None


def import_share(uid: str, code: str, notebook_id: str, unit_id: str | None) -> dict | None:
    data = get_share(code)
    if not data:
        return None
    st = {"id": _id(), "notebook_id": notebook_id, "unit_id": unit_id, "kind": data["kind"],
          "title": data["title"], "n_questions": data.get("n_questions", 0), "created_at": _now(),
          "markdown": data["markdown"], "shared_from": data.get("owner", ""),
          "share_code": re.sub(r"[^A-Z0-9]", "", code.upper())}
    get_store().save_set(uid, st)
    return st


# ─── 통계 ───

def attempt_rows(uid: str) -> list[dict]:
    """풀이 기록 요약 (오래된 것부터): [{ts, day, title, total, correct, pct}]"""
    return [{"ts": r.get("ts", ""), "day": (r.get("ts") or "")[:10], "title": r.get("title") or "",
             "total": r.get("total", 0), "correct": r.get("correct", 0), "pct": r.get("pct", 0)}
            for r in get_store().attempts(uid, with_text=False)]


def study_streak(days: set[str], on=None) -> int:
    """오늘(또는 어제)까지 연속으로 공부한 날 수."""
    from datetime import timedelta
    d = on or srs.today()
    if d.isoformat() not in days:
        d -= timedelta(days=1)
    n = 0
    while d.isoformat() in days:
        n += 1
        d -= timedelta(days=1)
    return n


def unit_accuracy(uid: str, status=None) -> list[dict]:
    """단원별 정답률 (풀어 본 문항 기준): [{notebook, unit, solved, correct, wrong, pct, nb_id, unit_id}]"""
    status = status if status is not None else question_status(uid)
    nbs = {nb["id"]: nb for nb in notebooks(uid)}
    sets = {s["id"]: s for s in get_store().sets(uid) if s.get("kind") != FLASH}
    agg: dict = {}
    for (sid, qid), q in status.items():
        s = sets.get(sid)
        if not s or q.last_correct is None or s.get("notebook_id") not in nbs:
            continue
        key = (s["notebook_id"], question_unit(s, qid))
        a = agg.setdefault(key, [0, 0])
        a[0] += 1
        a[1] += bool(q.last_correct)
    rows = []
    for (nb_id, unit_id), (solved, correct) in agg.items():
        nb = nbs[nb_id]
        rows.append({"notebook": f"{nb['emoji']} {nb['name']}", "unit": unit_name(nb, unit_id),
                     "solved": solved, "correct": correct, "wrong": solved - correct,
                     "pct": round(correct / solved * 100), "nb_id": nb_id, "unit_id": unit_id})
    return sorted(rows, key=lambda r: (r["pct"], -r["solved"]))


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
