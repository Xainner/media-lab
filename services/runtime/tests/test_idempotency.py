from concurrent.futures import ThreadPoolExecutor
import pytest
from media_lab.store import Store, IdempotencyConflict


def test_repeat_is_same_job_even_full_or_restarted(tmp_path):
    store = Store(tmp_path / "lab.db")
    args = ("first", "s", "generate", {"prompt": "x"}, 1, "key")
    assert store.create_job_once(*args) == ("first", True)
    assert store.create_job_once("second", *args[1:]) == ("first", False)
    store.mark_interrupted_on_boot()
    assert Store(store.path).create_job_once("third", *args[1:]) == ("first", False)
    assert store.get_job("second") is None


def test_conflicting_body_and_scoped_resume(tmp_path):
    store = Store(tmp_path / "lab.db")
    store.create_job_once("first", "s", "generate", {"prompt": "x"}, key="key")
    with pytest.raises(IdempotencyConflict):
        store.create_job_once("second", "s", "generate", {"prompt": "y"}, key="key")
    assert store.create_job_once("third", "s", "production", {}, key="key", scope="resume:old") == ("third", True)


def test_concurrent_reservations_are_atomic(tmp_path):
    store = Store(tmp_path / "lab.db")
    def submit(index):
        return store.create_job_once(f"j{index}", "s", "generate", {"prompt": "x"}, key="shared")
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(submit, range(16)))
    assert sum(created for _, created in results) == 1
    assert len({job for job, _ in results}) == 1
    assert store.queue_counts() == {"running": 0, "pending": 1}


@pytest.mark.parametrize("key", ["", "x y", "x\n", "ñ", "a" * 129])
def test_bad_keys_rejected(tmp_path, key):
    with pytest.raises(ValueError):
        Store(tmp_path / "lab.db").create_job_once("j", "s", "generate", {}, key=key)
