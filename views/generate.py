import os
from datetime import datetime

import streamlit as st

import ui
from cbt import parse_cbt_questions, render_cbt
from config import OUTPUTS_DIR
from constants import (ANSWER_FORMATS, BRAND, CONTENT_TYPES, DEFAULT_ANSWER_FORMATS, DIFFICULTIES,
                       OCR_MODE_OPTIONS, TERM_LANG_OPTIONS, TERM_LANG_RULE, VIEW_CBT_PER_Q, VIEW_MODES,
                       VIEW_PREVIEW, cbt_mode_value)
from extractors import ALL_TYPES, IMAGE_TYPES, TEXT_TYPES, OCRConfig, estimate_tokens, extract_bytes, tesseract_available
from llm import MODELS
from pdf_export import autonumber_choices, build_pdf
from question_generator import BLUEPRINT, REPLACE, STATUS, generate_questions


@st.cache_data(show_spinner=False, max_entries=64)
def _extract_cached(name: str, data: bytes, ocr: OCRConfig) -> str:
    return extract_bytes(name, data, ocr)


def _extract_all(files, ocr: OCRConfig) -> str:
    """업로드 파일들을 텍스트로. 같은 파일·설정이면 캐시를 써서 rerun마다 OCR을 다시 돌리지 않는다."""
    if not files:
        return ""
    out = []
    for f in files:
        with st.spinner(f"📄 {f.name} 텍스트 추출 중{' (OCR)' if ocr.enabled else ''}..."):
            try:
                text = _extract_cached(f.name, f.getvalue(), ocr)
            except Exception as e:
                st.error(f"{f.name} 추출 실패: {e}")
                continue
        if text.strip():
            out.append(text)
        else:
            st.warning(f"⚠️ {f.name}에서 텍스트를 찾지 못했습니다. 스캔본이면 OCR을 켜세요.")
    return "\n\n".join(out)


