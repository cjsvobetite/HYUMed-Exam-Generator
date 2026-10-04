import hashlib

import auth
import llm
from cbt import parse_cbt_questions
from config import USERS_PATH
from pdf_export import build_pdf
from storage import load_json, save_json

SAMPLE = """
<details>
<summary>**문제 1.** 심근경색의 가장 흔한 원인은?</summary>

   ① 관상동맥 죽상경화
   ② 대동맥 박리
   ③ 심낭염
   ④ 판막 협착
   ⑤ 빈혈

<details>
<summary>✅ 정답 확인</summary>

✅ **정답: ①**
💡 **해설:** 죽상경화반 파열 후 혈전.

</details>
</details>

<details>
<summary>**문제 2.** BNP 상승의 의미를 쓰시오.</summary>

<details>
<summary>✅ 정답 확인</summary>

💡 심실 벽 신장 → 심부전 시사.

</details>
</details>
"""


def test_parse_cbt_questions():
    qs = parse_cbt_questions(SAMPLE)
    assert [q["id"] for q in qs] == ["문제 1", "문제 2"]
    assert qs[0]["choices"][0] == "관상동맥 죽상경화"
    assert qs[0]["answers"] == [0]
    assert not qs[0]["is_subjective"]
    assert qs[1]["is_subjective"]


def test_build_pdf_handles_special_text():
    pdf = build_pdf(SAMPLE + "\nBP < 90 & **unclosed bold\n", title="테스트")
    assert pdf.startswith(b"%PDF")


def test_signup_login_and_duplicate():
    save_json(USERS_PATH, {})
    assert auth.signup("alice", "1234", "1234") is None
    assert auth.signup("alice", "1234", "1234") == "이미 사용 중인 아이디입니다."
    assert auth.signup("a", "1234", "1234")
    assert auth.signup("bob", "12a4", "12a4")
    assert auth.signup("bob", "1234", "4321")
    assert auth.login("alice", "1234")
    assert not auth.login("alice", "0000")
    assert not auth.login("nobody", "1234")
    assert load_json(USERS_PATH)["alice"].startswith("pbkdf2$")


def test_legacy_sha256_password_is_upgraded():
    save_json(USERS_PATH, {"old": hashlib.sha256(b"5678").hexdigest()})
    assert auth.login("old", "5678")
    assert load_json(USERS_PATH)["old"].startswith("pbkdf2$")
    assert auth.login("old", "5678")


def test_completion_kwargs_per_model():
    assert llm.completion_kwargs("gpt-4o", 16000, 0.4) == {
        "model": "gpt-4o", "max_tokens": 16000, "temperature": 0.4}
    assert llm.completion_kwargs("gpt-4-turbo", 16000, 0.4)["max_tokens"] == 4096
    assert llm.completion_kwargs("o3", 16000, 0.4) == {"model": "o3", "max_completion_tokens": 32000}
    assert llm.completion_kwargs("gpt-5", 60000, 0.4)["max_completion_tokens"] == 64000
    assert llm.MODELS[0] == "gpt-5"
    assert "temperature" not in llm.completion_kwargs("gpt-5", 16000, 0.4)


def test_transcript_only_option_reaches_prompts(monkeypatch):
    import question_generator
    from prompt_loader import TRANSCRIPT_ONLY_RULE

    sent = []

    def fake_generate(*a, **kw):
        sent.clear()
        list(question_generator.generate_questions(*a, use_blueprint=False, **kw))
        return sent[-1][0]["content"], sent[-1][1]["content"]

    monkeypatch.setattr(question_generator, "get_client", lambda: _fake_stream_client(sent))
    system, user = fake_generate("슬라이드 내용", "교수님 설명", num_mcq=2, transcript_only=True)
    assert TRANSCRIPT_ONLY_RULE in system
    assert "전사본에 없는 내용은 출제 금지" in user and "유일한 출제 범위" in user
    system, user = fake_generate("슬라이드 내용", "교수님 설명", num_mcq=2, transcript_only=False)
    assert TRANSCRIPT_ONLY_RULE not in system + user
    system, user = fake_generate("슬라이드 내용", "", num_mcq=2, transcript_only=True)   # 전사본 없으면 무시
    assert TRANSCRIPT_ONLY_RULE not in system + user


def _fake_stream_client(sent, topics_json=None):
    """주제 뽑기(JSON) 요청과 문항 생성(stream) 요청을 구분해 흉내 내는 가짜 OpenAI 클라이언트."""
    import json
    import types

    class Completions:
        @staticmethod
        def create(messages, **kw):
            sent.append(messages)
            if kw.get("response_format"):
                if topics_json is None:
                    raise ValueError("topic error")
                msg = types.SimpleNamespace(content=json.dumps(topics_json, ensure_ascii=False))
                return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
            delta = types.SimpleNamespace(content="문제 1")
            return iter([types.SimpleNamespace(choices=[types.SimpleNamespace(delta=delta, finish_reason="stop")])])

    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=Completions))


def test_login_locks_after_five_failures(monkeypatch):
    save_json(USERS_PATH, {})
    auth._fails.clear()
    assert auth.signup("carol", "1234", "1234") is None
    for i in range(auth.MAX_FAILS):
        assert auth.fails_left("carol") == auth.MAX_FAILS - i
        assert not auth.login("carol", "0000")
    assert auth.locked_for("Carol") > 0
    assert not auth.login("carol", "1234")          # 잠긴 동안엔 맞는 비밀번호도 거절
    monkeypatch.setattr(auth.time, "time", lambda: 10**12)   # 잠금 시간이 지나면 다시 로그인
    assert auth.locked_for("carol") == 0 and auth.login("carol", "1234")
    assert auth.fails_left("carol") == auth.MAX_FAILS
