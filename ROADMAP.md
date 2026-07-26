# Development Roadmap — AssistCluedo

## 1. Project Vision

The objective is to develop two distinct but closely connected systems:

1. a reusable framework for generating coherent investigation scenarios from a finite set of symbolic elements;
2. a game named **AssistCluedo**, built on top of this framework.

The underlying framework is responsible for:

* generating a finite world from a seed;
* generating a coherent hidden scenario;
* constructing an authoritative timeline;
* deriving observable traces from the scenario;
* generating textual documents from those traces;
* validating the consistency of the generated content;
* generating scenario-specific questions and answers.

The AssistCluedo game is responsible for:

* presenting the generated case to the player;
* allowing the player to read and organize the documents;
* hiding the authoritative scenario;
* presenting a multiple-choice questionnaire;
* evaluating how well the player understood the hidden scenario;
* revealing the solution and explanations after completion.

The core generation pipeline is:

```text
Master Seed
    ↓
Finite World Generation
    ↓
Hidden Scenario Generation
    ↓
Authoritative Timeline
    ↓
Trace Generation
    ↓
Document Planning
    ↓
Textual Document Generation
    ↓
Document Validation
    ↓
Player Case Package
    ↓
Scenario-Specific Quiz
    ↓
Player Evaluation
```

The main architectural principle is:

> The symbolic framework determines what is true.
> The language model only determines how those truths, errors, lies, and traces are expressed as text.

---

# 2. Product Boundaries

## 2.1 The underlying framework

The reusable framework should eventually be usable independently of AssistCluedo.

It should support scenarios such as:

* murder investigations;
* thefts;
* disappearances;
* sabotage;
* corporate espionage;
* cyber incidents;
* military investigations;
* political investigations;
* scientific misconduct;
* accidents involving multiple actors;
* international investigations.

The framework should expose APIs for:

```python
generate_world(...)
generate_scenario(...)
generate_timeline(...)
generate_traces(...)
generate_document_plans(...)
generate_documents(...)
generate_quiz(...)
validate_scenario(...)
evaluate_answers(...)
```

## 2.2 The AssistCluedo game

AssistCluedo is the first application of the framework.

The initial game should focus on:

* a closed investigation environment;
* a finite set of characters;
* a finite set of locations;
* a hidden major incident;
* heterogeneous textual evidence;
* false leads and contradictions;
* a final scenario-specific questionnaire;
* an ultimate statement to classify as true or false.

Example ultimate statement:

> Did the head chef kill the general on Sunday, August 9, in the kitchen?

---

# 3. Target Player Experience

A complete AssistCluedo game session should follow this flow:

```text
1. Start a new game
2. Select or randomly generate a seed
3. Generate the hidden investigation scenario
4. Present an introduction to the case
5. Present a shuffled collection of textual documents
6. Allow the player to inspect and organize the documents
7. Allow optional note-taking
8. Present a scenario-specific multiple-choice quiz
9. Ask an ultimate true-or-false question
10. Calculate a comprehension score
11. Reveal the hidden scenario
12. Explain the correct answers
```

The player should have access only to:

* the public case introduction;
* the generated documents;
* document metadata intended to be visible;
* note-taking tools;
* the quiz.

The player must not have access to:

* the oracle timeline;
* the hidden roles;
* the full ground truth;
* the proof graph;
* the quiz answer key;
* the provenance graph before the end of the game.

---

# 4. High-Level Architecture

The project should be divided into two main layers.

```text
assistcluedo/
├── framework/
│   ├── core/
│   ├── ontology/
│   ├── world/
│   ├── scenario/
│   ├── timeline/
│   ├── constraints/
│   ├── traces/
│   ├── documents/
│   ├── llm/
│   ├── questions/
│   ├── validation/
│   ├── evaluation/
│   └── serialization/
├── game/
│   ├── application/
│   ├── sessions/
│   ├── player_package/
│   ├── ui/
│   ├── scoring/
│   └── persistence/
├── api/
├── cli/
├── configs/
├── templates/
├── scenario_packs/
├── examples/
└── tests/
```

The framework layer should not depend on the game interface.

The game layer may depend on the framework.

---

# 5. Main Framework Components

The framework should contain the following components:

```text
OntologyLoader
SeedManager
WorldGenerator
ScenarioGenerator
ConstraintEngine
TimelineEngine
TraceGenerator
DocumentPlanner
DocumentRenderer
DocumentValidator
ProofGraphBuilder
QuestionGenerator
QuestionValidator
ScenarioEvaluator
PackageExporter
```

