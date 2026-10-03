"""OpenAI 클라이언트와 모델별 호출 파라미터.

- 클라이언트는 처음 쓸 때 만든다 → API 키가 없어도 앱 화면은 뜨고, 호출 시점에 안내 메시지를 낸다.
- o-시리즈 / gpt-5 같은 추론 모델은 temperature를 받지 않고 max_completion_tokens를 쓴다.
"""
from functools import lru_cache

from config import get_secret

# 화면에 보여줄 모델 목록 (첫 항목이 기본값)
MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o4-mini", "o3", "gpt-5", "gpt-4-turbo"]

# 모델별 1회 출력 토큰 한도
_MAX_OUTPUT = {
    "gpt-4-turbo": 4096,
    "gpt-4o": 16000,
    "gpt-4o-mini": 16000,
    "gpt-4.1": 32000,
    "gpt-4.1-mini": 32000,
}
_DEFAULT_MAX_OUTPUT = 16000
_REASONING_MAX_OUTPUT = 32000

# 모델별 입력 토큰 안전 한도 (출력 여유분 확보)
_INPUT_LIMIT = {
    "gpt-4-turbo": 12000,   # TPM 30k → 입력 12k + 출력 4k
    "gpt-4o": 100000,
    "gpt-4o-mini": 100000,
    "gpt-4.1": 200000,
    "gpt-4.1-mini": 200000,
    "o4-mini": 100000,
    "o3": 100000,
    "gpt-5": 200000,
}
_DEFAULT_INPUT_LIMIT = 12000


class MissingAPIKeyError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_client():
    key = get_secret("OPENAI_API_KEY")
    if not key:
        raise MissingAPIKeyError(
            "OPENAI_API_KEY가 설정되지 않았습니다. "
            "환경변수나 .streamlit/secrets.toml (Streamlit Cloud는 Secrets)에 넣어 주세요."
        )
    from openai import OpenAI
    return OpenAI(api_key=key)


def is_reasoning_model(model: str) -> bool:
    return model.startswith(("o1", "o3", "o4", "gpt-5"))


def max_output_tokens(model: str) -> int:
    if is_reasoning_model(model):
        return _REASONING_MAX_OUTPUT
    return _MAX_OUTPUT.get(model, _DEFAULT_MAX_OUTPUT)


def input_limit(model: str) -> int:
    return _INPUT_LIMIT.get(model, _DEFAULT_INPUT_LIMIT)


def completion_kwargs(model: str, max_tokens: int, temperature: float) -> dict:
    """chat.completions.create()에 넘길 모델별 파라미터."""
    max_tokens = min(max_tokens, max_output_tokens(model))
    if is_reasoning_model(model):
        return {"model": model, "max_completion_tokens": max_tokens}
    return {"model": model, "max_tokens": max_tokens, "temperature": temperature}
