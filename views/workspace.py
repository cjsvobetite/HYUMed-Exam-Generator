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


# ═════════════════════════ 결과 화면의 '📒 내 노트북에 저장' 허브 ═════════════════════════

def save_hub(markdown: str, kind: str, default_title: str, key: str, term_rule: str = "") -> str | None:
    """문항 세트와 플래시카드를 과목·단원 노트북에 저장한다.
    저장된 문항 세트 id를 돌려준다 (이후 CBT 풀이 기록이 이 세트에 연결됨).
    플래시카드는 세션의 f"{key}_cards"에 미리 만들어 둘 수 있다 (문항 생성 시 자동 생성 옵션)."""
    uid = _uid()
    saved_set = st.session_state.get(f"{key}_saved_set")
    saved_deck = st.session_state.get(f"{key}_saved_deck")
    cards = st.session_state.get(f"{key}_cards")
    n_q = len(parse_cbt_questions(markdown))

    with st.container(border=True, key=f"{key}_hub"):
        st.markdown('<div class="hub-hd">📒 내 노트북에 저장</div>'
                    '<div class="hub-sub">과목·단원 노트북에 모아 두면 틀린 문항·🚩 표시 문항·모르는 카드만 골라 다시 볼 수 있어요.</div>',
                    unsafe_allow_html=True)
        t1, t2 = st.columns(2)
        with t1:
            st.markdown(f"**📝 문항 세트** · {n_q}문항")
            ui.pills([(f"✅ 저장됨 — {saved_set['path']}", "ok")] if saved_set else [("아직 저장 안 함", "warn")])
        with t2:
            if cards is None:
                st.markdown("**🃏 플래시카드** · 아직 안 만듦")
                if st.button("🃏 이 문항들로 플래시카드 만들기", key=f"{key}_mkcards", use_container_width=True,
                             help="문항마다 핵심 사실을 앞면(질문)·뒷면(답+이유) 카드로 만듭니다."):
                    _make_cards(markdown, key, term_rule)
                    st.rerun()
            else:
                st.markdown(f"**🃏 플래시카드** · {len(cards)}장")
                ui.pills([(f"✅ 저장됨 — {saved_deck['path']}", "ok")] if saved_deck else [("아직 저장 안 함", "warn")])
        if st.session_state.get(f"{key}_err"):
            st.warning(st.session_state.pop(f"{key}_err"))
        if cards:
            with st.expander(f"🃏 플래시카드 미리보기 ({len(cards)}장)"):
                ui.table([{"앞면": c["front"], "뒷면": c["back"]} for c in cards[:30]], columns=["앞면", "뒷면"],
                         height=320)

        can_set = not saved_set
        can_deck = bool(cards) and not saved_deck
        if can_set or can_deck:
            _save_form(uid, markdown, kind, default_title, key, cards, can_set, can_deck)
        if saved_set or saved_deck:
            nb_id = (saved_set or saved_deck)["nb"]
            if st.button("📒 노트북 열기", key=f"{key}_open", use_container_width=not (can_set or can_deck)):
                st.session_state.ws_nb = nb_id
                page = st.session_state.get("_pages", {}).get("workspace")
                if page:
                    st.switch_page(page)
    return saved_set["id"] if saved_set else None


def _make_cards(markdown: str, key: str, term_rule: str) -> None:
    import flashcards
    with st.spinner("🃏 플래시카드 만드는 중..."):
        try:
            st.session_state[f"{key}_cards"] = flashcards.make_flashcards(markdown, term_rule=term_rule)
        except Exception as e:
            st.session_state[f"{key}_err"] = f"플래시카드 생성 실패: {e}"