The AssistCluedo game should contain:

```text
GameSessionManager
CasePresentationService
DocumentBrowser
PlayerNotebook
QuizController
ScoreCalculator
SolutionPresenter
SaveGameManager
```

---

# 6. Phase 0 — Project Initialization

## Objective

Create a clean, installable, testable, and extensible project.

## Tasks

* create the Python package;
* define the framework and game packages separately;
* configure `pyproject.toml`;
* add static typing;
* add automated tests;
* add linting and formatting;
* add JSON and YAML serialization;
* add deterministic seed management;
* create a minimal command-line interface;
* add basic technical documentation.

## Suggested tools

* Python 3.12;
* Pydantic;
* Typer;
* pytest;
* Ruff;
* mypy or Pyright;
* NetworkX;
* Jinja2;
* Z3 or OR-Tools;
* FastAPI for a future web backend.

## Initial commands

```bash
assistcluedo --help
assistcluedo version
assistcluedo framework validate-config
pytest
```

## Acceptance criteria

* the package can be installed locally;
* all tests pass;
* framework and game modules are separated;
* the CLI can accept a master seed;
* the project can serialize and reload configuration files.

---

# 7. Phase 1 — Symbolic Data Model

## Objective

Define the complete symbolic representation independently of generated text.

## Core entities

### Character

```python
class Character:
    id: str
    name: str
    public_role: str
    private_role: str | None
    attributes: dict
    capabilities: list[str]
    relationship_ids: list[str]
```

### Location

```python
class Location:
    id: str
    name: str
    location_type: str
    parent_id: str | None
    attributes: dict
```

### WorldObject

```python
class WorldObject:
    id: str
    name: str
    object_type: str
    location_id: str | None
    owner_id: str | None
    attributes: dict
```

### Relationship

```python
class Relationship:
    id: str
    source_character_id: str
    target_character_id: str
    relationship_type: str
    attributes: dict
```

### Event

```python
class Event:
    id: str
    event_type: str
    actor_ids: list[str]
    target_ids: list[str]
    location_id: str | None
    start_time: datetime
    end_time: datetime | None
    object_ids: list[str]
    attributes: dict
```

### Fact

```python
class Fact:
    id: str
    subject: str
    predicate: str
    object: str | int | float | bool | None
    time: datetime | None
    location_id: str | None
    polarity: bool
```

### Trace

```python
class Trace:
    id: str
    trace_type: str
    source_event_ids: list[str]
    fact_ids: list[str]
    reliability: float
    authenticity: float
    truth_mode: str
    attributes: dict
```

### DocumentPlan

```python
class DocumentPlan:
    id: str
    document_type: str
    source_trace_ids: list[str]
    mandatory_fact_ids: list[str]
    forbidden_fact_ids: list[str]
    author_id: str | None
    source_system_id: str | None
    truth_mode: str
    style: dict
```

### GeneratedDocument

```python
class GeneratedDocument:
    id: str
    plan_id: str
    title: str
    text: str
    visible_metadata: dict
    extracted_fact_ids: list[str]
```

### QuizQuestion

```python
class QuizQuestion:
    id: str
    category: str
    text: str
    choices: list["Choice"]
    correct_choice_ids: list[str]
    supporting_fact_ids: list[str]
    supporting_document_ids: list[str]
    difficulty: float
```

### Scenario

```python
class Scenario:
    world: "World"
    ground_truth: "GroundTruth"
    events: list[Event]
    facts: list[Fact]
    traces: list[Trace]
    document_plans: list[DocumentPlan]
    documents: list[GeneratedDocument]
    questions: list[QuizQuestion]
    proof_graph: "ProofGraph"
```

## Acceptance criteria

* all entities are strongly typed;
* all entities can be serialized to JSON and YAML;
* a complete scenario can be saved and reloaded without information loss;
* generated text is not required to instantiate the symbolic scenario.

---

# 8. Phase 2 — Finite Ontology and Scenario Packs

## Objective

Define the finite elements from which scenarios can be generated.

## Configurable domains

* character roles;
* hidden roles;
* professions;
* relationships;
* motives;
* locations;
* location types;
* objects;
* weapons;
* communication channels;
* event types;
* trace types;
* document types;
* sensor types;
* access permissions;
* scenario constraints.

## Example ontology

