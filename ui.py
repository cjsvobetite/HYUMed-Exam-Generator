"""공통 디자인: 스타일, 페이지 헤더, 단계 제목, 배지, 마크다운 렌더."""
import html
import re

import streamlit as st

from constants import BRAND, TAGLINE
from images import inline_images_html

_TOPBAR_H = 74

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700;800&display=swap');

:root {
  --bar: #666666;            /* 상단 회색 띠 */
  --line: #99BBE8;           /* 패널 테두리 (연파랑) */
  --line-soft: #C5D5EA;
  --head1: #F3F7FC; --head2: #DAE6F4;   /* 패널 머리 그라데이션 */
  --head-ink: #15428B;       /* 패널 제목 글자 */
  --select: #FFE28A;         /* 트리 선택 (노랑) */
  --ink: #222222; --ink-soft: #666666;
}
html, body, .stApp, .stMarkdown p, .stMarkdown li, label, button p, input, textarea,
[data-baseweb="select"] div, [data-testid="stMetricValue"], [data-testid="stMetricLabel"] p {
  font-family: 'Nanum Gothic', 'Malgun Gothic', '맑은 고딕', 'Dotum', '돋움', sans-serif !important;
}
#MainMenu, footer, [data-testid="stStatusWidget"], [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] { top: __TOP__px; background: transparent; height: 2.5rem; }
.block-container, [data-testid="stMainBlockContainer"] { padding-top: calc(__TOP__px + 14px) !important; max-width: 1280px; }

/* ── 상단 회색 띠 ── */
.topbar {
  position: fixed; top: 0; left: 0; right: 0; height: __TOP__px; z-index: 999990;
  background: var(--bar); color: #fff; padding: 9px 30px; box-sizing: border-box;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid #555;
}
.topbar-title { font-size: 27px; font-weight: 800; letter-spacing: -0.5px; line-height: 1.15; }
.topbar-sub   { font-size: 15px; letter-spacing: .3px; opacity: .95; margin-top: 3px; }
.topbar-user  { font-size: 13px; opacity: .9; text-align: right; }

