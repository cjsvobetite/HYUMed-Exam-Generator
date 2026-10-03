import pandas as pd
import streamlit as st

import auth
import ui
from config import ADMIN_ID, HISTORY_PATH
from storage import load_json


def render() -> None:
    ui.hero("관리자 대시보드", f"관리자: {ADMIN_ID}")
    all_users = auth.load_users()
    all_history = load_json(HISTORY_PATH)

    total = sum(len(v) for v in all_history.values())
    active = len([u for u, h in all_history.items() if h])
    c1, c2, c3 = st.columns(3)
    c1.metric("전체 가입자", f"{len(all_users)}명")
    c2.metric("CBT 이용자", f"{active}명")
    c3.metric("총 풀이 횟수", f"{total}회")

    tab1, tab2, tab3 = st.tabs(["👥 유저 목록", "📊 사용 통계", "📋 전체 풀이 기록"])
    with tab1:
        if not all_users:
            st.info("가입된 유저가 없습니다.")
        else:
            rows = []
            for uid in all_users:
                h = all_history.get(uid, [])
                rows.append({
                    "아이디": uid,
                    "총 풀이 횟수": len(h),
                    "평균 정답률": f"{sum(a.get('pct', 0) for a in h) / len(h):.1f}%" if h else "-",
                    "마지막 풀이": max(a.get("ts", "") for a in h)[:16] if h else "없음",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with tab2:
        if all_history:
            chart_df = pd.DataFrame(
                [(u, len(h)) for u, h in all_history.items() if h], columns=["유저", "풀이 횟수"]
            ).sort_values("풀이 횟수", ascending=False)
            st.bar_chart(chart_df.set_index("유저"))
        else:
            st.info("아직 풀이 기록이 없습니다.")

    with tab3:
        user_list = list(all_users.keys())
        if not user_list:
            st.info("가입된 유저가 없습니다.")
            return
        sel_user = st.selectbox("유저 선택", user_list)
        uh = all_history.get(sel_user, [])
        if not uh:
            st.info(f"{sel_user}의 풀이 기록이 없습니다.")
            return
        rows = [{"회차": i, "날짜/시각": a.get("ts", "")[:16], "세트": a.get("title") or "-",
                 "정답률": f"{a.get('pct', 0)}%", "총 문항": a.get("total", "-"),
                 "정답 수": a.get("correct", "-")} for i, a in enumerate(uh, 1)]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        idx = st.selectbox("회차 선택 → 틀린 문항", range(len(rows)),
                           format_func=lambda i: f"{rows[i]['회차']}회차 ({rows[i]['날짜/시각']})",
                           key="admin_sel")
        wq = uh[idx].get("wrong_ids", [])
        if wq:
            st.markdown(f"**틀린 문항 ({len(wq)}개):** {', '.join(wq)}")
        else:
            st.success("틀린 문항이 없습니다! 🎉")