```yaml
roles:
  - id: general
    category: military
    compatible_hidden_roles:
      - victim
      - suspect
      - witness

  - id: head_chef
    category: household_staff
    compatible_hidden_roles:
      - culprit
      - suspect
      - witness

event_types:
  - move
  - meet
  - call
  - send_message
  - access_location
  - take_object
  - kill
  - hide_object
  - discover_body
```

## Scenario pack structure

```text
scenario_packs/
└── classic_manor/
    ├── pack.yaml
    ├── characters.yaml
    ├── locations.yaml
    ├── objects.yaml
    ├── events.yaml
    ├── traces.yaml
    ├── documents.yaml
    ├── constraints.yaml
    └── templates/
```

## Acceptance criteria

* a new setting can be added without changing the core engine;
* invalid ontology combinations are detected;
* scenario packs are versioned;
* the generated scenario stores an ontology snapshot.

---

# 9. Phase 3 — Deterministic Seed Management

## Objective

Guarantee reproducible symbolic generation.

A master seed should generate independent sub-seeds:

```python
subseeds = {
    "world": derive_seed(master_seed, "world"),
    "scenario": derive_seed(master_seed, "scenario"),
    "timeline": derive_seed(master_seed, "timeline"),
    "traces": derive_seed(master_seed, "traces"),
    "documents": derive_seed(master_seed, "documents"),
    "quiz": derive_seed(master_seed, "quiz"),
    "shuffle": derive_seed(master_seed, "shuffle"),
}
```

## Requirements

* never use Python’s global random generator;
* pass an explicit RNG object to each module;
* sort unordered collections before random selection;
* generate deterministic identifiers;
* record all derived seeds;
* record the framework version;
* record the scenario-pack version.

## Acceptance criteria

```python
assert generate_symbolic_scenario(seed=42) == generate_symbolic_scenario(seed=42)
assert generate_symbolic_scenario(seed=42) != generate_symbolic_scenario(seed=43)
```

Textual outputs may vary when an external LLM is used, but the following must remain stable:

* world;
* hidden scenario;
* timeline;
* facts;
* traces;
* document plans;
* quiz answers;
* proof graph.

---

# 10. Phase 4 — World Generator

## Objective

Generate a finite and coherent world from the selected scenario pack.

## Generated elements

* characters;
* public roles;
* hidden roles;
* locations;
* travel graph;
* objects;
* inventories;
* relationships;
* access permissions;
* communication systems;
* sensors;
* devices.

## Example world

```text
Manor
├── Entrance Hall
├── Kitchen
├── Pantry
├── Dining Room
├── General's Office
├── Library
├── Garden
└── Garage
```

## Required validations

* the location graph is connected;
* all required scenario locations exist;
* required objects are reachable;
* characters have compatible roles;
* devices required for traces exist;
* access-control rules are consistent;
* objects are not assigned to incompatible locations.

## Acceptance criteria

The generated world is always sufficient to support at least one valid scenario.

---

# 11. Phase 5 — Hidden Scenario Generator

## Objective

Generate the authoritative hidden scenario.

## Minimum scenario structure

Each scenario should include:

* one main incident;
* one responsible actor;
* one victim or target;
* one main location;
* one date and time range;
* one instrument or method;
* one motive;
* preparation events;
* aftermath events;
* plausible suspects;
* at least one false lead;
* at least one exculpatory fact;
* at least one contradiction between sources.

## Example

```yaml
main_incident:
  event_type: kill
  actor_id: head_chef
  target_id: general
  location_id: kitchen
  time: "2026-08-09T21:14:00"
  instrument_id: kitchen_knife
  motive_id: blackmail
```

## Initial scope

The first version should support only:

* one major incident;
* one culprit;
* one victim;
* a fixed investigation period;
* one closed-world setting.

Later versions can support:

* multiple incidents;
* accomplices;
* unknown perpetrators;
* overlapping conspiracies;
* several independent secrets.

## Acceptance criteria

* the scenario is logically consistent;
* every selected entity exists in the world;
* the hidden truth is serializable;
* the hidden scenario does not depend on generated text.

---

# 12. Phase 6 — Constraint Engine

## Objective

Guarantee physical, temporal, causal, social, and narrative consistency.

## Temporal constraints

* a character cannot be in two places simultaneously;
* travel times must be respected;
* a message cannot be received before it is sent;
* a report cannot be written before its source event;
* a body cannot be discovered before death;
* an autopsy cannot occur before discovery.

## Physical constraints

* an object must be accessible before use;
* a locked location requires authorized access or forced entry;
* a direct witness must be present and able to perceive the event;
* a sensor-generated trace requires an existing active sensor.

