import json
import os
import types
import uuid

import pytest

import workspace as ws
from cbt import parse_cbt_questions
from history import save_attempt
from store import JsonStore, PgStore
from tests.test_quality import q_block

PG_URL = os.environ.get("TEST_DATABASE_URL")


def _uid():
    return "w" + uuid.uuid4().hex[:8]


def _set_md(prefix, n=3):
    return "".join(q_block(i, f"{prefix} 문항 {i}?", ["A", "B", "C", "D"], answer="①") for i in range(1, n + 1))


@pytest.fixture(params=["file", "postgres"])
def store(request, monkeypatch):
    if request.param == "postgres":
        if not PG_URL:
            pytest.skip("TEST_DATABASE_URL 없음")
        s = PgStore(PG_URL)
    else:
        s = JsonStore()
    monkeypatch.setattr(ws, "get_store", lambda: s)
    monkeypatch.setattr("history.get_store", lambda: s)
    return s


def test_store_notebooks_and_sets_are_scoped_by_user(store):
    a, b = _uid(), _uid()
    nb = ws.create_notebook(a, "발생학")
    st_ = ws.save_set(a, _set_md("근육"), "exam", "족보", nb["id"], None)
    assert [n["name"] for n in store.notebooks(a)] == ["발생학"] and store.notebooks(b) == []
    assert store.get_set(b, st_["id"]) is None                     # 다른 유저는 못 읽음
    store.delete_set(b, st_["id"])                                 # 다른 유저는 못 지움
    assert store.get_set(a, st_["id"])["n_questions"] == 3
    assert "markdown" not in store.sets(a)[0] and store.sets(a, with_markdown=True)[0]["markdown"]
    store.delete_notebook(a, nb["id"])
    assert store.notebooks(a) == [] and store.sets(a) == []


def test_units(store):
    uid = _uid()
    nb = ws.find_or_create_notebook(uid, "생리학")
    assert ws.find_or_create_notebook(uid, " 생리학 ")["id"] == nb["id"]
    u1 = ws.add_unit(uid, nb, "심장")
    assert ws.add_unit(uid, nb, "심장")["id"] == u1["id"]
    st_ = ws.save_set(uid, _set_md("심장"), "generated", "세트", nb["id"], u1["id"])
    ws.rename_unit(uid, nb, u1["id"], "심혈관")
    assert ws.unit_name(store.notebooks(uid)[0], u1["id"]) == "심혈관"
    ws.delete_unit(uid, nb, u1["id"])
    assert store.get_set(uid, st_["id"])["unit_id"] is None        # 세트는 남고 단원만 해제


def _solve(uid, md, answers, set_id=None, sources=None, flagged=()):
    qs = parse_cbt_questions(md)
    ua = {q["id"]: [a] for q, a in zip(qs, answers)}
    return save_attempt(uid, qs, ua, full_text=md, set_id=set_id, sources=sources, flagged=list(flagged))


def test_question_status_and_review(store):
    uid = _uid()
    nb = ws.create_notebook(uid, "발생학")
    u_muscle = ws.add_unit(uid, nb, "근육")
    u_bone = ws.add_unit(uid, nb, "뼈")
    s1 = ws.save_set(uid, _set_md("근육"), "generated", "근육 세트", nb["id"], u_muscle["id"])
    s2 = ws.save_set(uid, _set_md("뼈"), "exam", "뼈 족보", nb["id"], u_bone["id"])

    # 근육 세트: 1번 맞힘, 2·3번 틀림, 3번 🔖
    _solve(uid, s1["markdown"], [0, 1, 2], set_id=s1["id"], flagged=["문제 3"])
    status = ws.question_status(uid)
    assert status[(s1["id"], "문제 1")].last_correct is True
    assert status[(s1["id"], "문제 2")].last_correct is False and status[(s1["id"], "문제 3")].flagged
    assert ws.notebook_stats(uid, nb)["wrong"] == 2

    # 틀린 문항만 복습 (근육 단원)
    md, mapping, total = ws.build_review(uid, nb, [u_muscle["id"]], [ws.SRC_WRONG], 0, shuffle=False)
    assert total == 2 and mapping == {"문제 1": [s1["id"], "문제 2"], "문제 2": [s1["id"], "문제 3"]}
    assert [q["id"] for q in parse_cbt_questions(md)] == ["문제 1", "문제 2"]
    assert "근육 문항 2?" in md and "근육 문항 3?" in md

    # 복습에서 원래 2번을 맞히고 3번은 또 틀림, 🔖 해제 → 원래 문항 상태가 바뀜
    _solve(uid, md, [0, 3], sources=mapping)
    status = ws.question_status(uid)
    assert status[(s1["id"], "문제 2")].last_correct is True and status[(s1["id"], "문제 2")].ever_wrong
    assert status[(s1["id"], "문제 3")].last_correct is False and not status[(s1["id"], "문제 3")].flagged
    _, mapping, total = ws.build_review(uid, nb, None, [ws.SRC_WRONG], 0)
    assert total == 1
    _, _, total = ws.build_review(uid, nb, None, [ws.SRC_EVER_WRONG], 0)
    assert total == 2

    # 기출 전체 / 안 푼 문항 / 개수 제한
    _, mapping, total = ws.build_review(uid, nb, None, [ws.SRC_EXAM], 2, seed=1)
    assert total == 3 and len(mapping) == 2 and all(v[0] == s2["id"] for v in mapping.values())
    _, _, total = ws.build_review(uid, nb, None, [ws.SRC_UNSOLVED], 0)
    assert total == 3                                           # 뼈 족보 3문항

    # 주관식(채점 안 됨)도 풀었으면 '안 푼 문항'에서 빠진다
    subj_md = q_block(1, "위성세포가 발현하는 전사인자는?", answer="Pax7")
    s3 = ws.save_set(uid, subj_md, "generated", "주관식", nb["id"], None)
    _solve(uid, subj_md, [0], set_id=s3["id"])
    status = ws.question_status(uid)
    assert status[(s3["id"], "문제 1")].tries == 1 and status[(s3["id"], "문제 1")].last_correct is None
    _, _, total = ws.build_review(uid, nb, [None], [ws.SRC_EXAM, ws.SRC_GENERATED], 0)
    assert total == 1                                           # 단원 미지정 세트는 주관식 세트 하나뿐


def test_suggest_classification(store, monkeypatch):
    uid = _uid()
    nb = ws.create_notebook(uid, "발생학")
    ws.add_unit(uid, nb, "근골격계")
    seen = {}

    class C:
        @staticmethod
        def create(messages, **kw):
            seen["prompt"] = messages[0]["content"]
            msg = types.SimpleNamespace(content=json.dumps({"subject": "발생학", "unit": "근골격계", "title": "근육 발생"}))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setattr("llm.get_client", lambda: types.SimpleNamespace(chat=types.SimpleNamespace(completions=C)))
    sug = ws.suggest_classification(uid, _set_md("MyoD"))
    assert sug == {"subject": "발생학", "unit": "근골격계", "title": "근육 발생"}
    assert "근골격계" in seen["prompt"] and "MyoD 문항 1?" in seen["prompt"]
