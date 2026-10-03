"""데이터 저장소 — 회원, 풀이 기록, 문항 그림.

DATABASE_URL(Neon 등 Postgres 연결 주소)이 있으면 DB에, 없으면 data/ 폴더의 JSON·PNG 파일에 저장한다.
Streamlit Cloud는 재시작하면 파일이 지워지므로 배포할 때는 DATABASE_URL을 넣는다.

화면 코드는 get_store()가 돌려주는 객체의 메서드만 쓴다:
  get_user / all_users / add_user / set_password
  add_attempt / attempts / all_attempts
  put_image / get_image
  notebooks / save_notebook / delete_notebook          (학습 공간: 과목 노트북 + 단원)
  sets / get_set / save_set / delete_set               (노트북에 저장한 문항 세트)
모든 학습 공간 메서드는 uid로 범위를 제한한다 — 다른 사람 노트북·세트는 읽거나 지울 수 없다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from config import DATA_DIR, HISTORY_PATH, USERS_PATH, get_secret

WORKSPACE_PATH = str(Path(DATA_DIR) / "workspace.json")
from storage import load_json, update_json

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    uid         TEXT PRIMARY KEY,
    pw_hash     TEXT NOT NULL,
    plan        TEXT NOT NULL DEFAULT 'free',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS attempts (
    id          BIGSERIAL PRIMARY KEY,
    uid         TEXT NOT NULL,
    record      JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS attempts_uid_idx ON attempts (uid, id);
CREATE TABLE IF NOT EXISTS notebooks (
    id          TEXT PRIMARY KEY,
    uid         TEXT NOT NULL,
    data        JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS notebooks_uid_idx ON notebooks (uid);
CREATE TABLE IF NOT EXISTS sets (
    id           TEXT PRIMARY KEY,
    uid          TEXT NOT NULL,
    notebook_id  TEXT,
    meta         JSONB NOT NULL,
    markdown     TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sets_uid_idx ON sets (uid, notebook_id);
CREATE TABLE IF NOT EXISTS images (
    id          TEXT PRIMARY KEY,
    data        BYTEA NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class JsonStore:
    """data/ 폴더 파일 저장 (로컬 실행·테스트용)."""

    kind = "file"

    def __init__(self):
        self.images_dir = Path(DATA_DIR) / "images"

    # 회원
    def get_user(self, uid: str) -> str | None:
        return load_json(USERS_PATH).get(uid)

    def all_users(self) -> dict:
        return load_json(USERS_PATH)

    def add_user(self, uid: str, pw_hash: str) -> bool:
        def _add(users):
            if uid in users:
                return False
            users[uid] = pw_hash
            return True
        return update_json(USERS_PATH, _add)

    def set_password(self, uid: str, pw_hash: str) -> None:
        def _set(users):
            users[uid] = pw_hash
        update_json(USERS_PATH, _set)

    # 풀이 기록 (오래된 것 → 최신 순)
    def add_attempt(self, uid: str, record: dict) -> None:
        update_json(HISTORY_PATH, lambda data: data.setdefault(uid, []).append(record))

    def attempts(self, uid: str) -> list:
        return load_json(HISTORY_PATH).get(uid, [])

    def all_attempts(self) -> dict:
        return load_json(HISTORY_PATH)

    # 그림
    def put_image(self, img_id: str, data: bytes) -> None:
        self.images_dir.mkdir(parents=True, exist_ok=True)
        path = self.images_dir / f"{img_id}.webp"
        if not path.exists():
            path.write_bytes(data)

    def get_image(self, img_id: str) -> bytes | None:
        path = self.images_dir / f"{img_id}.webp"
        return path.read_bytes() if path.exists() else None

    # 학습 공간 — data/workspace.json: {uid: {"notebooks": {id: nb}, "sets": {id: set}}}
    def _ws(self, uid: str) -> dict:
        return load_json(WORKSPACE_PATH).get(uid, {"notebooks": {}, "sets": {}})

    def _ws_update(self, uid: str, fn):
        def _apply(data):
            ws = data.setdefault(uid, {"notebooks": {}, "sets": {}})
            ws.setdefault("notebooks", {})
            ws.setdefault("sets", {})
            return fn(ws)
        return update_json(WORKSPACE_PATH, _apply)

    def notebooks(self, uid: str) -> list:
        return sorted(self._ws(uid).get("notebooks", {}).values(), key=lambda n: n.get("created_at", ""))

    def save_notebook(self, uid: str, nb: dict) -> None:
        self._ws_update(uid, lambda ws: ws["notebooks"].__setitem__(nb["id"], nb))

    def delete_notebook(self, uid: str, nb_id: str) -> None:
        def _del(ws):
            ws["notebooks"].pop(nb_id, None)
            for sid in [k for k, v in ws["sets"].items() if v.get("notebook_id") == nb_id]:
                ws["sets"].pop(sid)
        self._ws_update(uid, _del)

    def sets(self, uid: str, notebook_id: str | None = None, with_markdown: bool = False) -> list:
        out = []
        for st in self._ws(uid).get("sets", {}).values():
            if notebook_id is None or st.get("notebook_id") == notebook_id:
                out.append(st if with_markdown else {k: v for k, v in st.items() if k != "markdown"})
        return sorted(out, key=lambda x: x.get("created_at", ""))

    def get_set(self, uid: str, set_id: str) -> dict | None:
        return self._ws(uid).get("sets", {}).get(set_id)

    def save_set(self, uid: str, st: dict) -> None:
        self._ws_update(uid, lambda ws: ws["sets"].__setitem__(st["id"], st))

    def delete_set(self, uid: str, set_id: str) -> None:
        self._ws_update(uid, lambda ws: ws["sets"].pop(set_id, None))


class PgStore:
    """Postgres 저장 (Neon). 작업마다 연결을 새로 연다 — Neon이 잠들었다 깨어나도 끊긴 연결을 붙잡지 않는다."""

    kind = "postgres"

    def __init__(self, url: str):
        self.url = url
        with self._conn() as conn:
            conn.execute(_SCHEMA)

    def _conn(self):
        import psycopg
        return psycopg.connect(self.url, connect_timeout=15, autocommit=True)

    def _one(self, sql, params=()):
        with self._conn() as conn:
            return conn.execute(sql, params).fetchone()

    def _all(self, sql, params=()):
        with self._conn() as conn:
            return conn.execute(sql, params).fetchall()

    # 회원
    def get_user(self, uid: str) -> str | None:
        row = self._one("SELECT pw_hash FROM users WHERE uid = %s", (uid,))
        return row[0] if row else None

    def all_users(self) -> dict:
        return {uid: h for uid, h in self._all("SELECT uid, pw_hash FROM users ORDER BY created_at")}

    def add_user(self, uid: str, pw_hash: str) -> bool:
        row = self._one("INSERT INTO users (uid, pw_hash) VALUES (%s, %s) "
                        "ON CONFLICT (uid) DO NOTHING RETURNING uid", (uid, pw_hash))
        return row is not None

    def set_password(self, uid: str, pw_hash: str) -> None:
        self._one("UPDATE users SET pw_hash = %s WHERE uid = %s RETURNING uid", (pw_hash, uid))

    # 풀이 기록
    def add_attempt(self, uid: str, record: dict) -> None:
        from psycopg.types.json import Jsonb
        self._one("INSERT INTO attempts (uid, record) VALUES (%s, %s) RETURNING id", (uid, Jsonb(record)))

    def attempts(self, uid: str) -> list:
        return [r for (r,) in self._all("SELECT record FROM attempts WHERE uid = %s ORDER BY id", (uid,))]

    def all_attempts(self) -> dict:
        out: dict = {}
        # 관리자 화면은 통계만 쓰므로 무거운 full_text는 빼고 가져온다
        for uid, rec in self._all("SELECT uid, record - 'full_text' FROM attempts ORDER BY id"):
            out.setdefault(uid, []).append(rec)
        return out

    # 그림
    def put_image(self, img_id: str, data: bytes) -> None:
        self._one("INSERT INTO images (id, data) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING RETURNING id",
                  (img_id, data))

    def get_image(self, img_id: str) -> bytes | None:
        row = self._one("SELECT data FROM images WHERE id = %s", (img_id,))
        return bytes(row[0]) if row else None

    # 학습 공간
    def notebooks(self, uid: str) -> list:
        return [d for (d,) in self._all("SELECT data FROM notebooks WHERE uid = %s ORDER BY created_at", (uid,))]

    def save_notebook(self, uid: str, nb: dict) -> None:
        from psycopg.types.json import Jsonb
        self._one("INSERT INTO notebooks (id, uid, data) VALUES (%s, %s, %s) "
                  "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data WHERE notebooks.uid = EXCLUDED.uid "
                  "RETURNING id", (nb["id"], uid, Jsonb(nb)))

    def delete_notebook(self, uid: str, nb_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM sets WHERE uid = %s AND notebook_id = %s", (uid, nb_id))
            conn.execute("DELETE FROM notebooks WHERE uid = %s AND id = %s", (uid, nb_id))

    def sets(self, uid: str, notebook_id: str | None = None, with_markdown: bool = False) -> list:
        cols = "meta, markdown" if with_markdown else "meta, NULL"
        if notebook_id is None:
            rows = self._all(f"SELECT {cols} FROM sets WHERE uid = %s ORDER BY created_at", (uid,))
        else:
            rows = self._all(f"SELECT {cols} FROM sets WHERE uid = %s AND notebook_id = %s ORDER BY created_at",
                             (uid, notebook_id))
        return [dict(meta, markdown=md) if with_markdown else meta for meta, md in rows]

    def get_set(self, uid: str, set_id: str) -> dict | None:
        row = self._one("SELECT meta, markdown FROM sets WHERE uid = %s AND id = %s", (uid, set_id))
        return dict(row[0], markdown=row[1]) if row else None

    def save_set(self, uid: str, st: dict) -> None:
        from psycopg.types.json import Jsonb
        meta = {k: v for k, v in st.items() if k != "markdown"}
        self._one("INSERT INTO sets (id, uid, notebook_id, meta, markdown) VALUES (%s, %s, %s, %s, %s) "
                  "ON CONFLICT (id) DO UPDATE SET notebook_id = EXCLUDED.notebook_id, meta = EXCLUDED.meta, "
                  "markdown = EXCLUDED.markdown WHERE sets.uid = EXCLUDED.uid RETURNING id",
                  (st["id"], uid, st.get("notebook_id"), Jsonb(meta), st.get("markdown", "")))

    def delete_set(self, uid: str, set_id: str) -> None:
        self._one("DELETE FROM sets WHERE uid = %s AND id = %s RETURNING id", (uid, set_id))


@lru_cache(maxsize=1)
def get_store():
    url = get_secret("DATABASE_URL")
    return PgStore(url) if url else JsonStore()


def migrate_files_to(target) -> dict:
    """data/ 폴더에 쌓인 회원·기록·그림을 target 저장소로 옮긴다 (이미 있는 회원은 건너뜀)."""
    src = JsonStore()
    counts = {"users": 0, "attempts": 0, "images": 0}
    for uid, h in src.all_users().items():
        counts["users"] += bool(target.add_user(uid, h))
    for uid, recs in src.all_attempts().items():
        for rec in recs:
            target.add_attempt(uid, rec)
            counts["attempts"] += 1
    if src.images_dir.exists():
        for path in src.images_dir.glob("*.webp"):
            target.put_image(path.stem, path.read_bytes())
            counts["images"] += 1
    return counts


if __name__ == "__main__":
    # 사용법: DATABASE_URL=postgresql://... python store.py migrate
    import sys
    if sys.argv[1:] == ["migrate"]:
        store = get_store()
        if store.kind != "postgres":
            sys.exit("DATABASE_URL을 설정하고 실행하세요.")
        print(json.dumps(migrate_files_to(store), ensure_ascii=False))
    else:
        print(__doc__)
