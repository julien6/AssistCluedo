from __future__ import annotations

import argparse
from pathlib import Path
from statistics import mean
from typing import Any, cast

from assistcluedo import __version__
from assistcluedo.framework.audit import audit_framework_export, audit_game_export
from assistcluedo.framework.difficulty import DIFFICULTIES
from assistcluedo.framework.export import (
    export_scenario,
    load_exported_scenario,
    regenerate_documents,
)
from assistcluedo.framework.generator import generate_symbolic_scenario
from assistcluedo.framework.inspect import inspect_export
from assistcluedo.framework.validation import validate_export
from assistcluedo.game.evaluation import evaluate_answers_file
from assistcluedo.game.review import review_export
from assistcluedo.game.tty import play_exported_game, start_game


def main() -> None:
    parser = argparse.ArgumentParser(prog="assistcluedo")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("version")

    framework = subparsers.add_parser("framework")
    framework_sub = framework.add_subparsers(dest="framework_command")
    framework_sub.add_parser("validate-config")
    generate = framework_sub.add_parser("generate")
    generate.add_argument("--seed", type=int, required=True)
    generate.add_argument("--pack", default="classic_manor")
    generate.add_argument("--difficulty", choices=sorted(DIFFICULTIES), default="easy")
    generate.add_argument("--output", type=Path, default=None)
    stress = framework_sub.add_parser("stress")
    stress.add_argument("--start-seed", type=int, default=1)
    stress.add_argument("--count", type=int, default=100)
    stress.add_argument("--pack", default="classic_manor")
    stress.add_argument("--difficulty", choices=sorted(DIFFICULTIES), default="spark")
    validate = framework_sub.add_parser("validate")
    validate.add_argument("path", type=Path)
    audit = framework_sub.add_parser("audit")
    audit.add_argument("path", type=Path)
    inspect = framework_sub.add_parser("inspect")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--oracle", action="store_true")
    inspect_oracle = framework_sub.add_parser("inspect-oracle")
    inspect_oracle.add_argument("path", type=Path)
    regenerate_documents_parser = framework_sub.add_parser("regenerate-documents")
    regenerate_documents_parser.add_argument("path", type=Path)
    regenerate_documents_parser.add_argument("--provider", default="template")

    game = subparsers.add_parser("game")
    game_sub = game.add_subparsers(dest="game_command")
    start = game_sub.add_parser("start")
    start.add_argument("--seed", type=int, required=True)
    start.add_argument("--pack", default="classic_manor")
    start.add_argument("--difficulty", choices=sorted(DIFFICULTIES), default="easy")
    start.add_argument("--output", type=Path, default=None)
    start.add_argument("--resume", action="store_true")
    play = game_sub.add_parser("play")
    play.add_argument("export_dir", type=Path)
    evaluate = game_sub.add_parser("evaluate")
    evaluate.add_argument("export_dir", type=Path)
    evaluate.add_argument("answers_json", type=Path)
    evaluate.add_argument("--output", type=Path, default=None)
    review = game_sub.add_parser("review")
    review.add_argument("export_dir", type=Path)
    game_audit = game_sub.add_parser("audit")
    game_audit.add_argument("export_dir", type=Path)

    args = parser.parse_args()

    if args.command == "version":
        print(__version__)
        return
    if args.command == "framework":
        _framework(args)
        return
    if args.command == "game":
        _game(args)
        return
    parser.print_help()


