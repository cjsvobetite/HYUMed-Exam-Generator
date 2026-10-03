"""SaluTerra — Streamlit 진입점: 로그인 → 페이지 이동."""
import streamlit as st

import ui
from config import ADMIN_ID
from constants import BRAND
from views import admin, exam_cbt, generate, history_view, login

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
p_generate = st.Page(generate.render, title="AI 문항 생성", url_path="generate", default=True)
p_exam = st.Page(exam_cbt.render, title="문제지 CBT", url_path="exam")
p_history = st.Page(history_view.render, title="복습 기록", url_path="history")
p_admin = st.Page(admin.render, title="관리자 대시보드", url_path="admin")
is_admin = user == ADMIN_ID
nav = st.navigation([p_generate, p_exam, p_history] + ([p_admin] if is_admin else []), position="hidden")

ui.topbar(user)
with st.sidebar:
    st.markdown(f'<div class="tree-head"><span>{user}</span></div>', unsafe_allow_html=True)
    nodes = [
        (0, "root", None, False),
        (1, "문항 출제", None, False),
        (2, "AI 문항 생성", p_generate, True),
        (1, "CBT 응시", None, not is_admin),
        (2, "문제지 CBT", p_exam, False),
        (2, "복습 기록", p_history, True),
    ]
    if is_admin:
        nodes += [(1, "관리", None, True), (2, "관리자 대시보드", p_admin, True)]
    ui.tree(nodes, nav.title)
    st.markdown('<div class="tree-foot">로그인 사용자: <b>' + user + '</b></div>', unsafe_allow_html=True)
    if st.button("로그아웃", use_container_width=True):
        st.session_state.clear()
        st.rerun()

nav.run()