## Causal constraints

* a killing event causes death;
* a disabled camera cannot record during the disabled period;
* moving an object changes its location;
* destroying a trace affects its availability;
* forging a document requires an actor and an original or target document.

## Narrative constraints

* at least two suspects must initially appear plausible;
* the case must not be solved by a single explicit confession;
* the final answer must be inferable from the player documents;
* false leads must remain refutable;
* contradictions must not make the case objectively undecidable.

## Suggested implementation

Start with explicit Python validation rules.

Introduce Z3 or OR-Tools only when scenario generation requires constraint solving.

## Acceptance criteria

No invalid scenario reaches the trace-generation stage.

---

# 13. Phase 7 — Authoritative Timeline Engine

## Objective

Build the complete chronological sequence of real events.

## Initial event types

* enter;
* leave;
* move;
* meet;
* observe;
* call;
* send SMS;
* send email;
* join video call;
* access system;
* take object;
* use object;
* disable device;
* main incident;
* hide evidence;
* discover incident;
* begin investigation.

## Example

```yaml
timeline:
  - time: "2026-08-09T19:30:00"
    event_type: arrive
    actor_ids: [general]
    location_id: dining_room

  - time: "2026-08-09T20:45:00"
    event_type: move
    actor_ids: [head_chef]
    source_location_id: pantry
    target_location_id: kitchen

  - time: "2026-08-09T21:14:00"
    event_type: kill
    actor_ids: [head_chef]
    target_ids: [general]
    location_id: kitchen

  - time: "2026-08-09T21:32:00"
    event_type: discover_body
    actor_ids: [butler]
    target_ids: [general]
    location_id: kitchen
```

## Required outputs

* global chronological timeline;
* per-character timeline;
* per-location timeline;
* per-object timeline;
* causal links between events.

## Acceptance criteria

Every state change can be reconstructed from the timeline.

---

# 14. Phase 8 — Trace Generation

## Objective

Generate observable traces from the authoritative events.

## Initial trace types

* access-control log;
* GPS trace;
* telephone log;
* SMS record;
* email record;
* video-call transcript;
* witness statement;
* security report;
* police report;
* medical report;
* autopsy report;
* inventory report;
* receipt;
* invoice;
* camera log;
* sensor log;
* personal note;
* newspaper article.

## Trace-generation rules

Each event type may produce traces under specific conditions.

```yaml
event_type: move

trace_rules:
  - condition: actor_has_active_phone
    probability: 0.8
    produces: gps_trace

  - condition: destination_has_badge_reader
    probability: 1.0
    produces: access_log

  - condition: route_has_camera
    probability: 0.7
    produces: camera_trace
```

## Truth modes

```text
accurate
incomplete
mistaken
deceptive
forged
irrelevant
```

The symbolic engine must decide the truth mode.

The LLM must not decide whether a source lies or makes a mistake.

## Acceptance criteria

Every trace contains:

* source event identifiers;
* represented facts;
* creation conditions;
* reliability;
* authenticity;
* truth mode;
* provenance.

---

# 15. Phase 9 — Document Planning

## Objective

Convert traces into structured document plans before generating text.

## Each document plan should define

* document type;
* title category;
* author;
* source organization or system;
* creation date;
* referenced time period;
* mandatory facts;
* forbidden facts;
* intentional omissions;
* planned false claims;
* truth mode;
* tone;
* register;
* expected length;
* visible metadata.

## Example

```yaml
document_plan:
  id: doc_plan_014
  document_type: security_access_report
  author_id: manor_security_system
  created_at: "2026-08-10T07:00:00"

  mandatory_fact_ids:
    - fact_badge_access_2046

  forbidden_fact_ids:
    - fact_culprit_identity
    - fact_exact_weapon
    - fact_exact_death_time

  style:
    language: English
    register: administrative
    length: short
```

## Acceptance criteria

No text document is generated without a validated `DocumentPlan`.

---

# 16. Phase 10 — Textual Document Generation

## Objective

Generate realistic textual documents from symbolic plans.

## Generator abstraction

```python
class TextGenerator(Protocol):
    def generate(self, plan: DocumentPlan) -> GeneratedDocument:
        ...
```

## Implementations

* `TemplateTextGenerator`;
* `OpenAITextGenerator`;
* `LocalLLMTextGenerator`;
* `MockTextGenerator`.

The first working version must use deterministic templates.

LLM integration should be added only after the symbolic pipeline works end to end.

## LLM input requirements

The generation prompt should specify:

