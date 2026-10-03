"""문제지(PDF·사진·텍스트) → CBT 문항 + 해설.

1단계 read_exam():  페이지마다 비전 모델로 문항을 구조화(JSON)하고, 그림이 있는 문항은 그림을 잘라 붙인다.
2단계 solve_exam(): 정답·해설을 만들고, 불완전한 문항은 보완하거나 '(문항 복기 불완전)'으로 표시한다.
3단계 to_markdown(): 기존 CBT/PDF/복습 기록이 그대로 쓰는 마크다운으로 바꾼다.

그림 처리 순서 (문항마다)
  ① PDF에 들어 있는 이미지 객체 중 그 문항 영역 안에 있는 것 → 이미지 경계대로 잘라냄 (가장 정확)
  ② 없으면 모델이 알려준 그림 영역(figure_bbox)으로 잘라냄 (스캔본·사진)
  ③ 그것도 없으면 문항 영역 전체, 마지막으로 페이지 전체를 붙인다
"""
from __future__ import annotations

import base64
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from images import marker, save_image
from llm import completion_kwargs, get_client

INCOMPLETE_TAG = "(문항 복기 불완전)"
AI_FILLED_TAG = "(AI 보완)"
MISSING_CHOICE = "(복기 안 됨)"

PDF_TYPES = ["pdf"]
IMAGE_TYPES = ["png", "jpg", "jpeg", "webp"]
TEXT_TYPES = ["txt", "md"]
EXAM_TYPES = PDF_TYPES + IMAGE_TYPES + TEXT_TYPES

_RENDER_SCALE = 2.0          # 144dpi — 그림 자르기·비전 입력 공용
_MAX_SIDE = 2000             # 비전 입력 긴 변
_SCAN_AREA = 0.6             # 페이지의 60% 이상 덮는 이미지 = 스캔본 배경 → 그림 후보에서 제외
_TEXT_CHUNK = 6000           # 텍스트 입력은 이 글자 수 단위로 나눠 읽음
_SOLVE_BATCH = 6
_WORKERS = 4

_READ_PROMPT = """너는 한국 의과대학 시험 문제지를 디지털화하는 도구다. 주어진 페이지(이미지 또는 텍스트)에서 문항을 추출해 JSON으로만 답하라.

규칙
- number: 문제지에 적힌 문항 번호(숫자 문자열). 번호가 없으면 null.
- stem: 발문 원문. 번역·요약·교정 금지(명백한 OCR 오타만 교정). 증례, 검사 결과, <보기> 박스((가)(나)(다)…)는 줄바꿈으로 stem에 포함하고, 표는 마크다운 표로 적어라.
- choices: 선지 내용만 순서대로(①, 1., (1), A. 같은 번호 기호는 빼라). 번호는 있는데 내용이 비었거나 읽을 수 없는 선지는 ""로 자리를 지켜라. 주관식이면 [].
- answer: 문제지에 정답이 표시돼 있으면(정답표, 동그라미, 정답 표기) 선지 번호(1부터) 배열, 없으면 [].
- explanation: 문제지에 해설이 있으면 원문, 없으면 "".
- incomplete: 복기 문제처럼 발문이 잘렸거나, 선지가 빠졌거나(5지선다인데 3개만 있는 등), "기억 안 남", "?", "…" 같은 표시가 있으면 true.
- missing: 빠진 부분 — "stem", "choices" 중 해당하는 것.
- incomplete_note: 무엇이 빠졌는지 짧게. 완전하면 "".
- has_figure: 문항에 그림·사진·그래프·ECG·영상·조직 슬라이드·도식 같은 시각 자료가 있으면 true.
- figure_bbox: 시각 자료의 위치 [x0, y0, x1, y1] (페이지 너비·높이 대비 0~1, 왼쪽 위가 원점). 없거나 텍스트 입력이면 null.
- region_bbox: 문항 전체(번호부터 마지막 선지까지)의 위치 [x0, y0, x1, y1]. 텍스트 입력이면 null.
- continuation: 페이지 맨 위 내용이 이전 페이지 마지막 문항의 이어지는 부분이면, 그 조각을 첫 항목으로 넣고 true (number는 null).
- 표지, 응시 안내, 머리말·꼬리말 같은 문항이 아닌 내용은 무시.

형식: {"questions": [{"number": "1", "continuation": false, "stem": "", "choices": [], "answer": [], "explanation": "", "incomplete": false, "missing": [], "incomplete_note": "", "has_figure": false, "figure_bbox": null, "region_bbox": null}]}"""

