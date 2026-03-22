from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

import pytest

from coverage_stats.covers import covers, resolve_covers


class FakeItem:
    def __init__(self, function, cls=None, nodeid="test_file.py::test_fn"):
        self.function = function
        self.cls = cls
        self.nodeid = nodeid
        self._covers_lines = None


# --- Helper targets used in tests ---


def _sample_function():
    return 42


class _SampleClass:
    def method_a(self):
        return "a"

    def method_b(self):
        return "b"


@dataclasses.dataclass
class _SampleDataclass:
    x: int = 0
    y: str = ""


# --- Tests ---


@covers(covers)
def test_covers_zero_args_raises_typeerror():
    with pytest.raises(TypeError, match="@covers requires at least one argument"):
        covers()


@covers(covers)
def test_covers_stores_refs_on_function():
    @covers(_sample_function)
    def test_fn():
        pass

    assert hasattr(test_fn, "_covers_refs")
    assert _sample_function in test_fn._covers_refs


@covers(resolve_covers)
def test_resolve_covers_no_decorator():
    def test_fn():
        pass

    item = FakeItem(function=test_fn)
    resolve_covers(item)
    assert item._covers_lines == frozenset()


@covers(resolve_covers)
def test_resolve_covers_direct_function_ref():
    @covers(_sample_function)
    def test_fn():
        pass

    item = FakeItem(function=test_fn)
    resolve_covers(item)

    assert isinstance(item._covers_lines, frozenset)
    assert len(item._covers_lines) > 0
    for entry in item._covers_lines:
        assert isinstance(entry, tuple)
        assert len(entry) == 2
        assert isinstance(entry[0], str)
        assert isinstance(entry[1], int)


@covers(resolve_covers)
def test_resolve_covers_direct_class_ref():
    @covers(_SampleClass)
    def test_fn():
        pass

    item = FakeItem(function=test_fn)
    resolve_covers(item)

    assert isinstance(item._covers_lines, frozenset)
    # Should include class body lines plus method lines
    assert len(item._covers_lines) > 0

    # Verify all entries are (str, int) tuples
    for entry in item._covers_lines:
        assert isinstance(entry, tuple)
        assert len(entry) == 2
        assert isinstance(entry[0], str)
        assert isinstance(entry[1], int)

    # Should include lines from both methods
    all_linenos = {lineno for _, lineno in item._covers_lines}
    method_a_lines, method_a_start = inspect.getsourcelines(_SampleClass.method_a)
    method_b_lines, method_b_start = inspect.getsourcelines(_SampleClass.method_b)
    assert method_a_start in all_linenos
    assert method_b_start in all_linenos


@covers(resolve_covers)
def test_resolve_covers_dotted_string_function():
    @covers("coverage_stats.store.SessionStore.get_or_create")
    def test_fn():
        pass

    item = FakeItem(function=test_fn)
    resolve_covers(item)

    assert isinstance(item._covers_lines, frozenset)
    assert len(item._covers_lines) > 0
    for entry in item._covers_lines:
        assert isinstance(entry, tuple)
        assert len(entry) == 2
        assert isinstance(entry[0], str)
        assert isinstance(entry[1], int)


@covers(resolve_covers)
def test_resolve_covers_dotted_string_class():
    @covers("coverage_stats.store.SessionStore")
    def test_fn():
        pass

    item = FakeItem(function=test_fn)
    resolve_covers(item)

    assert isinstance(item._covers_lines, frozenset)
    assert len(item._covers_lines) > 0

    # Should include multiple methods (get_or_create, merge, to_dict, from_dict)
    from coverage_stats.store import SessionStore

    abs_path = str(Path(inspect.getsourcefile(SessionStore)).resolve())
    paths = {path for path, _ in item._covers_lines}
    assert abs_path in paths

    all_linenos = {lineno for _, lineno in item._covers_lines}
    _, get_or_create_start = inspect.getsourcelines(SessionStore.get_or_create)
    _, merge_start = inspect.getsourcelines(SessionStore.merge)
    assert get_or_create_start in all_linenos
    assert merge_start in all_linenos


@covers(resolve_covers)
def test_resolve_covers_multiple_refs():
    def fn_a():
        return "a"

    def fn_b():
        return "b"

    @covers(fn_a, fn_b)
    def test_fn():
        pass

    item = FakeItem(function=test_fn)
    resolve_covers(item)

    assert isinstance(item._covers_lines, frozenset)

    # Get individual line sets
    item_a = FakeItem(function=fn_a)

    @covers(fn_a)
    def test_fn_a():
        pass

    item_a = FakeItem(function=test_fn_a)

    @covers(fn_b)
    def test_fn_b():
        pass

    item_b = FakeItem(function=test_fn_b)
    resolve_covers(item_a)
    resolve_covers(item_b)

    combined = item_a._covers_lines | item_b._covers_lines
    assert item._covers_lines == combined


@covers(resolve_covers)
def test_resolve_covers_class_level_decorator():
    @covers(_sample_function)
    class TestSomeClass:
        def test_method(self):
            pass

    item = FakeItem(function=TestSomeClass.test_method, cls=TestSomeClass)
    resolve_covers(item)

    assert isinstance(item._covers_lines, frozenset)
    assert len(item._covers_lines) > 0


@covers(resolve_covers)
def test_resolve_covers_bad_dotted_string():
    @covers("no.such.module.Fn")
    def test_fn():
        pass

    item = FakeItem(function=test_fn)

    with pytest.raises(BaseException, match="coverage-stats: cannot resolve"):
        resolve_covers(item)


@covers(resolve_covers)
def test_resolve_covers_dataclass_does_not_raise():
    """@covers on a dataclass must not raise OSError for generated methods like __eq__."""
    @covers(_SampleDataclass)
    def test_fn():
        pass

    item = FakeItem(function=test_fn)
    resolve_covers(item)  # must not raise

    assert isinstance(item._covers_lines, frozenset)
    assert len(item._covers_lines) > 0
