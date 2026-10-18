from kettei_kart.duel_render import playback_frames


def test_fast_finish_keeps_both_crossings_and_marks_fast_frames():
    rows = {
        p: [{"evaluator": {"finished": i >= end}} for i in range(100)]
        for p, end in (("sqwish", 24), ("typesafe", 99))
    }
    frames = list(playback_frames(rows, 30, 12))
    assert frames[:180] == [(i, 1) for i in range(180)]
    assert frames[180] == (180, 12)
    assert frames[-60:] == [(i, 1) for i in range(540, 600)]
    assert all(a[0] < b[0] for a, b in zip(frames, frames[1:], strict=False))
    assert len(frames) < 300


def test_normal_speed_and_unfinished_races_keep_every_frame():
    rows = {p: [{"evaluator": {"finished": False}} for _ in range(10)] for p in ("a", "b")}
    expected = [(i, 1) for i in range(60)]
    assert list(playback_frames(rows, 30, 12)) == expected
    assert list(playback_frames(rows, 30, 1)) == expected
