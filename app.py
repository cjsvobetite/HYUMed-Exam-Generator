"""SaluTerra — Streamlit 진입점: 로그인 → 페이지 이동."""
import streamlit as st

import ui
from config import ADMIN_ID
from constants import BRAND
from views import admin, exam_cbt, generate, history_view, login

st.set_page_config(page_title=BRAND, page_icon="🐈", layout="wide")
ui.inject_css()

if "authed" not in st.session_state:
    st.session_state.authed = False
    st.session_state.user = None

if not st.session_state.authed:
    login.render()
    st.stop()

user = st.session_state.user
pages = [
    st.Page(generate.render, title="AI 문항 생성", icon="✨", url_path="generate", default=True),
    st.Page(exam_cbt.render, title="문제지 CBT", icon="📄", url_path="exam"),
    st.Page(history_view.render, title="복습 기록", icon="📋", url_path="history"),
]
if user == ADMIN_ID:
    pages.append(st.Page(admin.render, title="관리자", icon="🛠️", url_path="admin"))
nav = st.navigation(pages)

with st.sidebar:
    st.markdown(f"### 🐈 {BRAND}")
    c1, c2 = st.columns([3, 2])
    c1.markdown(f"👤 **{user}**")
    if c2.button("로그아웃", use_container_width=True):
        st.session_state.clear()
        st.rerun()

nav.run()
