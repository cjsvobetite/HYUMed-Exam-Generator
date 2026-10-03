"""📄 문제지 CBT — 문제지·복기 PDF를 올려 CBT로 풀고 해설지를 받는다."""
import copy
import hashlib
import os
from datetime import datetime

import streamlit as st

import ui
from cbt import parse_cbt_questions, render_cbt
from config import OUTPUTS_DIR
from constants import BRAND, TERM_LANG_OPTIONS, TERM_LANG_RULE, VIEW_MODES, VIEW_PREVIEW, cbt_mode_value
from exam_import import EXAM_TYPES, read_exam, solve_exam, to_markdown
from llm import MODELS
from pdf_export import build_pdf

_READ_MODELS = ["gpt-4o", "gpt-4.1", "gpt-5", "o4-mini", "gpt-4o-mini"]
_FILL = "🛠️ AI가 보완해서 풀기"
_MARK = "🏷️ 그대로 두고 '(문항 복기 불완전)' 표시"
_INCOMPLETE_HELP = {
    _FILL: "빠진 발문·선지를 AI가 출제 의도에 맞게 채우고 **(AI 보완)** 배지를 붙입니다. "
           "원래 있던 내용은 바꾸지 않습니다.",
    _MARK: "내용은 손대지 않고 **(문항 복기 불완전)** 배지만 붙입니다. 빠진 선지는 '(복기 안 됨)'으로 "
           "자리만 남기고, 남은 정보로 판단할 수 있을 때만 정답을 매깁니다. 정답이 없는 문항은 채점에서 빠집니다.",
}


def render() -> None:
    ui.hero("문제지 CBT", "문제지·족보·복기 파일을 올리면 CBT로 풀고 해설지까지 받습니다.")

    # ── 1. 업로드 ──
    ui.step(1, "문제지 올리기", "PDF, 사진(JPG/PNG), 텍스트 모두 됩니다. 여러 파일은 올린 순서대로 이어 붙입니다.")
    with st.container(border=True):
        tab_file, tab_text = st.tabs(["📁 파일", "✏️ 복기 텍스트 붙여넣기"])
        with tab_file:
            files = st.file_uploader("문제지 파일", type=EXAM_TYPES, accept_multiple_files=True,
                                     key="exam_files", label_visibility="collapsed")
        with tab_text:
            pasted = st.text_area("복기 텍스트", height=180, key="exam_pasted",
                                  placeholder="1. 다음 중 심근경색의 ...\n① ...\n② ...")
        c1, c2 = st.columns([1, 2])
        read_model = c1.selectbox("읽기 모델 (비전)", _READ_MODELS, key="exam_read_model",
                                  help="페이지 이미지를 보고 문항·선지·그림 위치를 찾습니다.")
        c2.markdown("")
        c2.caption("그림·사진·ECG·영상 등이 있는 문항은 그림을 잘라 문항에 붙입니다. "
                   "PDF에 이미지가 들어 있으면 원본 그대로, 스캔본이면 그림 영역을 찾아 잘라냅니다.")
        sig = _signature(files, pasted)
        has_input = bool(files) or bool(pasted.strip())
        if st.button("📖 문제지 읽기", type="primary", use_container_width=True, disabled=not has_input):
            _read(files, pasted, read_model, sig)

    read = st.session_state.get("exam_read")
    if not read:
        return
    if read["sig"] != sig and has_input:
        st.info("올린 파일이 바뀌었습니다. 다시 읽으려면 **📖 문제지 읽기**를 누르세요.")

    # ── 2. 확인 ──
    qs = read["questions"]
    ui.step(2, "읽은 문항 확인", f"{read['pages']}쪽에서 문항 {len(qs)}개를 찾았습니다.")
    for w in read["warnings"]:
        st.warning(w)
    if not qs:
        st.error("문항을 찾지 못했습니다. 파일이 문제지인지 확인하거나 다른 읽기 모델로 다시 시도하세요.")
        return
    n_incomplete = sum(q.incomplete for q in qs)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("문항", f"{len(qs)}개")
    m2.metric("복기 불완전", f"{n_incomplete}개")
    m3.metric("그림 포함", f"{sum(bool(q.images) for q in qs)}개")
    m4.metric("정답 표기됨", f"{sum(q.given_answer for q in qs)}개")
    with st.expander("문항 목록 보기", expanded=n_incomplete > 0):
        ui.table([{
            "번호": q.number,
            "발문": (q.stem.splitlines() or [""])[0][:60],
            "선지": len(q.choices),
            "상태": " · ".join(filter(None, [
                "복기 불완전" if q.incomplete else "",
                f"그림 {len(q.images)}" if q.images else "",
                "정답 있음" if q.given_answer else "",
            ])) or "정상",
            "빠진 부분": q.incomplete_note,
        } for q in qs], height=420, center=("번호", "상태"))

    # ── 3. 해설 ──
    ui.step(3, "해설지 만들기")
    with st.container(border=True):
        if n_incomplete:
            mode_label = st.radio(f"불완전한 문항 {n_incomplete}개 처리 방법", [_FILL, _MARK],
                                  index=1, key="exam_incomplete_mode")
            st.caption(_INCOMPLETE_HELP[mode_label])
        else:
            mode_label = _MARK
            ui.pills([("불완전한 문항 없음", "ok")])
        s1, s2, s3 = st.columns([1, 1.4, 1])
        solve_model = s1.selectbox("해설 모델", MODELS, key="exam_solve_model")
        term_label = s2.selectbox("해설 의학용어 표기", list(TERM_LANG_OPTIONS.keys()), index=2,
                                  key="exam_term")
        s3.markdown("")
        with_expl = s3.checkbox("AI 해설 생성", value=True, key="exam_with_expl",
                                help="끄면 문제지에 적힌 정답·해설만 씁니다 (API 비용 없음).")
        if st.button("💡 해설 만들고 CBT 시작" if with_expl else "▶️ 바로 CBT 시작",
                     type="primary", use_container_width=True):
            _solve(read, "fill" if mode_label == _FILL else "mark", solve_model,
                   TERM_LANG_RULE[TERM_LANG_OPTIONS[term_label]], with_expl)

    # ── 4. 풀기 ──
    result = st.session_state.get("exam_result")
    if not result or result["read_id"] != read["id"]:
        return
    ui.step(4, "풀기")
    top_l, top_r1, top_r2 = st.columns([3, 1, 1])
    view = top_l.radio("보기 방식", VIEW_MODES, index=1, horizontal=True, key="exam_view",
                       label_visibility="collapsed")
    top_r1.download_button("📄 해설지 PDF", data=result["pdf"], file_name=f"{result['base']}.pdf",
                           mime="application/pdf", type="primary", use_container_width=True,
                           key="exam_pdf_dl", help="문제지 + 정답·해설 분리 (그림 포함)")
    top_r2.download_button("⬇️ 마크다운", data=result["md"].encode("utf-8"),
                           file_name=f"{result['base']}.md", mime="text/markdown",
                           use_container_width=True, key="exam_md_dl")
    for w in result["warnings"]:
        st.warning(w)
    if view == VIEW_PREVIEW:
        ui.render_markdown(result["md"])
    else:
        render_cbt(parse_cbt_questions(result["md"]), mode=cbt_mode_value(view),
                   session_prefix=f"exam_{result['base']}", user=st.session_state.get("user", ""),
                   source_text=result["md"], title=result["title"])


