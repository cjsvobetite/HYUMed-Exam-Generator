import json
import types

import flashcards
import workspace as ws
from tests.test_quality import q_block
from tests.test_workspace import _set_md, _uid, store  # noqa: F401  (fixture 재사용)

MD = (q_block(1, "위성세포가 발현하는 전사인자는?", ["Pax7", "MyoD", "Sox9"], answer="①", expl="위성세포는 Pax7 양성")
      + q_block(2, "근섬유 융합 단계에서 발현하는 인자는?", answer="Myogenin", expl="말단 분화"))


def _client(cards):
    seen = {}

    class C:
        @staticmethod
        def create(messages, **kw):
            seen["system"], seen["user"], seen["kw"] = messages[0]["content"], messages[1]["content"], kw
            msg = types.SimpleNamespace(content=json.dumps({"cards": cards}, ensure_ascii=False))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=C)), seen


def test_make_flashcards(monkeypatch):
    client, seen = _client([
        {"front": "성체 골격근 줄기세포가 발현하는 전사인자?", "back": "Pax7 — 위성세포 표지", "qid": "문제 1"},
        {"front": "성체 골격근  줄기세포가 발현하는 전사인자?", "back": "중복", "qid": "문제 1"},
        {"front": "", "back": "앞면 없음"},
        {"front": "myoblast 융합·말단 분화 인자?", "back": "Myogenin", "qid": "문제 2"},
    ])
    monkeypatch.setattr("llm.get_client", lambda: client)
    cards = flashcards.make_flashcards(MD, term_rule="영어로")
    assert [c["back"] for c in cards] == ["Pax7 — 위성세포 표지", "Myogenin"]
    assert all(c["known"] is None and c["reviews"] == 0 and c["id"] for c in cards)
    payload = json.loads(seen["user"])["questions"]
    assert payload[0]["answer"] == [1] and payload[1]["answer"] == "Myogenin"
    assert "영어로" in seen["system"] and seen["kw"]["response_format"] == {"type": "json_object"}
    assert flashcards.loads(flashcards.dumps(cards)) == cards
    assert flashcards.loads("not json") == []


def test_deck_save_rate_and_stats(store):  # noqa: F811
    uid = _uid()
    nb = ws.create_notebook(uid, "발생학")
    unit = ws.add_unit(uid, nb, "근육")
    qs = ws.save_set(uid, _set_md("근육"), "generated", "근육 세트", nb["id"], unit["id"])
    cards = [flashcards.new_card("앞1", "뒤1", "문제 1"), flashcards.new_card("앞2", "뒤2", "문제 2")]
    deck = ws.save_deck(uid, cards, "근육 세트 · 플래시카드", nb["id"], unit["id"], source_set_id=qs["id"])
    assert deck["n_questions"] == 2 and deck["kind"] == ws.FLASH and deck["source_set_id"] == qs["id"]

    ws.rate_card(uid, deck["id"], cards[0]["id"], False)
    ws.rate_card(uid, deck["id"], cards[0]["id"], True)
    ws.rate_card(uid, deck["id"], cards[1]["id"], False)
    got = {c["id"]: c for c in ws.deck_cards(uid, deck["id"])}
    assert got[cards[0]["id"]]["known"] is True and got[cards[0]["id"]]["reviews"] == 2
    assert got[cards[1]["id"]]["known"] is False

    s = ws.notebook_stats(uid, nb)
    assert s["sets"] == 1 and s["questions"] == 3 and s["decks"] == 1 and s["cards"] == 2
    _, mapping, total = ws.build_review(uid, nb, None, [ws.SRC_UNSOLVED], 0)
    assert total == 3 and all(v[0] == qs["id"] for v in mapping.values())     # 덱은 문항 복습에 안 섞임
    assert ws.deck_cards(uid, qs["id"]) == []                                  # 문항 세트는 카드 아님
