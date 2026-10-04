"""CBT mode — 문항별 1개씩 표시 + 상단 번호 네비게이션 + 주관식 직접 입력.

시험 모드 (mode="exam"):
- 제한 시간을 정하고 시작 → 남은 시간 표시, 시간이 다 되면 자동 제출되고 답을 더 고칠 수 없다.
- 해설은 제출 후에만 보이고, 풀이 기록은 다른 모드와 똑같이 남는다.

v2.14 신규:
- 제출 완료 시 history.save_attempt() 호출 → 유저별 풀이 기록 저장 (문항별 모드는 전 문항 답변 후).
- _show_score()에 '틀린 문항만 다시 풀기' 버튼 추가 → 오답만 모아 render_cbt() 재실행.

v2.13 신규:
- CBT 제출 완료 후 점수 패널 하단에 📄 PDF 다운로드 버튼 추가.
  build_pdf()를 cbt.py에서 직접 호출. session_state.last_full_text 기반.

v2.12 신규:
- 🚩 문항 표시: 문항마다 표시 토글. 표시한 문항은 상단 목록에서 바로 이동.
- ✂️ 선지 제외(소거): 아니라고 판단한 선지를 취소선으로 지워 두기 (선택은 그대로 가능).
- 번호 버튼: 미답=N, 답변=✓N, 표시=🚩N, 현재=primary.
- 미완료 제출 허용: 미답 문항은 오답으로 처리되고 그냥 제출 가능.

v2.11 성능 최적화:
- render_cbt()에 @st.fragment 적용 → 버튼 클릭 시 앱 전체가 아닌 CBT 영역만 재렌더.
  네비게이션 속도 대폭 향상 + 화면 흐려짐(greying-out) 완전 제거.
- st.rerun() 제거 → fragment 내부는 state 변경 후 자동 재렌더되므로 불필요.
"""
import re
import time

import streamlit as st
import streamlit.components.v1 as components

from history import get_wrong_questions, is_graded, save_attempt
from images import IMG_RE, image_path
from pdf_export import build_pdf

# 문제지 CBT에서 붙이는 문항 상태 표시 (exam_import.INCOMPLETE_TAG / AI_FILLED_TAG)
_STATUS_TAGS = {
    "(문항 복기 불완전)": ("복기 불완전", "warn"),
    "(AI 보완)": ("AI 보완", "info"),
}

_CIRCLES = "①②③④⑤⑥⑦⑧⑨⑩"
_CIRCLE_IDX = {c: i for i, c in enumerate(_CIRCLES)}
# v2.15 — 조합형 답 선지 ⓐⓑⓒⓓⓔ 지원
_COMBO_LETTERS = "ⓐⓑⓒⓓⓔⓕⓖⓗ"
_COMBO_LETTER_IDX = {c: i for i, c in enumerate(_COMBO_LETTERS)}
_COMBO_LINE_RE = re.compile(r'[ⓐⓑⓒⓓⓔⓕⓖⓗ]')
_SUMMARY_RE = re.compile(r'<summary>(.*?)</summary>', re.DOTALL)
_QID_RE = re.compile(r'\*\*((?:문제|Q|C)\s*\d+\.?)\*\*\s*(.*)', re.DOTALL)
_ANS_RE = re.compile(r'✅\s*\*\*정답\s*[:：]?\s*(.*?)\*\*')


def _choice_idx(tok):
    tok = tok.strip()
    if tok and tok[0] in _CIRCLE_IDX:
        return _CIRCLE_IDX[tok[0]]
    # v2.15: 조합형 ⓐⓑⓒⓓⓔ → 인덱스
    if tok and tok[0] in _COMBO_LETTER_IDX:
        return _COMBO_LETTER_IDX[tok[0]]
    m = re.match(r'^\((\d+)\)', tok)
    if m:
        return int(m.group(1)) - 1
    return None


