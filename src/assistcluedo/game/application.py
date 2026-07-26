from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from assistcluedo.framework.export import export_scenario, load_exported_scenario
from assistcluedo.framework.generator import generate_symbolic_scenario
from assistcluedo.framework.models import Scenario
from assistcluedo.framework.serialization import read_json
from assistcluedo.game.session import GameSession, load_session, save_session


@dataclass(frozen=True)
class LoadedGame:
    scenario: Scenario
    session: GameSession
    session_path: Path


class GameSessionManager:
    def start_new_or_resume(
        self,
        seed: int,
        output_dir: Path | None = None,
        resume: bool = False,
        difficulty: str = "easy",
        content_provider: str = "local-llm",
        fallback: str = "procedural",
        max_attempts: int = 2,
        model: str = "local",
    ) -> LoadedGame:
        run_dir = output_dir or Path("runs") / f"scenario_{seed:06d}"
        session_path = run_dir / "session.json"
        if resume and session_path.exists():
            scenario = self._load_scenario_or_generate(
                run_dir,
                seed,
                difficulty,
                content_provider,
                fallback,
                max_attempts,
                model,
            )
            return LoadedGame(scenario, load_session(session_path), session_path)

        scenario = generate_symbolic_scenario(
            seed,
            difficulty=difficulty,
            content_provider=content_provider,
            fallback=fallback,
            max_attempts=max_attempts,
            model=model,
        )
        export_scenario(scenario, run_dir)
        session = GameSession.new(scenario)
        save_session(session_path, session)
        return LoadedGame(scenario, session, session_path)

    def play_export(self, export_dir: Path) -> LoadedGame:
        scenario = load_exported_scenario(export_dir)
        session_path = export_dir / "session.json"
        if session_path.exists():
            session = load_session(session_path)
        else:
            session = GameSession.new(scenario)
            save_session(session_path, session)
        return LoadedGame(scenario, session, session_path)

    def _load_scenario_or_generate(
        self,
        run_dir: Path,
        seed: int,
        difficulty: str,
        content_provider: str,
        fallback: str,
        max_attempts: int,
        model: str,
    ) -> Scenario:
        scenario_path = run_dir / "scenario.json"
        if scenario_path.exists():
            return Scenario.from_dict(read_json(scenario_path))
        return generate_symbolic_scenario(
            seed,
            difficulty=difficulty,
            content_provider=content_provider,
            fallback=fallback,
            max_attempts=max_attempts,
            model=model,
        )
