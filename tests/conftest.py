from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def disable_local_llm_for_deterministic_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASSISTCLUEDO_LOCAL_LLM_COMMAND", raising=False)