_SOLVE_PROMPT = """너는 한국 의과대학 시험 해설 전문가다. 주어진 문항마다 정답과 해설을 만들어 JSON으로만 답하라.

규칙
- answer: 정답 선지 번호(1부터) 배열. '모두 고르시오'면 여러 개. 주관식이면 [].
- 문제지에 정답(given_answer)이 있으면 그 정답을 쓰되, 틀렸다고 확신하면 explanation 끝에 "※ AI 검토: …"로 의견을 적어라.
- explanation: 정답 근거를 핵심 개념 중심으로 설명하고, 오답 선지마다 왜 틀렸는지 한 줄씩. 주관식이면 모범 답안을 먼저 적어라. 그림이 함께 주어지면 그림 소견을 근거로 써라.
{incomplete_rule}
{term_rule}
형식: {{"results": [{{"number": "1", "answer": [], "explanation": "", "completed_stem": null, "completed_choices": null, "filled_note": ""}}]}}"""

_FILL_RULE = """- incomplete가 true인 문항은 원래 출제 의도에 맞게 빠진 부분만 보완하라: completed_stem(발문 전체), completed_choices(선지 전체, 보통 5개). 이미 있는 내용은 바꾸지 말고 빈 곳만 채워라. filled_note에 무엇을 보완했는지 짧게 적어라. 보완한 문항 기준으로 answer와 explanation을 만들어라.
- 완전한 문항은 completed_stem, completed_choices를 null로 둬라."""

_MARK_RULE = """- incomplete가 true인 문항은 내용을 보완하지 마라(completed_stem, completed_choices는 null). 남아 있는 정보로 정답을 판단할 수 있을 때만 answer를 채우고, 아니면 []로 두고 explanation에 이 문항이 묻는 핵심 개념을 정리하라."""


@dataclass
class Question:
    number: str | None
    stem: str
    choices: list[str] = field(default_factory=list)
    answer: list[int] = field(default_factory=list)       # 0부터
    explanation: str = ""
    incomplete: bool = False
    missing: list[str] = field(default_factory=list)
    incomplete_note: str = ""
    has_figure: bool = False
    figure_bbox: list[float] | None = None
    region_bbox: list[float] | None = None
    images: list[str] = field(default_factory=list)
    page: int = 0
    given_answer: bool = False
    ai_filled: bool = False
    filled_note: str = ""
    continuation: bool = False      # 이전 페이지 마지막 문항의 이어지는 조각


@dataclass
class _Page:
    index: int
    source: str
    image: object = None             # PIL.Image (렌더링된 페이지 / 사진)
    text: str = ""
    embedded: list = field(default_factory=list)   # 정규화된 이미지 객체 bbox 목록


@dataclass
class ReadResult:
    questions: list[Question]
    warnings: list[str]
    pages: int


# ─── 1단계: 읽기 ───

def load_pages(files: list[tuple[str, bytes]], pasted_text: str = "") -> list[_Page]:
    pages: list[_Page] = []
    for name, data in files:
        ext = Path(name).suffix.lower().lstrip(".")
        if ext in PDF_TYPES:
            pages += _pdf_pages(name, data, start=len(pages))
        elif ext in IMAGE_TYPES:
            from extractors import _load_image
            pages.append(_Page(len(pages), name, image=_load_image(data)))
        elif ext in TEXT_TYPES:
            from extractors import _decode_text
            pages += _text_pages(name, _decode_text(data), start=len(pages))
    if pasted_text.strip():
        pages += _text_pages("붙여넣은 텍스트", pasted_text, start=len(pages))
    return pages


