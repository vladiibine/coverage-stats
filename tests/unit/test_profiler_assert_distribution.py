from __future__ import annotations

import types

from coverage_stats import covers
from coverage_stats.profiler import ProfilerContext
from coverage_stats.store import SessionStore


def make_item(covers_lines=frozenset(), nodeid="tests/test_mod.py::test_example"):
    return types.SimpleNamespace(_covers_lines=covers_lines, nodeid=nodeid)


# --- record_assertion tests ---


@covers(ProfilerContext.record_assertion)
def test_record_assertion_increments_during_call_phase():
    ctx = ProfilerContext(current_phase="call", current_test_item=make_item())
    ctx.record_assertion()
    assert ctx.current_assert_count == 1


@covers(ProfilerContext.record_assertion)
def test_record_assertion_does_not_increment_during_setup_phase():
    ctx = ProfilerContext(current_phase="setup", current_test_item=make_item())
    ctx.record_assertion()
    assert ctx.current_assert_count == 0


@covers(ProfilerContext.record_assertion)
def test_record_assertion_does_not_increment_during_teardown_phase():
    ctx = ProfilerContext(current_phase="teardown", current_test_item=make_item())
    ctx.record_assertion()
    assert ctx.current_assert_count == 0


@covers(ProfilerContext.record_assertion)
def test_record_assertion_does_not_increment_when_no_test_item():
    ctx = ProfilerContext(current_phase="call", current_test_item=None)
    ctx.record_assertion()
    assert ctx.current_assert_count == 0


@covers(ProfilerContext.record_assertion)
def test_record_assertion_accumulates_multiple_calls():
    ctx = ProfilerContext(current_phase="call", current_test_item=make_item())
    ctx.record_assertion()
    ctx.record_assertion()
    assert ctx.current_assert_count == 2


# --- distribute_asserts tests ---


@covers(ProfilerContext.distribute_asserts)
def test_distribute_asserts_no_asserts_still_records_test_counts():
    """Zero asserts: assert counts stay zero but test counts are still recorded."""
    store = SessionStore()
    ctx = ProfilerContext(
        current_phase="teardown",
        current_test_item=make_item(),
        current_assert_count=0,
    )
    f = "/fake/file.py"
    ctx.current_test_lines = {(f, 1), (f, 2)}

    ctx.distribute_asserts(store)

    for key in [(f, 1), (f, 2)]:
        ld = store.get_or_create(key)
        assert ld.incidental_asserts == 0
        assert ld.incidental_tests == 1
    assert ctx.current_assert_count == 0
    assert ctx.current_test_lines == set()


@covers(ProfilerContext.distribute_asserts)
def test_distribute_asserts_two_asserts_three_incidental_lines():
    """2 asserts, 3 incidental lines: each line gets incidental_asserts += 2."""
    store = SessionStore()
    f = "/fake/file.py"
    lines = {(f, 1), (f, 2), (f, 3)}
    ctx = ProfilerContext(
        current_phase="teardown",
        current_test_item=make_item(covers_lines=frozenset()),
        current_assert_count=2,
    )
    ctx.current_test_lines = set(lines)

    ctx.distribute_asserts(store)

    for key in lines:
        ld = store.get_or_create(key)
        assert ld.incidental_asserts == 2, f"{key} incidental_asserts should be 2"
        assert ld.deliberate_asserts == 0, f"{key} deliberate_asserts should be 0"

    assert ctx.current_assert_count == 0
    assert ctx.current_test_lines == set()


