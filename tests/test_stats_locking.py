import sqlite3

import stats


def test_rate_limit_repeated_call_does_not_leave_database_locked(tmp_path, monkeypatch):
    db = tmp_path / "stats.db"
    monkeypatch.setattr(stats, "DB_PATH", str(db))
    monkeypatch.setattr(stats, "_conn", None)

    first = stats.check_rate_limit("127.0.0.1", "chat")
    second = stats.check_rate_limit("127.0.0.1", "chat")
    assert first[0] is True
    assert second[0] is True

    # A separate connection must still be able to write immediately.
    other = sqlite3.connect(db, timeout=1)
    other.execute(
        "INSERT INTO api_keys(key_hash,label,balance_usdc_microcents,created_at,total_requests) VALUES(?,?,?,?,0)",
        ("abc", "test", 0, 1),
    )
    other.commit()
    other.close()
