from __future__ import annotations

import types

from coverage_stats.assert_counter import distribute_asserts, record_assertion
from coverage_stats.profiler import ProfilerContext
from coverage_stats.store import SessionStore


def make_item(covers_lines=frozenset()):
    return types.SimpleNamespace(_covers_lines=covers_lines)


# --- record_assertion tests ---


def test_record_assertion_increments_during_call_phase():
    ctx = ProfilerContext(current_phase="call", current_test_item=make_item())
    record_assertion(ctx)
    assert ctx.current_assert_count == 1


def test_record_assertion_does_not_increment_during_setup_phase():
    ctx = ProfilerContext(current_phase="setup", current_test_item=make_item())
    record_assertion(ctx)
    assert ctx.current_assert_count == 0


def test_record_assertion_does_not_increment_during_teardown_phase():
    ctx = ProfilerContext(current_phase="teardown", current_test_item=make_item())
    record_assertion(ctx)
    assert ctx.current_assert_count == 0


def test_record_assertion_does_not_increment_when_no_test_item():
    ctx = ProfilerContext(current_phase="call", current_test_item=None)
    record_assertion(ctx)
    assert ctx.current_assert_count == 0


def test_record_assertion_accumulates_multiple_calls():
    ctx = ProfilerContext(current_phase="call", current_test_item=make_item())
    record_assertion(ctx)
    record_assertion(ctx)
    assert ctx.current_assert_count == 2


# --- distribute_asserts tests ---


def test_distribute_asserts_no_asserts_store_unchanged():
    """Zero asserts: store must not be modified."""
    store = SessionStore()
    ctx = ProfilerContext(
        current_phase="teardown",
        current_test_item=make_item(),
        current_assert_count=0,
    )
    f = "/fake/file.py"
    ctx.current_test_lines = {(f, 1), (f, 2)}

    distribute_asserts(ctx, store)

    assert store._data == {}
    assert ctx.current_assert_count == 0
    assert ctx.current_test_lines == set()


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

    distribute_asserts(ctx, store)

    for key in lines:
        ld = store.get_or_create(key)
        assert ld.incidental_asserts == 2, f"{key} incidental_asserts should be 2"
        assert ld.deliberate_asserts == 0, f"{key} deliberate_asserts should be 0"

    assert ctx.current_assert_count == 0
    assert ctx.current_test_lines == set()


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
    ctx.current_test_lines = {deliberate_key, incidental_key}

    distribute_asserts(ctx, store)

    assert store.get_or_create(deliberate_key).deliberate_asserts == 1
    assert store.get_or_create(deliberate_key).incidental_asserts == 0
    assert store.get_or_create(incidental_key).incidental_asserts == 1
    assert store.get_or_create(incidental_key).deliberate_asserts == 0

    assert ctx.current_assert_count == 0
    assert ctx.current_test_lines == set()


def test_distribute_asserts_empty_lines_non_zero_count():
    """count=3 but no executed lines: store unchanged, count reset."""
    store = SessionStore()
    ctx = ProfilerContext(
        current_phase="teardown",
        current_test_item=make_item(),
        current_assert_count=3,
    )
    ctx.current_test_lines = set()

    distribute_asserts(ctx, store)

    assert store._data == {}
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

    distribute_asserts(ctx, store)

    assert ctx.current_assert_count == 0
    assert ctx.current_test_lines == set()
