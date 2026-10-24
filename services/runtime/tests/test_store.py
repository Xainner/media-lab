from media_lab.store import Store


def test_restart_marks_inflight_interrupted(tmp_path):
    store = Store(tmp_path / "lab.db")
    store.create_job("j1", "s1", "generate", {"prompt": "x"})
    store.update_job("j1", status="running")
    assert store.mark_interrupted_on_boot() == 1
    assert store.get_job("j1")["status"] == "interrupted"


def test_sessions_roundtrip(tmp_path):
    store = Store(tmp_path / "lab.db")
    store.add_message("s1", "user", "hola", [])
    assert store.session("s1")["messages"][0]["content"] == "hola"


def test_queue_capacity_is_enforced_atomically(tmp_path):
    store = Store(tmp_path / "lab.db")
    assert store.create_job("j1", "s1", "generate", {"prompt": "x"}, max_pending=1)
    assert not store.create_job("j2", "s2", "generate", {"prompt": "y"}, max_pending=1)
    assert store.get_job("j2") is None
