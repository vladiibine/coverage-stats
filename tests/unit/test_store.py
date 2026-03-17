from __future__ import annotations

from coverage_stats.store import LineData, SessionStore


class TestLineDataDefaults:
    def test_all_fields_default_to_zero(self) -> None:
        ld = LineData()
        assert ld.incidental_executions == 0
        assert ld.deliberate_executions == 0
        assert ld.incidental_asserts == 0
        assert ld.deliberate_asserts == 0
        assert ld.incidental_tests == 0
        assert ld.deliberate_tests == 0


class TestSessionStoreGetOrCreate:
    def test_new_key_returns_zero_line_data(self) -> None:
        store = SessionStore()
        key = ("/some/file.py", 42)
        ld = store.get_or_create(key)
        assert ld == LineData(0, 0, 0, 0, 0, 0)

    def test_new_key_is_stored(self) -> None:
        store = SessionStore()
        key = ("/some/file.py", 42)
        ld = store.get_or_create(key)
        assert key in store._data
        assert store._data[key] is ld

    def test_existing_key_returns_same_object(self) -> None:
        store = SessionStore()
        key = ("/some/file.py", 10)
        ld_first = store.get_or_create(key)
        ld_first.deliberate_executions = 5
        ld_second = store.get_or_create(key)
        assert ld_second is ld_first
        assert ld_second.deliberate_executions == 5


class TestSessionStoreMerge:
    def test_merge_additive_shared_key(self) -> None:
        key = ("/a/b.py", 1)

        store_a = SessionStore()
        ld_a = store_a.get_or_create(key)
        ld_a.incidental_executions = 3
        ld_a.deliberate_executions = 1
        ld_a.incidental_asserts = 2
        ld_a.deliberate_asserts = 0
        ld_a.incidental_tests = 2
        ld_a.deliberate_tests = 1

        store_b = SessionStore()
        ld_b = store_b.get_or_create(key)
        ld_b.incidental_executions = 10
        ld_b.deliberate_executions = 4
        ld_b.incidental_asserts = 1
        ld_b.deliberate_asserts = 7
        ld_b.incidental_tests = 3
        ld_b.deliberate_tests = 2

        store_a.merge(store_b)

        result = store_a.get_or_create(key)
        assert result.incidental_executions == 13
        assert result.deliberate_executions == 5
        assert result.incidental_asserts == 3
        assert result.deliberate_asserts == 7
        assert result.incidental_tests == 5
        assert result.deliberate_tests == 3

    def test_merge_disjoint_keys_all_present(self) -> None:
        key_a = ("/x.py", 1)
        key_b = ("/y.py", 2)

        store_a = SessionStore()
        store_a.get_or_create(key_a).incidental_executions = 1

        store_b = SessionStore()
        store_b.get_or_create(key_b).deliberate_executions = 5

        store_a.merge(store_b)

        assert key_a in store_a._data
        assert key_b in store_a._data
        assert store_a.get_or_create(key_b).deliberate_executions == 5


class TestSessionStoreToDict:
    def test_empty_store_returns_empty_dict(self) -> None:
        store = SessionStore()
        assert store.to_dict() == {}

    def test_to_dict_contains_null_byte_separated_key(self) -> None:
        store = SessionStore()
        key = ("/some/path.py", 99)
        ld = store.get_or_create(key)
        ld.incidental_executions = 1
        ld.deliberate_executions = 2
        ld.incidental_asserts = 3
        ld.deliberate_asserts = 4

        result = store.to_dict()
        assert "/some/path.py\x0099" in result
        assert result["/some/path.py\x0099"] == [1, 2, 3, 4, 0, 0]


class TestSessionStoreRoundTrip:
    def test_round_trip_identical_keys_and_values(self) -> None:
        store = SessionStore()

        key1 = ("/a/b.py", 1)
        ld1 = store.get_or_create(key1)
        ld1.incidental_executions = 5
        ld1.deliberate_executions = 3
        ld1.incidental_asserts = 2
        ld1.deliberate_asserts = 1
        ld1.incidental_tests = 4
        ld1.deliberate_tests = 2

        key2 = ("/c/d.py", 100)
        ld2 = store.get_or_create(key2)
        ld2.incidental_executions = 0
        ld2.deliberate_executions = 7
        ld2.incidental_asserts = 0
        ld2.deliberate_asserts = 4
        ld2.incidental_tests = 0
        ld2.deliberate_tests = 3

        serialized = store.to_dict()
        restored = SessionStore.from_dict(serialized)

        restored_ld1 = restored.get_or_create(key1)
        assert restored_ld1.incidental_executions == 5
        assert restored_ld1.deliberate_executions == 3
        assert restored_ld1.incidental_asserts == 2
        assert restored_ld1.deliberate_asserts == 1
        assert restored_ld1.incidental_tests == 4
        assert restored_ld1.deliberate_tests == 2

        restored_ld2 = restored.get_or_create(key2)
        assert restored_ld2.incidental_executions == 0
        assert restored_ld2.deliberate_executions == 7
        assert restored_ld2.incidental_asserts == 0
        assert restored_ld2.deliberate_asserts == 4
        assert restored_ld2.incidental_tests == 0
        assert restored_ld2.deliberate_tests == 3

    def test_round_trip_via_json_serialization(self) -> None:
        """Verify null-byte separator survives json.dumps → json.loads (xdist transport)."""
        import json

        store = SessionStore()
        key = ("/src/mymodule.py", 7)
        ld = store.get_or_create(key)
        ld.incidental_executions = 3
        ld.deliberate_executions = 1
        ld.incidental_asserts = 2
        ld.deliberate_asserts = 0
        ld.incidental_tests = 2
        ld.deliberate_tests = 1

        json_str = json.dumps(store.to_dict())
        restored = SessionStore.from_dict(json.loads(json_str))

        restored_ld = restored.get_or_create(key)
        assert restored_ld.incidental_executions == 3
        assert restored_ld.deliberate_executions == 1
        assert restored_ld.incidental_asserts == 2
        assert restored_ld.deliberate_asserts == 0
        assert restored_ld.incidental_tests == 2
        assert restored_ld.deliberate_tests == 1

    def test_round_trip_path_with_colon(self) -> None:
        store = SessionStore()
        key = ("/a:b/c.py", 55)
        ld = store.get_or_create(key)
        ld.incidental_executions = 9
        ld.deliberate_executions = 8
        ld.incidental_asserts = 7
        ld.deliberate_asserts = 6
        ld.incidental_tests = 5
        ld.deliberate_tests = 4

        serialized = store.to_dict()
        restored = SessionStore.from_dict(serialized)

        restored_ld = restored.get_or_create(key)
        assert restored_ld.incidental_executions == 9
        assert restored_ld.deliberate_executions == 8
        assert restored_ld.incidental_asserts == 7
        assert restored_ld.deliberate_asserts == 6
        assert restored_ld.incidental_tests == 5
        assert restored_ld.deliberate_tests == 4
