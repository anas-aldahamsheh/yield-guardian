"""The evaluation script stores its result in llm_evaluations, and the import command stores a
result file once. Model answers are scripted; nothing reaches Token Factory."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import respx

from tests.agent.helpers import ScriptedModel, json_reply
from tests.agent.test_agent_evaluation import ROUTER_MODEL, ROUTER_SET, load_script
from tests.agent.test_agent_recording import load
from tests.db.conftest import clean
from tests.llm.helpers import PLACEHOLDER_KEY
from yield_guardian.db.engine import Database
from yield_guardian.llm.dbstores import DbEvaluationStore


async def _stored(url: str) -> int:
    database = Database(url, migrate_on_start=False)
    try:
        return len(await DbEvaluationStore(database.sessionmaker).all())
    finally:
        await database.stop()


def test_a_confirmed_run_is_stored_and_its_file_imports_once(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    asyncio.run(clean(database_url))
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", PLACEHOLDER_KEY)
    monkeypatch.setenv("DATABASE_URL", database_url)
    path = tmp_path / "set.json"
    path.write_text(json.dumps(ROUTER_SET), encoding="utf-8")
    out = tmp_path / "result.json"
    model = ScriptedModel().mount(respx_mock)
    model.add("router", *(json_reply({"intent": "unit_risk"}) for _ in range(3)))
    argv = [str(path), "--model", ROUTER_MODEL, "--confirm", "--out", str(out)]
    assert load_script().main(argv) == 0
    assert "Stored in llm_evaluations." in capsys.readouterr().out
    assert asyncio.run(_stored(database_url)) == 1

    importer = load("import_evaluation")
    assert importer.main([str(out)]) == 0
    assert "already stored" in capsys.readouterr().out
    asyncio.run(clean(database_url))
    assert importer.main([str(out), str(out)]) == 0
    assert asyncio.run(_stored(database_url)) == 1