_GANA_LABELS = ['가', '나', '다', '라', '마', '바', '사', '아', '자', '차']
_GANA_PREFIX_RE = re.compile(r'^\([가나다라마바사아자차]\)')
# v2.16: 조합형 답 선지 ①②→가, 나 변환
_CIRCLE_TO_GANA = {c: _GANA_LABELS[i] for i, c in enumerate(_CIRCLES[:10])}


def _fmt_combo_opt(text: str) -> str:
    """①②③ → 가, 나, 다 형태로 변환. 예: '①③④' → '가, 다, 라'"""
    parts = [_CIRCLE_TO_GANA[ch] for ch in text if ch in _CIRCLE_TO_GANA]
    return ', '.join(parts) if parts else text

def parse_cbt_questions(md):
    """마크다운에서 CBT용 문항 파싱 (선택형 + 주관식 모두).
    반환: [{id, stem, choices, answers, explanation, is_subjective}]
    v2.16: 조합형 본선지 텍스트 → stem에 포함, choices = combo 선지만.
    """
    questions = []
    lines = md.split('\n')
    n = len(lines)
    i = 0
    while i < n:
        if '<details>' not in lines[i]:
            i += 1
            continue
        summary_text = ''
        for j in range(i, min(n, i + 6)):
            sm = _SUMMARY_RE.search(lines[j])
            if sm:
                summary_text = sm.group(1)
                break
        qm = _QID_RE.search(summary_text)
        if not qm:
            i += 1
            continue
        qid = qm.group(1).rstrip('.')
        stem = re.sub(r'\*+', '', qm.group(2)).strip()
        choices, answers, expl_lines, images = [], [], [], []
        answer_text = ""
        pre_combo_buf = []   # v2.16: 조합형 본선지 임시 버퍼
        depth, in_answer = 1, False
        k = i + 2
        while k < n and depth > 0:
            l = lines[k]
            ls = l.strip()
            if '<details>' in ls:
                depth += 1
                sm2 = _SUMMARY_RE.search(ls)
                if sm2 and '정답' in sm2.group(1):
                    in_answer = True
                k += 1; continue
            if '</details>' in ls:
                depth -= 1
                if depth == 1: in_answer = False
                if depth == 0: break
                k += 1; continue
            sm2 = _SUMMARY_RE.search(l)
            if sm2:
                if '정답' in sm2.group(1): in_answer = True
                k += 1; continue
            if not in_answer:
                # v2.16 fix: 빈 줄은 pre_combo_buf를 flush하지 않고 무시
                if not ls:
                    k += 1
                    continue
                im = IMG_RE.fullmatch(ls)
                if im:
                    images.append(im.group(1))
                    k += 1
                    continue
                is_choice_line = bool(
                    ls and (ls[0] in _CIRCLE_IDX
                            or re.match(r'^\(\d+\)', ls)
                            or _GANA_PREFIX_RE.match(ls))
                )
                if is_choice_line:
                    # 일단 버퍼에 저장 — combo 라인이 뒤에 오면 stem으로, 아니면 choices로
                    pre_combo_buf.append(ls)
                elif _COMBO_LINE_RE.search(ls):
                    # v2.16: 조합형 답 선지 라인 ⓐ ... ⓑ ... → combo choices
                    combo_opts = re.findall(
                        r'[ⓐⓑⓒⓓⓔⓕⓖⓗ]\s*(.+?)(?=\s*[ⓐⓑⓒⓓⓔⓕⓖⓗ]|$)', ls
                    )
                    combo_opts = [_fmt_combo_opt(o.strip()) for o in combo_opts if o.strip()]
                    if combo_opts and pre_combo_buf:
                        # 본선지 텍스트 → stem에 가나다라 형태로 추가
                        stem_items = []
                        for _gi, _pc in enumerate(pre_combo_buf):
                            _body = re.sub(
                                r'^\([가나다라마바사아자차]\)\s*|^[①-⑳]\s*|^\(\d+\)\s*', '', _pc
                            ).strip()
                            _lbl = _GANA_LABELS[_gi] if _gi < len(_GANA_LABELS) else str(_gi+1)
                            stem_items.append(f"({_lbl}) {_body}")
                        stem += '\n' + '\n'.join(stem_items)
                        pre_combo_buf = []
                        choices = combo_opts
                    elif combo_opts:
                        choices = combo_opts  # pre_combo_buf 없는 경우 (이미 변환됨)
                else:
                    # 일반 비선지 라인 — pre_combo_buf 있으면 일반 choices로 flush
                    if pre_combo_buf:
                        for _pc in pre_combo_buf:
                            _body = re.sub(
                                r'^[①-⑳]\s*|^\(\d+\)\s*|^\([가나다라마바사아자차]\)\s*', '', _pc
                            ).strip()
                            choices.append(_body)
                        pre_combo_buf = []
                    # v2.16: 선지 수집 전 텍스트 (케이스 증례 설명·발문 확장) → stem에 추가
                    if not choices and ls and not ls.startswith('<') and not ls.startswith('✅'):
                        _stem_add = re.sub(r'^>\s*', '', ls).strip()  # blockquote '>' prefix 제거
                        _stem_add = re.sub(r'\*\*(.*?)\*\*', r'\1', _stem_add)  # **bold** → plain
                        if _stem_add:
                            stem += '\n' + _stem_add
            else:
                am = _ANS_RE.search(l)
                if am:
                    answer_text = am.group(1).strip()
                    for tok in re.split(r'[,，\s]+', am.group(1)):
                        idx = _choice_idx(tok.strip())
                        if idx is not None: answers.append(idx)
                elif ls and not ls.startswith('<') and not ls.startswith('✅'):
                    expl_lines.append(re.sub(r'\*+', '', ls))
            k += 1
        # 루프 종료 후 남은 pre_combo_buf → choices
        if pre_combo_buf:
            for _pc in pre_combo_buf:
                _body = re.sub(
                    r'^[①-⑳]\s*|^\(\d+\)\s*|^\([가나다라마바사아자차]\)\s*', '', _pc
                ).strip()
                choices.append(_body)
        explanation = '\n'.join(e for e in expl_lines if e).strip()
        if not choices and answer_text:
            # 주관식: 정답 줄의 답(모범 답안)을 해설 맨 위에 보여 준다
            explanation = f"**정답:** {answer_text}" + (f"\n\n{explanation}" if explanation else "")
        if stem:
            questions.append({
                'id': qid, 'stem': stem, 'choices': choices,
                'answers': sorted(set(answers)),
                'explanation': explanation,
                'is_subjective': len(choices) == 0,
                'images': images,
                'answer_text': answer_text,
            })
        i = k + 1
    return questions


