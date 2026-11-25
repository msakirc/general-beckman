# packages/general_beckman/tests/test_grade_pass_captures_experience.py
"""P1 — a grade-PASS at apply.py:6073 captures a step-success experience."""
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
    from dabidabi import init_db, get_db
    await init_db()
    # C1: fresh DB lacks audit_log/task_traces that capture_exemplar (and other
    # posthook machinery) may SELECT — create them lazily like prod does.
    from kara_kutu.audit import _ensure_table as _ensure_audit
    from kara_kutu.tracing import _ensure_table as _ensure_trace
    _db = await get_db()
    await _ensure_audit(_db)
    await _ensure_trace(_db)
    return _db_mod


def _grade_verdict(source_id):
    from general_beckman.result_router import PostHookVerdict
    return PostHookVerdict(
        source_task_id=source_id, kind="grade", passed=True,
        raw={"passed": True, "relevant": True, "complete": True,
             "well_formed": True, "coherent": True},
    )


@pytest.mark.asyncio
async def test_grade_pass_calls_capture_with_step_key(tmp_path, monkeypatch):
    _db_mod = await _setup_db(tmp_path, monkeypatch)
    from dabidabi import add_task, update_task

    source_id = await add_task(
        title="[7.4a] db_schema_author",
        description="",
        agent_type="coder",
        mission_id=1,
        context={"_pending_posthooks": ["grade"]},
    )
    await update_task(source_id, status="ungraded", result="the schema output")

    from general_beckman import apply as _apply_mod
    verdict = _grade_verdict(source_id)
    source = await _db_mod.get_task(source_id)

    # C2: capture is imported LOCALLY inside apply.py's try-block, so patch the
    # SOURCE attribute kara_kutu.capture (NOT _apply_mod.capture, which does not
    # exist as a module attribute). i2p_step_key / quality_from_grade stay REAL so
    # the key + quality assertions are meaningful.
    with patch("kara_kutu.capture", AsyncMock(return_value=True)) as cap:
        await _apply_mod._apply_posthook_verdict_locked(source, verdict)

    cap.assert_awaited_once()
    args = cap.call_args.args
    kwargs = cap.call_args.kwargs
    from kara_kutu import i2p_step_key
    # workflow read from missions.workflow (mission 1 absent) → "" component
    expected_key = i2p_step_key("", "7.4a", "coder")
    assert args[0] == expected_key
    assert kwargs["task_id"] == source_id
    assert kwargs["result"] == "the schema output"
    assert kwargs["mission_id"] == 1
    assert 0.0 < kwargs["quality"] <= 1.0


@pytest.mark.asyncio
async def test_grade_pass_captures_end_to_end(tmp_path, monkeypatch):
    _db_mod = await _setup_db(tmp_path, monkeypatch)
    from dabidabi import add_task, update_task

    source_id = await add_task(
        title="[7.4a] db_schema_author",
        description="",
        agent_type="coder",
        mission_id=1,
        context={"_pending_posthooks": ["grade"]},
    )
    await update_task(source_id, status="ungraded", result="the schema output")

    from general_beckman import apply as _apply_mod
    verdict = _grade_verdict(source_id)
    source = await _db_mod.get_task(source_id)

    # NON-mocked: real capture → store. Proves hook → capture → store end-to-end.
    await _apply_mod._apply_posthook_verdict_locked(source, verdict)

    from kara_kutu import recall, i2p_step_key
    got = await recall(i2p_step_key("", "7.4a", "coder"))
    assert len(got) == 1
    assert got[0].text == "the schema output"
    assert got[0].task_id == source_id
