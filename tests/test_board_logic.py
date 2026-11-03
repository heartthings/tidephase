from datetime import date, time

from data_api.board_logic import (
    assign_themes,
    consecutive_height,
    fold_repeats,
    reason_verdict,
    same_push,
    theme_stage,
    tomorrow_line,
)


def test_consecutive_height_stops_at_a_gap():
    days = [date(2026, 11, 3), date(2026, 11, 2), date(2026, 10, 31)]
    assert consecutive_height(days, {date(2026, 11, 3), date(2026, 11, 2)}) == 2
    assert consecutive_height(days, {date(2026, 11, 3), date(2026, 10, 31)}) == 1


def test_theme_stage_uses_the_cognition_ladder():
    assert theme_stage(2, 8, 4, 0) == "聚集未完成"
    assert theme_stage(3, 8, 4, 0) == "启动"
    assert theme_stage(5, 8, 4, 0) == "发酵"
    assert theme_stage(6, 10, 8, 0) == "高潮"
    assert theme_stage(6, 5, 10, 1) == "分歧"
    assert theme_stage(4, 2, 10, 0) == "退潮"


def test_reason_verdict_marks_a_pocket_when_notes_disagree():
    assert reason_verdict("商业航天", ["商业航天+激光", "商业航天"])[0] == "成立"
    assert reason_verdict("国有企业", ["锂电池", "商业航天", "玻璃"])[0] == "口袋"


def test_same_push_needs_three_names_in_half_an_hour():
    stamps = [time(9, 31), time(9, 40), time(9, 48), time(13, 2)]
    assert same_push(stamps) == "合力"
    assert same_push([time(9, 31), time(14, 2)]) == "主力"


def test_tomorrow_line_stays_short():
    line = tomorrow_line(90, 4, 80)
    assert line["status"] == "一致看多"
    assert len(line["chips"]) <= 3


def test_messages_fold_and_group():
    rows = [
        {"title": "同一条", "content": "商业航天进展", "msg_ts": None},
        {"title": "同一条", "content": "商业航天进展", "msg_ts": None},
    ]
    folded = fold_repeats(rows)
    assert folded[0]["folded"] is False
    assert folded[1]["folded"] is True
    cards = assign_themes(folded, ["商业航天"])
    assert cards[0]["theme"] == "商业航天"
    assert cards[0]["count"] == 2
