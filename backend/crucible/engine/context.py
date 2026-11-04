"""What the analyzer, policy and leak guard grade against (PLAN §9.1 mode hooks)."""

from dataclasses import dataclass

from crucible.contracts.coding import EdgeCase, Mistake, ProblemSpec, RubricStep
from crucible.contracts.common import Language


@dataclass(frozen=True, slots=True)
class RubricContext:
    """Coding mode builds one from a `ProblemSpec`; the defense fix stage builds one from a `Finding`."""

    title: str
    brief_md: str  # problem statement, or finding explanation + chaos summary
    steps: list[RubricStep]  # rubric.steps, or finding.fix_steps
    edge_cases: list[EdgeCase]  # [] in defense
    common_mistakes: list[Mistake]  # [] in defense
    wrap_up_questions: list[str]  # [] in defense
    reference_text: str | None  # leak guard source: reference.py, or fix.patch
    files: list[
        str
    ]  # editable files: ["solution.py"] (the editor's id, whatever the language), or the finding's
    language: Language = Language.PYTHON  # what the code is written in; defense projects are Python

    @property
    def fence(self) -> str:
        """The Markdown code-fence tag for the candidate's code."""
        return self.language.value

    @classmethod
    def from_problem(cls, spec: ProblemSpec, language: Language = Language.PYTHON) -> "RubricContext":
        from crucible.coding.languages import signature, statement  # coding imports engine: import late

        examples = "\n".join(
            f"- Input: {e.input} → Output: {e.output}" + (f" ({e.explanation})" if e.explanation else "")
            for e in spec.examples
        )
        constraints = "\n".join(f"- {c}" for c in spec.constraints)
        # Only what the candidate can already see: the interviewer answers clarifying questions from this.
        brief = f"{statement(spec.statement_md, spec.function, language).strip()}\n\nFunction to implement: `{signature(spec.function, language)}`"
        if language != Language.PYTHON:
            brief += f"\n\nThe candidate is writing {LANGUAGE_NAMES[language]}, not Python."
        if examples:
            brief += f"\n\nExamples:\n{examples}"
        if constraints:
            brief += f"\n\nConstraints:\n{constraints}"
        return cls(
            title=spec.title,
            brief_md=brief,
            steps=spec.rubric.steps,
            edge_cases=spec.rubric.edge_cases,
            common_mistakes=spec.rubric.common_mistakes,
            wrap_up_questions=spec.rubric.wrap_up_questions,
            reference_text=spec.reference_solution or None,
            files=["solution.py"],
            language=language,
        )


LANGUAGE_NAMES: dict[Language, str] = {
    Language.PYTHON: "Python",
    Language.JAVA: "Java",
    Language.CPP: "C++",
    Language.C: "C",
}
