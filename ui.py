"""공통 디자인: 스타일, 페이지 헤더, 단계 제목, 배지, 마크다운 렌더."""
import re

import streamlit as st

from constants import BRAND, TAGLINE
from images import inline_images_html

_CSS = """
<style>
#MainMenu, footer, [data-testid="stStatusWidget"] { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.2rem; max-width: 1180px; }

:root {
  --ink: #2D241B; --ink-soft: #6E5E45; --line: #E7DDCC;
  --paper: #FCFAF6; --sand: #F3ECE1; --brown: #8A5A36;
}

/* ── 브랜드 헤더 ── */
.hero {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 18px 24px; margin: 0 0 22px 0;
  background: linear-gradient(135deg, #FBF7F1 0%, #F1E7D8 100%);
  border: 1px solid var(--line); border-radius: 16px;
}
.hero-kicker { font-size: 12px; font-weight: 600; letter-spacing: .08em; color: var(--brown); text-transform: uppercase; }
.hero-title  { font-size: 26px; font-weight: 700; color: var(--ink); letter-spacing: -.3px; margin-top: 2px; }
.hero-sub    { font-size: 14px; color: var(--ink-soft); margin-top: 4px; }

/* 고양이 (CSS only) */
.cat-wrap { width: 70px; height: 50px; position: relative; flex: none; }
.cat { position: absolute; bottom: 4px; left: 10px; width: 46px; height: 32px;
       background: #6E5E45; border-radius: 18px 22px 14px 14px; animation: cat-breathe 2.6s ease-in-out infinite; }
.cat::before, .cat::after { content: ""; position: absolute; top: -7px; width: 0; height: 0;
       border-left: 7px solid transparent; border-right: 7px solid transparent; border-bottom: 10px solid #6E5E45; }
.cat::before { left: 4px; } .cat::after { right: 4px; }
.cat-eye { position: absolute; top: 11px; width: 4px; height: 4px; background: #FAF7F2; border-radius: 50%;
       animation: cat-blink 4s infinite; }
.cat-eye.l { left: 12px; } .cat-eye.r { right: 12px; }
.cat-tail { position: absolute; bottom: 8px; right: -6px; width: 18px; height: 6px; background: #6E5E45;
       border-radius: 3px; transform-origin: left center; animation: cat-tail 1.8s ease-in-out infinite; }
@keyframes cat-breathe { 0%,100% {transform: scaleY(1);} 50% {transform: scaleY(1.05);} }
@keyframes cat-blink   { 0%,92%,100% {transform: scaleY(1);} 94%,98% {transform: scaleY(0.1);} }
@keyframes cat-tail    { 0%,100% {transform: rotate(-10deg);} 50% {transform: rotate(20deg);} }

/* ── 단계 제목 ── */
.step { display: flex; align-items: center; gap: 10px; margin: 6px 0 2px 0; }
.step-num { width: 26px; height: 26px; border-radius: 50%; background: var(--brown); color: #fff;
            display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; flex: none; }
.step-title { font-size: 18px; font-weight: 700; color: var(--ink); }
.step-cap { font-size: 13px; color: var(--ink-soft); margin: 0 0 10px 36px; }

/* ── 카드 (st.container(border=True)) ── */
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px; }

/* ── 배지 ── */
.pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
        margin: 0 4px 6px 0; border: 1px solid transparent; }
.pill-warn { background: #FFF1D6; color: #8A5A00; border-color: #F2D49B; }
.pill-info { background: #E8F0FB; color: #2B5797; border-color: #C5D6F0; }
.pill-ok   { background: #E7F4EA; color: #2E6B3B; border-color: #BFE0C7; }
.pill-mute { background: var(--sand); color: var(--ink-soft); border-color: var(--line); }

/* ── 통계 ── */
[data-testid="stMetric"] { background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 10px 14px; }

/* ── 버튼·업로더 ── */
.stButton > button, .stDownloadButton > button { border-radius: 10px; font-weight: 600; }
[data-testid="stFileUploaderDropzone"] { border-radius: 12px; background: #fff; }

/* ── 문항 그림 (미리보기) ── */
img.q-figure { max-width: 100%; max-height: 420px; border: 1px solid var(--line); border-radius: 8px; margin: 6px 0; }
details { margin: 4px 0; }
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str = "") -> None:
    st.markdown(f"""
<div class="hero">
  <div>
    <div class="hero-kicker">{BRAND}</div>
    <div class="hero-title">{title}</div>
    <div class="hero-sub">{subtitle or TAGLINE}</div>
  </div>
  <div class="cat-wrap"><div class="cat-tail"></div>
    <div class="cat"><div class="cat-eye l"></div><div class="cat-eye r"></div></div>
  </div>
</div>""", unsafe_allow_html=True)


def step(num, title: str, caption: str = "") -> None:
    st.markdown(f'<div class="step"><div class="step-num">{num}</div>'
                f'<div class="step-title">{title}</div></div>', unsafe_allow_html=True)
    if caption:
        st.markdown(f'<div class="step-cap">{caption}</div>', unsafe_allow_html=True)


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
