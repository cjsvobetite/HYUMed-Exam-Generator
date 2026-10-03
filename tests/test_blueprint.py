from collections import Counter

import blueprint
import question_generator
from blueprint import Topic, make_blueprint, render_blueprint
from tests.test_core import _fake_stream_client

AF = ["1) 오지선다 하나만 고르시오 (단일정답)", "3) 오지선다 모두 고르시오 (복수정답)"]
CT = ["기본개념형 (정의·분류·단순 기전)", "응용개념형 (2단계 추론·교차 비교)", "케이스형 (임상 시나리오 통합)"]


def _topics(n):
    return [Topic(section=f"S{i // 5}", point=f"포인트 {i}", emphasis=i % 3, has_sequence=i % 4 == 0)
            for i in range(n)]


def test_each_question_gets_a_different_point_spread_over_lecture():
    slots = make_blueprint(20, AF, CT, _topics(30), seed=1)
    points = [s.topic.point for s in slots]
    assert len(set(points)) == 20                         # 겹치는 포인트 없음
    idx = [int(p.split()[1]) for p in points]
    assert idx == sorted(idx) and idx[0] < 3 and idx[-1] > 26   # 강의 처음~끝을 고르게
    assert not any(s.repeat for s in slots)


def test_few_points_are_reused_with_different_angles():
    slots = make_blueprint(10, AF, CT, _topics(4), seed=2)
    assert sum(s.repeat for s in slots) == 6
    for s in slots:
        if s.repeat:
            first = next(x for x in slots if x.topic is s.topic and not x.repeat)
            assert s.angle != first.angle


def test_formats_rotate_and_angles_vary():
    slots = make_blueprint(12, AF, CT, _topics(20), seed=3)
    assert Counter(s.answer_format for s in slots) == {AF[0]: 6, AF[1]: 6}
    assert all(s.angle == "임상 적용 (증례)" for s in slots if "케이스" in s.content_type)
    assert len({s.angle for s in slots}) >= 4
    assert all(slots[i].angle != slots[i + 1].angle or "케이스" in slots[i].content_type
               for i in range(len(slots) - 1))


def test_select_all_answer_counts_are_balanced():
    slots = make_blueprint(20, AF, CT, _topics(20), seed=4)
    counts = [s.n_answers for s in slots if "모두" in s.answer_format]
    assert sorted(Counter(counts).values()) == [2, 2, 2, 2, 2]     # 1~5개 각 2문항
    assert all(a != b for a, b in zip(counts, counts[1:]))
    assert all(s.n_answers is None for s in slots if "하나만" in s.answer_format)


def test_without_topics_falls_back_to_regions():
    slots = make_blueprint(8, AF, CT, [], seed=5)
    assert {s.region for s in slots} == {"전반부 (0~25%)", "중반부-1 (25~50%)", "중반부-2 (50~75%)", "후반부 (75~100%)"}
    assert "다른 문항과 겹치지 않는 포인트" in render_blueprint(slots)


def test_render_blueprint_table():
    table = render_blueprint(make_blueprint(3, AF, CT, _topics(3), seed=6))
    assert table.splitlines()[0].startswith("| 문항 |")
    assert "| 문제 2 | 오지선다 모두 고르시오 (정답 " in table and "[S0] 포인트 1" in table


def test_extract_topics_dedupes(monkeypatch):
    sent = []
    data = {"topics": [{"section": "A", "point": "MyoD는 분화 결정 인자", "emphasis": 2},
                       {"section": "A", "point": "MyoD는  분화 결정 인자", "emphasis": 1},
                       {"section": "B", "point": "Pax3는 이동에 필요", "emphasis": "x"},
                       {"point": ""}]}
    monkeypatch.setattr("llm.get_client", lambda: _fake_stream_client(sent, data))
    topics = blueprint.extract_topics("전사본", "자료", 10)
    assert [t.point for t in topics] == ["MyoD는 분화 결정 인자", "Pax3는 이동에 필요"]
    assert topics[1].emphasis == 1


def test_generator_sends_blueprint(monkeypatch):
    sent = []
    data = {"topics": [{"section": "근육 발생", "point": f"포인트 {i}", "emphasis": 1} for i in range(6)]}
    client = _fake_stream_client(sent, data)
    monkeypatch.setattr(question_generator, "get_client", lambda: client)
    monkeypatch.setattr("llm.get_client", lambda: client)
    out = list(question_generator.generate_questions("자료", "전사본", answer_formats=AF, content_types=CT,
                                                     num_mcq=4))
    kinds = [d for d, _ in out]
    assert question_generator.BLUEPRINT in kinds and question_generator.STATUS in kinds
    user = sent[-1][1]["content"]
    assert "=== 문항별 설계표" in user and "[근육 발생] 포인트" in user


def test_generator_falls_back_when_topics_fail(monkeypatch):
    sent = []
    client = _fake_stream_client(sent, None)          # 주제 뽑기 실패
    monkeypatch.setattr(question_generator, "get_client", lambda: client)
    monkeypatch.setattr("llm.get_client", lambda: client)
    out = list(question_generator.generate_questions("자료", "전사본", answer_formats=AF, content_types=CT,
                                                     num_mcq=4))
    assert any("실패" in full for d, full in out if d == question_generator.STATUS)
    assert out[-1][1] == "문제 1"                      # 그래도 생성은 진행
    assert "겹치지 않는 포인트" in sent[-1][1]["content"]