def _pdf_pages(name: str, data: bytes, start: int) -> list[_Page]:
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    out = []
    pdf = pdfium.PdfDocument(data)
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            w, h = page.get_size()
            embedded = []
            for obj in page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,)):
                bounds = obj.get_bounds() if hasattr(obj, "get_bounds") else obj.get_pos()  # v5 / v4
                left, bottom, right, top = bounds
                box = _clamp_box([left / w, 1 - top / h, right / w, 1 - bottom / h])
                if box and _area(box) < _SCAN_AREA:
                    embedded.append(box)
            text = page.get_textpage().get_text_bounded().strip()
            out.append(_Page(start + i, f"{name} p.{i + 1}",
                             image=page.render(scale=_RENDER_SCALE).to_pil(),
                             text=text, embedded=embedded))
    finally:
        pdf.close()
    return out


def _text_pages(name: str, text: str, start: int) -> list[_Page]:
    chunks, buf = [], ""
    for para in re.split(r"\n\s*\n", text):
        if buf and len(buf) + len(para) > _TEXT_CHUNK:
            chunks.append(buf)
            buf = ""
        buf += para + "\n\n"
    if buf.strip():
        chunks.append(buf)
    return [_Page(start + i, f"{name} #{i + 1}", text=c) for i, c in enumerate(chunks)]


def read_exam(files, model: str = "gpt-4o", pasted_text: str = "", on_progress=None) -> ReadResult:
    pages = load_pages(files, pasted_text)
    if not pages:
        return ReadResult([], ["읽을 페이지가 없습니다."], 0)

    per_page: dict[int, list[Question]] = {}
    warnings = []
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = {pool.submit(_read_page, p, model): p for p in pages}
        for done, fut in enumerate(as_completed(futures), 1):
            page = futures[fut]
            try:
                per_page[page.index] = fut.result()
            except RuntimeError:
                raise
            except Exception as e:
                per_page[page.index] = []
                warnings.append(f"{page.source}: 읽기 실패 ({e})")
            if on_progress:
                on_progress(done, len(pages))

    questions: list[Question] = []
    for page in pages:
        page_qs = per_page.get(page.index, [])
        _attach_figures(page, page_qs)
        for q in page_qs:
            if q.continuation and questions:
                _merge(questions[-1], q)
            else:
                questions.append(q)
    _number_questions(questions)
    return ReadResult(questions, warnings, len(pages))


def _read_page(page: _Page, model: str) -> list[Question]:
    if page.image is not None:
        content = [{"type": "image_url", "image_url": {"url": _data_url(page.image), "detail": "high"}}]
        if page.text:
            content.insert(0, {"type": "text", "text":
                               "페이지 텍스트 레이어 (오탈자 확인용 참고 자료, 비어 있거나 순서가 뒤섞였을 수 있음):\n"
                               + page.text[:_TEXT_CHUNK]})
    else:
        content = [{"type": "text", "text": "문제지 텍스트:\n" + page.text}]
    data = _chat_json(model, _READ_PROMPT, content, max_tokens=16000)
    out = []
    for raw in data.get("questions") or []:
        if not isinstance(raw, dict):
            continue
        q = Question(
            number=_str_or_none(raw.get("number")),
            stem=str(raw.get("stem") or "").strip(),
            choices=[str(c or "").strip() for c in raw.get("choices") or []],
            answer=_answer_indices(raw.get("answer")),
            explanation=str(raw.get("explanation") or "").strip(),
            incomplete=bool(raw.get("incomplete")),
            missing=[str(m) for m in raw.get("missing") or []],
            incomplete_note=str(raw.get("incomplete_note") or "").strip(),
            has_figure=bool(raw.get("has_figure")) and page.image is not None,
            figure_bbox=_clamp_box(raw.get("figure_bbox")),
            region_bbox=_clamp_box(raw.get("region_bbox")),
            page=page.index,
        )
        q.given_answer = bool(q.answer)
        if any(c == "" for c in q.choices):
            q.incomplete = True
            if "choices" not in q.missing:
                q.missing.append("choices")
        q.continuation = bool(raw.get("continuation")) and q.number is None
        if q.stem or q.choices:
            out.append(q)
    return out


def _merge(prev: Question, frag: Question) -> None:
    if frag.stem:
        if prev.choices:      # 선지 뒤에 이어진 텍스트 = 마지막 선지의 연속
            prev.choices[-1] = (prev.choices[-1] + " " + frag.stem).strip()
        else:
            prev.stem = (prev.stem + "\n" + frag.stem).strip()
    prev.choices += frag.choices
    prev.answer = prev.answer or frag.answer
    prev.explanation = "\n".join(filter(None, [prev.explanation, frag.explanation]))
    prev.images += frag.images
    prev.has_figure = prev.has_figure or frag.has_figure
    prev.incomplete = prev.incomplete or frag.incomplete
    prev.missing = sorted(set(prev.missing + frag.missing))