/* ── 왼쪽 트리 ── */
[data-testid="stSidebar"] { top: __TOP__px !important; height: calc(100vh - __TOP__px) !important;
  background: #FFFFFF; border-right: 6px solid #E4EAF2; }
[data-testid="stSidebarContent"] { padding-top: 0; }
[data-testid="stSidebarHeader"] { height: 0; padding: 0; min-height: 0; }
[data-testid="stSidebarCollapseButton"] { position: absolute; right: 8px; top: 8px; z-index: 5; }
[data-testid="stSidebarCollapseButton"] button { color: var(--head-ink) !important; }
[data-testid="stSidebarUserContent"] { padding: 0 !important; }
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
[data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { margin: 0 !important; }
[data-testid="stSidebar"] .stElementContainer { margin: 0 !important; }
.tree-head {
  background: linear-gradient(#F3F7FC, #D9E5F3); border-bottom: 1px solid var(--line);
  color: var(--head-ink); font-weight: 800; font-size: 15px; padding: 12px 14px;
  display: flex; justify-content: space-between;
}
.tree-row { font-size: 15px; color: var(--ink); padding: 0 10px; white-space: nowrap; height: 34px;
            display: flex; align-items: center; }
.tree-row .tw { color: #9AA6B2; }
.tree-row.active { background: var(--select); }
[data-testid="stSidebar"] [data-testid="stPageLink"] a {
  padding: 0 10px !important; height: 34px; border-radius: 0 !important; background: transparent !important; margin: 0 !important;
}
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover { background: #EEF3FA !important; }
[data-testid="stSidebar"] [data-testid="stPageLink"] p { font-size: 15px !important; color: var(--ink) !important; }
.tree-foot { padding: 14px 12px 6px 12px; border-top: 1px dotted #C8C8C8; margin-top: 14px;
  font-size: 13px; color: var(--ink-soft); }

/* ── 탭 띠 + 페이지 제목 ── */
.tabstrip { display: flex; gap: 4px; border-bottom: 1px solid var(--line); margin: 0 0 12px 0; padding-left: 4px; }
.tabstrip .tab {
  border: 1px solid var(--line); border-bottom: none; border-radius: 4px 4px 0 0;
  background: linear-gradient(#F7FAFD, #E1EAF5); padding: 7px 14px; font-size: 15px; color: #333;
  position: relative; top: 1px;
}
.tabstrip .tab.on { background: #fff; font-weight: 700; color: #15428B; }
.tabstrip .chk { color: #3BAA35; font-weight: 800; margin-right: 6px; }
.tabstrip .x { color: #8AA0BC; margin-left: 8px; font-size: 13px; }
.page-title { font-size: 25px; font-weight: 800; color: #222; margin: 4px 0 2px 2px; letter-spacing: -0.5px; }
.page-desc  { font-size: 13.5px; color: var(--ink-soft); margin: 0 0 14px 3px; }

/* ── 패널 (st.container(border=True)) ── */
[data-testid="stVerticalBlockBorderWrapper"], .stVerticalBlock[data-testid="stVerticalBlock"]:has(> .stElementContainer) {}
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 0 !important; border: 1px solid var(--line) !important; background: #fff; }
.panel-hd {
  background: linear-gradient(var(--head1), var(--head2)); border: 1px solid var(--line);
  color: var(--head-ink); font-weight: 800; font-size: 14.5px; padding: 7px 10px; margin: 16px 0 0 0;
}
.panel-hd .sq { display: inline-block; width: 8px; height: 8px; background: #15428B; margin: 0 8px 2px 2px; }
.panel-cap { font-size: 13px; color: var(--ink-soft); border: 1px solid var(--line); border-top: none;
  background: #FAFCFE; padding: 5px 10px; margin-bottom: 8px; }

/* ── 입력 ── */
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="textarea"], [data-testid="stNumberInputContainer"] {
  border-radius: 3px !important; border: 1px solid #A9BFD6 !important; background: #fff !important;
}
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea, [data-baseweb="base-input"] { background: #fff !important; }
[data-testid="stFileUploaderDropzone"] { border-radius: 0 !important; border: 1px dashed #A9BFD6 !important; background: #F8FAFD !important; }

/* ── 버튼: 옛 회색/파랑 그라데이션 ── */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button, [data-testid="stPageLink"] + div button {
  border-radius: 3px !important; border: 1px solid #A3AEBB !important; color: #222 !important;
  background: linear-gradient(#FFFFFF, #E4E8EE) !important; font-weight: 700; box-shadow: none !important;
}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {
  background: linear-gradient(#FFFFFF, #D6DEE9) !important; border-color: #7F95B0 !important;
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background: linear-gradient(#5A8BC8, #2F5D9A) !important; border-color: #244B80 !important; color: #fff !important;
}
.stButton > button[kind="primary"] p, .stDownloadButton > button[kind="primary"] p, .stFormSubmitButton > button[kind="primary"] p { color: #fff !important; }
.stButton > button:disabled { opacity: .55; }

/* ── st.tabs: ExtJS 탭 ── */
[data-baseweb="tab-list"] { gap: 3px; border-bottom: 1px solid var(--line); }
button[role="tab"] {
  border: 1px solid var(--line) !important; border-bottom: none !important; border-radius: 4px 4px 0 0 !important;
  background: linear-gradient(#F7FAFD, #E1EAF5) !important; padding: 4px 12px !important; margin-bottom: -1px;
}
button[role="tab"][aria-selected="true"] { background: #fff !important; }
button[role="tab"][aria-selected="true"] p { color: #15428B !important; font-weight: 700; }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none; }

/* ── 접이식 ── */
[data-testid="stExpander"] details { border-radius: 0 !important; border: 1px solid var(--line) !important; }
[data-testid="stExpander"] summary { background: linear-gradient(var(--head1), var(--head2)); color: var(--head-ink); }
[data-testid="stExpander"] summary p { font-weight: 700; color: var(--head-ink); }

/* ── 통계·표·알림 ── */
[data-testid="stMetric"] { background: #FAFCFE; border: 1px solid var(--line-soft); border-radius: 0; padding: 8px 12px; }
[data-testid="stMetricValue"] { font-size: 26px; color: #15428B; }
[data-testid="stDataFrame"], [data-testid="stTable"] { border: 1px solid var(--line); }
[data-testid="stAlert"] { border-radius: 0 !important; }
hr { border-color: #D5DEEA !important; }

/* ── 표: 학사 시스템 그리드 ── */
.grid-wrap { border: 1px solid var(--line); background: #fff; overflow: auto; margin: 4px 0 12px 0; }
table.grid { border-collapse: collapse; width: 100%; font-size: 14px; margin: 0 !important; }
.grid-wrap + p, .stMarkdown:has(.grid-wrap) p:empty { display: none; }
table.grid th {
  position: sticky; top: 0; z-index: 1;
  background: linear-gradient(#FAFAFA, #E6E6E6); color: #222; font-weight: 700; text-align: center;
  padding: 9px 8px; border-right: 1px dotted #C8C8C8; border-bottom: 1px solid #C4C4C4; white-space: nowrap;
}
table.grid th:last-child, table.grid td:last-child { border-right: none; }
table.grid td { padding: 7px 8px; border-right: 1px dotted #DADADA; border-bottom: 1px solid #ECECEC; color: #222; }
table.grid td.num { text-align: right; font-variant-numeric: tabular-nums; }
table.grid td.ctr { text-align: center; }
table.grid tbody tr:nth-child(even) td { background: #FAFAFA; }
table.grid tbody tr:hover td { background: #EAF1FB; }
table.grid td.empty { text-align: center; color: #888; padding: 18px; background: #fff !important; }

/* ── 배지: 대괄호 느낌의 각진 표식 ── */
.pill { display: inline-block; padding: 1px 8px; border-radius: 2px; font-size: 12.5px; font-weight: 700;
        margin: 0 4px 6px 0; border: 1px solid; }
.pill-warn { background: #FFF6D5; color: #8A5A00; border-color: #E2C36B; }
.pill-info { background: #EAF1FB; color: #15428B; border-color: #99BBE8; }
.pill-ok   { background: #EAF6E8; color: #2E6B2A; border-color: #9CCB95; }
.pill-mute { background: #F4F4F4; color: #555; border-color: #CCCCCC; }

/* ── 로그인 상자 ── */
.login-hd { background: linear-gradient(#6E6E6E, #555); color: #fff; font-weight: 800; padding: 9px 14px;
  font-size: 15px; letter-spacing: 1px; }

/* ── 문항 그림 (미리보기) ── */
img.q-figure { max-width: 100%; max-height: 420px; border: 1px solid #BBB; margin: 6px 0; }
details { margin: 4px 0; }
</style>
""".replace("__TOP__", str(_TOPBAR_H))


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def topbar(user: str | None = None) -> None:
    right = f'<div class="topbar-user">👤 {user} 님</div>' if user else ""
    st.markdown(f"""
<div class="topbar">
  <div>
    <div class="topbar-title">{BRAND} CBT / 문항 출제 관리 시스템</div>
    <div class="topbar-sub">We help you easily make and solve your exam questions!</div>
  </div>
  {right}
</div>""", unsafe_allow_html=True)


def hero(title: str, subtitle: str = "") -> None:
    """탭 띠 + 굵은 페이지 제목."""
    st.markdown(f"""
<div class="tabstrip">
  <div class="tab"><span class="chk">✔</span>홈<span class="x">×</span></div>
  <div class="tab on"><span class="chk">✔</span>{title}<span class="x">×</span></div>
</div>
<div class="page-title">{title}</div>
<div class="page-desc">{subtitle or TAGLINE}</div>""", unsafe_allow_html=True)


def step(num, title: str, caption: str = "") -> None:
    prefix = f"{num}. " if isinstance(num, int) else ""
    st.markdown(f'<div class="panel-hd"><span class="sq"></span>{prefix}{title}</div>'
                + (f'<div class="panel-cap">{caption}</div>' if caption else '<div style="height:8px"></div>'),
                unsafe_allow_html=True)


def tree(nodes, current_title: str) -> None:
    """사이드바 트리. nodes: [(depth, label, page_or_None, is_last)] — page가 None이면 폴더.
    링크 라벨은 앞 공백이 잘리므로 들여쓰기에 점자 빈칸(U+2800)과 │ 를 쓴다."""
    blank = "\u2800\u2800"
    last_at = {}
    for depth, label, page, is_last in nodes:
        last_at[depth] = is_last
        guide = ""
        if depth:
            guide = "".join(blank if last_at.get(d) else "│" + "\u2800" for d in range(1, depth))
            guide += "└ " if is_last else "├ "
        icon = "📂" if page is None else "📄"
        if page is None or page.title == current_title:
            active = " active" if page is not None else ""
            st.markdown(f'<div class="tree-row{active}"><span class="tw">{guide}</span>{icon} {label}</div>',
                        unsafe_allow_html=True)
        else:
            st.page_link(page, label=f"{guide}{icon} {label}")


def table(rows: list[dict], columns: list[str] | None = None, height: int | None = None,
          center: tuple = (), empty: str = "조회된 데이터가 없습니다.") -> None:
    """학사 시스템 느낌의 HTML 표. 숫자 칸은 오른쪽, center에 든 칸은 가운데 정렬."""
    columns = columns or (list(rows[0].keys()) if rows else [])
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in columns)
    if rows:
        body = []
        for r in rows:
            cells = []
            for c in columns:
                v = r.get(c, "")
                cls = "num" if isinstance(v, (int, float)) and not isinstance(v, bool) else ("ctr" if c in center else "")
                cells.append(f'<td class="{cls}">{html.escape("" if v is None else str(v))}</td>')
            body.append("<tr>" + "".join(cells) + "</tr>")
        body = "".join(body)
    else:
        body = f'<tr><td class="empty" colspan="{max(len(columns), 1)}">{html.escape(empty)}</td></tr>'
    style = f' style="max-height:{height}px"' if height else ""
    st.markdown(f'<div class="grid-wrap"{style}><table class="grid"><thead><tr>{head}</tr></thead>'
                f"<tbody>{body}</tbody></table></div>", unsafe_allow_html=True)


def pills(items) -> None:
    """items: [(label, kind)] — kind: warn | info | ok | mute"""
    html = " ".join(f'<span class="pill pill-{kind}">{label}</span>' for label, kind in items)
    if html:
        st.markdown(html, unsafe_allow_html=True)


_SUMMARY_RE = re.compile(r"<summary>(.*?)</summary>")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BREAK_RE = re.compile(r"^\s*([①-⑳ⓐ-ⓗ✅💡📝>]|\([가-하]\))")


def _bold_summary(m) -> str:
    return "<summary>" + _BOLD_RE.sub(r"<b>\1</b>", m.group(1)) + "</summary>"


def render_markdown(md: str) -> None:
    """문항 마크다운(토글·그림 포함) 미리보기.
    <summary> 안은 HTML이라 마크다운 **굵게**가 적용되지 않으므로 <b>로 바꿔 준다."""
    md = _SUMMARY_RE.sub(_bold_summary, md)
    # 선지·정답·해설 줄은 마크다운에서 한 문단으로 합쳐지므로 줄 끝에 강제 줄바꿈("  ")을 붙인다
    md = "\n".join(ln + "  " if _BREAK_RE.match(ln) else ln for ln in md.split("\n"))
    st.markdown(inline_images_html(md), unsafe_allow_html=True)
