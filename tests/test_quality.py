import types

from cbt import parse_cbt_questions
from quality import clean_meta, find_issues, repair, split_blocks


def q_block(n, stem, choices=None, answer="①", expl="해설"):
    lines = ["<details>", f"<summary>**문제 {n}.** {stem}</summary>", ""]
    for i, c in enumerate(choices or []):
        lines.append(f"   {'①②③④⑤'[i]} {c}")
    lines += ["", "<details>", "<summary>✅ 정답 확인</summary>", "", f"✅ **정답: {answer}**",
              f"💡 **해설:** {expl}", "", "</details>", "</details>", ""]
    return "\n".join(lines)


CARCIN = q_block(9, "'게(crab)'에서 유래한 그리스어 어근으로 '암'을 뜻해 암종(carcinoma)에서 쓰이는 어근을 쓰시오. (예외·함정)",
                 answer="카르시노 (carcin/o)")
LONG = q_block(2, "심부전 1차 치료로 옳은 것은?",
               ["베타차단제", "칼슘통로차단제", "디곡신",
                "체액 과부하가 있으면 루프 이뇨제로 울혈 증상을 먼저 조절한다", "니트로글리세린"], answer="④")
FINE = q_block(3, "근육 위성세포가 발현하는 전사인자는?", ["Pax7", "MyoD", "Myf5", "Myogenin", "Sox9"], answer="①")
MULTI_LONG = q_block(4, "옳은 것을 모두 고르시오.",
                     ["Dystrophin 결손으로 근섬유막이 불안정해져 수축 시 손상된다",
                      "근위부 근육 약화가 먼저 나타나며 Gower sign이 관찰된다",
                      "상염색체 우성", "CK 정상", "여아 호발"], answer="①, ②")


def test_clean_meta_removes_angle_labels_from_stems():
    md = clean_meta(CARCIN + q_block(5, "증례에 대한 설명으로 옳은 것은? (임상 적용 (증례))", ["a", "b", "c"]))
    assert "(예외·함정)" not in md and "(임상 적용 (증례))" not in md
    assert "어근을 쓰시오.</summary>" in md


def test_find_issues():
    qs = parse_cbt_questions(CARCIN + LONG + FINE + MULTI_LONG)
    issues = find_issues(qs)
    assert "carcin" in issues["문제 9"][0]
    assert "정답 선지만" in issues["문제 2"][0]
    assert "문제 3" not in issues
    assert "정답 선지들이" in issues["문제 4"][0]


def test_answer_inside_stem_is_flagged():
    qs = parse_cbt_questions(q_block(6, "Pax7을 발현하는 세포는? 힌트: Pax7", ["Pax7", "위성세포", "섬유모세포"], answer="②"))
    assert find_issues(qs) == {}
    qs = parse_cbt_questions(q_block(7, "위성세포가 발현하는 Pax7과 관련된 것은?", ["Pax7", "MyoD", "Sox9"], answer="①"))
    assert "발문에 그대로" in find_issues(qs)["문제 7"][0]


def test_split_blocks():
    md = "머리말\n" + LONG + FINE + "<details>\n<summary>전체 정답표</summary>\n| 1 | ② |\n</details>"
    blocks = split_blocks(md)
    assert list(blocks) == ["문제 2", "문제 3"]
    s, e = blocks["문제 3"]
    lines = md.split("\n")
    assert "**문제 3.**" in lines[s + 1] and lines[e] == "</details>"


def _client(reply):
    class C:
        @staticmethod
        def create(messages, **kw):
            C.sent = messages
            msg = types.SimpleNamespace(content=reply)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=C)), C


def test_repair_replaces_only_valid_rewrites(monkeypatch):
    md = LONG + FINE + CARCIN
    issues = find_issues(parse_cbt_questions(md))
    fixed_long = q_block(2, "심부전 1차 치료로 옳은 것은?",
                         ["베타차단제 단독", "칼슘통로차단제", "루프 이뇨제", "디곡신 증량", "질산염"], answer="③")
    broken_carcin = q_block(9, "상피 기원 악성 종양을 뜻하는 어근은?", ["a", "b", "c"], answer="①")  # 주관식→객관식: 거부
    client, sent = _client("```markdown\n" + fixed_long + broken_carcin + "\n```")
    monkeypatch.setattr("llm.get_client", lambda: client)
    new_md, n = repair(md, issues, "SYSTEM", "gpt-4o")
    assert n == 1
    qs = {q["id"]: q for q in parse_cbt_questions(new_md)}
    assert qs["문제 2"]["choices"][2] == "루프 이뇨제" and qs["문제 2"]["answers"] == [2]
    assert qs["문제 3"]["choices"][0] == "Pax7"                 # 손대지 않은 문항 그대로
    assert "carcinoma" in qs["문제 9"]["stem"]                  # 형식이 바뀐 재작성은 버림
    assert "문제점:" in sent.sent[1]["content"] and sent.sent[0]["content"] == "SYSTEM"


def test_generator_runs_quality_pass(monkeypatch):
    import question_generator

    class Completions:
        calls = 0

        @staticmethod
        def create(messages, **kw):
            Completions.calls += 1
            if kw.get("stream"):
                delta = types.SimpleNamespace(content=LONG + FINE)
                return iter([types.SimpleNamespace(choices=[types.SimpleNamespace(delta=delta, finish_reason="stop")])])
            fixed = q_block(2, "심부전 1차 치료로 옳은 것은?", ["베타차단제", "루프 이뇨제", "디곡신", "질산염", "ARB"],
                            answer="②")
            msg = types.SimpleNamespace(content=fixed)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=Completions))
    monkeypatch.setattr(question_generator, "get_client", lambda: client)
    monkeypatch.setattr("llm.get_client", lambda: client)
    out = list(question_generator.generate_questions("자료", "전사본", num_mcq=2, use_blueprint=False))
    assert out[-1][0] == question_generator.REPLACE
    final = {q["id"]: q for q in parse_cbt_questions(out[-1][1])}
    assert final["문제 2"]["choices"][1] == "루프 이뇨제"
    assert any("보정" in full for d, full in out if d == question_generator.STATUS)
