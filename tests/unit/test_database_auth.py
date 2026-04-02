from __future__ import annotations

from tools.database import ActigraphDB


def test_user_create_verify_and_lockout(tmp_path):
    db = ActigraphDB(db_path=str(tmp_path / "test.db"))
    assert db.create_or_update_user("tester", "secret123", role="admin") is True
    assert db.verify_user_password("tester", "secret123") is True
    assert db.verify_user_password("tester", "wrong") is False

    for _ in range(3):
        db.record_login_attempt("tester", False)

    locked, remain = db.is_locked_out("tester", max_attempts=3, window_minutes=60, lockout_minutes=15)
    assert locked is True
    assert remain > 0
