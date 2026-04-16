"""Tests for SessionContext — shared state between Agent and collaborators."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from contemplative_agent.adapters.moltbook.session_context import SessionContext
from contemplative_agent.core.memory import MemoryStore
from contemplative_agent.core.skill_router import SkillRouter


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStore:
    return MemoryStore(
        log_dir=tmp_path / "logs",
        knowledge_path=tmp_path / "k.json",
        commented_cache_path=tmp_path / "commented.json",
        agents_path=tmp_path / "agents.json",
    )


class TestSessionContext:
    def test_skill_router_defaults_to_none(self, memory: MemoryStore) -> None:
        ctx = SessionContext(memory=memory)
        assert ctx.skill_router is None

    def test_skill_router_can_be_injected(
        self, memory: MemoryStore, tmp_path: Path,
    ) -> None:
        router = SkillRouter(
            skills_dir=tmp_path / "skills",
            embed_fn=lambda _texts: None,
            log_dir=tmp_path / "logs",
        )
        ctx = SessionContext(memory=memory, skill_router=router)
        assert ctx.skill_router is router

    def test_skill_router_mock_is_accepted(self, memory: MemoryStore) -> None:
        """Typing-wise Optional[SkillRouter]; ducks are fine for tests."""
        mock_router = MagicMock(spec=SkillRouter)
        ctx = SessionContext(memory=memory, skill_router=mock_router)
        assert ctx.skill_router is mock_router