* mandatory facts;
* allowed facts;
* forbidden facts;
* source identity;
* document type;
* truth mode;
* style;
* wording constraints;
* prohibition against inventing new facts.

## Recommended structured output

```json
{
  "title": "Security Access Report",
  "text": "The access-control system recorded...",
  "facts_expressed": [
    {
      "fact_id": "fact_badge_access_2046"
    }
  ]
}
```

## Acceptance criteria

* the document is readable;
* the style matches the source;
* all mandatory facts are expressed;
* no forbidden fact is revealed;
* the document introduces no unsupported entities or events.

---

# 17. Phase 11 — Document Validation

## Objective

Prevent hallucinations, accidental revelations, and logical inconsistencies.

## Validation levels

### Structural validation

* non-empty title and body;
* valid metadata;
* valid encoding;
* expected output format.

### Entity validation

* all characters exist;
* all locations exist;
* all objects exist;
* no unsupported organization is introduced.

### Factual validation

* mandatory facts are present;
* forbidden facts are absent;
* no unsupported date is introduced;
* no unsupported relationship is introduced;
* no new event is invented.

### Logical validation

* source behavior matches the source type;
* a witness does not claim impossible direct access;
* a system log does not include subjective interpretation;
* a forged document contains only the planned falsifications;
* the creation date follows the source event.

## Recovery strategy

```text
1. Regenerate with stricter instructions
2. Reduce generation creativity
3. Use a deterministic fallback template
4. Fail explicitly after a maximum number of attempts
```

## Acceptance criteria

Only validated documents may enter the player package.

---

# 18. Phase 12 — Player Document Package

## Objective

Build the final set of documents shown to the player.

## Document categories

* essential evidence;
* corroborating evidence;
* contradictory evidence;
* misleading evidence;
* contextual documents;
* irrelevant documents.

## Example difficulty configuration

```yaml
document_selection:
  essential_documents: 5
  corroborating_documents: 4
  misleading_documents: 3
  irrelevant_documents: 5
  duplicate_information_ratio: 0.2
```

## Packaging rules

* documents should not be presented chronologically;
* file names should not reveal importance;
* documents may have realistic dates and identifiers;
* the order should depend on the shuffle seed;
* oracle metadata must be stripped;
* hidden fact identifiers must never be exposed.

## Acceptance criteria

The player package contains enough information to solve the case, but does not expose the solution directly.

---

# 19. Phase 13 — Proof Graph

## Objective

Create a symbolic graph connecting documents to conclusions.

## Structure

```text
Document
    ↓
Expressed claim
    ↓
Validated fact
    ↓
Intermediate inference
    ↓
Scenario conclusion
    ↓
Quiz answer
```

## Example

```yaml
conclusion:
  fact_id: fact_head_chef_in_kitchen_at_2114

support:
  - document_id: badge_report
    fact_id: fact_badge_used_at_2046

  - document_id: gps_report
    fact_id: fact_phone_near_kitchen_at_2112

  - document_id: witness_transcript
    fact_id: fact_chef_seen_leaving_at_2120
```

## Uses

The proof graph should be used to:

* verify that the case is solvable;
* generate quiz explanations;
* identify essential documents;
* estimate reasoning difficulty;
* prevent unsupported questions;
* calculate the minimum evidence path.

## Acceptance criteria

Every quiz answer is linked to at least one valid proof path.

---

# 20. Phase 14 — Scenario-Specific Quiz Generator

## Objective

Generate a multiple-choice questionnaire that evaluates the player’s understanding of the specific generated scenario.

The quiz must not be generic.

Every question must be derived from:

* scenario facts;
* the authoritative timeline;
* document claims;
* contradictions;
* source reliability;
* the proof graph.

## Question categories

### Factual comprehension

* Where was the general at 8:30 p.m.?
* Who sent the message to the colonel?
* Which object disappeared?

### Temporal comprehension

* Which event happened first?
* Who could physically reach the kitchen before 9:15 p.m.?
* During which period was the camera unavailable?

### Causal comprehension

* Which event explains the missing video footage?
* Why was the kitchen knife accessible?
* What caused the contradiction between the GPS record and the testimony?

### Source comprehension

* Which document provides the most direct evidence of entry into the kitchen?
* Which statement comes from a potentially falsified source?
* Which testimony is contradicted by an automated record?

### Hypothesis elimination

* Which suspect has a confirmed alibi?
* Which hypothesis violates the travel-time constraints?
* Which character could not access the weapon?

### Ultimate statement

Example:

