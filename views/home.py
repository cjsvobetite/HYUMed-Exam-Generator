"""🏠 홈 — 오늘 복습할 것 · 학습 통계 · 풀이 기록 (예전 '복습 기록' 페이지를 합침)."""
from datetime import datetime, timedelta

import streamlit as st

import srs
import ui
import workspace as ws
from cbt import parse_cbt_questions, render_cbt
from constants import CBT_MODES, cbt_mode_value
from history import get_wrong_questions, load_history

_BLUE = "#3B6BB0"


def _uid() -> str:
    return st.session_state.get("user", "")


def _go(name: str) -> None:
    page = st.session_state.get("_pages", {}).get(name)
    if page:
        st.switch_page(page)


def render() -> None:
    uid = _uid()
    ui.hero("홈", f"{uid}님, 오늘 복습할 것부터 시작하세요.")
    status = ws.question_status(uid)
    due_q = ws.due_question_count(uid, status)
    due_pool, new_cards = ws.due_cards(uid)
    rows = ws.attempt_rows(uid)
    days = {r["day"] for r in rows}
    week_ago = (srs.today() - timedelta(days=6)).isoformat()
    week = [r for r in rows if r["day"] >= week_ago]
    week_total = sum(r["total"] for r in week)
    week_pct = f"{round(sum(r['correct'] for r in week) / week_total * 100)}%" if week_total else "—"

    cards = [("📅 오늘 복습할 문항", f"{due_q}"), ("🃏 오늘 복습할 카드", f"{len(due_pool)}"),
             ("🔥 연속 학습", f"{ws.study_streak(days)}일"), ("🎯 최근 7일 정답률", week_pct)]
    cols = st.columns(4)
    for col, (label, num) in zip(cols, cards):
        col.markdown(f'<div class="home-card"><div class="home-lbl">{label}</div>'
                     f'<div class="home-num">{num}</div></div>', unsafe_allow_html=True)
    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)

    t_today, t_stats, t_hist = st.tabs(["📅 오늘 복습", "📊 학습 통계", "📋 풀이 기록"])
    with t_today:
        _today(uid, due_q, due_pool, new_cards, status)
    with t_stats:
        stats_panel(uid, rows, status)
    with t_hist:
        _history(uid)


# ─── 📅 오늘 복습 ───

def _today(uid, due_q, due_pool, new_cards, status):
    if not ws.notebooks(uid):
        st.info("아직 노트북이 없습니다. 문항이나 플래시카드를 만든 뒤 결과 화면의 '📒 내 노트북에 저장'으로 모아 두면, "
                "여기서 간격 반복으로 복습할 차례가 된 것만 골라 줍니다.")
        c1, c2, c3 = st.columns(3)
        if c1.button("✨ AI 문항 생성", use_container_width=True, type="primary"):
            _go("generate")
        if c2.button("📄 문제지 CBT", use_container_width=True):
            _go("exam")
        if c3.button("📒 내 노트북", use_container_width=True):
            _go("workspace")
        return

    st.caption("간격 반복: 맞힌 문항·아는 카드는 점점 길게(1일→3일→1주→2주…), 틀린 것은 다시 오늘 복습 목록에 올라옵니다.")
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.markdown(f"**📝 문항 복습** · 오늘 {due_q}문항")
        limit = st.number_input("최대 문항 수 (0 = 전부)", 0, 200, 30, key="home_due_n")
        mode = st.radio("풀이 방식", CBT_MODES, horizontal=True, key="home_due_mode")
        if st.button("📝 오늘 문항 복습 시작", type="primary", use_container_width=True, disabled=not due_q,
                     key="home_due_go"):
            md, mapping, total = ws.build_review(uid, None, None, [ws.SRC_DUE], int(limit))
            st.session_state.home_review = {"md": md, "map": mapping, "total": total,
                                            "ts": datetime.now().strftime("%Y%m%d%H%M%S")}
            st.session_state.pop("home_cards", None)
    with right, st.container(border=True):
        st.markdown(f"**🃏 카드 복습** · 오늘 {len(due_pool)}장" + (f" · 새 카드 {new_cards}장" if new_cards else ""))
        with_new = st.number_input("새 카드도 섞기 (장)", 0, 200, min(new_cards, 20), key="home_new_n",
                                   help="아직 한 번도 안 본 카드를 이만큼 더해 학습합니다.")
        st.markdown('<div style="height:38px"></div>', unsafe_allow_html=True)
        if st.button("🃏 오늘 카드 복습 시작", type="primary", use_container_width=True,
                     disabled=not (due_pool or (new_cards and with_new)), key="home_cards_go"):
            import random
            pool = list(due_pool) + _new_cards(uid, int(with_new))
            random.shuffle(pool)
            st.session_state.home_cards = {"pool": pool, "ts": datetime.now().strftime("%H%M%S%f")}
            st.session_state.pop("home_review", None)

    rv = st.session_state.get("home_review")
    if rv:
        st.divider()
        st.markdown(f"**📅 오늘 복습** · 복습할 {rv['total']}문항 중 {len(rv['map'])}문항")
        render_cbt(parse_cbt_questions(rv["md"]), mode=cbt_mode_value(st.session_state.get("home_due_mode")),
                   session_prefix=f"home_rv_{rv['ts']}", user=uid, source_text=rv["md"],
                   title="오늘 복습 (간격 반복)", sources=rv["map"])
    run = st.session_state.get("home_cards")
    if run:
        st.divider()
        from views.workspace import _flash_session
        _flash_session(uid, None, f"home_fc_{run['ts']}", run["pool"])

    weak = [r for r in ws.unit_accuracy(uid, status) if r["solved"] >= 3][:5]
    if weak:
        ui.step(None, "약한 단원", "풀어 본 문항이 3개 이상인 단원 중 정답률이 낮은 순서입니다 (최근 풀이 기준).")
        ui.table([{"과목": r["notebook"], "단원": r["unit"], "푼 문항": r["solved"], "틀린 문항": r["wrong"],
                   "정답률": f"{r['pct']}%"} for r in weak], center=("정답률",))