def _split_status(line: str):
    """발문 첫 줄 앞의 '(문항 복기 불완전)' 같은 표시를 떼어 배지로 돌려준다."""
    badges = []
    changed = True
    while changed:
        changed = False
        for tag, badge in _STATUS_TAGS.items():
            if line.startswith(tag):
                line = line[len(tag):].lstrip()
                badges.append(badge)
                changed = True
    return line, badges


def _check_button(prefix, cur, shown, shown_key, disabled=False):
    """문항별 해설 모드: 답을 고른 뒤 눌러야 채점·해설이 나온다 (복수정답을 다 고르기 전에 오답이 뜨지 않게)."""
    def _reveal():
        shown.add(cur)
        st.session_state[shown_key] = shown
    st.button("✅ 정답 확인", key=f"{prefix}_check_{cur}", on_click=_reveal,
              type="primary", disabled=disabled,
              help="답을 고른 뒤 누르세요." if disabled else None)


_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def _md_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("~", "\\~")


def _choice_label(ci: int, choice: str, excluded: bool) -> str:
    label = f"({ci+1}) {choice}"
    return f":gray[~~{_md_escape(label)}~~]" if excluded else label


def _excluded(prefix: str, qid: str) -> set:
    return set(st.session_state.get(f"{prefix}_excl", {}).get(qid, []))


