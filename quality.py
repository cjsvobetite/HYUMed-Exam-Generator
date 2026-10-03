"""생성된 문항 자동 점검·보정.

모델에게 "힌트를 주지 마라"고 해도 정답이 발문에 드러나거나 정답 선지만 길어지는 일이 잦다.
그래서 생성이 끝난 뒤 코드로 한 번 더 걸러 낸다.
  - clean_meta():  발문에 새어 나온 설계표 라벨("(예외·함정)" 등)을 지운다.
  - find_issues(): 정답이 발문에 드러난 문항, 정답 선지만 긴 문항을 찾는다.
  - repair():      문제가 있는 문항만 모델에게 다시 쓰게 해서 원문에 끼워 넣는다.
"""
from __future__ import annotations

import re
from statistics import mean

from blueprint import ANGLES

MAX_REPAIR = 12                 # 한 번에 다시 쓰는 최대 문항 수
_LONG_RATIO = 1.4               # 정답 선지 길이가 오답 평균의 몇 배 이상이면 문제
_LONG_DIFF = 8                  # ...그리고 글자 수 차이가 이 이상일 때

_ANGLE_ALT = "|".join(re.escape(a) for a in sorted(ANGLES + ["임상 적용 (증례)"], key=len, reverse=True))
_META_RE = re.compile(rf"\s*[\(\[]\s*(?:{_ANGLE_ALT})\s*[\)\]]")
_QHEAD_RE = re.compile(r"\*\*(?:문제|Q|C)\s*(\d+)\.?\*\*")
_STOP = {"cell", "cells", "type", "factor", "system", "disease", "syndrome", "protein", "gene"}


def clean_meta(md: str) -> str:
    """발문(<summary> 줄)에 붙은 묻는 방식 라벨을 지운다."""
    return "\n".join(_META_RE.sub("", ln) if "<summary>" in ln else ln for ln in md.split("\n"))


def _len(s: str) -> int:
    return len(re.sub(r"\s+", "", s))


def _leaks(answer: str, stem: str) -> list[str]:
    """정답 텍스트의 핵심 단어(또는 그 어근)가 발문에 들어 있으면 그 단어들을 돌려준다."""
    stem_l = stem.lower()
    found = []
    for tok in re.findall(r"[A-Za-z]{5,}|[가-힣]{3,}", answer):
        t = tok.lower()
        if t in _STOP:
            continue
        root = t[: max(5, len(t) - 2)] if t.isascii() else t
        if root in stem_l:
            found.append(tok)
    return found


def find_issues(questions: list[dict]) -> dict[str, list[str]]:
    """parse_cbt_questions() 결과에서 문항별 문제점 목록."""
    issues: dict[str, list[str]] = {}

    def add(q, msg):
        issues.setdefault(q["id"], []).append(msg)

    for q in questions:
        stem = q["stem"]
        if q["is_subjective"]:
            leaked = _leaks(q.get("answer_text", ""), stem)
            if leaked:
                add(q, f"발문에 정답 단서가 그대로 있음: {', '.join(leaked)} — 정답·번역·어원·파생어를 발문에서 빼고 "
                       "기능·소견·상황으로 묻도록 다시 쓸 것")
            continue
        choices, answers = q["choices"], q["answers"]
        if not answers or len(choices) < 3 or len(answers) >= len(choices):
            continue
        lens = [_len(c) for c in choices]
        right = [lens[i] for i in answers if i < len(lens)]
        wrong = [lens[i] for i in range(len(lens)) if i not in answers]
        if not right or not wrong:
            continue
        if len(answers) == 1 and right[0] == max(lens) \
                and right[0] >= _LONG_RATIO * mean(wrong) and right[0] - mean(wrong) >= _LONG_DIFF:
            add(q, "정답 선지만 눈에 띄게 길고 자세함 — 선지 길이·구체성을 비슷하게 맞출 것")
        elif len(answers) > 1 and mean(right) >= _LONG_RATIO * mean(wrong) and mean(right) - mean(wrong) >= _LONG_DIFF:
            add(q, "정답 선지들이 오답보다 눈에 띄게 길고 자세함 — 선지 길이·구체성을 비슷하게 맞출 것")
        for i in answers:
            c = choices[i] if i < len(choices) else ""
            if _len(c) >= 3 and c.strip().lower() in stem.lower():
                add(q, "정답 선지 내용이 발문에 그대로 들어 있음")
                break
    return issues


def split_blocks(md: str) -> dict[str, tuple[int, int]]:
    """문항 번호 → (시작 줄, 끝 줄) — 바깥 <details>부터 짝이 맞는 </details>까지."""
    lines = md.split("\n")
    blocks, i, n = {}, 0, len(lines)
    while i < n:
        if "<details>" in lines[i]:
            head = next((m for j in range(i, min(n, i + 4)) for m in [_QHEAD_RE.search(lines[j])] if m), None)
            if head:
                depth, k = 0, i
                while k < n:
                    depth += lines[k].count("<details>") - lines[k].count("</details>")
                    if depth <= 0:
                        break
                    k += 1
                blocks[f"문제 {head.group(1)}"] = (i, min(k, n - 1))
                i = k + 1
                continue
        i += 1
    return blocks


def repair(md: str, issues: dict[str, list[str]], system_prompt: str, model: str) -> tuple[str, int]:
    """문제 문항만 다시 쓰게 해서 끼워 넣는다. (새 마크다운, 고친 문항 수)"""
    from cbt import parse_cbt_questions
    from llm import completion_kwargs, get_client

    blocks = split_blocks(md)
    targets = [qid for qid in issues if qid in blocks][:MAX_REPAIR]
    if not targets:
        return md, 0
    lines = md.split("\n")
    req = ["아래 문항들에서 문제점이 발견됐다. 각 문항을 고쳐서 다시 써라.",
           "- 문항 번호, 출제 포인트, 선지 형식, 정답 개수는 그대로 유지한다.",
           "- 고친 문항만, 원래와 같은 마크다운 형식(<details> 구조)으로 출력하고 다른 말은 쓰지 마라.", ""]
    for qid in targets:
        s, e = blocks[qid]
        req.append(f"### {qid} — 문제점: " + " / ".join(issues[qid]))
        req.append("\n".join(lines[s:e + 1]))
        req.append("")
    resp = get_client().chat.completions.create(
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": "\n".join(req)}],
        **completion_kwargs(model, max_tokens=16000, temperature=0.4),
    )
    new_md = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", (resp.choices[0].message.content or "").strip())
    new_blocks = split_blocks(new_md)
    new_lines = new_md.split("\n")
    old_qs = {q["id"]: q for q in parse_cbt_questions(md)}

    replaced = {}
    for qid in targets:
        if qid not in new_blocks:
            continue
        s, e = new_blocks[qid]
        block = "\n".join(new_lines[s:e + 1])
        parsed = parse_cbt_questions(block)
        old = old_qs.get(qid)
        # 형식이 깨졌거나 선지 수·정답 개수가 달라졌으면 원래 문항을 둔다
        if len(parsed) != 1 or not old or parsed[0]["is_subjective"] != old["is_subjective"] \
                or len(parsed[0]["answers"]) != len(old["answers"]):
            continue
        replaced[qid] = block

    for qid in sorted(replaced, key=lambda q: blocks[q][0], reverse=True):
        s, e = blocks[qid]
        lines[s:e + 1] = replaced[qid].split("\n")
    return "\n".join(lines), len(replaced)
