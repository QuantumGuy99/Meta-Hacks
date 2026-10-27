"""WebSocket messages on /ws/sessions/{id} (PLAN §7.6, §8.2).

Every message has a required `type` (the discriminator). When a server message carries one contract model,
it sits in a single field named after it (`run.result` → `result: RunResult`).
"""

from typing import Annotated, Literal

from pydantic import Field

from crucible.contracts.coding import StepProgress, SuspectedIssue
from crucible.contracts.common import Phase, Session, Strict
from crucible.contracts.defense import (
    AuditPublic,
    ChaosMetric,
    ChaosRun,
    Finding,
    GrillTurn,
    SamHighlight,
    Verdict,
)
from crucible.contracts.events import (
    CodeSnapshot,
    EditorEvent,
    IntegrityFlag,
    Intervention,
    RunResult,
    TranscriptTurn,
)

MAX_CIRCLE_IMAGE_B64 = 1_400_000  # a 1 MB image, base64-encoded (§8.2 defense.circle)

# --- client → server ---------------------------------------------------------------------------------------


class Hello(Strict):
    type: Literal["hello"]
    client_now_ms: int


class EditorEvents(Strict):
    type: Literal["editor.events"]
    events: list[EditorEvent]


class EditorSnapshot(Strict):
    type: Literal["editor.snapshot"]
    snapshot: CodeSnapshot


class CodeRun(Strict):
    type: Literal["code.run"]
    file: str
    code: str


class CodeSubmit(Strict):
    type: Literal["code.submit"]
    file: str
    code: str


class ChatSend(Strict):
    type: Literal["chat.send"]
    text: str


class HintRequest(Strict):
    type: Literal["hint.request"]
    step_id: str | None = None


class PhaseAdvance(Strict):
    type: Literal["phase.advance"]
    to: Phase  # the server accepts only clarify → coding and coding → wrap_up


class DefenseRunChaos(Strict):
    type: Literal["defense.run_chaos"]
    finding_id: str


class DefenseVerify(Strict):
    type: Literal["defense.verify"]
    finding_id: str
    files: dict[str, str]  # path → edited code


class DefenseCircle(Strict):  # P1 (§11.7)
    type: Literal["defense.circle"]
    finding_id: str
    source: Literal["canvas", "webcam"]
    image_b64: str = Field(max_length=MAX_CIRCLE_IMAGE_B64)
    node_boxes: dict[str, list[float]] | None = None  # canvas only: node_id → [x1, y1, x2, y2]


class SessionEnd(Strict):
    type: Literal["session.end"]


ClientMessage = Annotated[
    Hello
    | EditorEvents
    | EditorSnapshot
    | CodeRun
    | CodeSubmit
    | ChatSend
    | HintRequest
    | PhaseAdvance
    | DefenseRunChaos
    | DefenseVerify
    | DefenseCircle
    | SessionEnd,
    Field(discriminator="type"),
]

# --- server → client ---------------------------------------------------------------------------------------


class SessionState(Strict):
    type: Literal["session.state"]
    session: Session
    phase: Phase
    remaining_s: int | None  # None while no timer runs (setup, ended)
    interviewer_state: Literal["idle", "listening", "thinking", "speaking"]


class InterviewerMessage(Strict):  # never sent for suppressed interventions
    type: Literal["interviewer.message"]
    intervention: Intervention


class TranscriptUpdate(Strict):
    type: Literal["transcript.update"]
    turn: TranscriptTurn  # partial (final=false) or final


class RunResultMsg(Strict):
    type: Literal["run.result"]
    result: RunResult  # hidden cases carry no inputs or outputs


class NotesUpdate(Strict):  # the "interviewer's notes" panel; sent after every analysis
    type: Literal["notes.update"]
    steps: list[StepProgress]
    issues: list[SuspectedIssue]
    stated_plan: str | None


class IntegrityMsg(Strict):
    type: Literal["integrity.flag"]
    flag: IntegrityFlag


class DefenseAudit(Strict):
    type: Literal["defense.audit"]
    audit: AuditPublic  # no explanations, grill specs or fix rubrics


class DefenseChaosMetric(Strict):
    type: Literal["defense.chaos.metric"]
    metric: ChaosMetric


class DefenseChaosDone(Strict):
    type: Literal["defense.chaos.done"]
    run: ChaosRun


class DefenseGrillEval(Strict):
    type: Literal["defense.grill.eval"]
    turn: GrillTurn
    finding: Finding  # the full finding is revealed only once its grill is graded


class DefenseSamHighlight(Strict):  # P1 (§11.7)
    type: Literal["defense.sam.highlight"]
    highlight: SamHighlight


class DefenseVerdict(Strict):
    type: Literal["defense.verdict"]
    verdict: Verdict


class ReportReady(Strict):
    type: Literal["report.ready"]
    session_id: str


class ErrorMsg(Strict):
    type: Literal["error"]
    code: str
    message: str
    retryable: bool


ServerMessage = Annotated[
    SessionState
    | InterviewerMessage
    | TranscriptUpdate
    | RunResultMsg
    | NotesUpdate
    | IntegrityMsg
    | DefenseAudit
    | DefenseChaosMetric
    | DefenseChaosDone
    | DefenseGrillEval
    | DefenseSamHighlight
    | DefenseVerdict
    | ReportReady
    | ErrorMsg,
    Field(discriminator="type"),
]