def _save_form(uid, markdown, kind, default_title, key, cards, can_set, can_deck):
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

    c1, c2, c3 = st.columns([1, 1, 1.4])
    subj = c1.selectbox("과목", names + [_NEW], key=k_subj)
    if subj == _NEW:
        c1.text_input("새 과목 이름", key=k_subj_new, placeholder="예: 발생학")
        c2.text_input("단원 (선택)", key=k_unit_new, placeholder="예: 근골격계 발생")
        unit = None
    else:
        units = [u["name"] for u in nbs[names.index(subj)].get("units", [])]
        unit = c2.selectbox("단원", units + [_NEW, _NO_UNIT], key=k_unit)
        if unit == _NEW:
            c2.text_input("새 단원 이름", key=k_unit_new)
    c3.text_input("제목", key=k_title)

    w1, w2, b1, b2 = st.columns([1, 1, 1, 1.2])
    # 저장 가능 여부가 바뀌면(예: 카드를 나중에 만듦) 체크박스를 새로 만들어 기본값(체크)을 다시 적용한다
    want_set = w1.checkbox("📝 문항 세트", value=can_set, disabled=not can_set, key=f"{key}_want_set_{int(can_set)}")
    want_deck = w2.checkbox("🃏 플래시카드", value=can_deck, disabled=not can_deck,
                            key=f"{key}_want_deck_{int(can_deck)}")
    b1.button("🤖 자동 분류", key=f"{key}_auto", on_click=_auto, use_container_width=True,
              help="문항 내용을 보고 과목·단원·제목을 추천합니다 (기존 노트북과 맞춰 줌).")
    if b2.button("💾 노트북에 저장", key=f"{key}_save", type="primary", use_container_width=True,
                 disabled=not ((want_set and can_set) or (want_deck and can_deck))):
        subj_name = st.session_state.get(k_subj_new, "").strip() if subj == _NEW else subj
        if not subj_name:
            st.error("과목 이름을 입력하세요.")
            return
        nb = ws.find_or_create_notebook(uid, subj_name)
        unit_name = st.session_state.get(k_unit_new, "").strip() if (subj == _NEW or unit == _NEW) else unit
        unit_id = ws.add_unit(uid, nb, unit_name)["id"] if unit_name and unit_name != _NO_UNIT else None
        title = st.session_state.get(k_title, "").strip() or default_title
        where = f"{nb['emoji']} {nb['name']} › {ws.unit_name(nb, unit_id)}"
        set_id = (st.session_state.get(f"{key}_saved_set") or {}).get("id")
        if want_set and can_set:
            set_id = ws.save_set(uid, markdown, kind, title, nb["id"], unit_id)["id"]
            st.session_state[f"{key}_saved_set"] = {"id": set_id, "nb": nb["id"], "path": f"{where} › {title}"}
        if want_deck and can_deck:
            deck = ws.save_deck(uid, cards, f"{title} · 플래시카드", nb["id"], unit_id, source_set_id=set_id)
            st.session_state[f"{key}_saved_deck"] = {"id": deck["id"], "nb": nb["id"], "path": where}
        st.toast(f"📒 {where}에 저장했습니다.")
        st.rerun()


# 이전 이름 호환
save_panel = save_hub


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
    ui.step(1, "내 노트북", "AI 문항 생성·문제지 CBT 결과 화면 아래 '📒 내 노트북에 저장'에서 문항 세트와 플래시카드를 모을 수 있습니다.")
    status = ws.question_status(uid)
    cols = st.columns(3)
    for i, nb in enumerate(nbs):
        s = ws.notebook_stats(uid, nb, status)
        with cols[i % 3], st.container(border=True):
            st.markdown(f'<div class="nb-title">{nb["emoji"]} {nb["name"]}</div>', unsafe_allow_html=True)
            st.caption(" · ".join(u["name"] for u in nb.get("units", [])) or "단원 없음")
            ui.pills([(f"세트 {s['sets']}", "mute"), (f"문항 {s['questions']}", "mute"),
                      (f"🃏 {s['cards']}", "mute"),
                      (f"❌ {s['wrong']}", "warn" if s["wrong"] else "mute"),
                      (f"🚩 {s['flagged']}", "info" if s["flagged"] else "mute")])
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
    m = st.columns(5)
    m[0].metric("문항 세트", f"{s['sets']}개")
    m[1].metric("문항", f"{s['questions']}개")
    m[2].metric("틀린 문항", f"{s['wrong']}개")
    m[3].metric("🚩 표시한 문항", f"{s['flagged']}개")
    m[4].metric("🃏 플래시카드", f"{s['cards']}장")

    t_review, t_flash, t_sets, t_units, t_cfg = st.tabs(
        ["📝 복습 만들기", "🃏 플래시카드", "📂 세트·덱", "🗂️ 단원", "⚙️ 설정"])
    with t_review:
        _review(uid, nb, status)
    with t_flash:
        _flash(uid, nb)
    with t_sets:
        _sets(uid, nb, status)
    with t_units:
        _units(uid, nb)
    with t_cfg:
        _settings(uid, nb)


