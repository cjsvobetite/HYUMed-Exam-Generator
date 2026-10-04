"""홈·노트북 화면과 시험 모드가 실제로 그려지고 동작하는지 (AppTest)."""
import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

import flashcards
import workspace as ws
from tests.test_workspace import _set_md, _solve, _uid

ROOT = Path(__file__).resolve().parents[1]
HEAD = f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n"

EXAM = HEAD + '''
from cbt import parse_cbt_questions, render_cbt
from tests.test_quality import q_block
md = q_block(1, "하나", ["A", "B", "C"], answer="①") + q_block(2, "둘", ["A", "B", "C"], answer="③")
render_cbt(parse_cbt_questions(md), mode="exam", session_prefix="t", user="", source_text=md)
'''


def test_exam_mode_timer_and_lock():
    at = AppTest.from_string(EXAM, default_timeout=30).run()
    assert at.number_input(key="t_exam_minutes").value == 2            # 기본: 문항당 1분
    assert not at.radio                                                  # 시작 전엔 문항이 안 보임
    at.button(key="t_exam_start").click().run()
    assert at.session_state["t_exam_deadline"] > time.time() + 100
    at.radio(key="t_exam_r_문제 1").set_value(0).run()
    at.button(key="t_exam_next").click().run()
    at.button(key="t_exam_submit_btn").click().run()
    assert any("1 / 2" in m.value for m in at.metric)
    assert at.radio(key="t_exam_r_문제 2").disabled                      # 제출 뒤에는 답을 못 바꿈
    assert any("걸린 시간" in c.value for c in at.caption)


def test_exam_mode_auto_submits_when_time_is_up():
    at = AppTest.from_string(EXAM, default_timeout=30).run()
    at.button(key="t_exam_start").click().run()
    at.session_state["t_exam_deadline"] = time.time() - 1
    at.run()
    assert any("시간이 끝나" in w.value for w in at.warning)
    assert any("0 / 2" in m.value for m in at.metric)


def _page(view: str, uid: str, **state):
    at = AppTest.from_string(HEAD + f"import ui\nui.inject_css()\nfrom views import {view}\n{view}.render()\n",
                             default_timeout=60)
    at.session_state["user"] = uid
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def _seed():
    uid = _uid()
    nb = ws.create_notebook(uid, "생리학")
    unit = ws.add_unit(uid, nb, "심장")
    s1 = ws.save_set(uid, _set_md("심장"), "generated", "심장 세트", nb["id"], unit["id"])
    _solve(uid, s1["markdown"], [0, 1, 2], set_id=s1["id"])
    cards = [flashcards.new_card("앞1", "뒤1"), flashcards.new_card("앞2", "뒤2")]
    deck = ws.save_deck(uid, cards, "심장 덱", nb["id"], unit["id"])
    ws.rate_card(uid, deck["id"], cards[0]["id"], False)
    return uid, nb, s1, deck


def test_home_today_review_and_history():
    uid, nb, s1, deck = _seed()
    at = _page("home", uid)
    assert not at.exception
    html = " ".join(m.value for m in at.markdown)
    assert "오늘 복습할 문항" in html and ">2<" in html                   # 틀린 2문항
    at.button(key="home_due_go").click().run()
    assert not at.exception and at.session_state["home_review"]["total"] == 2
    at.button(key="home_cards_go").click().run()
    assert not at.exception and len(at.session_state["home_cards"]["pool"]) == 2   # 복습 1장 + 새 카드 1장
    at.button(key="hist_start_0").click().run()                          # 📋 풀이 기록: 세트에서 문항을 다시 읽어 재풀이
    assert not at.exception and [q["id"] for q in at.session_state["review_qs"]] == ["문제 2", "문제 3"]


def test_home_without_notebooks_shows_links():
    at = _page("home", _uid())
    assert not at.exception and any("아직 노트북이 없습니다" in i.value for i in at.info)


def test_notebook_tabs_search_edit_share():
    uid, nb, s1, deck = _seed()
    at = _page("workspace", uid, ws_nb=nb["id"])
    assert not at.exception
    labels = [t.label for t in at.tabs]
    for name in ("🔍 검색", "📊 통계", "✏️ 편집", "📤 Anki 내보내기", "🔗 공유", "🤖 문항별 단원 분류"):
        assert name in labels
    at.text_input(key=f"srch_{nb['id']}").input("심장 문항 2").run()
    assert not at.exception
    at.button(key=f"srch_go_{nb['id']}").click().run()
    assert list(at.session_state[f"srch_rv_{nb['id']}"]["map"].values()) == [[s1["id"], "문제 2"]]

    pick = at.selectbox(key=f"set_pick_{nb['id']}")
    at = pick.set_value(next(o for o in pick.options if o.startswith("심장 세트"))).run()
    key = f"edit_txt_{s1['id']}_문제 1"
    at.text_area(key=key).input(at.text_area(key=key).value.replace("심장 문항 1?", "고친 발문?")).run()
    at.button(key=f"edit_save_{s1['id']}_문제 1").click().run()
    assert not at.exception and "고친 발문?" in ws.get_store().get_set(uid, s1["id"])["markdown"]

    at.button(key=f"share_btn_{s1['id']}").click().run()
    code = at.session_state[f"share_code_{s1['id']}"]
    assert ws.get_share(code)["title"] == "심장 세트"


def test_login_form_shows_lockout():
    import auth
    uid = _uid()
    assert auth.signup(uid, "1234", "1234") is None
    at = AppTest.from_string(HEAD + "from views import login\nlogin.render()\n", default_timeout=30).run()
    for i in range(auth.MAX_FAILS):
        at.text_input[0].input(uid)
        at.text_input[1].input("0000")
        at.button[0].click().run()
    assert any("잠겼습니다" in e.value for e in at.error)
    at.text_input[1].input("1234")
    at.button[0].click().run()
    assert "authed" not in at.session_state or not at.session_state["authed"]
    assert any("잠겼습니다" in e.value for e in at.error)
