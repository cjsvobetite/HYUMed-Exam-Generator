import json
import types
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

import exam_import
from cbt import parse_cbt_questions
from exam_import import AI_FILLED_TAG, INCOMPLETE_TAG, MISSING_CHOICE, read_exam, solve_exam, to_markdown
from history import is_graded
from images import IMG_RE, image_path
from pdf_export import build_pdf


def _figure_png():
    img = Image.new("RGB", (400, 300), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 380, 280], outline="red", width=8)
    d.line([20, 150, 380, 150], fill="blue", width=6)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _exam_pdf():
    """1쪽: 문제 1(그림 포함) + 문제 2(선지 일부 누락), 2쪽: 문제 2의 이어지는 선지 + 문제 3."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(600, 800))
    c.drawString(50, 760, "PAGE-ONE 1. What does this ECG show?")
    c.drawImage(ImageReader(BytesIO(_figure_png())), 50, 520, width=300, height=200)   # y(top)=0.1~0.35
    c.drawString(50, 300, "2. Most common cause of MI?")
    c.showPage()
    c.drawString(50, 760, "PAGE-TWO continued choices / 3. Write the BNP meaning")
    c.showPage()
    c.save()
    return buf.getvalue()


READ_RESPONSES = {
    "PAGE-ONE": {"questions": [
        {"number": "1", "stem": "What does this ECG show?", "choices": ["STEMI", "AF", "VT", "Normal", "WPW"],
         "answer": [], "incomplete": False, "has_figure": True,
         "figure_bbox": [0.05, 0.05, 0.9, 0.5], "region_bbox": [0.05, 0.03, 0.95, 0.45]},
        {"number": "2", "stem": "Most common cause of MI?", "choices": ["Atherosclerosis", ""],
         "answer": [], "incomplete": False, "has_figure": False,
         "region_bbox": [0.05, 0.6, 0.95, 0.99]},
    ]},
    "PAGE-TWO": {"questions": [
        {"number": None, "continuation": True, "stem": "", "choices": ["Vasculitis", "Embolism"]},
        {"number": "3", "stem": "Write the BNP meaning", "choices": [], "answer": [],
         "explanation": "Ventricular stretch", "has_figure": False},
    ]},
}


class FakeClient:
    def __init__(self):
        self.calls = []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    def create(self, messages, **kw):
        self.calls.append(kw)
        system, content = messages[0]["content"], messages[1]["content"]
        texts = " ".join(p.get("text", "") for p in content if p["type"] == "text")
        if "디지털화" in system:
            data = next(v for k, v in READ_RESPONSES.items() if k in texts)
        else:
            payload = json.loads(content[0]["text"])
            fill = "보완하라" in system
            results = []
            for q in payload["questions"]:
                r = {"number": q["number"], "answer": [1], "explanation": f"해설 {q['number']}"}
                if q["number"] == "3":
                    r["answer"] = []
                if q["incomplete"] and fill:
                    r.update(completed_choices=["Atherosclerosis", "Spasm", "Vasculitis", "Embolism", "Trauma"],
                             filled_note="2번 선지 보완")
                if q["incomplete"] and not fill:
                    r["answer"] = []
                results.append(r)
            data = {"results": results}
        msg = types.SimpleNamespace(content=json.dumps(data, ensure_ascii=False))
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


@pytest.fixture
def fake(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(exam_import, "get_client", lambda: client)
    return client


def test_read_exam_structures_pages(fake):
    res = read_exam([("exam.pdf", _exam_pdf())])
    assert res.pages == 2 and res.warnings == []
    q1, q2, q3 = res.questions
    assert [q.number for q in res.questions] == ["1", "2", "3"]
    # 이어지는 선지가 문제 2에 붙고, 빈 선지 때문에 불완전 표시
    assert q2.choices == ["Atherosclerosis", "", "Vasculitis", "Embolism"]
    assert q2.incomplete and "choices" in q2.missing
    # 그림: PDF에 든 이미지 객체 경계로 잘라 붙임 (원본 비율 3:2 근처)
    assert len(q1.images) == 1
    w, h = Image.open(image_path(q1.images[0])).size
    assert 1.3 < w / h < 1.7
    assert not q2.images
    assert q3.explanation == "Ventricular stretch" and q3.choices == []
    assert all(c["response_format"] == {"type": "json_object"} for c in fake.calls)


def test_scanned_page_uses_model_figure_bbox(fake):
    # 이미지 객체가 없는 경우(사진 업로드) → 모델이 준 figure_bbox로 잘라냄
    img = Image.new("RGB", (1000, 1400), "white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    pages = exam_import.load_pages([("photo.png", buf.getvalue())])
    pages[0].text = "PAGE-ONE"
    qs = exam_import._read_page(pages[0], "gpt-4o")
    exam_import._attach_figures(pages[0], qs)
    w, h = Image.open(image_path(qs[0].images[0])).size
    assert abs(w - 1000 * 0.874) < 30 and abs(h - 1400 * 0.474) < 30


def test_solve_mark_mode(fake):
    qs = read_exam([("exam.pdf", _exam_pdf())]).questions
    solve_exam(qs, incomplete_mode="mark")
    md = to_markdown(qs)
    parsed = parse_cbt_questions(md)
    p1, p2, p3 = parsed
    assert p1["answers"] == [0] and len(p1["images"]) == 1 and is_graded(p1)
    assert p2["id"] == "문제 2" and p2["stem"].startswith(INCOMPLETE_TAG)
    assert p2["choices"][1] == MISSING_CHOICE and len(p2["choices"]) == 4
    assert p2["answers"] == [] and not is_graded(p2)         # 정답 없음 → 채점 제외
    assert p3["is_subjective"] and "Ventricular stretch" in p3["explanation"]


def test_solve_fill_mode(fake):
    qs = read_exam([("exam.pdf", _exam_pdf())]).questions
    solve_exam(qs, incomplete_mode="fill")
    q2 = qs[1]
    assert q2.ai_filled and q2.choices[1] == "Spasm" and q2.answer == [0]
    p2 = parse_cbt_questions(to_markdown(qs))[1]
    assert p2["stem"].startswith(AI_FILLED_TAG) and len(p2["choices"]) == 5
    assert "2번 선지 보완" in p2["explanation"]


def test_given_answer_is_kept(fake, monkeypatch):
    resp = json.loads(json.dumps(READ_RESPONSES))
    resp["PAGE-ONE"]["questions"][0]["answer"] = [3]
    monkeypatch.setitem(READ_RESPONSES, "PAGE-ONE", resp["PAGE-ONE"])
    qs = read_exam([("exam.pdf", _exam_pdf())]).questions
    solve_exam(qs)
    assert qs[0].given_answer and qs[0].answer == [2]       # AI 답(1번)이 아니라 문제지 정답(3번)


def test_pdf_includes_figures(fake):
    qs = read_exam([("exam.pdf", _exam_pdf())]).questions
    solve_exam(qs)
    md = to_markdown(qs)
    assert IMG_RE.search(md)
    pdf = build_pdf(md, title="문제지")
    assert pdf.startswith(b"%PDF") and b"/Subtype /Image" in pdf


def test_text_input(fake, monkeypatch):
    monkeypatch.setitem(READ_RESPONSES, "복기", {"questions": [
        {"number": "7", "stem": "심부전 1차 치료제는?", "choices": ["이뇨제", "?", ""], "incomplete": True,
         "missing": ["choices"], "incomplete_note": "선지 3개만 기억남"}]})
    res = read_exam([], pasted_text="복기 7. 심부전 1차 치료제는? ① 이뇨제 ② ?")
    assert res.pages == 1 and res.questions[0].incomplete
    assert "선지 3개만 기억남" in to_markdown(res.questions)
