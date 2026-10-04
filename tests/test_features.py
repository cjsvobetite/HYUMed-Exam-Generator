"""간격 반복 · 문항/카드 편집 · 검색 · 공유 · Anki · 문항별 단원 · 기록 용량 줄이기."""
import json
import types
from datetime import date, timedelta

import flashcards
import srs
import workspace as ws
from cbt import parse_cbt_questions
from history import load_history
from tests.test_quality import q_block
from tests.test_workspace import _set_md, _solve, _uid, store  # noqa: F401  (fixture 재사용)

D0 = date(2026, 3, 2)


def test_card_spaced_repetition():
    c = flashcards.new_card("앞", "뒤")
    assert not srs.card_due(c, D0)                                  # 안 본 카드는 '복습'이 아님
    srs.rate(c, True, D0)
    assert c["box"] == 1 and c["due"] == "2026-03-03" and c["reviews"] == 1
    assert not srs.card_due(c, D0) and srs.card_due(c, D0 + timedelta(days=1))
    srs.rate(c, True, D0 + timedelta(days=1))
    assert c["box"] == 2 and c["due"] == "2026-03-05"
    srs.rate(c, False, D0 + timedelta(days=3))
    assert c["box"] == 0 and c["due"] == "2026-03-05" and c["known"] is False
    assert srs.card_due(c, D0 + timedelta(days=3))
    old = {"front": "a", "back": "b", "known": False, "reviews": 1}  # 예전 기록 (due 없음)
    assert srs.card_due(old, D0)


def test_question_due_dates():
    assert srs.question_due_date(0, None, D0) is None
    assert srs.question_due_date(0, False, D0) == D0
    assert srs.question_due_date(1, True, D0) == D0 + timedelta(days=1)
    assert srs.question_due_date(3, True, D0) == D0 + timedelta(days=7)
    assert srs.question_due_date(99, True, D0) == D0 + timedelta(days=120)


def test_due_questions_and_cards(store, monkeypatch):
    uid = _uid()
    nb = ws.create_notebook(uid, "생리학")
    s1 = ws.save_set(uid, _set_md("심장"), "generated", "심장", nb["id"], None)
    _solve(uid, s1["markdown"], [0, 1, 0], set_id=s1["id"])        # 1 맞음, 2 틀림, 3 맞음
    status = ws.question_status(uid)
    assert status[(s1["id"], "문제 1")].streak == 1 and status[(s1["id"], "문제 2")].streak == 0
    assert ws.due_question_count(uid, status) == 1                 # 틀린 문항은 오늘 바로
    md, mapping, total = ws.build_review(uid, None, None, [ws.SRC_DUE], 0)   # 모든 노트북에서
    assert total == 1 and list(mapping.values()) == [[s1["id"], "문제 2"]]

    tomorrow = srs.today() + timedelta(days=1)
    monkeypatch.setattr(srs, "today", lambda: tomorrow)
    assert ws.due_question_count(uid) == 3                         # 맞힌 문항도 하루 뒤에 복습

    cards = [flashcards.new_card("앞1", "뒤1"), flashcards.new_card("앞2", "뒤2")]
    deck = ws.save_deck(uid, cards, "덱", nb["id"], None)
    ws.rate_card(uid, deck["id"], cards[0]["id"], False)
    pool, new = ws.due_cards(uid)
    assert [c["front"] for _, c in pool] == ["앞1"] and new == 1


def test_attempts_on_saved_sets_skip_full_text(store):
    uid = _uid()
    nb = ws.create_notebook(uid, "발생학")
    s1 = ws.save_set(uid, _set_md("근육"), "exam", "족보", nb["id"], None)
    _solve(uid, s1["markdown"], [0, 1, 2], set_id=s1["id"])
    rec = load_history(uid)[0]
    assert "full_text" not in rec and ws.attempt_markdown(uid, rec) == s1["markdown"]

    md, mapping, _ = ws.build_review(uid, nb, None, [ws.SRC_WRONG], 0, shuffle=False)
    _solve(uid, md, [3, 3], sources=mapping)
    rec = load_history(uid)[0]
    assert "full_text" not in rec and ws.attempt_markdown(uid, rec) == md

    loose = _set_md("자유", 1)                                       # 세트에 없는 문항은 원문을 남긴다
    _solve(uid, loose, [0])
    assert load_history(uid)[0]["full_text"] == loose
    assert store.attempts(uid, with_text=False)[-1].get("full_text") is None

    ws.update_question(uid, s1["id"], "문제 2", None)              # 문항을 지우면 복습 기록은 다시 못 만든다
    assert ws.attempt_markdown(uid, load_history(uid)[1]) == ""


