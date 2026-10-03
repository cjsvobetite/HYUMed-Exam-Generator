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
    assert llm.completion_kwargs("o3", 16000, 0.4) == {"model": "o3", "max_completion_tokens": 16000}
    assert "temperature" not in llm.completion_kwargs("gpt-5", 16000, 0.4)


def test_transcript_only_option_reaches_prompts(monkeypatch):
    import types

    import question_generator
    from prompt_loader import TRANSCRIPT_ONLY_RULE

    sent = []

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(messages, **kw):
                    sent.append(messages)
                    delta = types.SimpleNamespace(content="문제 1", )
                    return iter([types.SimpleNamespace(
                        choices=[types.SimpleNamespace(delta=delta, finish_reason="stop")])])

    monkeypatch.setattr(question_generator, "get_client", lambda: FakeClient)

    def run(transcript, flag):
        sent.clear()
        list(question_generator.generate_questions("슬라이드 내용", transcript, num_mcq=2,
                                                   transcript_only=flag))
        system, user = sent[0][0]["content"], sent[0][1]["content"]
        return system, user

    system, user = run("교수님 설명", True)
    assert TRANSCRIPT_ONLY_RULE in system and TRANSCRIPT_ONLY_RULE in user
    assert "전사본에 없는 내용은 출제 금지" in user
    system, user = run("교수님 설명", False)
    assert TRANSCRIPT_ONLY_RULE not in system + user
    system, user = run("", True)               # 전사본이 없으면 옵션 무시
    assert TRANSCRIPT_ONLY_RULE not in system + user
