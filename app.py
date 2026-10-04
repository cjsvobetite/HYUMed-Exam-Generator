"""SaluTerra — Streamlit 진입점: 로그인 → 페이지 이동."""
import sys
from pathlib import Path

import streamlit as st

# ── 배포 후 옛 모듈이 메모리에 남는 문제 방지 ──
# Streamlit Cloud는 새 코드를 받아도 이미 불러온 모듈 일부를 그대로 쓰는 경우가 있다
# (예: 새 workspace.py가 옛 store.py의 저장소 객체를 받아 AttributeError).
# 이 파일은 매번 새로 실행되므로, 프로젝트 .py 파일이 바뀌었으면 프로젝트 모듈을 모두 비워 새로 불러온다.
_ROOT = Path(__file__).resolve().parent
_code_sig = max(p.stat().st_mtime_ns for p in [*_ROOT.glob("*.py"), *_ROOT.glob("views/*.py")])
if getattr(sys, "_saluterra_code_sig", None) != _code_sig:
    for _name, _mod in list(sys.modules.items()):
        _file = getattr(_mod, "__file__", None) or ""
        if _name != "__main__" and _file.startswith(str(_ROOT)) and "/tests/" not in _file:
            del sys.modules[_name]
    sys._saluterra_code_sig = _code_sig

import ui
from config import ADMIN_ID
from constants import BRAND
from views import admin, exam_cbt, generate, home, login, workspace

st.set_page_config(page_title=f"{BRAND} CBT", page_icon="🐈", layout="wide")
ui.inject_css()

if "authed" not in st.session_state:
    st.session_state.authed = False
    st.session_state.user = None

if not st.session_state.authed:
    ui.topbar()
    login.render()
    st.stop()

user = st.session_state.user
p_home = st.Page(home.render, title="홈", url_path="home", default=True)
p_generate = st.Page(generate.render, title="AI 문항 생성", url_path="generate")
p_exam = st.Page(exam_cbt.render, title="문제지 CBT", url_path="exam")
p_workspace = st.Page(workspace.render, title="내 노트북", url_path="workspace")
p_admin = st.Page(admin.render, title="관리자 대시보드", url_path="admin")
is_admin = user == ADMIN_ID
nav = st.navigation([p_home, p_generate, p_exam, p_workspace] + ([p_admin] if is_admin else []),
                    position="hidden")
st.session_state["_pages"] = {"home": p_home, "workspace": p_workspace, "generate": p_generate, "exam": p_exam}

ui.topbar(user)
with st.sidebar:
    st.markdown(f'<div class="tree-head"><span>{user}</span></div>', unsafe_allow_html=True)
    nodes = [
        (0, "root", None, False),
        (1, "홈 (오늘 복습·통계·기록)", p_home, False),
        (1, "문항 출제", None, False),
        (2, "AI 문항 생성", p_generate, True),
        (1, "CBT 응시", None, False),
        (2, "문제지 CBT", p_exam, True),
        (1, "학습 공간", None, not is_admin),
        (2, "내 노트북", p_workspace, True),
    ]
    if is_admin:
        nodes += [(1, "관리", None, True), (2, "관리자 대시보드", p_admin, True)]
    ui.tree(nodes, nav.title)
    st.markdown('<div class="tree-foot">로그인 사용자: <b>' + user + '</b></div>', unsafe_allow_html=True)
    if st.button("로그아웃", use_container_width=True):
        st.session_state.clear()
        st.rerun()

nav.run()
