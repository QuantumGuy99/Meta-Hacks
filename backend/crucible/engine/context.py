"""What the analyzer, policy and leak guard grade against (PLAN §9.1 mode hooks)."""

from dataclasses import dataclass

from crucible.contracts.coding import EdgeCase, Mistake, ProblemSpec, RubricStep


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
    files: list[str]  # editable files: ["solution.py"], or the finding's files

    @classmethod
    def from_problem(cls, spec: ProblemSpec) -> "RubricContext":
        params = ", ".join(f"{p.name}: {p.type}" for p in spec.function.params)
        signature = f"def {spec.function.name}({params}) -> {spec.function.returns}"
        return cls(
            title=spec.title,
            brief_md=f"{spec.statement_md.strip()}\n\nFunction to implement: `{signature}`",
            steps=spec.rubric.steps,
            edge_cases=spec.rubric.edge_cases,
            common_mistakes=spec.rubric.common_mistakes,
            wrap_up_questions=spec.rubric.wrap_up_questions,
            reference_text=spec.reference_solution or None,
            files=["solution.py"],
        )
