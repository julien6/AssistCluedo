from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from assistcluedo.framework.generator import generate_symbolic_scenario


def test_cli_validate_config() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "assistcluedo", "framework", "validate-config"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "OK:" in result.stdout


def test_cli_stress_outputs_statistics() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "stress",
            "--count",
            "3",
            "--difficulty",
            "medium",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "generated 3/3 scenarios" in result.stdout
    assert "Documents:" in result.stdout
    assert "Questions:" in result.stdout
    assert "Events:" in result.stdout


def test_cli_game_play_uses_existing_export(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--difficulty",
            "medium",
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "assistcluedo", "game", "play", str(tmp_path)],
        input="q\n",
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Seed: 42 | Difficulty: medium" in result.stdout
    assert (tmp_path / "session.json").exists()


def test_cli_game_evaluate_writes_results(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--difficulty",
            "medium",
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    scenario = generate_symbolic_scenario(42, difficulty="medium")
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps({"answers": {question.id: question.correct_choice_ids[0] for question in scenario.questions}}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "assistcluedo", "game", "evaluate", str(tmp_path), str(answers_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    results_path = tmp_path / "evaluation" / "results.json"
    assert "Score: 100/100" in result.stdout
    assert results_path.exists()
    report = json.loads(results_path.read_text(encoding="utf-8"))
    assert report["score"]["total"] == 100
    assert len(report["questions"]) == len(scenario.questions)


def test_cli_game_play_can_submit_tty_quiz_with_confidence(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--difficulty",
            "easy",
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    scenario = generate_symbolic_scenario(42, difficulty="easy")
    quiz_input = "6\n" + "".join("a\n5\n" for _ in scenario.questions)
    result = subprocess.run(
        [sys.executable, "-m", "assistcluedo", "game", "play", str(tmp_path)],
        input=quiz_input,
        check=True,
        capture_output=True,
        text=True,
    )
    session = json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))
    assert "Results" in result.stdout
    assert len(session["answers"]) == len(scenario.questions)
    assert len(session["answer_confidence"]) == len(scenario.questions)
    assert session["state"] == "solution_revealed"


def test_cli_game_review_uses_evaluation_results(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--difficulty",
            "medium",
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    scenario = generate_symbolic_scenario(42, difficulty="medium")
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps({"answers": {question.id: question.correct_choice_ids[0] for question in scenario.questions}}),
        encoding="utf-8",
    )
    subprocess.run(
        [sys.executable, "-m", "assistcluedo", "game", "evaluate", str(tmp_path), str(answers_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "assistcluedo", "game", "review", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Score: 100/100" in result.stdout
    assert "Answer review:" in result.stdout
    assert "Supporting events:" in result.stdout
    assert "Choice review:" in result.stdout
    assert "Solution:" in result.stdout


def test_cli_framework_inspect_is_player_safe_by_default(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--difficulty",
            "medium",
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "assistcluedo", "framework", "inspect", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Scenario:" in result.stdout
    assert "Player Package" in result.stdout
    assert "Oracle" not in result.stdout


def test_cli_framework_inspect_oracle_is_explicit(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--difficulty",
            "medium",
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "assistcluedo", "framework", "inspect", str(tmp_path), "--oracle"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Oracle" in result.stdout
    assert "Culprit:" in result.stdout


def test_cli_framework_regenerate_documents_restores_template_outputs(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--difficulty",
            "medium",
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    scenario_path = tmp_path / "scenario.json"
    scenario_data = json.loads(scenario_path.read_text(encoding="utf-8"))
    original_truth = scenario_data["ground_truth"]
    original_questions = scenario_data["questions"]
    scenario_data["documents"][0]["text"] = "BROKEN DOCUMENT BODY"
    scenario_path.write_text(json.dumps(scenario_data), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "regenerate-documents",
            str(tmp_path),
            "--provider",
            "template",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    regenerated = json.loads(scenario_path.read_text(encoding="utf-8"))
    player_doc = next((tmp_path / "player_package" / "documents").glob("*.json"))
    player_data = json.loads(player_doc.read_text(encoding="utf-8"))
    assert "Regenerated" in result.stdout
    assert "BROKEN DOCUMENT BODY" not in json.dumps(regenerated["documents"])
    assert "BROKEN DOCUMENT BODY" not in json.dumps(player_data)
    assert regenerated["ground_truth"] == original_truth
    assert regenerated["questions"] == original_questions


def test_cli_framework_regenerate_documents_rejects_unknown_provider(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "regenerate-documents",
            str(tmp_path),
            "--provider",
            "unknown",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Unknown text generation provider" in result.stderr


def test_cli_framework_regenerate_documents_supports_mock_provider(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "regenerate-documents",
            str(tmp_path),
            "--provider",
            "mock",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    scenario = json.loads((tmp_path / "scenario.json").read_text(encoding="utf-8"))
    assert scenario["documents"][0]["visible_metadata"]["text_provider"] == "mock"


def test_cli_framework_regenerate_documents_supports_local_llm_provider(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    script = tmp_path / "local_llm.py"
    script.write_text(
        """import json, sys
request = json.loads(sys.stdin.read())
doc_type = request['document_type']
if doc_type == 'sms':
    text = 'SMS export\\nFrom: Alex\\nTo: Blake\\nSent: 20:27\\n20:27  Alex: Hi! Are you still there?\\n20:28  Blake: Yes. Keep it quiet.'
elif doc_type == 'email':
    text = 'From: Alex\\nTo: Blake\\nSubject: Tonight\\nDate: now\\n\\nBlake,\\nWe need to settle this privately.'
elif doc_type == 'witness interview':
    text = 'Statement ref: WIT-LOCAL | audio quality: usable\\nDetective: What did you notice?\\nWitness: I heard footsteps near the hall.'
elif doc_type == 'personal note':
    text = '[recovered from desk drawer]\\nI heard voices again tonight. My hands were shaking when I wrote this.'
elif doc_type in {'access-control log', 'gps report', 'receipt', 'call log'}:
    if doc_type == 'access-control log':
        text = 'timestamp | credential | cardholder | door | result\\n20:27 | LLM-2041 | Alex | Hall | granted'
    elif doc_type == 'gps report':
        text = 'export ref: LOC-LOCAL | source: device cache\\ntimestamp | handset | estimated area | confidence | note\\n20:27 | Alex handset | Hall | medium | local row'
    elif doc_type == 'receipt':
        text = 'receipt no: RCPT-LOCAL | copy: carbon duplicate\\nterminal: service desk\\nline | description | location | clerk\\n01 | signed slip | Hall | desk'
    else:
        text = 'log ref: TEL-LOCAL | exchange clock checked after export\\ntime | extension | party | route note | duration\\n20:27 | house line | Alex | routed near Hall | 00:41'
elif doc_type == 'inventory report':
    text = 'Sheet ref: INV-LOCAL | second count: pending\\nItem checks:\\n- Object: usual storage listed as Hall. Shelf label slightly torn.'
elif doc_type == 'autopsy report':
    text = 'Preliminary autopsy note\\nCase ref: ME-LOCAL\\nFindings:\\n- Estimated death window recorded.\\nChain note: worksheet cross-checked.'
elif doc_type == 'security report':
    text = 'Security maintenance ticket\\nexport ref: SEC-LOCAL | retention: rolling buffer\\nSystem: internal camera network\\nStatus notes:\\n- feed loss recorded.'
elif doc_type == 'newspaper clipping':
    text = 'Society column clipping\\nPublication: Local LLM Gazette\\nClipping filed: now\\nColumn note: page edge torn\\nGuests were noticed near the hall.'
else:
    text = 'Preliminary source excerpt\\nObservation recorded in source format.'
json.dump({
  'title': request['title'],
  'text': text,
  'facts_expressed': request['mandatory_fact_ids'],
  'entities_mentioned': [],
}, sys.stdout)
""",
        encoding="utf-8",
    )
    env = {**os.environ, "ASSISTCLUEDO_LOCAL_LLM_COMMAND": f"{sys.executable} {script}"}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "regenerate-documents",
            str(tmp_path),
            "--provider",
            "local-llm",
            "--fallback",
            "template",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    scenario = json.loads((tmp_path / "scenario.json").read_text(encoding="utf-8"))
    assert scenario["documents"][0]["visible_metadata"]["text_provider"] == "local-llm"


def test_cli_framework_generate_uses_local_llm_by_default_when_configured(tmp_path: Path) -> None:
    script = tmp_path / "local_llm.py"
    script.write_text(
        """import json, sys
request = json.loads(sys.stdin.read())
if request.get('task') == 'assistcluedo_world_content':
    json.dump({
      'characters': {
        item['id']: {
          'name': f"Qwen Character {index}",
          'public_role': f"Qwen role {index}",
          'description': f"Qwen character description {index}",
        }
        for index, item in enumerate(request['characters'], start=1)
      },
      'locations': {
        item['id']: {
          'name': f"Qwen Room {index}",
          'description': f"Qwen location description {index}",
        }
        for index, item in enumerate(request['locations'], start=1)
      },
      'objects': {
        item['id']: {
          'name': f"Qwen Object {index}",
          'description': f"Qwen object description {index}",
        }
        for index, item in enumerate(request['objects'], start=1)
      },
      'motives': ['Qwen motive alpha', 'Qwen motive beta', 'Qwen motive gamma'],
    }, sys.stdout)
elif request.get('task') == 'assistcluedo_scenario_texts':
    json.dump({
      'introduction': {
        'title': 'Qwen case file',
        'context': 'Qwen public context.',
        'objective': 'Qwen objective.',
      },
      'questions': {
        item['id']: {'text': 'Qwen ' + item['text'], 'explanation': 'Qwen ' + item['explanation']}
        for item in request['questions']
      },
    }, sys.stdout)
else:
    doc_type = request['document_type']
    if doc_type == 'sms':
        text = 'SMS export\\nFrom: Alex\\nTo: Blake\\nSent: 20:27\\n20:27  Alex: Hi! Are you still there?\\n20:28  Blake: Yes. Keep it quiet.'
    elif doc_type == 'email':
        text = 'From: Alex\\nTo: Blake\\nSubject: Tonight\\nDate: now\\n\\nBlake,\\nWe need to settle this privately.'
    elif doc_type == 'witness interview':
        text = 'Statement ref: WIT-LOCAL | audio quality: usable\\nDetective: What did you notice?\\nWitness: I heard footsteps near the hall.'
    elif doc_type == 'personal note':
        text = '[recovered from desk drawer]\\nI heard voices again tonight. My hands were shaking when I wrote this.'
    elif doc_type in {'access-control log', 'gps report', 'receipt', 'call log'}:
        if doc_type == 'access-control log':
            text = 'timestamp | credential | cardholder | door | result\\n20:27 | LLM-2041 | Alex | Hall | granted'
        elif doc_type == 'gps report':
            text = 'export ref: LOC-LOCAL | source: device cache\\ntimestamp | handset | estimated area | confidence | note\\n20:27 | Alex handset | Hall | medium | local row'
        elif doc_type == 'receipt':
            text = 'receipt no: RCPT-LOCAL | copy: carbon duplicate\\nterminal: service desk\\nline | description | location | clerk\\n01 | signed slip | Hall | desk'
        else:
            text = 'log ref: TEL-LOCAL | exchange clock checked after export\\ntime | extension | party | route note | duration\\n20:27 | house line | Alex | routed near Hall | 00:41'
    elif doc_type == 'inventory report':
        text = 'Sheet ref: INV-LOCAL | second count: pending\\nItem checks:\\n- Object: usual storage listed as Hall. Shelf label slightly torn.'
    elif doc_type == 'autopsy report':
        text = 'Preliminary autopsy note\\nCase ref: ME-LOCAL\\nFindings:\\n- Estimated death window recorded.\\nChain note: worksheet cross-checked.'
    elif doc_type == 'security report':
        text = 'Security maintenance ticket\\nexport ref: SEC-LOCAL | retention: rolling buffer\\nSystem: internal camera network\\nStatus notes:\\n- feed loss recorded.'
    elif doc_type == 'newspaper clipping':
        text = 'Society column clipping\\nPublication: Local LLM Gazette\\nClipping filed: now\\nColumn note: page edge torn\\nGuests were noticed near the hall.'
    else:
        text = 'Preliminary source excerpt\\nObservation recorded in source format.'
    json.dump({
      'title': request['title'],
      'text': text,
      'facts_expressed': request['mandatory_fact_ids'],
      'entities_mentioned': [],
    }, sys.stdout)
""",
        encoding="utf-8",
    )
    env = {**os.environ, "ASSISTCLUEDO_LOCAL_LLM_COMMAND": f"{sys.executable} {script}"}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--difficulty",
            "easy",
            "--output",
            str(tmp_path / "run"),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    scenario = json.loads((tmp_path / "run" / "scenario.json").read_text(encoding="utf-8"))
    assert scenario["documents"][0]["visible_metadata"]["text_provider"] == "local-llm"
    assert scenario["documents"][0]["visible_metadata"]["fallback_used"] is False
    assert scenario["world"]["characters"][0]["name"].startswith("Qwen Character")
    assert scenario["public_introduction"]["title"] == "Qwen case file"
    assert scenario["content_metadata"]["world_content_provider"] == "local-llm"


def test_cli_framework_generate_accepts_content_options(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--difficulty",
            "easy",
            "--content-provider",
            "procedural",
            "--fallback",
            "procedural",
            "--max-attempts",
            "1",
            "--model",
            "local",
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    scenario = json.loads((tmp_path / "scenario.json").read_text(encoding="utf-8"))
    assert scenario["content_metadata"]["world_content_provider"] == "procedural"
    assert scenario["documents"][0]["visible_metadata"]["text_provider"] == "procedural"


def test_cli_game_start_accepts_content_options(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "game",
            "start",
            "--seed",
            "42",
            "--difficulty",
            "easy",
            "--content-provider",
            "procedural",
            "--fallback",
            "procedural",
            "--max-attempts",
            "1",
            "--output",
            str(tmp_path),
        ],
        input="q\n",
        check=True,
        capture_output=True,
        text=True,
    )
    scenario = json.loads((tmp_path / "scenario.json").read_text(encoding="utf-8"))
    assert "Seed: 42 | Difficulty: easy" in result.stdout
    assert scenario["content_metadata"]["world_content_provider"] == "procedural"


def test_cli_framework_audit_reports_definition_of_done(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--difficulty",
            "spark",
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "assistcluedo", "framework", "audit", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Framework DoD Audit: OK" in result.stdout
    assert "- F12 [PASS]" in result.stdout


def test_cli_game_audit_requires_and_accepts_complete_session(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "assistcluedo",
            "framework",
            "generate",
            "--seed",
            "42",
            "--difficulty",
            "easy",
            "--output",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    incomplete = subprocess.run(
        [sys.executable, "-m", "assistcluedo", "game", "audit", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert incomplete.returncode == 1
    assert "Game DoD Audit: FAILED" in incomplete.stdout

    scenario = generate_symbolic_scenario(42, difficulty="easy")
    quiz_input = "6\n" + "".join("a\n5\n" for _ in scenario.questions)
    subprocess.run(
        [sys.executable, "-m", "assistcluedo", "game", "play", str(tmp_path)],
        input=quiz_input,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, "-m", "assistcluedo", "game", "review", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    complete = subprocess.run(
        [sys.executable, "-m", "assistcluedo", "game", "audit", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Game DoD Audit: OK" in complete.stdout
    assert "- G10 [PASS]" in complete.stdout
