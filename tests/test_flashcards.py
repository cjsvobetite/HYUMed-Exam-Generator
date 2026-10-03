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


def test_request_with_material_is_chunked_and_merged(monkeypatch):
    calls = []

    class C:
        @staticmethod
        def create(messages, **kw):
            system, user = messages[0]["content"], messages[1]["content"]
            calls.append((system, user))
            if "강의 자료 (1/" in user:
                cards = [{"front": "Myotome", "back": "근육이 되는 체절 부분"},
                         {"front": "Sclerotome", "back": "뼈·연골이 되는 부분"}]
            elif "강의 자료 (2/" in user:
                cards = [{"front": "sclerotome", "back": "중복"}, {"front": "Dermatome", "back": "진피가 되는 부분"}]
            else:
                cards = [{"front": "Pax7", "back": "위성세포 표지", "qid": "문제 1"}]
            msg = types.SimpleNamespace(content=json.dumps({"cards": cards}, ensure_ascii=False))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setattr("llm.get_client", lambda: types.SimpleNamespace(chat=types.SimpleNamespace(completions=C)))
    monkeypatch.setattr(flashcards, "_CHUNK", 200)
    material = ("체절은 myotome, sclerotome, dermatome으로 나뉜다. " * 6) + "\n\n" + ("피부절과 근육절 설명. " * 12)
    cards = flashcards.make_flashcards(MD, instruction=flashcards.EXAMPLE_REQUEST, material=material)

    assert [c["front"] for c in cards] == ["Myotome", "Sclerotome", "Dermatome", "Pax7"]   # 덩어리별 결과 합치고 중복 제거
    assert len(calls) == 3                                                               # 자료 2덩어리 + 문항 1번
    assert all(flashcards.EXAMPLE_REQUEST in system and "최우선" in system for system, _ in calls)
    assert cards[0]["qid"] == "" and cards[-1]["qid"] == "문제 1"


def test_request_without_material_uses_questions(monkeypatch):
    client, seen = _client([{"front": "A", "back": "B", "qid": "문제 1"}])
    monkeypatch.setattr("llm.get_client", lambda: client)
    cards = flashcards.make_flashcards(MD, instruction="수치만 카드로")
    assert len(cards) == 1 and "수치만 카드로" in seen["system"]
    assert json.loads(seen["user"])["questions"][0]["qid"] == "문제 1"


def test_default_prompt_has_no_request(monkeypatch):
    client, seen = _client([])
    monkeypatch.setattr("llm.get_client", lambda: client)
    assert flashcards.make_flashcards(MD) == []
    assert "사용자 요청 (최우선" not in seen["system"]