def _exclude_control(prefix: str, qid: str, n: int) -> None:
    """✂️ 선지 제외(소거): 고른 선지에 취소선. 문항을 오가도 유지되도록 따로 저장한다."""
    store = st.session_state.setdefault(f"{prefix}_excl", {})
    key = f"{prefix}_ex_{qid}"

    def _save():
        store[qid] = list(st.session_state.get(key) or [])

    st.pills("✂️ 선지 제외 — 아니라고 생각하는 선지를 눌러 지워 두기", options=list(range(n)),
             format_func=lambda i: _CIRCLED[i] if i < len(_CIRCLED) else str(i + 1),
             selection_mode="multi", default=store.get(qid, []), key=key, on_change=_save)


def _set_cur(prefix, idx):
    st.session_state[f"{prefix}_cur"] = idx


def _show_result(q, ua):
    """선택형 정오 표시."""
    if not q['answers']:
        st.info("정답이 제공되지 않은 문항이라 채점하지 않습니다.")
        if q['explanation']:
            with st.expander("📖 해설", expanded=True):
                st.markdown(q['explanation'])
        return
    ok = sorted(q['answers']) == sorted(ua)
    if ok:
        st.success("✅ 정답!")
    else:
        ans_str = ', '.join(f"({i+1})" for i in q['answers'])
        st.error(f"❌ 오답 — 정답: **{ans_str}**")
    if q['explanation']:
        with st.expander("📖 해설"):
            st.markdown(q['explanation'])


def _show_score(questions, user_ans, prefix, user="", source_text="", save=True, title="",
                set_id=None, sources=None, flagged=None):
    """점수 패널. save=False면 점수만 보여주고 기록은 남기지 않는다 (문항별 모드 진행 중)."""
    obj_qs = [q for q in questions if is_graded(q)]
    if not obj_qs:
        st.info("채점할 수 있는 객관식 문항이 없습니다.")
        return
    skipped = sum(1 for q in questions if not q['is_subjective'] and not q['answers'])
    correct = sum(
        1 for q in obj_qs
        if q['answers'] and sorted(q['answers']) == sorted(
            user_ans.get(q['id']) if isinstance(user_ans.get(q['id']), list) else []
        )
    )
    denom = len(obj_qs)
    pct = int(correct / denom * 100)
    st.metric("🎯 점수 (객관식)", f"{correct} / {denom}  ({pct}%)",
              delta="Pass ✅" if pct >= 60 else "Fail ❌")
    if skipped:
        st.caption(f"정답이 없는 {skipped}문항은 채점에서 뺐습니다.")
    if not save:
        st.caption("모든 문항을 풀면 기록이 저장됩니다.")
        return
    if pct >= 80 and not st.session_state.get(f"{prefix}_saved"):
        st.balloons()

    # ── v2.14: 풀이 기록 저장 ──
    if user and not st.session_state.get(f"{prefix}_saved"):
        try:
            record = save_attempt(user, questions, user_ans, full_text=source_text, title=title,
                                  set_id=set_id, sources=sources, flagged=flagged)
            st.session_state[f"{prefix}_saved"] = True
            st.session_state[f"{prefix}_wrong_ids"] = record["wrong_ids"]
            st.caption(f"📝 기록 저장됨 — {record['ts']}")
        except Exception as _e:
            st.caption(f"기록 저장 실패: {_e}")

    # ── 틀린 문항만 다시 풀기 (v2.14) ──
    wrong_ids = st.session_state.get(f"{prefix}_wrong_ids", [])
    if wrong_ids:
        st.warning(f"❌ 틀린 문항: {', '.join(wrong_ids)} ({len(wrong_ids)}개)")
        if st.button("🔁 틀린 문항만 다시 풀기", key=f"{prefix}_retry_wrong", use_container_width=True):
            wrong_qs = get_wrong_questions(questions, wrong_ids)
            retry_prefix = f"{prefix}_retry"
            for k in list(st.session_state.keys()):
                if k.startswith(retry_prefix):
                    del st.session_state[k]
            st.session_state[f"{prefix}_retry_qs"] = wrong_qs
            st.rerun()

    # ── CBT 완료 후 PDF 다운로드 (v2.13) ──
    raw_md = source_text
    if raw_md:
        try:
            pdf_bytes = build_pdf(raw_md, title="SaluTerra CBT 결과")
            st.download_button(
                "📄 PDF 다운로드 (문제지 + 정답·해설)",
                data=pdf_bytes,
                file_name=f"cbt_result_{prefix}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
                key=f"{prefix}_pdf_dl",
            )
        except Exception as _e:
            st.warning(f"PDF 생성 실패: {_e}")

    # 다시 풀기 — fragment 밖의 전역 state를 초기화하므로 st.rerun() 필요
    if st.button("🔄 처음부터 다시 풀기", key=f"{prefix}_reset"):
        for k in list(st.session_state.keys()):
            if k.startswith(prefix):
                del st.session_state[k]
        st.rerun()


