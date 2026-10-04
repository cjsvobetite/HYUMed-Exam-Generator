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
    # 앱이 프로젝트 모듈을 새로 불러오므로, 끝나면 원래 모듈로 모두 되돌려 다른 테스트에 영향이 없게 한다
    saved = {k: m for k, m in sys.modules.items() if str(getattr(m, "__file__", "") or "").startswith(str(ROOT))}
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
        for k in [k for k, m in sys.modules.items()
                  if str(getattr(m, "__file__", "") or "").startswith(str(ROOT)) and k not in saved]:
            del sys.modules[k]
        sys.modules.update(saved)