def _new_cards(uid, n):
    import flashcards
    from store import get_store
    out = []
    for d in get_store().sets(uid, None, with_markdown=True):
        if d.get("kind") == ws.FLASH:
            out += [(d["id"], c) for c in flashcards.loads(d["markdown"]) if not c.get("reviews")]
    return out[:n]


# ─── 📊 학습 통계 ───

def stats_panel(uid, rows, status, nb=None):
    """풀이 추이·단원별 정답률·카드 단계. nb를 주면 그 노트북만."""
    import altair as alt
    import pandas as pd

    if nb is None and not rows:
        st.info("CBT로 문항을 다 풀면 통계가 쌓입니다.")
        return

    axis = dict(labelFont="Nanum Gothic, Malgun Gothic, sans-serif", titleFont="Nanum Gothic, Malgun Gothic, sans-serif", labelColor="#475569", titleColor="#475569",
                gridColor="#E5ECF5")
    if nb is None:
        since = srs.today() - timedelta(days=29)
        recent = [r for r in rows if r["day"] >= since.isoformat()]
        if recent:
            df = pd.DataFrame(recent).groupby("day")[["total", "correct"]].sum()
            df = df.reindex(pd.date_range(since, srs.today()).strftime("%Y-%m-%d"), fill_value=0).reset_index(
                names="day")
            df["day"] = pd.to_datetime(df["day"])
            df["pct"] = (df["correct"] / df["total"].where(df["total"] > 0) * 100).round()
            x = alt.X("day:T", title=None, axis=alt.Axis(format="%m/%d", labelAngle=0, tickCount=6, **axis))
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**최근 30일 · 하루에 푼 문항**")
                bars = alt.Chart(df).mark_bar(color=_BLUE, size=9).encode(
                    x, alt.Y("total:Q", title=None, axis=alt.Axis(tickMinStep=1, **axis)),
                    tooltip=[alt.Tooltip("day:T", title="날짜", format="%Y-%m-%d"),
                             alt.Tooltip("total:Q", title="푼 문항")])
                st.altair_chart(bars.properties(height=220), use_container_width=True)
            with c2:
                st.markdown("**최근 30일 · 날짜별 정답률(%)**")
                pts = df.dropna(subset=["pct"])
                y = alt.Y("pct:Q", title=None, scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(**axis))
                base = alt.Chart(pts).encode(x, y, tooltip=[alt.Tooltip("day:T", title="날짜", format="%Y-%m-%d"),
                                                            alt.Tooltip("pct:Q", title="정답률(%)")])
                line = base.mark_line(color=_BLUE, strokeWidth=2) + base.mark_point(color=_BLUE, filled=True, size=55)
                st.altair_chart(line.properties(height=220), use_container_width=True)
        else:
            st.caption("최근 30일 풀이 기록이 없습니다.")

    acc = [r for r in ws.unit_accuracy(uid, status) if nb is None or r["nb_id"] == nb["id"]]
    if acc:
        st.markdown("**단원별 정답률(%)** · 풀어 본 문항 기준, 최근 풀이로 계산 (낮은 순)")
        df = pd.DataFrame({"단원": [r["unit"] if nb else f"{r['notebook']} › {r['unit']}" for r in acc],
                           "pct": [r["pct"] for r in acc], "solved": [r["solved"] for r in acc]})
        y = alt.Y("단원:N", sort=None, title=None, axis=alt.Axis(labelLimit=260, **axis))
        base = alt.Chart(df).encode(y, alt.X("pct:Q", title=None, scale=alt.Scale(domain=[0, 100]),
                                             axis=alt.Axis(**axis)),
                                    tooltip=["단원", alt.Tooltip("pct:Q", title="정답률(%)"),
                                             alt.Tooltip("solved:Q", title="푼 문항")])
        bars = base.mark_bar(color=_BLUE, size=16) + base.mark_text(align="left", dx=4, color="#334155").encode(
            text=alt.Text("pct:Q", format=".0f"))
        st.altair_chart(bars.properties(height=34 * len(acc) + 30), use_container_width=True)
    else:
        st.caption("단원별로 풀어 본 문항이 아직 없습니다.")

    boxes = _card_boxes(uid, nb)
    if sum(boxes.values()):
        st.markdown("**🃏 카드 단계** · 오른쪽으로 갈수록 오래 기억하는 카드 (다음 복습까지 간격)")
        df = pd.DataFrame({"단계": list(boxes), "카드": list(boxes.values())})
        base = alt.Chart(df).encode(alt.X("단계:N", sort=list(boxes), title=None, axis=alt.Axis(labelAngle=0, **axis)),
                                    alt.Y("카드:Q", title=None, axis=alt.Axis(tickMinStep=1, **axis)))
        chart = base.mark_bar(color=_BLUE, size=26) + base.mark_text(dy=-7, color="#334155").encode(text="카드:Q")
        st.altair_chart(chart.properties(height=200), use_container_width=True)