@covers(ProfilerContext.distribute_asserts)
def test_distribute_asserts_mixed_deliberate_and_incidental():
    """1 assert, (f,1) deliberate, (f,2) incidental: split correctly."""
    store = SessionStore()
    f = "/fake/file.py"
    deliberate_key = (f, 1)
    incidental_key = (f, 2)
    ctx = ProfilerContext(
        current_phase="teardown",
        current_test_item=make_item(covers_lines=frozenset([deliberate_key])),
        current_assert_count=1,
    )
    ctx.current_covers_lines = frozenset([deliberate_key])
    ctx.current_test_lines = {deliberate_key, incidental_key}

    ctx.distribute_asserts(store)

    assert store.get_or_create(deliberate_key).deliberate_asserts == 1
    assert store.get_or_create(deliberate_key).incidental_asserts == 0
    assert store.get_or_create(incidental_key).incidental_asserts == 1
    assert store.get_or_create(incidental_key).deliberate_asserts == 0

    assert ctx.current_assert_count == 0
    assert ctx.current_test_lines == set()


@covers(ProfilerContext.distribute_asserts)
def test_distribute_asserts_empty_lines_non_zero_count():
    """count=3 but no executed lines: store unchanged, count reset."""
    store = SessionStore()
    ctx = ProfilerContext(
        current_phase="teardown",
        current_test_item=make_item(),
        current_assert_count=3,
    )
    ctx.current_test_lines = set()

    ctx.distribute_asserts(store)

    assert store._data == {}  # no lines → nothing written
    assert ctx.current_assert_count == 0
    assert ctx.current_test_lines == set()


def test_distribute_asserts_new_test_resets_state():
    """Previous test leftover count and lines are cleared by setup (defensive reset)."""
    ctx = ProfilerContext(
        current_phase="call",
        current_test_item=make_item(),
        current_assert_count=5,
    )
    ctx.current_test_lines = {("/fake/file.py", 1)}

    # Simulate setup clearing state
    ctx.current_test_lines.clear()
    ctx.current_assert_count = 0

    assert ctx.current_assert_count == 0
    assert ctx.current_test_lines == set()


@covers(ProfilerContext.distribute_asserts)
def test_distribute_asserts_records_incidental_test_count():
    """Each line in current_test_lines gets incidental_tests += 1 when not in covers_lines."""
    store = SessionStore()
    f = "/fake/file.py"
    ctx = ProfilerContext(
        current_phase="teardown",
        current_test_item=make_item(covers_lines=frozenset()),
        current_assert_count=0,
    )
    ctx.current_test_lines = {(f, 1), (f, 2)}

    ctx.distribute_asserts(store)

    assert store.get_or_create((f, 1)).incidental_tests == 1
    assert store.get_or_create((f, 2)).incidental_tests == 1
    assert store.get_or_create((f, 1)).deliberate_tests == 0


@covers(ProfilerContext.distribute_asserts)
def test_distribute_asserts_records_deliberate_test_count():
    """Lines in covers_lines get deliberate_tests += 1."""
    store = SessionStore()
    f = "/fake/file.py"
    deliberate_key = (f, 1)
    incidental_key = (f, 2)
    ctx = ProfilerContext(
        current_phase="teardown",
        current_test_item=make_item(covers_lines=frozenset([deliberate_key])),
        current_assert_count=0,
    )
    ctx.current_covers_lines = frozenset([deliberate_key])
    ctx.current_test_lines = {deliberate_key, incidental_key}

    ctx.distribute_asserts(store)

    assert store.get_or_create(deliberate_key).deliberate_tests == 1
    assert store.get_or_create(deliberate_key).incidental_tests == 0
    assert store.get_or_create(incidental_key).incidental_tests == 1
    assert store.get_or_create(incidental_key).deliberate_tests == 0


@covers(ProfilerContext.distribute_asserts)
def test_distribute_asserts_accumulates_test_counts_across_calls():
    """Calling distribute_asserts twice (two tests) accumulates test counts."""
    store = SessionStore()
    f = "/fake/file.py"
    key = (f, 10)

    for _ in range(3):
        ctx = ProfilerContext(
            current_phase="teardown",
            current_test_item=make_item(covers_lines=frozenset()),
            current_assert_count=1,
        )
        ctx.current_test_lines = {key}
        ctx.distribute_asserts(store)

    assert store.get_or_create(key).incidental_tests == 3