def _ocr_settings() -> OCRConfig:
    with st.expander("🔍 OCR 설정 — 스캔본·사진·슬라이드 그림 속 글자 인식", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            label = st.radio("OCR 모드", list(OCR_MODE_OPTIONS.keys()), index=1, key="ocr_mode",
                             help="자동: 글자를 읽을 수 없는 스캔 PDF 페이지·이미지·슬라이드 그림만 OCR합니다.")
        mode = OCR_MODE_OPTIONS[label]
        engine, model = "openai", "gpt-4o-mini"
        if mode != "off":
            engines = ["OpenAI 비전 (정확, 유료)"]
            if tesseract_available():
                engines.append("Tesseract (무료, 로컬)")
            with c2:
                if st.selectbox("OCR 엔진", engines, key="ocr_engine").startswith("Tesseract"):
                    engine = "tesseract"
            if engine == "openai":
                with c3:
                    model = st.selectbox("OCR 모델", ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"], key="ocr_model")
    return OCRConfig(mode=mode, engine=engine, model=model)


def render() -> None:
    ui.hero("AI 문항 생성", "강의 자료와 전사본으로 시험 대비 문항 세트를 만듭니다.")

    # ── 1. 자료 ──
    ui.step(1, "자료 올리기", "강의 자료와 전사본 중 하나 이상이 필요합니다. 전사본 내용을 우선 반영합니다.")
    col1, col2 = st.columns(2)
    with col1, st.container(border=True):
        st.markdown("**📚 강의 자료**")
        lecture_files = st.file_uploader("PDF / PPTX / TXT / 이미지", type=ALL_TYPES,
                                         accept_multiple_files=True, key="lecture")
    with col2, st.container(border=True):
        st.markdown("**🎙️ 강의 전사본**")
        tab_file, tab_text = st.tabs(["📁 파일", "✏️ 직접 입력"])
        with tab_file:
            transcript_files = st.file_uploader("TXT / MD / 이미지", type=TEXT_TYPES + IMAGE_TYPES,
                                                accept_multiple_files=True, key="transcript")
        with tab_text:
            st.text_area("전사본 붙여넣기", height=140, key="transcript_direct_input",
                         placeholder="강의 전사본 텍스트를 붙여넣으세요...")
    ocr = _ocr_settings()

    lecture_text = _extract_all(lecture_files, ocr)
    transcript_text = "\n\n".join(filter(None, [
        _extract_all(transcript_files, ocr),
        st.session_state.get("transcript_direct_input", "").strip(),
    ]))
    if lecture_text or transcript_text:
        tokens_in = estimate_tokens(lecture_text + transcript_text)
        ui.pills([(f"강의 자료 {len(lecture_text):,}자", "mute"),
                  (f"전사본 {len(transcript_text):,}자", "mute"),
                  (f"입력 ≈ {tokens_in:,} 토큰", "info")])
        with st.expander("📄 추출된 텍스트 미리보기"):
            if transcript_text:
                st.text_area("전사본 (앞 3000자)", transcript_text[:3000], height=180)
            if lecture_text:
                st.text_area("강의 자료 (앞 3000자)", lecture_text[:3000], height=180)

    # ── 2. 옵션 ──
    ui.step(2, "출제 옵션")
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.2, 1, 1.2, 1.6])
        model = c1.selectbox("모델", MODELS, index=0, key="gen_model")
        num_mcq = c2.number_input("문항 수", 0, 80, 20, key="gen_num")
        difficulty = c3.selectbox("난이도", DIFFICULTIES, key="gen_difficulty")
        term_label = c4.selectbox("의학용어 표기", list(TERM_LANG_OPTIONS.keys()), index=2, key="gen_term")

        f1, f2 = st.columns([1.3, 1])
        with f1:
            st.markdown("**선지 형식** (복수 선택)")
            answer_formats = [opt for i, opt in enumerate(ANSWER_FORMATS)
                              if st.checkbox(opt, value=(i in DEFAULT_ANSWER_FORMATS), key=f"af_{i}")]
        with f2:
            st.markdown("**내용 형식** (복수 선택)")
            content_types = [opt for i, opt in enumerate(CONTENT_TYPES)
                             if st.checkbox(opt, value=(i == 0), key=f"ct_{i}")]
            st.markdown("**출제 범위**")
            transcript_only = st.checkbox(
                "전사본에서 언급하지 않은 내용은 출제에서 제외", key="gen_transcript_only",
                disabled=not transcript_text,
                help="교수님이 수업에서 실제로 말한 내용만 출제합니다. 강의 자료는 용어·수치 확인용으로만 씁니다. "
                     "전사본을 올리거나 붙여넣어야 켤 수 있습니다.",
            ) and bool(transcript_text)
            extra = st.text_area("추가 지시사항 (선택)", placeholder="예: 학습목표 중심으로 출제해줘",
                                 height=90, key="gen_extra")

    with st.expander("📁 기출문제 참고·변형 (선택)"):
        past_files = st.file_uploader("기출문제 파일 (PDF/PPTX/TXT/이미지)", type=ALL_TYPES,
                                      accept_multiple_files=True, key="past_exam")
        g1, g2 = st.columns(2)
        generation_mode = g1.radio("생성 모드", ["새 문제 생성", "기출 변형 생성"], horizontal=True,
                                   key="gen_mode_radio")
        variation_degree = "적당한 변형"
        if generation_mode == "기출 변형 생성":
            variation_degree = g2.select_slider("변형 강도", ["유사 변형", "적당한 변형", "창의적 변형"],
                                                value="적당한 변형", key="variation_slider")
        st.caption("기출문제를 그대로 풀고 싶다면 왼쪽 메뉴의 **📄 문제지 CBT**를 쓰세요.")
    past_text = _extract_all(past_files, ocr)
    variation_mode = variation_degree if (generation_mode == "기출 변형 생성" and past_text) else ""

    # ── 3. 생성 ──
    ui.step(3, "생성하기")
    if not answer_formats:
        st.warning("⚠️ 선지 형식을 1개 이상 선택하세요.")
    if not content_types:
        st.warning("⚠️ 내용 형식을 1개 이상 선택하세요.")
    can_run = bool((lecture_text or transcript_text) and answer_formats and content_types)
    if st.button("✨ 문항 세트 생성", type="primary", use_container_width=True, disabled=not can_run):
        _generate(
            lecture_text, transcript_text, answer_formats, content_types, num_mcq, difficulty, extra,
            TERM_LANG_RULE[TERM_LANG_OPTIONS[term_label]], past_text, variation_mode, model,
            transcript_only,
        )

    _results()