def _card_boxes(uid, nb):
    import flashcards
    from store import get_store
    names = ["안 봄", "모름", "1일", "2일", "4일", "8일", "16일+"]
    out = dict.fromkeys(names, 0)
    for d in get_store().sets(uid, nb["id"] if nb else None, with_markdown=True):
        if d.get("kind") != ws.FLASH:
            continue
        for c in flashcards.loads(d["markdown"]):
            if not c.get("reviews"):
                out["안 봄"] += 1
            elif not c.get("box"):
                out["모름"] += 1
            else:
                out[names[min(int(c["box"]) + 1, len(names) - 1)]] += 1
    return out


# ─── 📋 풀이 기록 ───

def _history(uid):
    hist = load_history(uid) if uid else []
    if not hist:
        ui.table([], columns=["#", "날짜", "세트", "총 문항", "정답", "정답률", "틀린 문항 수"])
        st.caption("CBT에서 문항을 다 풀면 자동으로 저장됩니다.")
        return
    avg = sum(r["pct"] for r in hist) / len(hist)
    c1, c2, c3 = st.columns(3)
    c1.metric("풀이 횟수", f"{len(hist)}회")
    c2.metric("평균 정답률", f"{avg:.0f}%")
    c3.metric("최근 정답률", f"{hist[0]['pct']}%")
    rows = [{"#": i + 1, "날짜": r["ts"], "세트": r.get("title") or "-", "총 문항": r["total"],
             "정답": r["correct"], "정답률": f"{r['pct']}%", "틀린 문항 수": len(r["wrong_ids"])}
            for i, r in enumerate(hist)]
    ui.table(rows, height=320, center=("날짜", "정답률"))

    ui.step(None, "오답 재풀이", "회차를 고르면 그 회차에서 틀린 문항만 다시 풉니다.")
    sel = st.selectbox("재풀이할 회차", list(range(len(hist))), key="history_page_sel",
                       format_func=lambda x: f"#{x + 1}  {hist[x]['ts']}  {hist[x].get('title') or ''}  "
                                             f"정답률 {hist[x]['pct']}%")
    rec = hist[sel]
    if not rec["wrong_ids"]:
        st.success("🎉 이 회차는 모든 문항을 맞혔습니다!")
        return
    st.markdown(f"**틀린 문항 ({len(rec['wrong_ids'])}개):** {', '.join(rec['wrong_ids'])}")
    full_text = ws.attempt_markdown(uid, rec)
    if not full_text:
        st.warning("⚠️ 이 회차의 문항을 찾을 수 없습니다 (예전 기록이거나 세트·문항을 지웠음).")
        return
    review_mode = st.radio("복습 모드", CBT_MODES, horizontal=True, key="history_review_mode")
    if st.button("🔁 오답 재풀이 시작", type="primary", use_container_width=True, key=f"hist_start_{sel}"):
        st.session_state.review_qs = get_wrong_questions(parse_cbt_questions(full_text), rec["wrong_ids"])
        st.session_state.review_rec = dict(rec, full_text=full_text)
        st.rerun()
    if st.session_state.get("review_qs"):
        rec = st.session_state.review_rec
        rqs = st.session_state.review_qs
        st.divider()
        st.subheader(f"🔁 오답 재풀이 — {rec['ts']} ({len(rqs)}문항)")
        # 세트·복습 세트에서 나온 기록은 원래 문항에 결과를 이어 적는다
        sources = None
        if rec.get("set_id"):
            sources = {q["id"]: [rec["set_id"], q["id"]] for q in rqs}
        elif rec.get("sources"):
            sources = {q["id"]: rec["sources"][q["id"]] for q in rqs if q["id"] in rec["sources"]}
        render_cbt(rqs, mode=cbt_mode_value(review_mode),
                   session_prefix=f"review_{rec['ts'].replace(' ', '_').replace(':', '')}",
                   user=uid, source_text=rec.get("full_text", ""),
                   title=f"{rec.get('title') or '복습'} (오답 재풀이)", sources=sources)
