"""배포 후 옛 모듈이 남아 있어도 app.py가 프로젝트 모듈을 새로 불러오는지."""
import sys
import types
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_stale_project_modules_are_reloaded():
    import store as real_store

    stale = types.ModuleType("store")                     # 병합 전 store.py를 흉내 — notebooks 없음
    stale.__file__ = real_store.__file__
    stale.get_store = lambda: types.SimpleNamespace(kind="file")
    saved = {k: sys.modules[k] for k in ("store", "workspace", "views.workspace") if k in sys.modules}
    sys.modules["store"] = stale
    for k in ("workspace", "views.workspace"):
        sys.modules.pop(k, None)
    had_sig = hasattr(sys, "_saluterra_code_sig")
    if had_sig:
        del sys._saluterra_code_sig                       # '코드가 바뀐 뒤 첫 실행' 상황
    try:
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
        assert not at.exception
        assert sys.modules["store"] is not stale
        assert hasattr(sys.modules["store"].get_store(), "notebooks")
    finally:
        sys.modules.update(saved)
