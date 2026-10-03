"""회원 계정 (아이디 + 숫자 4자리 비밀번호).

비밀번호는 salt를 붙인 PBKDF2로 저장한다.
예전 노트북 버전의 sha256 해시도 그대로 로그인되며, 로그인 성공 시 새 방식으로 바뀐다.
"""
import hashlib
import hmac
import re
import secrets

from config import USERS_PATH
from storage import load_json, update_json

_ITERATIONS = 200_000
_UID_RE = re.compile(r"[A-Za-z0-9_]{3,20}")
_PW_RE = re.compile(r"\d{4}")


def hash_password(pw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), _ITERATIONS).hex()
    return f"pbkdf2${_ITERATIONS}${salt}${digest}"


def verify_password(pw: str, stored: str) -> bool:
    if stored.startswith("pbkdf2$"):
        _, iters, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(iters)).hex()
        return hmac.compare_digest(calc, digest)
    # 예전 형식: salt 없는 sha256
    return hmac.compare_digest(hashlib.sha256(pw.encode()).hexdigest(), stored)


def load_users() -> dict:
    return load_json(USERS_PATH)


def login(uid: str, pw: str) -> bool:
    stored = load_users().get(uid)
    if not stored or not verify_password(pw or "", stored):
        return False
    if not stored.startswith("pbkdf2$"):
        def _upgrade(users):
            users[uid] = hash_password(pw)
        update_json(USERS_PATH, _upgrade)
    return True


def signup(uid: str, pw: str, pw2: str) -> str | None:
    """성공하면 None, 실패하면 오류 메시지."""
    if not _UID_RE.fullmatch(uid or ""):
        return "아이디는 영문/숫자/_ 3~20자로 입력하세요."
    if not _PW_RE.fullmatch(pw or ""):
        return "비밀번호는 숫자 4자리여야 합니다."
    if pw != pw2:
        return "비밀번호가 일치하지 않습니다."

    def _add(users):
        if uid in users:
            return "이미 사용 중인 아이디입니다."
        users[uid] = hash_password(pw)
        return None
    return update_json(USERS_PATH, _add)
