"""📒 학습 공간 — 과목 노트북 · 단원 · 세트 · 골라서 복습."""
from datetime import datetime

import streamlit as st

import ui
import workspace as ws
from cbt import parse_cbt_questions, render_cbt
from constants import CBT_MODES, cbt_mode_value
from store import get_store

_NEW = "＋ 새로 만들기"
_NO_UNIT = "단원 미지정"


def _uid() -> str:
    return st.session_state.get("user", "")


# ═════════════════════════ 결과 화면에 붙는 '학습 공간에 저장' 패널 ═════════════════════════

def save_panel(markdown: str, kind: str, default_title: str, key: str) -> str | None:
    """세트를 과목·단원에 저장한다. 저장된 세트 id를 돌려준다 (이후 풀이 기록이 이 세트에 연결됨)."""
    uid = _uid()
    saved = st.session_state.get(f"{key}_saved")
    if saved:
        ui.pills([(f"📒 학습 공간에 저장됨 — {saved['path']}", "ok")])
        return saved["id"]

    nbs = ws.notebooks(uid)
    names = [nb["name"] for nb in nbs]
    k_subj, k_subj_new, k_unit, k_unit_new, k_title = (f"{key}_{x}" for x in ("subj", "subj_new", "unit", "unit_new", "title"))
    st.session_state.setdefault(k_title, default_title)

    def _auto():
        try:
            sug = ws.suggest_classification(uid, markdown)
        except Exception as e:
            st.session_state[f"{key}_err"] = f"자동 분류 실패: {e}"
            return
        if sug["subject"] in names:
            st.session_state[k_subj] = sug["subject"]
            unit_names = [u["name"] for u in nbs[names.index(sug["subject"])].get("units", [])]
            if sug["unit"] in unit_names:
                st.session_state[k_unit] = sug["unit"]
            elif sug["unit"]:
                st.session_state[k_unit], st.session_state[k_unit_new] = _NEW, sug["unit"]
        else:
            st.session_state[k_subj], st.session_state[k_subj_new] = _NEW, sug["subject"]
            st.session_state[k_unit_new] = sug["unit"]
        if sug["title"]:
            st.session_state[k_title] = sug["title"]

    with st.expander("📒 학습 공간에 저장 — 과목·단원별로 모아 두고 나중에 틀린 문항만 복습", expanded=False):
        if st.session_state.get(f"{key}_err"):
            st.warning(st.session_state.pop(f"{key}_err"))
        c1, c2, c3 = st.columns([1, 1, 1.4])
        subj = c1.selectbox("과목", names + [_NEW], key=k_subj)
        if subj == _NEW:
            c1.text_input("새 과목 이름", key=k_subj_new, placeholder="예: 발생학")
            units = []
        else:
            units = [u["name"] for u in nbs[names.index(subj)].get("units", [])]
        if subj == _NEW:
            c2.text_input("단원 (선택)", key=k_unit_new, placeholder="예: 근골격계 발생")
            unit = None
        else:
            unit = c2.selectbox("단원", units + [_NEW, _NO_UNIT], key=k_unit)
            if unit == _NEW:
                c2.text_input("새 단원 이름", key=k_unit_new)
        c3.text_input("세트 제목", key=k_title)
        b1, b2 = st.columns(2)
        b1.button("🤖 자동 분류", key=f"{key}_auto", on_click=_auto, use_container_width=True,
                  help="문항 내용을 보고 과목·단원·제목을 추천합니다 (기존 노트북과 맞춰 줌).")
        if b2.button("💾 저장", key=f"{key}_save", type="primary", use_container_width=True):
            subj_name = st.session_state.get(k_subj_new, "").strip() if subj == _NEW else subj
            if not subj_name:
                st.error("과목 이름을 입력하세요.")
                return None
            nb = ws.find_or_create_notebook(uid, subj_name)
            unit_name = st.session_state.get(k_unit_new, "").strip() if (subj == _NEW or unit == _NEW) else unit
            unit_id = None
            if unit_name and unit_name != _NO_UNIT:
                unit_id = ws.add_unit(uid, nb, unit_name)["id"]
            title = st.session_state.get(k_title, "").strip() or default_title
            st_ = ws.save_set(uid, markdown, kind, title, nb["id"], unit_id)
            path = f"{nb['emoji']} {nb['name']} › {ws.unit_name(nb, unit_id)} › {title}"
            st.session_state[f"{key}_saved"] = {"id": st_["id"], "path": path}
            st.rerun()
    return None


