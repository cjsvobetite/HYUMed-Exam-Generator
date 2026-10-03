"""저장소 테스트 — 파일 저장소는 항상, Postgres는 TEST_DATABASE_URL이 있을 때만."""
import os
import uuid

import pytest

from store import JsonStore, PgStore, migrate_files_to

PG_URL = os.environ.get("TEST_DATABASE_URL")


def _stores():
    yield pytest.param(lambda: JsonStore(), id="file")
    yield pytest.param(lambda: PgStore(PG_URL), id="postgres",
                       marks=pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL 없음"))


@pytest.fixture(params=list(_stores()))
def store(request):
    return request.param()


def _uid():
    return "u" + uuid.uuid4().hex[:10]


def test_users(store):
    uid = _uid()
    assert store.get_user(uid) is None
    assert store.add_user(uid, "h1")
    assert not store.add_user(uid, "h2")          # 중복 가입 거부
    assert store.get_user(uid) == "h1"
    store.set_password(uid, "h3")
    assert store.get_user(uid) == "h3"
    assert store.all_users()[uid] == "h3"


def test_attempts_keep_order(store):
    uid = _uid()
    for i in range(3):
        store.add_attempt(uid, {"ts": f"t{i}", "pct": i * 10, "full_text": "x" * 10, "wrong_ids": ["문제 1"]})
    recs = store.attempts(uid)
    assert [r["ts"] for r in recs] == ["t0", "t1", "t2"]
    assert recs[0]["wrong_ids"] == ["문제 1"] and recs[0]["full_text"] == "x" * 10
    assert [r["ts"] for r in store.all_attempts()[uid]] == ["t0", "t1", "t2"]


def test_images(store):
    img_id = uuid.uuid4().hex[:20]
    assert store.get_image(img_id) is None
    store.put_image(img_id, b"\x00\x01binary")
    store.put_image(img_id, b"other")              # 같은 id는 덮어쓰지 않음
    assert store.get_image(img_id) == b"\x00\x01binary"


@pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL 없음")
def test_postgres_admin_view_skips_full_text():
    pg = PgStore(PG_URL)
    uid = _uid()
    pg.add_attempt(uid, {"ts": "t", "pct": 50, "full_text": "big"})
    rec = pg.all_attempts()[uid][0]
    assert rec["pct"] == 50 and "full_text" not in rec


@pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL 없음")
def test_migrate_files_to_postgres():
    src, pg = JsonStore(), PgStore(PG_URL)
    uid = _uid()
    src.add_user(uid, "hash")
    src.add_attempt(uid, {"ts": "t", "pct": 70})
    src.put_image("feedc0ffee" + uuid.uuid4().hex[:10], b"img")
    counts = migrate_files_to(pg)
    assert counts["users"] >= 1 and pg.get_user(uid) == "hash"
    assert pg.attempts(uid)[-1]["pct"] == 70


@pytest.mark.skipif(not PG_URL, reason="TEST_DATABASE_URL 없음")
def test_app_flow_on_postgres(monkeypatch):
    """auth·history·images가 DB 저장소로 끝까지 동작하는지."""
    import store as store_mod
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    store_mod.get_store.cache_clear()
    try:
        import auth
        import images
        from history import load_history, save_attempt
        from PIL import Image

        uid = _uid()
        assert auth.signup(uid, "1234", "1234") is None
        assert auth.login(uid, "1234") and not auth.login(uid, "9999")
        q = {"id": "문제 1", "is_subjective": False, "answers": [0]}
        save_attempt(uid, [q], {"문제 1": [0]}, full_text="md", title="세트")
        rec = load_history(uid)[0]
        assert rec["pct"] == 100 and rec["title"] == "세트"

        img_id = images.save_image(Image.new("RGB", (60, 40), "red"))
        images._cache_path(img_id).unlink()          # 다른 서버(캐시 없음)에서 읽는 상황
        path = images.image_path(img_id)
        assert path and Image.open(path).size == (60, 40)
    finally:
        store_mod.get_store.cache_clear()
