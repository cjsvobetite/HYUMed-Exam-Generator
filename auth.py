"""회원 계정 (아이디 + 숫자 4자리 비밀번호).

비밀번호는 salt를 붙인 PBKDF2로 저장한다.
예전 노트북 버전의 sha256 해시도 그대로 로그인되며, 로그인 성공 시 새 방식으로 바뀐다.
"""
import hashlib
import hmac
import re
import secrets
import threading
import time

from store import get_store

_ITERATIONS = 200_000
_UID_RE = re.compile(r"[A-Za-z0-9_]{3,20}")
_PW_RE = re.compile(r"\d{4}")

# 비밀번호가 숫자 4자리라 무차별 대입을 막기 위해 아이디별로 연속 실패를 센다
MAX_FAILS = 5
LOCK_SECONDS = 600
_fails: dict[str, tuple[int, float]] = {}   # uid → (연속 실패 횟수, 잠금 해제 시각)
_fails_lock = threading.Lock()


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
    return get_store().all_users()


def locked_for(uid: str) -> int:
    """잠겨 있으면 남은 초, 아니면 0."""
    with _fails_lock:
        _, until = _fails.get((uid or "").lower(), (0, 0.0))
    return max(0, int(until - time.time() + 0.999))


def login(uid: str, pw: str) -> bool:
    """잠긴 아이디는 비밀번호를 확인하지 않고 False. MAX_FAILS번 연속 실패하면 LOCK_SECONDS 동안 잠근다."""
    key = (uid or "").lower()
    if locked_for(uid):
        return False
    stored = get_store().get_user(uid or "")
    if not stored or not verify_password(pw or "", stored):
        with _fails_lock:
            count = _fails.get(key, (0, 0.0))[0] + 1
            if count >= MAX_FAILS:
                _fails[key] = (0, time.time() + LOCK_SECONDS)
            else:
                _fails[key] = (count, 0.0)
        return False
    with _fails_lock:
        _fails.pop(key, None)
    if not stored.startswith("pbkdf2$"):
        get_store().set_password(uid, hash_password(pw))
    return True


def fails_left(uid: str) -> int:
    with _fails_lock:
        return MAX_FAILS - _fails.get((uid or "").lower(), (0, 0.0))[0]


def signup(uid: str, pw: str, pw2: str) -> str | None:
    """성공하면 None, 실패하면 오류 메시지."""
    if not _UID_RE.fullmatch(uid or ""):
        return "아이디는 영문/숫자/_ 3~20자로 입력하세요."
    if not _PW_RE.fullmatch(pw or ""):
        return "비밀번호는 숫자 4자리여야 합니다."
    if pw != pw2:
        return "비밀번호가 일치하지 않습니다."

    if not get_store().add_user(uid, hash_password(pw)):
        return "이미 사용 중인 아이디입니다."
    return None