# ═════════════════════════ 학습 공간 페이지 ═════════════════════════

def render() -> None:
    uid = _uid()
    ui.hero("학습 공간", "과목별 노트북에 문항 세트를 모으고, 단원·틀린 문항·기출만 골라 복습합니다.")
    nbs = ws.notebooks(uid)
    current = next((nb for nb in nbs if nb["id"] == st.session_state.get("ws_nb")), None)
    if current:
        _notebook(uid, current)
    else:
        _gallery(uid, nbs)


def _gallery(uid: str, nbs: list) -> None:
    ui.step(1, "내 노트북", "문항 생성·문제지 CBT 결과 화면의 '📒 학습 공간에 저장'으로 세트를 모을 수 있습니다.")
    status = ws.question_status(uid)
    cols = st.columns(3)
    for i, nb in enumerate(nbs):
        s = ws.notebook_stats(uid, nb, status)
        with cols[i % 3], st.container(border=True):
            st.markdown(f'<div class="nb-title">{nb["emoji"]} {nb["name"]}</div>', unsafe_allow_html=True)
            st.caption(" · ".join(u["name"] for u in nb.get("units", [])) or "단원 없음")
            ui.pills([(f"세트 {s['sets']}", "mute"), (f"문항 {s['questions']}", "mute"),
                      (f"❌ {s['wrong']}", "warn" if s["wrong"] else "mute"),
                      (f"🔖 {s['flagged']}", "info" if s["flagged"] else "mute")])
            if st.button("열기", key=f"open_{nb['id']}", use_container_width=True, type="primary"):
                st.session_state.ws_nb = nb["id"]
                st.rerun()
    with cols[len(nbs) % 3], st.container(border=True):
        st.markdown('<div class="nb-title">＋ 새 과목 노트북</div>', unsafe_allow_html=True)
        name = st.text_input("과목 이름", key="ws_new_nb", placeholder="예: 생리학", label_visibility="collapsed")
        if st.button("만들기", key="ws_create", use_container_width=True, disabled=not name.strip()):
            nb = ws.create_notebook(uid, name)
            st.session_state.ws_nb = nb["id"]
            st.rerun()


def _notebook(uid: str, nb: dict) -> None:
    if st.button("← 노트북 목록", key="ws_back"):
        st.session_state.pop("ws_nb", None)
        st.rerun()
    status = ws.question_status(uid)
    s = ws.notebook_stats(uid, nb, status)
    st.markdown(f'<div class="page-title">{nb["emoji"]} {nb["name"]}</div>', unsafe_allow_html=True)
    m = st.columns(4)
    m[0].metric("세트", f"{s['sets']}개")
    m[1].metric("문항", f"{s['questions']}개")
    m[2].metric("틀린 문항", f"{s['wrong']}개")
    m[3].metric("🔖 나중에 확인", f"{s['flagged']}개")

    t_review, t_sets, t_units, t_cfg = st.tabs(["📝 복습 만들기", "📂 세트", "🗂️ 단원", "⚙️ 설정"])
    with t_review:
        _review(uid, nb, status)
    with t_sets:
        _sets(uid, nb, status)
    with t_units:
        _units(uid, nb)
    with t_cfg:
        _settings(uid, nb)


def _unit_rows(uid, nb, status):
    sets = get_store().sets(uid, nb["id"])
    rows = []
    for u in nb.get("units", []) + [{"id": None, "name": _NO_UNIT}]:
        mine = [x for x in sets if x.get("unit_id") == u["id"]]
        if u["id"] is None and not mine:
            continue
        ids = {x["id"] for x in mine}
        rows.append({
            "단원": u["name"], "세트": len(mine), "문항": sum(x.get("n_questions", 0) for x in mine),
            "틀린 문항": sum(1 for (sid, _), q in status.items() if sid in ids and q.last_correct is False),
            "🔖": sum(1 for (sid, _), q in status.items() if sid in ids and q.flagged),
            "안 푼 문항": sum(x.get("n_questions", 0) for x in mine)
                       - sum(1 for (sid, _), q in status.items() if sid in ids and q.tries),
        })
    return rows


