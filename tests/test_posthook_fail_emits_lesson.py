# packages/general_beckman/tests/test_posthook_fail_emits_lesson.py
"""P1b — a posthook-exhaustion emits a mission lesson via kara_kutu.capture.

Proves `_maybe_emit_lesson_from_posthook_fail` routes through the SINGLE
lessons writer (capture failure-mode → upsert_mission_lesson), not a direct
second upsert.
"""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch


async def _setup_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    import dabidabi as _db_mod
    monkeypatch.setattr(_db_mod, "DB_PATH", db_path)
    if _db_mod._db_connection is not None:
        await _db_mod._db_connection.close()
        _db_mod._db_connection = None
    from dabidabi import init_db
    await init_db()  # creates mission_lessons + missions (registered in dabidabi)
    return _db_mod


@pytest.mark.asyncio
async def test_posthook_fail_calls_capture_failure_mode(tmp_path, monkeypatch):
    await _setup_db(tmp_path, monkeypatch)
    from general_beckman import apply as _apply_mod

    # capture is imported LOCALLY inside the writer's try-block → patch the
    # SOURCE attribute kara_kutu.capture. error_domain_key stays REAL so the
    # key assertion is meaningful.
    with patch("kara_kutu.capture", AsyncMock(return_value=True)) as cap:
        await _apply_mod._maybe_emit_lesson_from_posthook_fail(
            {"id": 42, "mission_id": 1},
            "critic_gate", "verdict garbage", "supply a real verdict", 5,
        )

    cap.assert_awaited_once()
    args, kwargs = cap.call_args.args, cap.call_args.kwargs
    from kara_kutu import error_domain_key
    # mission 1 absent → stack "unknown"; domain == the posthook kind
    assert args[0] == error_domain_key("unknown", "critic_gate")
    assert kwargs["task_id"] == 42
    assert kwargs["mission_id"] == 1
    assert kwargs["pattern"] == "verdict garbage"
    assert kwargs["fix"] == "supply a real verdict"
    assert kwargs["severity"] == "blocker"
    assert kwargs["source_kind"] == "posthook_fail"
    assert kwargs["source_ref"]["kind"] == "critic_gate"
    assert kwargs["source_ref"]["attempts"] == 5
    assert kwargs["source_ref"]["source_task_id"] == 42


@pytest.mark.asyncio
async def test_posthook_fail_writes_lesson_end_to_end(tmp_path, monkeypatch):
    await _setup_db(tmp_path, monkeypatch)
    from general_beckman import apply as _apply_mod

    # NON-mocked: writer → capture → upsert_mission_lesson → row.
    await _apply_mod._maybe_emit_lesson_from_posthook_fail(
        {"id": 42, "mission_id": 1},
        "critic_gate", "verdict garbage", "supply a real verdict", 5,
    )

    from kara_kutu.mission_lessons import _dedup_key
    from dabidabi import get_db
    db = await get_db()
    dk = _dedup_key("unknown", "critic_gate", "verdict garbage")
    row = await (await db.execute(
        "SELECT domain, severity, source_kind, fix, occurrences "
        "FROM mission_lessons WHERE dedup_key=?", (dk,))).fetchone()
    assert row is not None
    assert row[0] == "critic_gate"
    assert row[1] == "blocker"
    assert row[2] == "posthook_fail"
    assert row[3] == "supply a real verdict"
    assert row[4] == 1

    # idempotent: a second identical exhaustion bumps occurrences, no dup row
    await _apply_mod._maybe_emit_lesson_from_posthook_fail(
        {"id": 42, "mission_id": 1},
        "critic_gate", "verdict garbage", "supply a real verdict", 5,
    )
    row2 = await (await db.execute(
        "SELECT occurrences FROM mission_lessons WHERE dedup_key=?", (dk,))).fetchone()
    assert row2[0] == 2
