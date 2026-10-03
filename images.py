"""문항 그림 저장소.

문항 마크다운에는 그림을 `![그림](img:<id>)` 한 줄로 넣고, 그림 자체는 store(DB 또는 data/images)에 둔다.
→ 풀이 기록에 base64가 쌓이지 않고, CBT·미리보기·PDF가 같은 그림을 공유한다.
DB에서 읽은 그림은 data/images/에 캐시해서 같은 서버에서는 다시 내려받지 않는다.
"""
import base64
import hashlib
import re
from io import BytesIO
from pathlib import Path

from config import DATA_DIR

IMAGES_DIR = Path(DATA_DIR) / "images"
IMG_RE = re.compile(r"!\[[^\]]*\]\(img:([0-9a-f]{8,64})\)")
_EXT = "webp"            # 무손실 PNG보다 훨씬 작고 ECG 같은 선 그림도 깨끗하다
_QUALITY = 90


def _cache_path(img_id: str) -> Path:
    return IMAGES_DIR / f"{img_id}.{_EXT}"


def save_image(img) -> str:
    """PIL 이미지를 저장하고 id를 돌려준다 (같은 그림은 같은 id)."""
    from store import get_store

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="WEBP", quality=_QUALITY, method=6)
    data = buf.getvalue()
    img_id = hashlib.sha1(data).hexdigest()[:20]
    get_store().put_image(img_id, data)
    _write_cache(img_id, data)
    return img_id


def _write_cache(img_id: str, data: bytes) -> Path:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(img_id)
    if not path.exists():
        path.write_bytes(data)
    return path


def image_path(img_id: str) -> Path | None:
    """로컬 파일 경로. 캐시에 없으면 store에서 받아 캐시한다. 어디에도 없으면 None."""
    path = _cache_path(img_id)
    if path.exists():
        return path
    from store import get_store
    try:
        data = get_store().get_image(img_id)
    except Exception:
        return None
    return _write_cache(img_id, data) if data else None


def marker(img_id: str) -> str:
    return f"![그림](img:{img_id})"


def inline_images_html(md: str) -> str:
    """미리보기용: 그림 표식을 data URI <img>로 바꾼다."""
    def _sub(m):
        path = image_path(m.group(1))
        if not path:
            return "<em>[그림 파일을 찾을 수 없습니다]</em>"
        b64 = base64.b64encode(path.read_bytes()).decode()
        return f'<img class="q-figure" src="data:image/{_EXT};base64,{b64}"/>'
    return IMG_RE.sub(_sub, md)
