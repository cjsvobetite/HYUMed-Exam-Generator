"""JSON 파일 저장소 — 원자적 쓰기 + 프로세스 내 잠금.

Streamlit은 세션마다 스레드가 따로 돌기 때문에, 두 사람이 동시에 저장하면
파일이 깨지거나 한쪽 기록이 사라질 수 있다. update_json()으로 읽기-수정-쓰기를 한 번에 한다.
"""
import json
import os
import tempfile
import threading
from pathlib import Path

_LOCK = threading.RLock()


def load_json(path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_json(path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise


def update_json(path, fn):
    """data = load → fn(data) → save. fn의 반환값을 돌려준다."""
    with _LOCK:
        data = load_json(path)
        result = fn(data)
        save_json(path, data)
        return result