def _exam_start(prefix: str, total: int) -> bool:
    """시험 모드 시작 전 화면. 시작했으면 True."""
    if st.session_state.get(f"{prefix}_deadline"):
        return True
    with st.container(border=True):
        st.markdown(f"**⏱️ 시험 모드** · {total}문항 — 시간이 끝나면 자동으로 제출되고, 해설은 제출 후에 보입니다.")
        c1, c2 = st.columns([1, 1])
        minutes = c1.number_input("제한 시간 (분)", 1, 300, max(1, total), key=f"{prefix}_minutes",
                                  help="기본값: 문항당 1분")

        def _start():
            st.session_state[f"{prefix}_deadline"] = time.time() + int(minutes) * 60
            st.session_state[f"{prefix}_limit"] = int(minutes) * 60

        c2.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
        c2.button("▶ 시험 시작", key=f"{prefix}_start", type="primary", on_click=_start, use_container_width=True)
    return False


def _countdown(seconds: int) -> None:
    """남은 시간을 1초마다 줄여 보여 준다 (화면 표시만 — 시간 종료 판정은 서버가 한다)."""
    components.html(f"""
<div id="t" style="font:700 15px/1.4 'Nanum Gothic','Malgun Gothic',sans-serif;color:#15428B;padding:6px 10px;
 border:1px solid #9FB4D3;background:#EEF3FA;display:inline-block">⏱️ 남은 시간 <span id="v"></span></div>
<script>
let left = {max(0, int(seconds))};
const v = document.getElementById('v'), box = document.getElementById('t');
function draw() {{
  const m = Math.floor(left / 60), s = left % 60;
  v.textContent = m + ':' + String(s).padStart(2, '0');
  if (left <= 60) {{ box.style.color = '#C0392B'; box.style.borderColor = '#E3A39B'; box.style.background = '#FCEFEE'; }}
}}
draw();
setInterval(() => {{ if (left > 0) {{ left -= 1; draw(); }} }}, 1000);
</script>""", height=44)


@st.fragment(run_every=5)
def _exam_clock(prefix: str, total: int) -> None:
    """5초마다 서버에서 남은 시간을 확인하고, 시간이 다 되면 자동 제출한다."""
    shown_key = f"{prefix}_shown"
    shown = st.session_state.get(shown_key, set())
    if len(shown) >= total:
        used = st.session_state.get(f"{prefix}_used")
        if used is not None:
            st.caption(f"⏱️ 제출 완료 — 걸린 시간 {used // 60}분 {used % 60}초"
                       + (" (시간 종료로 자동 제출)" if st.session_state.get(f"{prefix}_timeup") else ""))
        return
    left = st.session_state[f"{prefix}_deadline"] - time.time()
    if left <= 0:
        st.session_state[shown_key] = set(range(total))
        st.session_state[f"{prefix}_timeup"] = True
        st.session_state[f"{prefix}_used"] = st.session_state.get(f"{prefix}_limit", 0)
        st.rerun()                 # 시험 화면 전체를 다시 그려 제출 상태로
    _countdown(int(left))


