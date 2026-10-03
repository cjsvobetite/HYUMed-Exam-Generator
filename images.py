"""문항 그림 저장소.

문항 마크다운에는 그림을 `![그림](img:<id>)` 한 줄로 넣고, 실제 PNG는 data/images/<id>.png에 둔다.
→ 풀이 기록(JSON)에 base64가 쌓이지 않고, CBT·미리보기·PDF가 같은 그림을 공유한다.
"""
import base64
import hashlib
import re
from io import BytesIO
from pathlib import Path

from config import DATA_DIR

IMAGES_DIR = Path(DATA_DIR) / "images"
IMG_RE = re.compile(r"!\[[^\]]*\]\(img:([0-9a-f]{8,64})\)")


def save_image(img) -> str:
    """PIL 이미지를 PNG로 저장하고 id를 돌려준다 (같은 그림은 같은 id)."""
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    data = buf.getvalue()
    img_id = hashlib.sha1(data).hexdigest()[:20]
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    path = IMAGES_DIR / f"{img_id}.png"
    if not path.exists():
        path.write_bytes(data)
    return img_id


def image_path(img_id: str) -> Path | None:
    path = IMAGES_DIR / f"{img_id}.png"
    return path if path.exists() else None


def marker(img_id: str) -> str:
    return f"![그림](img:{img_id})"


def inline_images_html(md: str) -> str:
    """미리보기용: 그림 표식을 data URI <img>로 바꾼다."""
    def _sub(m):
        path = image_path(m.group(1))
        if not path:
            return "<em>[그림 파일을 찾을 수 없습니다]</em>"
        b64 = base64.b64encode(path.read_bytes()).decode()
        return f'<img class="q-figure" src="data:image/png;base64,{b64}"/>'
    return IMG_RE.sub(_sub, md)
