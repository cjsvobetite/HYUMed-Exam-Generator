"""문항별 해설 모드: 답을 골라도 '정답 확인'을 누르기 전에는 채점 결과가 나오지 않아야 한다."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = f'''
import sys
sys.path.insert(0, {str(ROOT)!r})
from cbt import parse_cbt_questions, render_cbt
from tests.test_quality import q_block
md = q_block(1, "모두 고르시오", ["A", "B", "C", "D", "E"], answer="①, ②") + q_block(2, "하나", ["A", "B", "C"], answer="③")
render_cbt(parse_cbt_questions(md), mode="per_q", session_prefix="t", user="", source_text=md)
'''


def _texts(at):
    return [e.value for e in at.success] + [e.value for e in at.error]


def test_multi_answer_waits_for_check_button():
    at = AppTest.from_string(SCRIPT, default_timeout=30).run()
    at.checkbox(key="t_cb_문제 1_0").check().run()          # 정답 ①,② 중 ①만 선택
    assert _texts(at) == []                                   # 아직 오답 표시 없음
    btn = at.button(key="t_check_0")
    assert not btn.disabled
    at.checkbox(key="t_cb_문제 1_1").check().run()
    at.button(key="t_check_0").click().run()
    assert any("정답" in t for t in _texts(at))


def test_check_button_disabled_until_answer_chosen():
    at = AppTest.from_string(SCRIPT, default_timeout=30).run()
    assert at.button(key="t_check_0").disabled


SCRIPT_SUBMIT = SCRIPT.replace('mode="per_q"', 'mode="submit_all"')


def test_stem_is_body_size_not_heading():
    at = AppTest.from_string(SCRIPT, default_timeout=30).run()
    assert not [h for h in at.markdown if h.value.startswith("###")]
    assert any(m.value.startswith("**1.** 모두 고르시오") for m in at.markdown)


def test_excluded_choices_are_struck_and_survive_navigation():
    at = AppTest.from_string(SCRIPT_SUBMIT, default_timeout=30).run()
    at.button_group(key="t_ex_문제 1").set_value([2, 4]).run()          # ③ ⑤ 제외
    labels = [cb.label for cb in at.checkbox]
    assert labels[2].startswith(":gray[~~(3)") and labels[4].startswith(":gray[~~(5)")
    assert labels[0] == "(1) A"
    at.button(key="t_next").click().run()                                # 2번으로 갔다가
    at.button(key="t_prev").click().run()                                # 돌아와도
    labels = [cb.label for cb in at.checkbox]
    assert labels[2].startswith(":gray[~~") and labels[1] == "(2) B"
    at.checkbox(key="t_cb_문제 1_2").check().run()                       # 제외한 선지도 고를 수는 있음
    assert at.checkbox(key="t_cb_문제 1_2").value


def test_marked_questions_jump():
    at = AppTest.from_string(SCRIPT_SUBMIT, default_timeout=30).run()
    at.button(key="t_flag_0").click().run()
    assert at.button(key="t_flag_0").label == "🚩 표시 해제"
    at.button(key="t_next").click().run()
    assert any(b.label == "🚩1" for b in at.button)                      # 번호 버튼에 🚩
    at.button(key="t_mk_0").click().run()                                # 상단 목록에서 바로 이동
    assert any(m.value.startswith("**1.**") for m in at.markdown)
