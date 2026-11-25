"""P2b — the lessons writer keys an i2p workflow-step failure under 'i2p', not 'unknown'."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_writer_uses_i2p_base_for_workflow_step(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    import dabidabi as _db_mod
    monkeypatch.setattr(_db_mod, "DB_PATH", db_path)
    if _db_mod._db_connection is not None:
        await _db_mod._db_connection.close()
        _db_mod._db_connection = None
    from dabidabi import init_db, get_db
    await init_db()
    db = await get_db()
    await db.execute(
        "INSERT INTO missions (id, title, status, context) VALUES (7, 't', 'active', ?)",
        ('{"workflow_name": "i2p_v3"}',),
    )
    await db.commit()

    from general_beckman import apply as _apply_mod
    source = {"id": 42, "mission_id": 7, "title": "Workflow advance: mission #90", "agent_type": "coder"}

    with patch("kara_kutu.capture", AsyncMock(return_value=True)) as cap:
        await _apply_mod._maybe_emit_lesson_from_posthook_fail(
            source, "grounding", "grounding gate exhausted", None, 5,
        )

    cap.assert_awaited()
    key = cap.call_args.args[0]
    from kara_kutu import error_domain_key
    assert key == error_domain_key("i2p", "grounding")   # NOT ("unknown","grounding")


@pytest.mark.asyncio
async def test_writer_uses_unknown_for_non_workflow_step(tmp_path, monkeypatch):
    """Non-workflow tasks with no tech_stack → legacy 'unknown' stack (unchanged)."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    import dabidabi as _db_mod
    monkeypatch.setattr(_db_mod, "DB_PATH", db_path)
    if _db_mod._db_connection is not None:
        await _db_mod._db_connection.close()
        _db_mod._db_connection = None
    from dabidabi import init_db, get_db
    await init_db()
    db = await get_db()
    await db.execute("INSERT INTO missions (id, title, status, context) VALUES (9, 't', 'active', '{}')")
    await db.commit()

    from general_beckman import apply as _apply_mod
    source = {"id": 55, "mission_id": 9, "title": "some plain task", "agent_type": "coder"}

    with patch("kara_kutu.capture", AsyncMock(return_value=True)) as cap:
        await _apply_mod._maybe_emit_lesson_from_posthook_fail(
            source, "critic_gate", "verdict garbage", "supply a real verdict", 3,
        )

    cap.assert_awaited()
    key = cap.call_args.args[0]
    from kara_kutu import error_domain_key
    assert key == error_domain_key("unknown", "critic_gate")   # non-workflow → unknown
