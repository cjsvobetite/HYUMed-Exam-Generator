"""간격 반복 (spaced repetition) — 언제 다시 볼지 정한다.

카드: 덱에 box(연속으로 '알아요' 한 단계)와 due(다음 복습일 "YYYY-MM-DD")를 적는다.
  알아요 → box+1, due = 오늘 + CARD_DAYS[box]
  몰라요 → box 0, due = 오늘 (오늘 안에 다시)
문항: 풀이 기록에서 계산한다 (workspace.question_status).
  틀림 → 오늘 다시 · 맞힘 n번 연속 → 마지막으로 푼 날 + QUESTION_DAYS[n-1]
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

CARD_DAYS = [1, 2, 4, 8, 16, 32, 64, 120]
QUESTION_DAYS = [1, 3, 7, 14, 30, 60, 120]


def today() -> date:
    return date.today()


def to_date(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _step(days: list[int], n: int) -> int:
    return days[min(max(n, 0), len(days) - 1)]


def rate(card: dict, known: bool, on: date | None = None) -> dict:
    """카드에 '알아요/몰라요' 결과를 적는다 (card를 바꾸고 그대로 돌려준다)."""
    on = on or today()
    card["known"] = bool(known)
    card["reviews"] = int(card.get("reviews") or 0) + 1
    box = int(card.get("box") or 0)
    if known:
        card["due"] = (on + timedelta(days=_step(CARD_DAYS, box))).isoformat()
        card["box"] = box + 1
    else:
        card["box"] = 0
        card["due"] = on.isoformat()
    return card


def card_due(card: dict, on: date | None = None) -> bool:
    """한 번이라도 본 카드 중 복습일이 된 것. (예전 기록: due가 없으면 '몰라요'인 카드만)"""
    if not card.get("reviews"):
        return False
    due = to_date(card.get("due"))
    if due is None:
        return card.get("known") is False
    return due <= (on or today())


def question_due_date(streak: int, last_correct: bool | None, last_day: date | None) -> date | None:
    if last_correct is None or last_day is None:
        return None
    if not last_correct:
        return last_day
    return last_day + timedelta(days=_step(QUESTION_DAYS, streak - 1))