> Did the head chef kill the general on Sunday, August 9, in the kitchen?

Possible answers:

```text
Yes
No
Cannot be determined from the available evidence
```

The first version may use only single-answer multiple-choice questions.

---

# 21. Phase 15 — Distractor Generation

## Objective

Generate plausible but demonstrably incorrect answer choices.

## Distractor strategies

### Location questions

Use:

* another location visited by the same character;
* a neighboring location;
* a location mentioned in a false lead.

### Time questions

Use:

* a nearby time;
* the time of a related event;
* the time claimed in a deceptive statement.

### Character questions

Use:

* another plausible suspect;
* the actor of a secondary event;
* a person with access to the location.

### Object questions

Use:

* another accessible object;
* an object mentioned in a misleading document;
* an object of the same category.

## Requirements

* exactly one correct answer;
* no ambiguous distractors;
* every distractor must be false in the oracle scenario;
* distractors should remain plausible;
* answer length and phrasing should not reveal the correct choice.

---

# 22. Phase 16 — Quiz Validation

## Objective

Guarantee that each question is valid, clear, and answerable.

## Validation rules

For every question:

```text
The designated answer is true in the oracle scenario.

Every distractor is false in the oracle scenario.

The correct answer can be justified from player-visible documents.

The question does not require hidden oracle information.

The wording does not directly reveal the answer.

The question has only one reasonable interpretation.

The question does not depend on accidental LLM wording.
```

## Validation interface

```python
result = question_validator.validate(
    question=question,
    scenario=scenario,
    player_documents=documents,
    proof_graph=proof_graph,
)
```

## Acceptance criteria

No unsupported or ambiguous question enters the final quiz.

---

# 23. Phase 17 — Scoring System

## Objective

Measure the player’s understanding across several dimensions.

## Suggested score structure

```text
Total score: 100 points
```

Possible distribution:

```text
Factual comprehension       25 points
Temporal reasoning          20 points
Causal reasoning            20 points
Source assessment           15 points
Hypothesis elimination      10 points
Ultimate statement          10 points
```

## Optional metrics

* score by category;
* overall accuracy;
* player confidence;
* confidence calibration;
* time spent;
* documents opened;
* notes created;
* answer changes;
* evidence consulted before each answer.

## Example output

```yaml
score:
  total: 82
  factual: 23
  temporal: 16
  causal: 17
  source_assessment: 11
  hypothesis_elimination: 7
  ultimate_statement: 8
```

---

# 24. Phase 18 — Post-Game Explanations

## Objective

Explain the hidden scenario and help the player understand mistakes.

For each question, the game should show:

* the correct answer;
* the player’s answer;
* a concise explanation;
* the relevant documents;
* the relevant timeline events;
* why each distractor was incorrect.

At the end, the game should reveal:

* the full hidden scenario;
* the authoritative timeline;
* the culprit or responsible actor;
* the motive;
* the method;
* the relevant false leads;
* the misleading or forged sources.

Explanations must be generated from the proof graph.

They must not be improvised from scratch by an LLM.

---

# 25. Phase 19 — AssistCluedo Game Session Model

## Objective

Introduce game-specific session management above the framework.

## Game session state

```python
class GameSession:
    id: str
    scenario_id: str
    player_id: str | None
    state: str
    started_at: datetime
    completed_at: datetime | None
    opened_document_ids: list[str]
    notes: list["PlayerNote"]
    answers: list["PlayerAnswer"]
    score: "Score" | None
```

## Session states

```text
created
generating
ready
investigating
quiz_started
completed
solution_revealed
```

## Responsibilities

* prevent access to oracle files;
* track player progression;
* save notes;
* record answers;
* calculate scores;
* allow resuming a session;
* reveal the solution only after completion.

---

# 26. Phase 20 — Command-Line Interface

## Framework commands

```bash
assistcluedo framework generate \
  --seed 42 \
  --pack classic_manor \
  --output runs/scenario_42
```

```bash
assistcluedo framework validate runs/scenario_42
```

```bash
assistcluedo framework inspect-oracle runs/scenario_42
```

```bash
assistcluedo framework regenerate-documents \
  runs/scenario_42 \
  --provider template
```

## Game commands

```bash
assistcluedo game start \
  --seed 42 \
  --pack classic_manor
```

```bash
assistcluedo game play runs/scenario_42/player_package
```

```bash
assistcluedo game evaluate \
  runs/scenario_42 \
  answers.json
```

---

# 27. Phase 21 — Minimal Game Interface

## Objective