def _review(uid, nb, status):
    ui.step(1, "범위", "단원별 현황을 보고 복습할 단원을 고르세요.")
    ui.table(_unit_rows(uid, nb, status), columns=["단원", "세트", "문항", "틀린 문항", "🔖", "안 푼 문항"],
             empty="아직 저장한 세트가 없습니다.")
    unit_opts = {u["name"]: u["id"] for u in nb.get("units", [])}
    unit_opts[_NO_UNIT] = None
    chosen = st.multiselect("단원", list(unit_opts), default=list(unit_opts), key=f"rv_units_{nb['id']}")

    ui.step(2, "출처", "여러 개를 고르면 하나라도 해당하는 문항을 모읍니다.")
    sources = st.multiselect("문항 출처", list(ws.SOURCE_LABEL), default=[ws.SRC_WRONG, ws.SRC_FLAGGED],
                             format_func=ws.SOURCE_LABEL.get, key=f"rv_src_{nb['id']}")
    c1, c2, c3 = st.columns([1, 1, 2])
    limit = c1.number_input("최대 문항 수 (0 = 전부)", 0, 200, 20, key=f"rv_n_{nb['id']}")
    shuffle = c2.checkbox("순서 섞기", value=True, key=f"rv_shuf_{nb['id']}")
    mode = c3.radio("풀이 방식", CBT_MODES, horizontal=True, key=f"rv_mode_{nb['id']}")

    if st.button("📝 복습 시작", type="primary", use_container_width=True, disabled=not (chosen and sources),
                 key=f"rv_go_{nb['id']}"):
        md, mapping, total = ws.build_review(uid, nb, [unit_opts[c] for c in chosen], sources, int(limit), shuffle)
        if not mapping:
            st.info("조건에 맞는 문항이 없습니다. 출처나 단원을 바꿔 보세요.")
            st.session_state.pop("ws_review", None)
        else:
            label = ", ".join(ws.SOURCE_LABEL[s].split(" ", 1)[1].split(" (")[0] for s in sources)
            st.session_state.ws_review = {
                "nb": nb["id"], "md": md, "map": mapping, "total": total,
                "ts": datetime.now().strftime("%Y%m%d%H%M%S"),
                "title": f"복습: {nb['name']} — {label}",
            }
    rv = st.session_state.get("ws_review")
    if rv and rv["nb"] == nb["id"]:
        st.divider()
        st.markdown(f"**{rv['title']}** · 조건에 맞는 {rv['total']}문항 중 {len(rv['map'])}문항")
        render_cbt(parse_cbt_questions(rv["md"]), mode=cbt_mode_value(mode), session_prefix=f"ws_rv_{rv['ts']}",
                   user=uid, source_text=rv["md"], title=rv["title"], sources=rv["map"])


