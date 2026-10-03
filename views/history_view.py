import pandas as pd
import streamlit as st

import ui
from cbt import parse_cbt_questions, render_cbt
from constants import CBT_MODES, cbt_mode_value
from history import get_wrong_questions, load_history


def render() -> None:
    user = st.session_state.get("user", "")
    ui.hero("복습 기록", f"{user}님의 CBT 풀이 기록과 오답 재풀이")
    hist = load_history(user) if user else []
    if not hist:
        st.info("아직 제출 기록이 없습니다. CBT에서 문항을 다 풀면 자동으로 저장됩니다.")
        return

    avg = sum(r["pct"] for r in hist) / len(hist)
    c1, c2, c3 = st.columns(3)
    c1.metric("풀이 횟수", f"{len(hist)}회")
    c2.metric("평균 정답률", f"{avg:.0f}%")
    c3.metric("최근 정답률", f"{hist[0]['pct']}%")

    rows = [{"#": i + 1, "날짜": r["ts"], "세트": r.get("title") or "-", "총 문항": r["total"],
             "정답": r["correct"], "정답률": f"{r['pct']}%", "틀린 문항 수": len(r["wrong_ids"])}
            for i, r in enumerate(hist)]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    ui.step("↻", "오답 재풀이", "회차를 고르면 그 회차에서 틀린 문항만 다시 풉니다.")
    sel_idx = st.selectbox(
        "재풀이할 회차", options=list(range(len(hist))),
        format_func=lambda x: f"#{x + 1}  {hist[x]['ts']}  {hist[x].get('title') or ''}  정답률 {hist[x]['pct']}%",
        key="history_page_sel",
    )
    rec = hist[sel_idx]
    if not rec["wrong_ids"]:
        st.success("🎉 이 회차는 모든 문항을 맞혔습니다!")
        return
    st.markdown(f"**틀린 문항 ({len(rec['wrong_ids'])}개):** {', '.join(rec['wrong_ids'])}")
    full_text = rec.get("full_text", "")
    if not full_text:
        st.warning("⚠️ 이 회차 기록에는 문항 데이터가 없습니다 (예전 버전 기록).")
        return
    review_mode = st.radio("복습 모드", CBT_MODES, horizontal=True, key="history_review_mode")
    if st.button("🔁 오답 재풀이 시작", type="primary", use_container_width=True,
                 key=f"hist_start_{sel_idx}"):
        st.session_state["review_qs"] = get_wrong_questions(parse_cbt_questions(full_text), rec["wrong_ids"])
        st.session_state["review_rec"] = rec
        st.rerun()
    if st.session_state.get("review_qs"):
        rec = st.session_state["review_rec"]
        rqs = st.session_state["review_qs"]
        st.divider()
        st.subheader(f"🔁 오답 재풀이 — {rec['ts']} ({len(rqs)}문항)")
        render_cbt(rqs, mode=cbt_mode_value(review_mode),
                   session_prefix=f"review_{rec['ts'].replace(' ', '_').replace(':', '')}",
                   user=user, source_text=rec.get("full_text", ""),
                   title=f"{rec.get('title') or '복습'} (오답 재풀이)")