def _generate(lecture_text, transcript_text, answer_formats, content_types, num_mcq, difficulty,
              extra, term_rule, past_text, variation_mode, model, transcript_only=False) -> None:
    full_text, blueprint = "", ""
    progress = st.empty()
    status = "⏳ 준비 중..."
    with st.spinner(f"{model} 작업 중 (40문항 기준 1~3분)..."):
        try:
            for delta, full in generate_questions(
                lecture_text, transcript_text,
                answer_formats=answer_formats, content_types=content_types,
                num_mcq=num_mcq, num_short=0, difficulty=difficulty,
                extra_instructions=extra, term_lang_rule=term_rule,
                past_exam_text=past_text, variation_mode=variation_mode, model=model,
                transcript_only=transcript_only,
            ):
                if delta.startswith("\n<!-- TRIM_NOTICE"):
                    st.warning(full)
                    continue
                if delta == STATUS:
                    status = full
                    progress.caption(status)
                    continue
                if delta == BLUEPRINT:
                    blueprint = full
                    continue
                if delta == REPLACE:
                    full_text = full
                    continue
                full_text = full
                progress.caption(f"{status} ({len(full_text):,}자)")
        except Exception as e:
            st.error(f"생성 실패: {e}")
            return
    progress.empty()
    if not full_text.strip():
        st.error("모델이 빈 응답을 돌려줬습니다. 다시 시도하거나 다른 모델을 고르세요.")
        return

    full_text = autonumber_choices(full_text)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{BRAND}_{ts}"
    af_label = " + ".join(x.split(")")[0] + ")" for x in answer_formats)
    ct_label = " + ".join(x.split(" (")[0] for x in content_types)
    pdf_bytes = build_pdf(full_text, title=f"{BRAND} 문항 세트 — {af_label} / {ct_label}")

    st.session_state.last_full_text = full_text
    st.session_state.last_blueprint = blueprint
    st.session_state.last_ts = ts
    st.session_state.display_mode_radio = VIEW_CBT_PER_Q      # 생성 직후에는 바로 CBT로
    st.session_state.last_pdf = (f"{base}.pdf", pdf_bytes)
    for k in list(st.session_state.keys()):
        if k.startswith("cbt_"):
            del st.session_state[k]
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    with open(os.path.join(OUTPUTS_DIR, f"{base}.md"), "w", encoding="utf-8") as f:
        f.write(full_text)
    with open(os.path.join(OUTPUTS_DIR, f"{base}.pdf"), "wb") as f:
        f.write(pdf_bytes)


def _results() -> None:
    full_text = st.session_state.get("last_full_text")
    if not full_text:
        return
    st.divider()
    top_l, top_m, top_r = st.columns([2, 2, 1])
    top_l.success(f"✅ 생성 완료 — {len(full_text):,}자")
    if "display_mode_radio" not in st.session_state:
        st.session_state.display_mode_radio = VIEW_CBT_PER_Q
    view = top_m.radio("보기 방식", VIEW_MODES, horizontal=True, key="display_mode_radio",
                       label_visibility="collapsed")
    if st.session_state.get("last_blueprint"):
        with st.expander("🧭 출제 설계표 — 문항마다 배정된 출제 포인트·묻는 방식"):
            st.markdown(st.session_state.last_blueprint)
    if st.session_state.get("last_pdf"):
        name, data = st.session_state.last_pdf
        top_r.download_button("📄 PDF", data=data, file_name=name, mime="application/pdf",
                              help="문제지 + 정답·해설 분리", type="primary",
                              use_container_width=True, key="main_pdf_dl")
    if view == VIEW_PREVIEW:
        ui.render_markdown(full_text)
    else:
        qs = parse_cbt_questions(full_text)
        st.caption(f"{len(qs)}문항 파싱됨")
        render_cbt(qs, mode=cbt_mode_value(view), session_prefix=f"cbt_{st.session_state.last_ts}",
                   user=st.session_state.get("user", ""), source_text=full_text, title="AI 생성 세트")