def test_edit_questions_keeps_numbers(store):
    uid = _uid()
    nb = ws.create_notebook(uid, "병리학")
    s1 = ws.save_set(uid, _set_md("염증"), "generated", "염증", nb["id"], None)
    block = ws.question_block(s1["markdown"], "문제 2")
    fixed = block.replace("염증 문항 2?", "급성 염증의 첫 세포는?").replace("**문제 2.**", "**문제 9.**")
    assert ws.update_question(uid, s1["id"], "문제 2", fixed) is None
    qs = parse_cbt_questions(store.get_set(uid, s1["id"])["markdown"])
    assert [q["id"] for q in qs] == ["문제 1", "문제 2", "문제 3"]   # 번호는 그대로
    assert qs[1]["stem"] == "급성 염증의 첫 세포는?"
    assert ws.update_question(uid, s1["id"], "문제 2", "그냥 글자") is not None
    assert ws.update_question(uid, s1["id"], "문제 1", None) is None
    got = store.get_set(uid, s1["id"])
    assert got["n_questions"] == 2 and [q["id"] for q in parse_cbt_questions(got["markdown"])] == ["문제 2", "문제 3"]


def test_edit_deck_keeps_progress(store):
    uid = _uid()
    nb = ws.create_notebook(uid, "약리학")
    cards = [flashcards.new_card("앞1", "뒤1"), flashcards.new_card("앞2", "뒤2")]
    deck = ws.save_deck(uid, cards, "덱", nb["id"], None)
    ws.rate_card(uid, deck["id"], cards[0]["id"], True)
    n = ws.update_deck_cards(uid, deck["id"], [
        {"id": cards[0]["id"], "front": "앞1 고침", "back": "뒤1"},
        {"id": float("nan"), "front": "새 카드", "back": "새 뒤"},     # 표 편집기에서 새로 추가한 줄
        {"id": None, "front": "", "back": "앞면 없음"},
    ])
    got = ws.deck_cards(uid, deck["id"])
    assert n == 2 and [c["front"] for c in got] == ["앞1 고침", "새 카드"]
    assert got[0]["box"] == 1 and got[0]["id"] == cards[0]["id"] and got[1]["reviews"] == 0
    assert store.get_set(uid, deck["id"])["n_questions"] == 2


def test_search(store):
    uid = _uid()
    nb = ws.create_notebook(uid, "발생학")
    md = _set_md("근육", 2) + q_block(3, "신경관 결손을 예방하는 비타민은?", ["엽산", "비타민 C"], expl="임신 전 엽산 복용")
    s1 = ws.save_set(uid, md, "generated", "세트", nb["id"], None)
    ws.save_deck(uid, [flashcards.new_card("신경관이 닫히는 시기?", "4주")], "덱", nb["id"], None)
    qs, cards = ws.search(uid, nb, "신경관")
    assert [(h["set_id"], h["qid"]) for h in qs] == [(s1["id"], "문제 3")] and len(cards) == 1
    assert ws.search(uid, nb, "엽산 임신")[0] and not ws.search(uid, nb, "엽산 근육")[0]
    md2, mapping, _ = ws.build_review(uid, nb, None, [], 0, shuffle=False, only={(s1["id"], "문제 3")})
    assert list(mapping.values()) == [[s1["id"], "문제 3"]] and "신경관" in md2