@covers(ProfilerContext.distribute_asserts)
def test_distribute_asserts_resets_count_and_lines_after_distribution():
    """After distribute_asserts, both count and lines are cleared."""
    store = SessionStore()
    f = "/fake/file.py"
    ctx = ProfilerContext(
        current_phase="teardown",
        current_test_item=make_item(),
        current_assert_count=4,
    )
    ctx.current_test_lines = {(f, 10)}

    ctx.distribute_asserts(store)

    assert ctx.current_assert_count == 0
    assert ctx.current_test_lines == set()


# --- file-level assert accumulation ---


@covers(ProfilerContext.distribute_asserts)
def test_distribute_asserts_file_level_not_multiplied_by_line_count():
    """File-level incidental assert count = K, not K * N lines touched."""
    store = SessionStore()
    f = "/fake/file.py"
    ctx = ProfilerContext(
        current_phase="teardown",
        current_test_item=make_item(covers_lines=frozenset()),
        current_assert_count=3,
    )
    # 10 lines touched, 3 assertions — file-level should be 3, not 30
    ctx.current_test_lines = {(f, ln) for ln in range(1, 11)}

    ctx.distribute_asserts(store)

    inc, del_ = store.get_file_asserts(f)
    assert inc == 3
    assert del_ == 0


@covers(ProfilerContext.distribute_asserts)
def test_distribute_asserts_file_level_deliberate_when_covers_targets_file():
    """File-level deliberate asserts = K when covers_lines includes lines from that file."""
    store = SessionStore()
    f = "/fake/file.py"
    ctx = ProfilerContext(
        current_phase="teardown",
        current_test_item=make_item(covers_lines=frozenset([(f, 1)])),
        current_assert_count=2,
    )
    ctx.current_covers_lines = frozenset([(f, 1)])
    ctx.current_test_lines = {(f, 1), (f, 2), (f, 3)}

    ctx.distribute_asserts(store)

    inc, del_ = store.get_file_asserts(f)
    assert del_ == 2
    assert inc == 0


@covers(ProfilerContext.distribute_asserts)
def test_distribute_asserts_file_level_across_multiple_files():
    """Each file touched gets the assert count once, regardless of line count."""
    store = SessionStore()
    ctx = ProfilerContext(
        current_phase="teardown",
        current_test_item=make_item(covers_lines=frozenset()),
        current_assert_count=4,
    )
    ctx.current_test_lines = {("/a.py", 1), ("/a.py", 2), ("/b.py", 1)}

    ctx.distribute_asserts(store)

    assert store.get_file_asserts("/a.py") == (4, 0)
    assert store.get_file_asserts("/b.py") == (4, 0)


@covers(ProfilerContext.distribute_asserts)
def test_distribute_asserts_file_level_zero_count_does_not_write():
    """When assert count is 0, file-level asserts remain at 0."""
    store = SessionStore()
    f = "/fake/file.py"
    ctx = ProfilerContext(
        current_phase="teardown",
        current_test_item=make_item(),
        current_assert_count=0,
    )
    ctx.current_test_lines = {(f, 1), (f, 2)}

    ctx.distribute_asserts(store)

    assert store.get_file_asserts(f) == (0, 0)


@covers(ProfilerContext.distribute_asserts)
def test_distribute_asserts_file_level_accumulates_across_tests():
    """Multiple tests contribute independently to the file-level total."""
    store = SessionStore()
    f = "/fake/file.py"

    for count in (2, 3):
        ctx = ProfilerContext(
            current_phase="teardown",
            current_test_item=make_item(covers_lines=frozenset()),
            current_assert_count=count,
        )
        ctx.current_test_lines = {(f, 1)}
        ctx.distribute_asserts(store)

    assert store.get_file_asserts(f) == (5, 0)