@st.fragment
def render_cbt(questions, mode, session_prefix, user="", source_text=None, title="",
               set_id=None, sources=None):
    """CBT UI — 문항 1개씩 표시, 상단 번호 버튼 네비게이션.

    @st.fragment: 이 함수 내부의 위젯 변경은 전체 앱을 재실행하지 않고
    이 fragment만 재실행 → 네비게이션이 즉각적이고 화면이 흐려지지 않음.

    mode: 'per_q' | 'submit_all'
    source_text: 기록·PDF에 쓸 원본 마크다운 (기본값: 마지막 생성 결과)
    title: 풀이 기록에 남길 세트 이름
    set_id / sources: 학습 공간 세트·복습 세트와 기록을 잇는 정보 (history.save_attempt 참고)
    """
    if source_text is None:
        source_text = st.session_state.get("last_full_text", "")
    if not questions:
        st.info("ℹ️ 파싱된 문항이 없습니다.")
        return

    total = len(questions)
    exam = mode == "exam"
    if exam:
        session_prefix = f"{session_prefix}_exam"    # 다른 모드에서 고른 답과 섞이지 않게
        mode = "submit_all"
        if not _exam_start(session_prefix, total):
            return
        _exam_clock(session_prefix, total)
    cur_key   = f"{session_prefix}_cur"
    ans_key   = f"{session_prefix}_ans"
    shown_key = f"{session_prefix}_shown"

    flags_key = f"{session_prefix}_flags"

    if cur_key   not in st.session_state: st.session_state[cur_key]   = 0
    if ans_key   not in st.session_state: st.session_state[ans_key]   = {}
    if shown_key not in st.session_state: st.session_state[shown_key] = set()
    if flags_key not in st.session_state: st.session_state[flags_key] = set()

    cur      = st.session_state[cur_key]
    user_ans = st.session_state[ans_key]
    shown    = st.session_state[shown_key]
    flags    = st.session_state[flags_key]
    locked   = exam and len(shown) >= total      # 시험 모드는 제출(또는 시간 종료) 뒤 답을 바꿀 수 없다

    answered_count = sum(1 for v in user_ans.values() if v not in (None, [], ""))
    st.markdown(f"**총 {total}문항** · 답변: {answered_count}/{total}")
    st.progress(answered_count / total if total else 0)

    # ── 🚩 표시한 문항 (상단) — 눌러서 바로 이동 ──
    if flags:
        marked = sorted(flags)
        st.markdown(f"🚩 **표시한 문항 {len(marked)}개** — 눌러서 이동")
        mcols = st.container(key=f"{session_prefix}_mark_cbtnav").columns(10)
        for j, idx in enumerate(marked[:10]):
            mcols[j].button(f"{idx+1}", key=f"{session_prefix}_mk_{idx}", on_click=_set_cur,
                            args=(session_prefix, idx), use_container_width=True)
        if len(marked) > 10:
            st.caption(f"외 {len(marked) - 10}개 (번호 버튼의 🚩)")

    # ── 상단 번호 버튼 네비게이션 (10개씩 한 줄) ──
    # 미답=N, 답변=✓N, 표시=🚩N, 현재=primary
    COLS_PER_ROW = 10
    nav_box = st.container(key=f"{session_prefix}_cbtnav")   # 좁은 화면에서도 한 줄 10칸을 유지 (ui.py CSS)
    for row_start in range(0, total, COLS_PER_ROW):
        row_qs = list(range(row_start, min(row_start + COLS_PER_ROW, total)))
        cols = nav_box.columns(COLS_PER_ROW)
        for ci, idx in enumerate(row_qs):
            q_nav = questions[idx]
            ua_nav = user_ans.get(q_nav['id'])
            answered = ua_nav not in (None, [], "")
            is_flagged = idx in flags
            is_current = idx == cur
            if is_current:
                label = f"**{idx+1}**"
            elif is_flagged:
                label = f"🚩{idx+1}"
            elif answered:
                label = f"✓{idx+1}"
            else:
                label = str(idx+1)
            cols[ci].button(
                label,
                key=f"{session_prefix}_nav_{idx}",
                on_click=_set_cur, args=(session_prefix, idx),
                type="primary" if is_current else "secondary",
                use_container_width=True,
            )

    st.divider()

    # ── 현재 문항 ──
    q   = questions[cur]
    qid = q['id']
    ua  = user_ans.get(qid)
    answer_revealed = cur in shown

    # 🚩 문항 표시 토글 (문항 제목 옆)
    flag_label = "🚩 표시 해제" if cur in flags else "🚩 문항 표시"
    def _toggle_flag():
        if cur in flags:
            flags.discard(cur)
        else:
            flags.add(cur)
        st.session_state[flags_key] = flags
    col_stem, col_flag = st.columns([5, 1])
    with col_stem:
        # v2.16: stem에 '\n' 포함 시 (케이스형 증례 설명 등) 제목과 본문 분리 렌더링
        _stem_parts = q['stem'].split('\n', 1)
        _title, _badges = _split_status(_stem_parts[0])
        st.markdown(f"**{cur+1}.** {_title}")         # 본문과 같은 글자 크기
        if _badges:
            st.markdown(" ".join(f'<span class="pill pill-{kind}">{label}</span>'
                                 for label, kind in _badges), unsafe_allow_html=True)
        if len(_stem_parts) > 1 and _stem_parts[1].strip():
            st.markdown(_stem_parts[1].replace('\n', '  \n'), unsafe_allow_html=False)
        for _img_id in q.get('images', []):
            _path = image_path(_img_id)
            if _path:
                st.image(str(_path))
            else:
                st.caption("🖼️ 그림 파일을 찾을 수 없습니다 (서버 재시작 등으로 삭제됨).")
    with col_flag:
        st.button(flag_label, key=f"{session_prefix}_flag_{cur}", on_click=_toggle_flag,
                  use_container_width=True, type="primary" if cur in flags else "secondary")

    if q['is_subjective']:
        # 주관식 — 직접 타이핑
        # on_change 콜백으로 session_state에 저장 (rerun 없이)
        def _save_subj():
            user_ans[qid] = st.session_state[f"{session_prefix}_subj_{qid}"]
            st.session_state[ans_key] = user_ans

        prev_text = ua if isinstance(ua, str) else ""
        st.text_area(
            "답 입력", value=prev_text,
            key=f"{session_prefix}_subj_{qid}",
            height=120, placeholder="답을 직접 입력하세요...",
            on_change=_save_subj, disabled=locked,
        )

        if q['explanation']:
            if not answer_revealed:
                def _reveal_subj():
                    shown.add(cur)
                    st.session_state[shown_key] = shown
                st.button("정답·해설 확인",
                          key=f"{session_prefix}_check_{cur}",
                          on_click=_reveal_subj)
            else:
                with st.expander("📖 모범 답안 / 해설", expanded=True):
                    st.markdown(q['explanation'])

    elif len(q['answers']) != 1:
        # 복수정답 — 체크박스
        sel = list(ua) if isinstance(ua, list) else []
        new_sel = []
        excluded = _excluded(session_prefix, qid)
        for ci, choice in enumerate(q['choices']):
            if st.checkbox(_choice_label(ci, choice, ci in excluded), value=(ci in sel),
                           key=f"{session_prefix}_cb_{qid}_{ci}", disabled=locked):
                new_sel.append(ci)
        if not answer_revealed:
            _exclude_control(session_prefix, qid, len(q['choices']))
        user_ans[qid] = new_sel
        st.session_state[ans_key] = user_ans

        if answer_revealed:
            _show_result(q, new_sel)
        elif mode == 'per_q':
            _check_button(session_prefix, cur, shown, shown_key, disabled=not new_sel)

    else:
        # 단일정답 — 라디오
        excluded = _excluded(session_prefix, qid)
        labels   = [_choice_label(ci, c, ci in excluded) for ci, c in enumerate(q['choices'])]
        prev_idx = ua[0] if isinstance(ua, list) and ua else None
        sel_r = st.radio(
            "선택", options=list(range(len(labels))),
            format_func=lambda x: labels[x],
            index=prev_idx,
            key=f"{session_prefix}_r_{qid}",
            label_visibility="collapsed", disabled=locked,
        )
        new_ua = [sel_r] if sel_r is not None else []
        user_ans[qid] = new_ua
        st.session_state[ans_key] = user_ans
        if not answer_revealed:
            _exclude_control(session_prefix, qid, len(q['choices']))

        if answer_revealed:
            _show_result(q, new_ua)
        elif mode == 'per_q':
            _check_button(session_prefix, cur, shown, shown_key, disabled=not new_ua)

    st.divider()

    # ── 이전 / 다음 버튼 ──
    nav_l, _, nav_r = st.columns([1, 3, 1])
    with nav_l:
        if cur > 0:
            def _go_prev():
                st.session_state[cur_key] = cur - 1
            st.button("← 이전", key=f"{session_prefix}_prev",
                      on_click=_go_prev, use_container_width=True)
    with nav_r:
        if cur < total - 1:
            def _go_next():
                st.session_state[cur_key] = cur + 1
            st.button("다음 →", key=f"{session_prefix}_next",
                      on_click=_go_next, type="primary",
                      use_container_width=True)
        elif mode == 'submit_all' and not locked:
            unanswered = total - answered_count
            def _submit_all():
                for idx2 in range(total):
                    shown.add(idx2)
                st.session_state[shown_key] = shown
                if exam:
                    limit = st.session_state.get(f"{session_prefix}_limit", 0)
                    left = st.session_state[f"{session_prefix}_deadline"] - time.time()
                    st.session_state[f"{session_prefix}_used"] = int(min(limit, max(0, limit - left)))
            st.button("📝 최종 제출", type="primary",
                      key=f"{session_prefix}_submit_btn",
                      on_click=_submit_all,
                      use_container_width=True)
            if unanswered > 0:
                st.caption(f"⚠️ 미답 {unanswered}문항은 오답 처리됩니다.")

    # ── 오답 재풀이 모드 (v2.14) ──
    retry_qs = st.session_state.get(f"{session_prefix}_retry_qs")
    if retry_qs:
        st.markdown("---")
        st.subheader(f"🔁 오답 재풀이 ({len(retry_qs)}문항)")
        render_cbt(retry_qs, mode=mode,
                   session_prefix=f"{session_prefix}_retry", user=user,
                   source_text=source_text, title=f"{title} (오답 재풀이)" if title else "오답 재풀이",
                   set_id=set_id, sources=sources)
        return

    # ── 점수 패널 ──
    if mode == 'submit_all' and len(shown) >= total:
        st.markdown("---")
        if st.session_state.get(f"{session_prefix}_timeup"):
            st.warning("⏱️ 시간이 끝나 자동으로 제출했습니다. 답하지 않은 문항은 오답으로 처리됩니다.")
        _show_score(questions, user_ans, session_prefix, user=user, source_text=source_text,
                    title=f"{title} (시험 모드)" if exam and title else title,
                    set_id=set_id, sources=sources, flagged=[questions[i]['id'] for i in flags])
    elif mode == 'per_q' and shown:
        done = len(shown) >= total          # 모든 문항의 정답을 확인해야 기록 저장
        with st.expander(f"📊 현재 점수 (정답 확인 {len(shown)}/{total})", expanded=done):
            _show_score(questions, user_ans, session_prefix, user=user,
                        source_text=source_text, save=done, title=title, set_id=set_id, sources=sources,
                        flagged=[questions[i]['id'] for i in flags])