def test_share_only_own_sets(store):
    a, b = _uid(), _uid()
    nb_a = ws.create_notebook(a, "생리학")
    gen = ws.save_set(a, _set_md("심장"), "generated", "내가 만든 세트", nb_a["id"], None)
    exam = ws.save_set(a, _set_md("족보"), "exam", "족보", nb_a["id"], None)
    cards = [flashcards.new_card("앞", "뒤")]
    deck = ws.save_deck(a, cards, "덱", nb_a["id"], None)
    ws.rate_card(a, deck["id"], cards[0]["id"], True)

    assert ws.share_set(a, exam["id"]) is None                       # 기출은 공유 안 됨
    assert ws.share_set(b, gen["id"]) is None                        # 남의 세트는 공유 못 함
    code = ws.share_set(a, gen["id"])
    assert code and len(code) == 8 and ws.get_share(code.lower())["title"] == "내가 만든 세트"

    nb_b = ws.create_notebook(b, "생리학")
    got = ws.import_share(b, code, nb_b["id"], None)
    assert got["markdown"] == gen["markdown"] and got["shared_from"] == a
    assert not ws.can_share(got)                                     # 받은 세트는 다시 공유 안 됨
    assert ws.import_share(b, "ZZZZZZZZ", nb_b["id"], None) is None

    dcode = ws.share_set(a, deck["id"])
    shared_cards = flashcards.loads(ws.get_share(dcode)["markdown"])
    assert shared_cards[0]["front"] == "앞" and shared_cards[0]["reviews"] == 0   # 내 학습 기록은 빠짐


def test_per_question_units(store, monkeypatch):
    uid = _uid()
    nb = ws.create_notebook(uid, "발생학")
    bone = ws.add_unit(uid, nb, "뼈")
    s1 = ws.save_set(uid, _set_md("혼합"), "generated", "혼합", nb["id"], bone["id"])

    class C:
        @staticmethod
        def create(messages, **kw):
            seen.append(messages[0]["content"])
            out = {"units": {"문제 1": "뼈", "문제 2": "근육", "문제 3": "근육"}}
            msg = types.SimpleNamespace(content=json.dumps(out, ensure_ascii=False))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    seen = []
    monkeypatch.setattr("llm.get_client", lambda: types.SimpleNamespace(chat=types.SimpleNamespace(completions=C)))
    q_units = ws.classify_questions(uid, nb, s1["id"])
    nb = store.notebooks(uid)[0]
    muscle = next(u for u in nb["units"] if u["name"] == "근육")
    assert q_units == {"문제 1": bone["id"], "문제 2": muscle["id"], "문제 3": muscle["id"]}
    assert "혼합 문항 2?" in seen[0] and "뼈" in seen[0]
    full = store.get_set(uid, s1["id"])
    assert ws.unit_question_counts(full) == {bone["id"]: 1, muscle["id"]: 2}
    _, mapping, total = ws.build_review(uid, nb, [muscle["id"]], [ws.SRC_GENERATED], 0, shuffle=False)
    assert total == 2 and [v[1] for v in mapping.values()] == ["문제 2", "문제 3"]

    _solve(uid, full["markdown"], [0, 1, 1], set_id=s1["id"])
    acc = {r["unit"]: r for r in ws.unit_accuracy(uid)}
    assert acc["뼈"]["pct"] == 100 and acc["근육"]["pct"] == 0 and acc["근육"]["solved"] == 2


def test_anki_export():
    cards = [flashcards.new_card("Pax7\t표지?", "위성세포\n<줄기세포>")]
    out = flashcards.cards_to_anki(cards, "발생 학")
    lines = out.strip().split("\n")
    assert lines[:3] == ["#separator:tab", "#html:true", "#tags column:3"]
    assert lines[3] == "Pax7 표지?\t위성세포<br>&lt;줄기세포&gt;\t발생_학"
    q = flashcards.questions_to_anki(q_block(1, "위성세포 표지는?", ["Pax7", "MyoD"], answer="①", expl="Pax7 양성"))
    front, back = q.strip().split("\n")[-1].split("\t")
    assert front == "위성세포 표지는?<br>(1) Pax7<br>(2) MyoD" and back.startswith("정답: (1) Pax7<br><br>")


def test_study_streak():
    days = {"2026-03-01", "2026-03-02", "2026-03-04"}
    assert ws.study_streak(days, date(2026, 3, 2)) == 2
    assert ws.study_streak(days, date(2026, 3, 3)) == 2             # 오늘 아직 안 했으면 어제까지
    assert ws.study_streak(days, date(2026, 3, 6)) == 0
