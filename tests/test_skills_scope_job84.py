"""Job 84 — skills list scope param."""
from __future__ import annotations

import inspect

from app.services.skills import list_available_skills


def test_list_available_skills_accepts_scope():
    sig = inspect.signature(list_available_skills)
    assert "scope" in sig.parameters


def test_list_available_skills_source_has_scopes():
    src = inspect.getsource(list_available_skills)
    assert "deduped" in src
    assert "platform" in src
    assert "company" in src