def _sets(uid, nb, status):
    sets = get_store().sets(uid, nb["id"])
    rows = []
    for x in reversed(sets):
        solved = [q for (sid, _), q in status.items() if sid == x["id"] and q.tries]
        wrong = sum(1 for q in solved if q.last_correct is False)
        rows.append({"제목": x["title"], "종류": ws.KIND_LABEL.get(x["kind"], x["kind"]),
                     "단원": ws.unit_name(nb, x.get("unit_id")), "문항": x.get("n_questions", 0),
                     "푼 문항": len(solved), "틀린 문항": wrong, "저장일": x.get("created_at", "")[:10]})
    ui.table(rows, columns=["제목", "종류", "단원", "문항", "푼 문항", "틀린 문항", "저장일"], height=360,
             center=("종류", "단원", "저장일"), empty="저장한 세트가 없습니다.")
    if not sets:
        return
    by_label = {f"{x['title']} ({x.get('created_at', '')[:10]})": x for x in reversed(sets)}
    pick = by_label[st.selectbox("세트 선택", list(by_label), key=f"set_pick_{nb['id']}")]
    c1, c2, c3 = st.columns([1, 1.4, 1])
    if c1.button("▶ 이 세트 풀기", key=f"set_solve_{nb['id']}", type="primary", use_container_width=True):
        st.session_state.ws_solve = {"id": pick["id"], "ts": datetime.now().strftime("%Y%m%d%H%M%S")}
    unit_opts = {u["name"]: u["id"] for u in nb.get("units", [])}
    unit_opts[_NO_UNIT] = None
    target = c2.selectbox("단원 옮기기", list(unit_opts), key=f"set_mv_{nb['id']}", label_visibility="collapsed")
    if c2.button("단원 옮기기", key=f"set_mv_btn_{nb['id']}", use_container_width=True):
        ws.move_set(uid, pick["id"], nb["id"], unit_opts[target])
        st.rerun()
    confirm = c3.checkbox("삭제 확인", key=f"set_del_ok_{nb['id']}")
    if c3.button("🗑 삭제", key=f"set_del_{nb['id']}", disabled=not confirm, use_container_width=True):
        ws.delete_set(uid, pick["id"])
        st.session_state.pop("ws_solve", None)
        st.rerun()

    solve = st.session_state.get("ws_solve")
    if solve:
        full = get_store().get_set(uid, solve["id"])
        if full and full.get("notebook_id") == nb["id"]:
            st.divider()
            mode = st.radio("풀이 방식", CBT_MODES, horizontal=True, key=f"set_mode_{nb['id']}")
            render_cbt(parse_cbt_questions(full["markdown"]), mode=cbt_mode_value(mode),
                       session_prefix=f"ws_set_{solve['ts']}", user=uid, source_text=full["markdown"],
                       title=full["title"], set_id=full["id"])


def _units(uid, nb):
    units = nb.get("units", [])
    if units:
        for u in units:
            c1, c2, c3 = st.columns([3, 1, 1])
            new = c1.text_input("단원 이름", value=u["name"], key=f"unit_name_{u['id']}", label_visibility="collapsed")
            if c2.button("이름 변경", key=f"unit_ren_{u['id']}", use_container_width=True, disabled=new.strip() in ("", u["name"])):
                ws.rename_unit(uid, nb, u["id"], new)
                st.rerun()
            if c3.button("삭제", key=f"unit_del_{u['id']}", use_container_width=True,
                         help="단원만 지우고, 그 단원의 세트는 '단원 미지정'으로 남깁니다."):
                ws.delete_unit(uid, nb, u["id"])
                st.rerun()
    else:
        st.caption("아직 단원이 없습니다.")
    c1, c2 = st.columns([3, 1])
    name = c1.text_input("새 단원", key=f"unit_new_{nb['id']}", placeholder="예: 근골격계 발생", label_visibility="collapsed")
    if c2.button("＋ 단원 추가", key=f"unit_add_{nb['id']}", use_container_width=True, disabled=not name.strip()):
        ws.add_unit(uid, nb, name)
        st.rerun()


def _settings(uid, nb):
    c1, c2 = st.columns([1, 3])
    emoji = c1.selectbox("아이콘", ws.EMOJIS, index=ws.EMOJIS.index(nb["emoji"]) if nb["emoji"] in ws.EMOJIS else 0,
                         key=f"nb_emoji_{nb['id']}")
    name = c2.text_input("과목 이름", value=nb["name"], key=f"nb_name_{nb['id']}")
    if st.button("저장", key=f"nb_save_{nb['id']}"):
        nb["emoji"], nb["name"] = emoji, name.strip() or nb["name"]
        get_store().save_notebook(uid, nb)
        st.rerun()
    st.divider()
    ok = st.checkbox("이 노트북과 안의 세트를 모두 삭제합니다 (풀이 기록은 남음).", key=f"nb_del_ok_{nb['id']}")
    if st.button("🗑 노트북 삭제", key=f"nb_del_{nb['id']}", disabled=not ok):
        get_store().delete_notebook(uid, nb["id"])
        st.session_state.pop("ws_nb", None)
        st.rerun()
