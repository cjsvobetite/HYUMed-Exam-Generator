"""CBT 풀이 기록 저장·불러오기.

저장 위치: store.get_store() — DATABASE_URL이 있으면 DB, 없으면 data/cbt_history.json
구조:
  {
    "alice": [
      {
        "ts": "2026-05-10 15:30:00",
        "total": 20, "correct": 14, "pct": 70,
        "wrong_ids": ["문제 3", "문제 7", ...],
        "detail": {"문제 1": true, "문제 3": false, ...}
      },
      ...
    ],
    ...
  }
"""
from datetime import datetime

from store import get_store


def is_graded(q: dict) -> bool:
    """채점 대상: 정답이 있는 객관식 (정답 미제공 문항·주관식 제외)."""
    return not q["is_subjective"] and bool(q["answers"])


def save_attempt(user: str, questions: list, user_ans: dict, full_text: str = "", title: str = "",
                 set_id: str | None = None, sources: dict | None = None, flagged: list | None = None):
    """CBT 제출 결과를 기록에 추가.
    questions: parse_cbt_questions() 반환값
    user_ans:  {qid: [int,...] or str}  (session_state[ans_key])
    full_text: 원본 마크다운 전문 (복습 재풀이용, v2.16)
    set_id:    학습 공간에 저장된 세트를 푼 경우 그 세트 id
    sources:   복습 세트를 푼 경우 {복습 문항 번호: [set_id, 원래 문항 번호]}
    flagged:   🔖 표시한 문항 번호 목록 (나머지 문항은 🔖 해제로 기록)
    """
    obj_qs = [q for q in questions if is_graded(q)]
    detail = {}
    wrong_ids = []
    for q in obj_qs:
        qid = q["id"]
        ua = user_ans.get(qid)
        ua_list = ua if isinstance(ua, list) else []
        correct = sorted(q["answers"]) == sorted(ua_list)
        detail[qid] = correct
        if not correct:
            wrong_ids.append(qid)
    total = len(obj_qs)
    correct_cnt = total - len(wrong_ids)
    pct = int(correct_cnt / total * 100) if total else 0

    record = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "title": title,
        "total": total,
        "correct": correct_cnt,
        "pct": pct,
        "wrong_ids": wrong_ids,
        "detail": detail,
        "full_text": full_text,   # v2.16: 재풀이용 원본 마크다운 저장
    }
    if set_id:
        record["set_id"] = set_id
    if sources:
        record["sources"] = sources
    if set_id or sources:
        flagged_set = set(flagged or [])
        record["flagged_ids"] = [q["id"] for q in questions if q["id"] in flagged_set]
        record["unflagged_ids"] = [q["id"] for q in questions if q["id"] not in flagged_set]
        record["seen_ids"] = [q["id"] for q in questions]     # 채점 안 되는 문항(주관식 등)도 '풀었음'으로
    get_store().add_attempt(user, record)
    return record


def load_history(user: str) -> list:
    """유저의 풀이 기록 리스트 반환 (최신순)."""
    return list(reversed(get_store().attempts(user)))


def get_wrong_questions(questions: list, wrong_ids: list) -> list:
    """틀린 문항 ID 목록으로 해당 문항 객체만 필터링."""
    id_set = set(wrong_ids)
    return [q for q in questions if q["id"] in id_set]
