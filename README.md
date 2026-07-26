# AssistCluedo

AssistCluedo is a deterministic terminal investigation game. A master seed generates a classic manor murder case, a shuffled evidence package, a multiple-choice quiz, scoring, and a final solution reveal.

Run locally:

```bash
python -m assistcluedo game start --seed 42 --difficulty easy
```

Useful commands:

```bash
python -m assistcluedo --help
python -m assistcluedo version
python -m assistcluedo framework validate-config
python -m assistcluedo framework generate --seed 42 --difficulty spark --output runs/scenario_42_spark
python -m assistcluedo framework inspect runs/scenario_42_spark
python -m assistcluedo framework regenerate-documents runs/scenario_42_spark
python -m assistcluedo framework regenerate-documents runs/scenario_42_spark --provider template
python -m assistcluedo framework regenerate-documents runs/scenario_42_spark --provider openai --fallback template --max-attempts 3
python -m assistcluedo framework audit runs/scenario_42_spark
python -m assistcluedo framework stress --start-seed 1 --count 500 --difficulty spark
python -m assistcluedo game play runs/scenario_42_spark
python -m assistcluedo game evaluate runs/scenario_42_spark answers.json
python -m assistcluedo game review runs/scenario_42_spark
python -m assistcluedo game audit runs/scenario_42_spark
python -m pytest
python -m mypy src
```

Difficulties:

- `easy`: compact terminal case.
- `medium`: more characters, locations, documents, and questions.
- `hard`: denser evidence package.
- `spark`: larger deterministic case intended for heavier local testing.

The TTY document browser supports document type filters, search, notes, bookmarks, MCQ submission, confidence ratings, scoring, and post-game solution review. Sessions retain answers, confidence ratings, and the list of documents opened before each MCQ answer, so `game review` can show the evidence context used during submission.
Post-game explanations include the supporting documents, facts, timeline events, and a deterministic review of every MCQ choice so distractors are explained after the solution is revealed.

Exports keep oracle data, evaluation data, and the player package separate. Player package documents and quiz files intentionally omit answer keys, internal fact identifiers, explanations, proof links, and private-role fields.
`framework inspect` is player-safe by default; pass `--oracle` only when intentionally reviewing the hidden solution.

The framework pipeline is exposed as composable components for tests and future reuse:
`WorldGenerator`, `ScenarioGenerator`, `TimelineEngine`, `FactEngine`, `TraceGenerator`,
`DocumentPlanner`, `DocumentRenderer`, `ProofGraphBuilder`, and `QuestionGenerator`.
It also provides roadmap-level facade functions from `assistcluedo.framework`, including
`generate_world`, `generate_ground_truth`, `generate_timeline`, `generate_traces`,
`generate_document_plans`, `generate_documents`, `generate_quiz`, `validate_generated_scenario`,
and `evaluate_answers`.

The generated world now includes an explicit travel graph (`travel_edges`) loaded from the scenario pack,
with deterministic fallback edges for selected subgraphs. Validation checks that the graph is connected,
that localized character events respect shortest-path travel time, and that actors can access locations
and weapon locations according to their capabilities. Player-facing exports are produced from an
in-memory `PlayerPackage` model rather than ad hoc filtered oracle objects.
Document rendering is routed through a `TextGenerator` abstraction. The default provider is `local-llm` with
`template` fallback, so a local model such as Qwen is used automatically when
`ASSISTCLUEDO_LOCAL_LLM_COMMAND` is configured. If no local command is configured, or if the model returns
invalid JSON, deterministic source-specific templates keep generation usable. The template provider covers
SMS messages, emails, access logs, witness interviews, autopsy notes, security reports, personal notes,
inventory reports, and contextual records.

LLM providers must return structured JSON and are validated before any text enters the scenario. Document
validation checks visible metadata, text provider/fallback markers, plan/trace truth-mode alignment, mandatory
and forbidden facts, and document creation timestamps against the facts they express. LLM providers are style
engines only: symbolic facts, answers, proof paths, and truth modes remain controlled by the framework.

For `local-llm`, set `ASSISTCLUEDO_LOCAL_LLM_COMMAND` to a command that reads the JSON prompt on stdin and
returns the structured JSON document on stdout. For example, point it to a wrapper around Qwen through Ollama,
llama.cpp, or vLLM:

```bash
export ASSISTCLUEDO_LOCAL_LLM_COMMAND="python scripts/qwen_textgen.py"
python -m assistcluedo framework generate --seed 42 --output runs/scenario_42
```

The terminal game layer is split into testable services matching the roadmap responsibilities:
`CasePresentationService`, `DocumentBrowser`, `PlayerNotebook`, `QuizController`,
`SolutionPresenter`, and `SaveGameManager`.
`framework audit` and `game audit` provide terminal Definition-of-Done checks for the F1-F12
framework criteria and G1-G10 game criteria from the roadmap.

`game evaluate` accepts either a flat answer object or an object with an `answers` field:

```json
{
  "answers": {
    "q1": "c1",
    "q2": "c3"
  }
}
```