Create a playable user interface.

## Required screens

### Home screen

* start a new case;
* enter a seed;
* choose a difficulty;
* choose a scenario pack;
* resume a saved game.

### Case introduction

* title;
* context;
* public list of characters;
* public locations;
* investigation objective.

### Document browser

* list of documents;
* document reader;
* search;
* filters;
* opened/unopened state;
* optional bookmarks.

### Player notebook

* free-form notes;
* character notes;
* timeline notes;
* hypothesis notes.

### Quiz

* one question at a time or full questionnaire;
* answer selection;
* optional confidence rating;
* final submission.

### Results

* total score;
* category scores;
* correct answers;
* explanations;
* full scenario reveal.

## Technology options

For a rapid prototype:

* Streamlit.

For a durable architecture:

* FastAPI backend;
* React or Vue frontend;
* local or database-backed persistence.

---

# 28. Phase 22 — Scenario Export Structure

## Target output

```text
scenario_000042/
├── metadata.json
├── config_snapshot.yaml
├── ontology_snapshot.yaml
├── seeds.json
├── oracle/
│   ├── world.yaml
│   ├── ground_truth.yaml
│   ├── timeline.yaml
│   ├── facts.yaml
│   ├── traces.yaml
│   └── proof_graph.yaml
├── document_plans/
├── generated_documents/
├── player_package/
│   ├── introduction.json
│   ├── characters.json
│   ├── locations.json
│   ├── documents/
│   └── quiz.json
└── evaluation/
    ├── answer_key.json
    ├── explanations.json
    └── scoring_config.yaml
```

The `oracle` directory must never be exposed to the player before the game is completed.

---

# 29. Phase 23 — Testing Strategy

## Unit tests

* seed derivation;
* serialization;
* world generation;
* role compatibility;
* temporal constraints;
* travel constraints;
* object accessibility;
* trace generation;
* document-plan validation;
* document validation;
* distractor generation;
* quiz validation;
* score calculation.

## Integration tests

```text
Seed
→ World
→ Hidden scenario
→ Timeline
→ Traces
→ Document plans
→ Documents
→ Proof graph
→ Quiz
→ Player package
→ Evaluation
```

## Property-based tests

Run generation across hundreds of seeds and verify:

* no character occupies two locations simultaneously;
* no object is used before becoming accessible;
* no event refers to an unknown entity;
* no player question lacks documentary support;
* every question has exactly one valid answer;
* no forbidden oracle fact leaks into the player package;
* generation is reproducible.

## Regression tests

Store selected canonical seeds and compare:

* world snapshot;
* timeline snapshot;
* fact snapshot;
* quiz answer snapshot;
* proof graph snapshot.

---

# 30. Phase 24 — Difficulty Model

## Objective

Control the cognitive complexity of the generated game.

## Parameters

```yaml
difficulty:
  characters: 8
  locations: 12
  events: 40
  documents: 20
  essential_documents: 6
  misleading_documents: 4
  irrelevant_documents: 5
  contradiction_ratio: 0.2
  temporal_complexity: 0.7
  minimum_reasoning_hops: 3
  quiz_questions: 15
```

## Difficulty dimensions

```text
Spatial complexity
Temporal complexity
Number of characters
Number of relationships
Number of documents
Document redundancy
Number of false leads
Number of unreliable sources
Minimum proof length
Number of required source types
Question complexity
```

## Suggested levels

### Easy

* few characters;
* short timeline;
* mostly reliable sources;
* limited false leads;
* direct questions.

### Medium

* several suspects;
* some contradictions;
* shuffled chronology;
* multi-document questions.

### Hard

* many characters;
* deceptive sources;
* several false leads;
* longer reasoning chains;
* subtle distinctions between dates, locations, motives, and actors.

---

# 31. Phase 25 — Additional Scenario Packs

## Objective

Reuse the framework beyond the classic manor setting.

Potential packs:

```text
classic_manor
military_base
corporate_headquarters
university_campus
research_laboratory
cyber_incident
space_station
medieval_court
international_investigation
city_crime_case
```

Each pack should define:

* world ontology;
* roles;
* locations;
* objects;
* event rules;
* trace rules;
* document sources;
* text styles;
* constraints;
* scenario templates;
* quiz templates.

---

# 32. Recommended Implementation Order

Codex should follow this order.

