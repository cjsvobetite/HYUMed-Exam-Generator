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