def _number_questions(questions: list[Question]) -> None:
    """번호가 모두 고유한 숫자면 원래 번호, 아니면 1부터 차례대로."""
    nums = [q.number for q in questions]
    if all(n and n.isdigit() for n in nums) and len(set(nums)) == len(nums):
        return
    for i, q in enumerate(questions, 1):
        q.number = str(i)


# ─── 그림 ───

def _attach_figures(page: _Page, questions: list[Question]) -> None:
    if page.image is None or not questions:
        return
    used = set()
    for q in questions:
        if not q.has_figure:
            continue
        boxes = []
        if q.region_bbox:
            for k, box in enumerate(page.embedded):
                if k not in used and _contains(_expand(q.region_bbox, 0.02), _center(box)):
                    boxes.append(box)
                    used.add(k)
        if not boxes and q.figure_bbox:
            boxes = [q.figure_bbox]
        if not boxes and q.region_bbox:
            boxes = [q.region_bbox]
        if not boxes:
            boxes = [[0, 0, 1, 1]]
        for box in boxes:
            crop = _crop(page.image, _expand(box, 0.012))
            if crop is not None:
                q.images.append(save_image(crop))


def _crop(img, box):
    w, h = img.size
    x0, y0, x1, y1 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
    if x1 - x0 < 40 or y1 - y0 < 40:
        return None
    return img.crop((x0, y0, x1, y1))


def _clamp_box(box):
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        x0, y0, x1, y1 = (min(1.0, max(0.0, float(v))) for v in box)
    except (TypeError, ValueError):
        return None
    if x1 - x0 < 0.01 or y1 - y0 < 0.01:
        return None
    return [x0, y0, x1, y1]


def _area(b):
    return (b[2] - b[0]) * (b[3] - b[1])