def _signature(files, pasted: str) -> str:
    h = hashlib.sha1()
    for f in files or []:
        h.update(f.name.encode())
        h.update(hashlib.sha1(f.getvalue()).digest())
    h.update(pasted.strip().encode())
    return h.hexdigest()


def _read(files, pasted, model, sig) -> None:
    bar = st.progress(0.0, text="문제지를 읽는 중...")

    def on_progress(done, total):
        bar.progress(done / total, text=f"문제지를 읽는 중... ({done}/{total}쪽)")

    try:
        result = read_exam([(f.name, f.getvalue()) for f in files or []], model=model,
                           pasted_text=pasted, on_progress=on_progress)
    except Exception as e:
        bar.empty()
        st.error(f"읽기 실패: {e}")
        return
    bar.empty()
    names = [f.name for f in files or []] or ["붙여넣은 텍스트"]
    st.session_state["exam_read"] = {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S_%f"),
        "sig": sig,
        "title": names[0] if len(names) == 1 else f"{names[0]} 외 {len(names) - 1}개",
        "questions": result.questions,
        "warnings": result.warnings,
        "pages": result.pages,
    }
    st.session_state.pop("exam_result", None)


def _solve(read, incomplete_mode, model, term_rule, with_expl) -> None:
    questions = copy.deepcopy(read["questions"])     # 읽은 결과는 그대로 둬서 옵션을 바꿔 다시 만들 수 있게
    warnings = []
    if with_expl:
        bar = st.progress(0.0, text="정답·해설을 만드는 중...")

        def on_progress(done, total):
            bar.progress(done / total, text=f"정답·해설을 만드는 중... ({done}/{total})")

        try:
            warnings = solve_exam(questions, model=model, incomplete_mode=incomplete_mode,
                                  term_rule=term_rule, on_progress=on_progress)
        except Exception as e:
            bar.empty()
            st.error(f"해설 생성 실패: {e}")
            return
        bar.empty()

    md = to_markdown(questions)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{BRAND}_문제지_{ts}"
    pdf = build_pdf(md, title=f"{read['title']} — 문제지·해설")
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    with open(os.path.join(OUTPUTS_DIR, f"{base}.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(OUTPUTS_DIR, f"{base}.pdf"), "wb") as f:
        f.write(pdf)
    st.session_state["exam_result"] = {
        "read_id": read["id"], "md": md, "pdf": pdf, "base": base,
        "title": f"문제지: {read['title']}", "warnings": warnings,
    }