def _framework(args: argparse.Namespace) -> None:
    if args.framework_command == "validate-config":
        scenario = generate_symbolic_scenario(42)
        print(
            f"OK: pack={scenario.pack_id} version={scenario.pack_version} "
            f"documents={len(scenario.documents)} questions={len(scenario.questions)}"
        )
        return
    if args.framework_command == "generate":
        if args.pack != "classic_manor":
            raise SystemExit("Only the classic_manor pack is available.")
        scenario = generate_symbolic_scenario(args.seed, pack_id=args.pack, difficulty=args.difficulty)
        output = args.output or Path("runs") / scenario.id
        export_scenario(scenario, output)
        print(f"Generated {scenario.id} in {output}")
        return
    if args.framework_command == "stress":
        if args.pack != "classic_manor":
            raise SystemExit("Only the classic_manor pack is available.")
        document_counts: list[int] = []
        question_counts: list[int] = []
        event_counts: list[int] = []
        failures: list[tuple[int, str]] = []
        for seed in range(args.start_seed, args.start_seed + args.count):
            try:
                scenario = generate_symbolic_scenario(seed, pack_id=args.pack, difficulty=args.difficulty)
            except ValueError as exc:  # pragma: no cover - exercised by CLI use
                failures.append((seed, str(exc)))
                continue
            document_counts.append(len(scenario.documents))
            question_counts.append(len(scenario.questions))
            event_counts.append(len(scenario.events))
        generated = len(document_counts)
        print(
            f"{'OK' if not failures else 'FAILED'}: generated {generated}/{args.count} scenarios "
            f"with difficulty={args.difficulty}"
        )
        if generated:
            print(
                "Documents: "
                f"total={sum(document_counts)}, min={min(document_counts)}, "
                f"max={max(document_counts)}, avg={mean(document_counts):.1f}"
            )
            print(
                "Questions: "
                f"total={sum(question_counts)}, min={min(question_counts)}, "
                f"max={max(question_counts)}, avg={mean(question_counts):.1f}"
            )
            print(
                "Events: "
                f"total={sum(event_counts)}, min={min(event_counts)}, "
                f"max={max(event_counts)}, avg={mean(event_counts):.1f}"
            )
        if failures:
            for seed, message in failures[:10]:
                print(f"- seed {seed}: {message}")
            raise SystemExit(1)
        return
    if args.framework_command == "validate":
        if not args.path.exists():
            raise SystemExit(f"{args.path} does not exist.")
        report = validate_export(args.path)
        print(report.summary())
        if not report.ok:
            for issue in report.issues:
                print(f"- {issue.code}: {issue.message}")
            raise SystemExit(1)
        return
    if args.framework_command == "audit":
        if not args.path.exists():
            raise SystemExit(f"{args.path} does not exist.")
        audit_report = audit_framework_export(args.path)
        print(audit_report.render())
        if not audit_report.ok:
            raise SystemExit(1)
        return
    if args.framework_command == "inspect":
        if not args.path.exists():
            raise SystemExit(f"{args.path} does not exist.")
        print(inspect_export(args.path, include_oracle=args.oracle))
        return
    if args.framework_command == "inspect-oracle":
        oracle = args.path / "oracle"
        if not oracle.exists():
            raise SystemExit(f"No oracle directory at {oracle}")
        print(f"Oracle files in {oracle}:")
        for path in sorted(oracle.iterdir()):
            print(f"- {path.name}")
        return
    if args.framework_command == "regenerate-documents":
        if not args.path.exists():
            raise SystemExit(f"{args.path} does not exist.")
        try:
            scenario = regenerate_documents(args.path, provider=args.provider)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(
            f"Regenerated {len(scenario.documents)} documents in {args.path} "
            f"with provider={args.provider}"
        )
        return
    raise SystemExit("Unknown framework command.")


def _game(args: argparse.Namespace) -> None:
    if args.game_command == "start":
        if args.pack != "classic_manor":
            raise SystemExit("Only the classic_manor pack is available.")
        start_game(
            seed=args.seed,
            output_dir=args.output,
            resume=args.resume,
            difficulty=args.difficulty,
        )
        return
    if args.game_command == "play":
        if not args.export_dir.exists():
            raise SystemExit(f"{args.export_dir} does not exist.")
        play_exported_game(args.export_dir)
        return
    if args.game_command == "evaluate":
        if not args.export_dir.exists():
            raise SystemExit(f"{args.export_dir} does not exist.")
        if not args.answers_json.exists():
            raise SystemExit(f"{args.answers_json} does not exist.")
        scenario = load_exported_scenario(args.export_dir)
        output = args.output or args.export_dir / "evaluation" / "results.json"
        report = evaluate_answers_file(scenario, args.answers_json, output)
        score = cast(dict[str, Any], report["score"])
        print(f"Score: {score['total']}/100 ({score['correct']}/{score['possible']})")
        print(f"Wrote {output}")
        return
    if args.game_command == "review":
        if not args.export_dir.exists():
            raise SystemExit(f"{args.export_dir} does not exist.")
        try:
            print(review_export(args.export_dir))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return
    if args.game_command == "audit":
        if not args.export_dir.exists():
            raise SystemExit(f"{args.export_dir} does not exist.")
        audit_report = audit_game_export(args.export_dir)
        print(audit_report.render())
        if not audit_report.ok:
            raise SystemExit(1)
        return
    raise SystemExit("Unknown game command.")
