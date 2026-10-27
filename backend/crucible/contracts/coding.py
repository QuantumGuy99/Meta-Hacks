"""Problems, rubrics and the analyzer's output (PLAN §7.3)."""

from enum import StrEnum
from typing import Any, Literal

from crucible.contracts.common import Difficulty, Strict
from crucible.contracts.events import InterventionLevel, InterventionTrigger


class Param(Strict):
    name: str
    type: str  # Python annotation as text, e.g. "list[int]"


class FunctionSig(Strict):
    name: str
    params: list[Param]
    returns: str


Comparator = Literal["exact", "unordered", "float_tol", "unordered_inner", "set_of_lists"]


class CaseSpec(Strict):  # one test case (not named Test*, so pytest won't try to collect it)
    id: str
    args: list[Any]  # JSON values, positional
    expected: Any
    comparator: Comparator = "exact"
    edge_case_id: str | None = None


class Example(Strict):
    input: str
    output: str
    explanation: str | None = None


class RubricStep(Strict):
    id: str  # "s1", "s2", ...
    title: str  # "Handle empty input"
    description: str
    required: bool
    order: int  # expected order (later steps depend on earlier ones)
    look_for: list[str]  # observable signals in code/speech
    hints: list[str]  # exactly 3: [nudge, question, hint]; never code


class EdgeCase(Strict):
    id: str
    description: str


class Mistake(Strict):
    id: str
    description: str
    symptom: str  # what it looks like in code or test failures


class Approach(Strict):
    name: str  # "hash map of complements"
    time: str  # "O(n)"
    space: str
    acceptable: bool  # brute force is usually acceptable=False for medium/hard


class Rubric(Strict):
    approaches: list[Approach]
    steps: list[RubricStep]
    edge_cases: list[EdgeCase]
    common_mistakes: list[Mistake]
    wrap_up_questions: list[str]  # 2: complexity + trade-off/edge case


class ProblemSpec(Strict):  # data/problems/<slug>/problem.json (+ statement.md, reference.py, brute.py)
    slug: str
    title: str
    difficulty: Difficulty
    topics: list[str]
    function: FunctionSig
    starter_code: str
    examples: list[Example]
    constraints: list[str]
    tests_visible: list[CaseSpec]  # 2–4
    tests_hidden: list[CaseSpec]  # 8–25, includes every edge case
    rubric: Rubric
    time_limit_min: int
    illustration: str | None  # relative path, P1
    origin_note: str  # "Original. Pattern: sliding window."
    # loaded from sibling files at load time:
    statement_md: str = ""
    reference_solution: str = ""
    brute_force_solution: str | None = None


class ProblemSummary(Strict):
    slug: str
    title: str
    difficulty: Difficulty
    topics: list[str]


class ProblemPublic(Strict):  # what the browser receives: NO hidden tests, rubric or reference
    slug: str
    title: str
    difficulty: Difficulty
    topics: list[str]
    statement_md: str
    examples: list[Example]
    constraints: list[str]
    starter_code: str
    tests_visible: list[CaseSpec]
    illustration_url: str | None
    time_limit_min: int


class StepStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    INCORRECT = "incorrect"
    SKIPPED = "skipped"


class StepProgress(Strict):  # LLM output
    step_id: str
    status: StepStatus
    evidence: str  # short quote of code/speech


class SuspectedIssue(Strict):  # LLM output
    kind: Literal["bug", "edge_case", "complexity", "style"]
    line: int | None
    description: str
    mistake_id: str | None
    confidence: float  # 0..1


class InterventionProposal(Strict):  # LLM output
    trigger: InterventionTrigger
    level: InterventionLevel
    step_id: str | None
    text: str
    confidence: float


class Analysis(Strict):  # LLM output of the analyzer (§9.4)
    steps: list[StepProgress]
    issues: list[SuspectedIssue]
    stated_plan: str | None
    plan_matches_code: bool | None
    chosen_approach: str | None
    explanation_quality: Literal["none", "weak", "ok", "strong"]
    proposal: InterventionProposal | None
