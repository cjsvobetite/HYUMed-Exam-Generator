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
from views.workspace import _flash_session, card_request_box, request_box, save_hub

OUT_Q = "📝 CBT 문항 세트"
OUT_C = "🃏 플래시카드"
QUESTION_EXAMPLES = [
    ("학습목표 위주", "강의 학습목표에 해당하는 내용 위주로 출제해줘"),
    ("강조한 내용", "교수님이 '시험에 나온다', '중요하다'고 강조한 내용 위주로 출제해줘"),
    ("증례 많이", "임상 증례(케이스) 문항을 절반 이상 넣어줘"),
    ("수치·기준값", "수치·기준값·약물 용량을 묻는 문항을 꼭 포함해줘"),
]


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
    ui.pills([("📒 만든 문항과 🃏 플래시카드는 결과 아래 '내 노트북에 저장'으로 과목·단원별로 모아 둘 수 있어요", "info")])

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

    # ── 2. 만들 것 · 옵션 ──
    ui.step(2, "만들 것 · 옵션", "CBT 문항과 플래시카드 중 고르세요 (둘 다 가능). 요청(프롬프트)으로 원하는 대로 바꿀 수 있습니다.")
    with st.container(border=True):
        outputs = st.pills("만들 것", [OUT_Q, OUT_C], selection_mode="multi", default=[OUT_Q, OUT_C],
                           key="gen_outputs") or []
        want_q, want_c = OUT_Q in outputs, OUT_C in outputs
        answer_formats, content_types, transcript_only = [], [], False
        model, num_mcq, difficulty = MODELS[0], 0, DIFFICULTIES[0]
        if want_q:
            st.markdown("##### 📝 CBT 문항")
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
            request_box("gen_extra", "📝 문항 출제 요청 (프롬프트)", QUESTION_EXAMPLES,
                        "원하는 출제 방향을 적으면 출제 지침보다 우선해서 반영합니다.")
        else:
            term_label = st.selectbox("의학용어 표기", list(TERM_LANG_OPTIONS.keys()), index=2, key="gen_term")
        if want_c:
            st.markdown("##### 🃏 플래시카드")
            card_request_box("gen_card_request")
            st.caption("재료: 올린 강의 자료·전사본·기출문제(아래 '기출문제 참고'에 올린 경우)"
                       + (" + 만든 CBT 문항" if want_q else "") + " · 요청을 비우면 핵심 사실을 카드로 만듭니다.")
        extra = st.session_state.get("gen_extra", "") if want_q else ""

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
    if not (want_q or want_c):
        st.warning("⚠️ 만들 것을 하나 이상 고르세요.")
    if want_q and not answer_formats:
        st.warning("⚠️ 선지 형식을 1개 이상 선택하세요.")
    if want_q and not content_types:
        st.warning("⚠️ 내용 형식을 1개 이상 선택하세요.")
    has_material = bool(lecture_text or transcript_text or (want_c and not want_q and past_text))
    can_run = has_material and (want_q or want_c) and (not want_q or (answer_formats and content_types))
    label = {(True, True): "✨ 문항 세트 + 🃏 플래시카드 만들기", (True, False): "✨ 문항 세트 생성",
             (False, True): "🃏 플래시카드 만들기"}.get((want_q, want_c), "✨ 만들기")
    if st.button(label, type="primary", use_container_width=True, disabled=not can_run):
        _generate(
            lecture_text, transcript_text, answer_formats, content_types, num_mcq, difficulty, extra,
            TERM_LANG_RULE[TERM_LANG_OPTIONS[term_label]], past_text, variation_mode, model,
            transcript_only, want_q=want_q, want_c=want_c,
        )

    _results()