def _center(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def _contains(b, pt):
    return b[0] <= pt[0] <= b[2] and b[1] <= pt[1] <= b[3]


def _expand(b, pad):
    return [max(0.0, b[0] - pad), max(0.0, b[1] - pad), min(1.0, b[2] + pad), min(1.0, b[3] + pad)]


# ─── 2단계: 정답·해설 ───

def solve_exam(questions: list[Question], model: str = "gpt-4o", incomplete_mode: str = "mark",
               term_rule: str = "", on_progress=None) -> list[str]:
    """questions를 제자리에서 채운다. 경고 목록을 돌려준다."""
    batches = [questions[i:i + _SOLVE_BATCH] for i in range(0, len(questions), _SOLVE_BATCH)]
    prompt = _SOLVE_PROMPT.format(
        incomplete_rule=_FILL_RULE if incomplete_mode == "fill" else _MARK_RULE,
        term_rule=f"- 의학용어 표기: {term_rule}" if term_rule else "",
    )
    warnings = []
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = {pool.submit(_solve_batch, b, model, prompt, incomplete_mode): b for b in batches}
        for done, fut in enumerate(as_completed(futures), 1):
            try:
                fut.result()
            except RuntimeError:
                raise
            except Exception as e:
                nums = ", ".join(q.number or "?" for q in futures[fut])
                warnings.append(f"문제 {nums}: 해설 생성 실패 ({e})")
            if on_progress:
                on_progress(done, len(batches))
    return warnings


def _solve_batch(batch: list[Question], model: str, prompt: str, incomplete_mode: str) -> None:
    from images import image_path
    from PIL import Image

    items, content = [], []
    for q in batch:
        items.append({
            "number": q.number,
            "stem": q.stem,
            "choices": {str(i + 1): (c or "(빈칸)") for i, c in enumerate(q.choices)},
            "given_answer": [i + 1 for i in q.answer],
            "given_explanation": q.explanation,
            "incomplete": q.incomplete,
            "incomplete_note": q.incomplete_note,
            "figures": len(q.images),
        })
        for k, img_id in enumerate(q.images[:4], 1):
            path = image_path(img_id)
            if path:
                content.append({"type": "text", "text": f"[문제 {q.number} 그림 {k}]"})
                content.append({"type": "image_url",
                                "image_url": {"url": _data_url(Image.open(path)), "detail": "high"}})
    content.insert(0, {"type": "text", "text": json.dumps({"questions": items}, ensure_ascii=False)})

    data = _chat_json(model, prompt, content, max_tokens=16000)
    by_num = {str(r.get("number")): r for r in data.get("results") or [] if isinstance(r, dict)}
    for q in batch:
        r = by_num.get(str(q.number))
        if not r:
            continue
        if incomplete_mode == "fill" and q.incomplete:
            stem = str(r.get("completed_stem") or "").strip()
            choices = r.get("completed_choices")
            if stem or choices:
                if stem:
                    q.stem = stem
                if isinstance(choices, list) and choices:
                    q.choices = [str(c).strip() for c in choices]
                q.ai_filled = True
                q.filled_note = str(r.get("filled_note") or "").strip()
        answer = _answer_indices(r.get("answer"))
        if not q.given_answer:
            q.answer = answer
        expl = str(r.get("explanation") or "").strip()
        if expl:
            q.explanation = expl if not q.explanation else f"{q.explanation}\n\n{expl}"


# ─── 3단계: 마크다운 ───

def to_markdown(questions: list[Question]) -> str:
    blocks = []
    for q in questions:
        tag = ""
        if q.ai_filled:
            tag = AI_FILLED_TAG + " "
        elif q.incomplete:
            tag = INCOMPLETE_TAG + " "
        stem_lines = [ln.strip() for ln in q.stem.splitlines() if ln.strip()] or ["(발문 없음)"]
        lines = ["<details>", f"<summary>**문제 {q.number}.** {tag}{_one_line(stem_lines[0])}</summary>", ""]
        lines += [f"> {_one_line(ln)}" for ln in stem_lines[1:]]
        lines += [marker(i) for i in q.images]
        lines.append("")
        circles = "①②③④⑤⑥⑦⑧⑨⑩"
        for i, c in enumerate(q.choices[:10]):
            lines.append(f"   {circles[i]} {_one_line(c) or MISSING_CHOICE}")
        ans = ", ".join(circles[i] for i in q.answer if i < 10) or "정답 미제공"
        lines += ["", "<details>", "<summary>✅ 정답 확인</summary>", "", f"✅ **정답: {ans}**"]
        expl = "\n".join(ln.strip() for ln in q.explanation.splitlines() if ln.strip()) or "해설 없음"
        lines.append(f"💡 **해설:** {expl}")
        if q.ai_filled and q.filled_note:
            lines.append(f"📝 AI 보완: {q.filled_note}")
        elif q.incomplete and q.incomplete_note:
            lines.append(f"📝 복기 불완전: {q.incomplete_note}")
        lines += ["", "</details>", "</details>", ""]
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def _one_line(s: str) -> str:
    return " ".join(str(s).split())


# ─── 공통 ───

def _data_url(img) -> str:
    img = img.copy()
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((_MAX_SIDE, _MAX_SIDE))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _chat_json(model: str, system: str, content: list, max_tokens: int) -> dict:
    last_err = None
    for _ in range(2):
        resp = get_client().chat.completions.create(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": content}],
            response_format={"type": "json_object"},
            **completion_kwargs(model, max_tokens=max_tokens, temperature=0),
        )
        text = (resp.choices[0].message.content or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except ValueError as e:
            last_err = e
    raise ValueError(f"모델 응답을 JSON으로 읽지 못했습니다: {last_err}")


def _answer_indices(raw) -> list[int]:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    out = []
    for v in raw:
        try:
            n = int(str(v).strip().strip("①②③④⑤⑥⑦⑧⑨⑩()."))
        except ValueError:
            circ = "①②③④⑤⑥⑦⑧⑨⑩"
            s = str(v).strip()
            if s and s[0] in circ:
                n = circ.index(s[0]) + 1
            else:
                continue
        if 1 <= n <= 10 and n - 1 not in out:
            out.append(n - 1)
    return sorted(out)


def _str_or_none(v):
    if v is None:
        return None
    s = str(v).strip().rstrip(".")
    return s or None
