import streamlit as st

import auth
import ui


def render() -> None:
    ui.hero("로그인", "강의 자료로 문항을 만들고, 문제지를 CBT로 풀어 보세요.")
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid, st.container(border=True):
        tab_login, tab_signup = st.tabs(["로그인", "회원가입"])
        with tab_login:
            with st.form("login_form"):
                uid = st.text_input("아이디")
                pw = st.text_input("비밀번호 (숫자 4자리)", type="password", max_chars=4)
                ok = st.form_submit_button("로그인", type="primary", use_container_width=True)
            if ok:
                if auth.login(uid, pw):
                    st.session_state.authed = True
                    st.session_state.user = uid
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 일치하지 않습니다.")
        with tab_signup:
            with st.form("signup_form"):
                new_uid = st.text_input("아이디 (영문/숫자/_ 3~20자)")
                new_pw = st.text_input("비밀번호 (숫자 4자리)", type="password", max_chars=4)
                new_pw2 = st.text_input("비밀번호 확인", type="password", max_chars=4)
                ok2 = st.form_submit_button("회원가입", use_container_width=True)
            if ok2:
                err = auth.signup(new_uid, new_pw, new_pw2)
                if err:
                    st.error(err)
                else:
                    st.success("✅ 가입 완료. 로그인 탭에서 로그인하세요.")