def _generate(lecture_text, transcript_text, answer_formats, content_types, num_mcq, difficulty,
              extra, term_rule, past_text, variation_mode, model, transcript_only=False,
              want_q=True, want_c=False) -> None:
    if not want_q:
        _make_cards_only(lecture_text, transcript_text, past_text, term_rule)
        return
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
    st.session_state.last_term_rule = term_rule
    material = _card_material(lecture_text, transcript_text, past_text)
    st.session_state[f"save_gen_{ts}_material"] = material          # 결과 화면에서 카드를 다시 만들 때 사용
    st.session_state[f"save_gen_{ts}_card_req"] = st.session_state.get("gen_card_request", "")
    st.session_state.last_outputs = (True, want_c)
    if want_c:
        import flashcards
        progress.caption("🃏 플래시카드 만드는 중...")
        try:
            st.session_state[f"save_gen_{ts}_cards"] = flashcards.make_flashcards(
                full_text, term_rule=term_rule, instruction=st.session_state.get("gen_card_request", ""),
                material=material)
        except Exception as e:
            st.warning(f"플래시카드 생성 실패: {e} — 결과 화면의 '플래시카드 만들기'로 다시 시도할 수 있습니다.")
        progress.empty()
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


def _card_material(lecture_text, transcript_text, past_text) -> str:
    parts = [("강의 전사본", transcript_text), ("강의 자료", lecture_text), ("기출문제", past_text)]
    return "\n\n".join(f"=== {name} ===\n{text}" for name, text in parts if text and text.strip())


def _make_cards_only(lecture_text, transcript_text, past_text, term_rule) -> None:
    import flashcards
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    material = _card_material(lecture_text, transcript_text, past_text)
    with st.spinner("🃏 플래시카드 만드는 중... (자료가 길면 1~2분)"):
        try:
            cards = flashcards.make_flashcards("", term_rule=term_rule, material=material,
                                               instruction=st.session_state.get("gen_card_request", ""))
        except Exception as e:
            st.error(f"플래시카드 생성 실패: {e}")
            return
    if not cards:
        st.error("카드를 만들지 못했습니다. 자료나 요청을 확인해 주세요.")
        return
    st.session_state.last_full_text = ""
    st.session_state.last_blueprint = ""
    st.session_state.last_pdf = None
    st.session_state.last_ts = ts
    st.session_state.last_term_rule = term_rule
    st.session_state.last_outputs = (False, True)
    st.session_state[f"save_gen_{ts}_cards"] = cards
    st.session_state[f"save_gen_{ts}_material"] = material
    st.session_state[f"save_gen_{ts}_card_req"] = st.session_state.get("gen_card_request", "")


def _results() -> None:
    full_text = st.session_state.get("last_full_text")
    ts = st.session_state.get("last_ts")
    if not full_text:
        if ts and st.session_state.get(f"save_gen_{ts}_cards"):
            _cards_only_results(ts)
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
    ts = st.session_state.last_ts
    set_id = save_hub(full_text, "generated", f"AI 생성 세트 {ts[:8]}", key=f"save_gen_{ts}",
                      term_rule=st.session_state.get("last_term_rule", ""))
    if view == VIEW_PREVIEW:
        ui.render_markdown(full_text)
    else:
        qs = parse_cbt_questions(full_text)
        st.caption(f"{len(qs)}문항 파싱됨")
        render_cbt(qs, mode=cbt_mode_value(view), session_prefix=f"cbt_{ts}",
                   user=st.session_state.get("user", ""), source_text=full_text, title="AI 생성 세트",
                   set_id=set_id)


def _cards_only_results(ts: str) -> None:
    cards = st.session_state[f"save_gen_{ts}_cards"]
    st.divider()
    st.success(f"✅ 🃏 플래시카드 {len(cards)}장을 만들었습니다.")
    save_hub("", "generated", f"플래시카드 {ts[:8]}", key=f"save_gen_{ts}",
             term_rule=st.session_state.get("last_term_rule", ""), save_questions=False)
    with st.expander("🃏 저장 전에 바로 넘겨 보기 (기록되지 않음)"):
        _flash_session(st.session_state.get("user", ""), None, f"fcprev_{ts}", [(None, c) for c in cards])

