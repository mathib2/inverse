"""Expert contract. Every expert takes a Task and returns an ExpertResult
with at least one evidence item. Claims an expert wants remembered go in `findings`; the Lead writes them to
TeamMemory only after the Critic accepts the result, so a rejected claim never becomes shared memory."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Protocol

from ..budget import BudgetExceeded


class NoEvidence(ValueError):
    pass


@dataclass
class Task:
    id: str
    goal: str
    expert: str
    depends_on: list = field(default_factory=list)
    status: str = "pending"        # pending | running | done | rejected | failed
    attempts: int = 0
    feedback: str = ""             # the Critic's reason when the task was sent back
    context: str = ""              # accepted answers of the tasks this one depends on
    result: dict | None = None
    lessons: list = field(default_factory=list)   # reviewer reasons from earlier tasks of this expert (Reflexion), set by the Lead
    messages: list = field(default_factory=list)  # notes and results other experts addressed to this one, set by the Lead at delegation


@dataclass
class ExpertResult:
    answer: str
    evidence: list                 # [{"type": "sql|tool|calc|step|code", "source": ..., "detail": ...}]
    confidence: float = 0.5
    assumptions: list = field(default_factory=list)
    not_checked: list = field(default_factory=list)
    models_used: list = field(default_factory=list)
    trace_ref: str = ""
    findings: list = field(default_factory=list)   # [{"claim", "evidence", "source", "confidence"}], written to memory on accept

    def to_dict(self):
        return asdict(self)


def require_evidence(result):
    if not result.evidence:
        raise NoEvidence("expert returned a conclusion without evidence")
    return result


class ExpertBudget:
    """Per-expert caps on tool calls, tokens and wall-clock, enforced by the Lead."""

    def __init__(self, tool_calls=8, tokens=40000, seconds=240):
        self.max_tool_calls, self.max_tokens, self.max_seconds = tool_calls, tokens, seconds
        self.tool_calls = self.tokens = 0
        self.t0 = time.time()

    def charge_tool(self):
        self.tool_calls += 1
        self.check()

    def charge_tokens(self, usage):
        self.tokens += int((usage or {}).get("total_tokens") or 0)
        self.check()

    def check(self):
        if self.tool_calls > self.max_tool_calls:
            raise BudgetExceeded(f"tool-call budget {self.max_tool_calls} exceeded")
        if self.tokens > self.max_tokens:
            raise BudgetExceeded(f"token budget {self.max_tokens} exceeded")
        if time.time() - self.t0 > self.max_seconds:
            raise BudgetExceeded(f"wall-clock budget {self.max_seconds}s exceeded")


class Expert(Protocol):
    name: str
    role: str

    def run(self, task: Task, memory, budget: ExpertBudget) -> ExpertResult: ...