```text
Step 1
Project structure and typed models

Step 2
Serialization and deterministic seed management

Step 3
Finite YAML ontology

Step 4
World generator

Step 5
Single hidden-scenario generator

Step 6
Authoritative timeline

Step 7
Constraint validation

Step 8
Trace generation

Step 9
Document planning

Step 10
Template-based document generation

Step 11
Document validation

Step 12
Proof graph

Step 13
Scenario-specific quiz generation

Step 14
Distractor generation

Step 15
Quiz validation

Step 16
Scoring and explanations

Step 17
Player-package export

Step 18
Command-line game

Step 19
Minimal graphical interface

Step 20
Optional LLM integration

Step 21
Additional scenario packs
```

The LLM must not be integrated before the full symbolic pipeline works with deterministic templates.

---

# 33. Minimum Viable Framework

The first framework milestone should support:

* one scenario pack;
* one incident category;
* one culprit;
* one victim;
* five to eight characters;
* six to ten locations;
* one coherent timeline;
* deterministic trace generation;
* eight document types;
* template-based text generation;
* proof-graph construction;
* scenario-specific quiz generation.

The framework must be usable independently of the game UI.

---

# 34. Minimum Viable AssistCluedo Game

The first playable AssistCluedo version should support:

```bash
assistcluedo game start --seed 42
```

It should generate:

* one classic manor;
* six characters;
* one murder;
* one hidden motive;
* approximately twenty timeline events;
* approximately ten traces;
* eight to twelve documents;
* at least two false leads;
* five comprehension questions;
* one ultimate statement;
* automatic scoring;
* a final explanation.

## Initial document types

* SMS;
* email;
* access-control log;
* GPS report;
* witness interview;
* autopsy report;
* security report;
* personal note.

## Initial restrictions

* no external LLM;
* no multiplayer mode;
* no procedural visual map;
* no scenario type other than murder;
* no dynamic interaction with characters;
* one scenario pack only.

---

# 35. Definition of Done

The underlying framework is considered functional when:

```text
F1. A master seed deterministically generates a symbolic world.

F2. The same seed and configuration reproduce the same symbolic scenario.

F3. The scenario respects physical, temporal, and causal constraints.

F4. Every trace is linked to one or more source events.

F5. Every document is linked to a validated document plan.

F6. The generated text does not alter the symbolic truth.

F7. The proof graph connects documents to scenario conclusions.

F8. Every quiz question has exactly one valid answer.

F9. Every correct answer is supported by player-visible documents.

F10. Every distractor is false in the oracle scenario.

F11. The ultimate statement is evaluated from symbolic ground truth.

F12. The framework can export a complete player package.
```

The AssistCluedo game is considered functional when:

```text
G1. A player can start a game from a seed.

G2. A generated case can be read without exposing oracle data.

G3. The player can browse all generated documents.

G4. The player can take notes.

G5. The player can complete the scenario-specific quiz.

G6. The game calculates a comprehension score.

G7. The game reveals the solution only after submission.

G8. The game explains every correct answer using generated evidence.

G9. A game session can be saved and resumed.

G10. A complete game can be generated, played, evaluated, and reviewed.
```

---

# 36. Development Rules for Codex

Codex should follow these rules throughout implementation:

1. keep the framework independent from the game interface;
2. keep symbolic truth independent from generated text;
3. use typed models for all domain entities;
4. write tests alongside each feature;
5. never generate a document before creating its symbolic plan;
6. never calculate quiz answers from generated prose;
7. calculate answers only from oracle facts;
8. validate the scenario before generating traces;
9. validate traces before planning documents;
10. validate documents before building the player package;
11. validate questions before exposing the quiz;
12. keep complete provenance from events to traces, documents, and questions;
13. record configuration, ontology, version, and seed snapshots;
14. use deterministic templates before introducing an LLM;
15. fail explicitly rather than silently accepting inconsistent content.

---

# 37. First Implementation Milestone

Codex should first implement a narrow vertical slice.

## Input

```bash
assistcluedo game start --seed 42
```

## Framework output

```text
One manor
Six characters
Six locations
One murder
One authoritative timeline
Ten traces
Eight template-based documents
One proof graph
Five quiz questions
One ultimate statement
One answer key
```

## Game output

```text
One case introduction
One shuffled document list
One document reader
One basic note area
One six-question quiz
One final score
One solution page
```

## Restrictions

* no LLM;
* no authentication;
* no multiplayer;
* no advanced frontend;
* no scenario editor;
* no scenario category other than murder;
* one scenario pack: `classic_manor`.

This milestone should validate the complete separation between:

```text
Reusable scenario-generation framework
                    and
         AssistCluedo game application
```