def _unit_rows(uid, nb, status):
    all_sets = get_store().sets(uid, nb["id"])
    sets = [x for x in all_sets if x.get("kind") != ws.FLASH]
    decks = [x for x in all_sets if x.get("kind") == ws.FLASH]
    rows = []
    for u in nb.get("units", []) + [{"id": None, "name": _NO_UNIT}]:
        mine = [x for x in sets if x.get("unit_id") == u["id"]]
        my_cards = sum(x.get("n_questions", 0) for x in decks if x.get("unit_id") == u["id"])
        if u["id"] is None and not mine and not my_cards:
            continue
        ids = {x["id"] for x in mine}
        rows.append({
            "단원": u["name"], "세트": len(mine), "문항": sum(x.get("n_questions", 0) for x in mine),
            "틀린 문항": sum(1 for (sid, _), q in status.items() if sid in ids and q.last_correct is False),
            "🚩": sum(1 for (sid, _), q in status.items() if sid in ids and q.flagged),
            "안 푼 문항": sum(x.get("n_questions", 0) for x in mine)
                       - sum(1 for (sid, _), q in status.items() if sid in ids and q.tries),
            "🃏 카드": my_cards,
        })
    return rows


def _review(uid, nb, status):
    ui.step(1, "범위", "단원별 현황을 보고 복습할 단원을 고르세요.")
    ui.table(_unit_rows(uid, nb, status), columns=["단원", "세트", "문항", "틀린 문항", "🚩", "안 푼 문항", "🃏 카드"],
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
        if x.get("kind") == ws.FLASH:
            cards = ws.deck_cards(uid, x["id"])
            done = sum(1 for c in cards if c.get("reviews"))
            wrong = sum(1 for c in cards if c.get("known") is False)
        else:
            solved = [q for (sid, _), q in status.items() if sid == x["id"] and q.tries]
            done, wrong = len(solved), sum(1 for q in solved if q.last_correct is False)
        rows.append({"제목": x["title"], "종류": ws.KIND_LABEL.get(x["kind"], x["kind"]),
                     "단원": ws.unit_name(nb, x.get("unit_id")), "문항·카드": x.get("n_questions", 0),
                     "학습함": done, "틀림·모름": wrong, "저장일": x.get("created_at", "")[:10]})
    ui.table(rows, columns=["제목", "종류", "단원", "문항·카드", "학습함", "틀림·모름", "저장일"], height=360,
             center=("종류", "단원", "저장일"), empty="저장한 세트가 없습니다.")
    if not sets:
        return
    by_label = {f"{x['title']} ({x.get('created_at', '')[:10]})": x for x in reversed(sets)}
    pick = by_label[st.selectbox("세트 선택", list(by_label), key=f"set_pick_{nb['id']}")]
    c1, c2, c3 = st.columns([1, 1.4, 1])
    is_deck = pick.get("kind") == ws.FLASH
    if c1.button("▶ 카드 학습" if is_deck else "▶ 이 세트 풀기", key=f"set_solve_{nb['id']}", type="primary",
                 use_container_width=True):
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
        if full and full.get("notebook_id") == nb["id"] and full.get("kind") == ws.FLASH:
            st.divider()
            _flash_session(uid, nb, f"fcset_{solve['ts']}", [(full["id"], c) for c in ws.deck_cards(uid, full["id"])])
        elif full and full.get("notebook_id") == nb["id"]:
            st.divider()
            mode = st.radio("풀이 방식", CBT_MODES, horizontal=True, key=f"set_mode_{nb['id']}")
            render_cbt(parse_cbt_questions(full["markdown"]), mode=cbt_mode_value(mode),
                       session_prefix=f"ws_set_{solve['ts']}", user=uid, source_text=full["markdown"],
                       title=full["title"], set_id=full["id"])


# ─── 🃏 플래시카드 학습 ───

def _flash(uid, nb):
    decks = [x for x in get_store().sets(uid, nb["id"]) if x.get("kind") == ws.FLASH]
    if not decks:
        st.info("아직 플래시카드 덱이 없습니다. AI 문항 생성·문제지 CBT 결과 화면의 '📒 내 노트북에 저장'에서 "
                "🃏 플래시카드를 만들어 저장하세요.")
        return
    labels = {f"{d['title']} · {ws.unit_name(nb, d.get('unit_id'))} ({d.get('n_questions', 0)}장)": d for d in reversed(decks)}
    chosen = st.multiselect("덱", list(labels), default=list(labels), key=f"fc_decks_{nb['id']}")
    c1, c2 = st.columns([2, 1])
    which = c1.radio("카드", ["전체", "❌ 모르는 카드만", "🆕 안 본 카드만"], horizontal=True, key=f"fc_which_{nb['id']}")
    shuffle = c2.checkbox("순서 섞기", value=True, key=f"fc_shuf_{nb['id']}")
    if st.button("🃏 학습 시작", type="primary", use_container_width=True, disabled=not chosen, key=f"fc_go_{nb['id']}"):
        pool = []
        for lab in chosen:
            for c in ws.deck_cards(uid, labels[lab]["id"]):
                if which.startswith("❌") and c.get("known") is not False:
                    continue
                if which.startswith("🆕") and c.get("reviews"):
                    continue
                pool.append((labels[lab]["id"], c))
        if shuffle:
            import random
            random.shuffle(pool)
        st.session_state[f"fc_pool_{nb['id']}"] = {"ts": datetime.now().strftime("%H%M%S%f"), "pool": pool}
    run = st.session_state.get(f"fc_pool_{nb['id']}")
    if run:
        if not run["pool"]:
            st.info("조건에 맞는 카드가 없습니다.")
        else:
            st.divider()
            _flash_session(uid, nb, f"fc_{nb['id']}_{run['ts']}", run["pool"])


@st.fragment
def _flash_session(uid, nb, key, pool):
    """카드 한 장씩: 앞면 → 뒤집기 → 알아요/몰라요. 결과는 덱에 기록된다."""
    import html as _html

    stt = st.session_state.setdefault(key, {"i": 0, "flipped": False, "known": 0, "missed": [], "pool": list(pool)})
    pool = stt["pool"]                       # '몰랐던 카드 다시'로 바뀐 카드 목록을 이어서 쓴다
    total = len(pool)
    if stt["i"] >= total:
        k, m = stt["known"], len(stt["missed"])
        st.success(f"🎉 {total}장 학습 완료 — ✅ 알아요 {k}장 · ❌ 몰라요 {m}장")
        b1, b2 = st.columns(2)
        if m and b1.button(f"❌ 몰랐던 {m}장 다시", key=f"{key}_again", type="primary", use_container_width=True):
            st.session_state[key] = {"i": 0, "flipped": False, "known": 0, "missed": [], "pool": stt["missed"]}
            st.rerun(scope="fragment")
        if b2.button("처음부터 다시", key=f"{key}_restart", use_container_width=True):
            st.session_state[key] = {"i": 0, "flipped": False, "known": 0, "missed": [], "pool": pool}
            st.rerun(scope="fragment")
        return

    deck_id, card = pool[stt["i"]]
    st.markdown(f"**{stt['i'] + 1} / {total}** · ✅ {stt['known']} · ❌ {len(stt['missed'])}")
    st.progress(stt["i"] / total)
    esc = lambda t: _html.escape(t).replace("\n", "<br>")
    back = (f'<div class="fc-back"><div class="fc-side">뒷면</div>{esc(card["back"])}</div>'
            if stt["flipped"] else "")
    st.markdown(f'<div class="fc-card"><div class="fc-side">앞면</div><div class="fc-text">{esc(card["front"])}</div>'
                f'{back}</div>', unsafe_allow_html=True)

    def _flip():
        stt["flipped"] = True

    def _rate(known):
        ws.rate_card(uid, deck_id, card["id"], known)
        if known:
            stt["known"] += 1
        else:
            stt["missed"].append((deck_id, card))
        stt["i"] += 1
        stt["flipped"] = False

    if not stt["flipped"]:
        st.button("🔄 뒤집기", key=f"{key}_flip_{stt['i']}", on_click=_flip, type="primary", use_container_width=True)
    else:
        b1, b2 = st.columns(2)
        b1.button("❌ 몰라요", key=f"{key}_no_{stt['i']}", on_click=_rate, args=(False,), use_container_width=True)
        b2.button("✅ 알아요", key=f"{key}_yes_{stt['i']}", on_click=_rate, args=(True,), type="primary",
                  use_container_width=True)


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
