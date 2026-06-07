"""Rubric generation + counterfactual judging for the repo-memory eval.

This module owns two of the system's functions:

    G : OraclePacket -> Rubric                 (RubricGenerator)
    J : (history, instruction, criterion, candidate) -> {0,1}   (Judge)

plus the per-episode control flow that ties them together with the candidate
agent A and reports the metrics that actually matter.

THE EPISODE MODEL (notation maps to the whiteboard letters at the bottom):

    e        one pushback episode: (repo, session, turn_index j)
    h_e      history before the trigger: the prefix transcript m[0 .. j-1]
    w_e      workspace state before the trigger instruction
    u_e      trigger instruction         (the user msg m_j the agent answered)
    a_e      action on trial             (what the logged agent actually did)
    p_e      observed pushback           (the user's correction, m_{j+1})
    tail_e   the user's downstream msgs  (the user turns m_{j+1 .. n}; intent/taste)

    x_e      re-entry context the candidate agent sees: (workspace, history, u_e)
    o_e      oracle packet the EVALUATOR sees:
             (history, u_e, a_e, p_e, downstream_user_messages)

NOTE on what's deliberately NOT in o_e: the final committed diff. It's the
endpoint of the whole multi-turn repair -- incidental churn swamps the one
correction we care about, and it over-specifies a target for a single regenerated
turn. The user's own downstream messages are the clean taste/intent signal.

THE LEAKAGE FIREWALL (enforced by the types, not by good intentions):

    - The candidate agent A receives ONLY a ReentryContext (x_e). It never sees
      a_e, p_e, the downstream messages, or the rubric.
    - The rubric is generated ONLY from the OraclePacket (o_e). G never sees a
      candidate action.
    - The Judge sees the forked prefix (history + instruction) + a candidate +
      the criterion. It is NOT handed p_e: the criterion already encodes what
      "correct" means, so it scores on merit, not by matching the original.
    - SEPARATELY (and NOT enforceable here): the memory learner L must be built
      to exclude the session being scored -- learn from s' < s only. This file
      doesn't own L, so it can't stop that leak. Enforce it where L lives.

SIGN CONVENTION: a criterion is SATISFIED (pass = 1) when the candidate exhibits
the good property. Never "1 = the bad thing recurred".

MEMORY INJECTION: the warm arm is the same workspace with the memory artifact
written into it (w_e (+) k_e), read natively. Whether to instead nudge the
instruction with a "go read memory" suffix is an OPEN PRODUCT CALL, not settled
here -- see ReentryContext.memory_read_hint.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

import dspy
import structlog
from pydantic import BaseModel, Field


try:
    from app.config.lm_registry import lm_registry
except ModuleNotFoundError:
    lm_registry = None

logger = structlog.stdlib.get_logger(__name__)

# 1-3 is deliberate: a rubric centered on the flaw stays binary-ish and clean.
# Fat rubrics + a strict pass threshold make "cold fails" trivial and gut the
# reproducibility filter.
MAX_CRITERIA = 3
DEFAULT_N_SAMPLES = 3  # A is stochastic; a single draw is mostly noise at small n.
DEFAULT_TAU = 1.0  # warm "passes" only if it satisfies every criterion.


# ---------------------------------------------------------------------------
# Rubric (the case spec for one episode)
# ---------------------------------------------------------------------------


class Criterion(BaseModel):
    """One checkable property a correct action should exhibit.

    Phrased POSITIVELY: what a good action does, never "do not repeat <mistake>".
    A negation of the original action's specific move ("didn't touch the stagger
    delay") is vacuous when the candidate took a different route to the goal. Each
    criterion must be judgeable against a candidate that may have solved the task
    completely differently from the original.
    """

    id: int = Field(description='Stable 0-based index within the rubric.')
    requirement: str = Field(
        description='The property as a positive, checkable statement about the '
        "candidate action. E.g. 'Identifies the container animation timing as the "
        "cause of the slowdown' -- NOT 'does not change the item stagger again'. "
        "One orthogonal property per criterion. If two clauses can pass/fail "
        "independently, split or merge so that partial credit cannot reward the "
        "original flaw."
    )
    admission_condition: str = Field(
        default='',
        description='What concrete evidence must be present in a candidate action '
        'before this criterion can be judged satisfied. For entity/set errors, '
        'name the exact required entities and explicit false positives.'
    )
    rationale: str = Field(
        description='One sentence on why this is what the real user was actually '
        'after, grounded in the pushback and the downstream messages. For the team '
        'to read; not used in scoring.'
    )


class Rubric(BaseModel):
    """The full case spec for an episode: 1-3 criteria + the generator's reasoning."""

    criteria: list[Criterion]
    reasoning: str = Field(
        default='', description='Why these criteria and not others. Audit trail.'
    )
    admission_failures: list[str] = Field(
        default_factory=list,
        description='Generated criteria rejected before scoring because they were '
        'not self-contained, orthogonal, or independently judgeable.'
    )


# ---------------------------------------------------------------------------
# Oracle packet (evaluator-only evidence; the input to G)
# ---------------------------------------------------------------------------


class OraclePacket(BaseModel):
    """o_e: everything the EVALUATOR may inspect to understand what went wrong.

    NEVER handed to the candidate agent. This is the load-bearing firewall object.
    The final committed diff is intentionally absent because it pollutes the
    single-turn correction target.
    """

    history: str = Field(
        description='h_e: the prefix transcript m[0..j-1] -- what the agent was '
        'working on before the trigger. Context for the rubric, so criteria are '
        'grounded in the actual task.'
    )
    instruction: str = Field(description='u_e: the user instruction the agent answered.')
    original_action: str = Field(
        description='a_e: what the logged agent actually did and said -- the action '
        'that drew the pushback. Rendered tool calls + edits + final response.'
    )
    pushback: str = Field(
        description='p_e: the real user correction/rejection reacting to a_e. The '
        'primary signal for what went wrong.'
    )
    downstream_user_messages: str = Field(
        default='',
        description='The USER messages across the rest of the session (turns '
        'j+1..n) -- the taste/intent signal. User turns only, not agent turns, not '
        'the final diff. This includes the pushback as its first message; the '
        'pushback field above just surfaces it for emphasis. Empty string if none.',
    )


# ---------------------------------------------------------------------------
# Candidate action + re-entry context (what A produces / consumes; x_e)
# ---------------------------------------------------------------------------


class CandidateAction(BaseModel):
    """a-hat: the agent's regenerated turn, in a form the judge can read."""

    rendered: str = Field(
        description='The candidate turn rendered for judging. Keep this focused on '
        'what the candidate claimed or did in the regenerated turn; do not include '
        'harness setup diffs, memory overlays, or replay baseline diffs.'
    )
    diff: str | None = Field(
        default=None,
        description='Optional unified diff of the edits the candidate proposed, if '
        'separable from the rendered transcript.',
    )


class ReentryContext(BaseModel):
    """x_e: everything (and ONLY what) the candidate agent gets.

    Carries no oracle info -- no original_action, no pushback, no rubric. Cold and
    warm differ solely in whether `workspace_path` already has the memory artifact
    written into it.
    """

    workspace_path: str = Field(
        description='w_e: path to the repo checked out at the pre-trigger state. For '
        'the WARM arm the memory files (AGENTS.md / skills) are already written '
        'here and the agent reads them natively.'
    )
    history: str = Field(
        description='h_e: rendered prior transcript up to (not including) the '
        'trigger turn.'
    )
    instruction: str = Field(description='u_e: the trigger instruction to act on.')
    memory_read_hint: str | None = Field(
        default=None,
        description='OPEN CALL: leave None for native AGENTS.md read (default). Set '
        'to a short suffix like "check any AGENTS.md/skills in the repo first" to '
        'force the read. Forcing the read measures "memory helps IF read"; native '
        'measures "memory helps in practice". Must be applied consistently.'
    )


class CandidateAgent(Protocol):
    """A: the agent under test. Implement over Claude Code headless (or any
    AGENTS.md-reading agent). MUST be the same model/config for cold and warm --
    that fixed-agent contrast is the entire point. Implementation lives in the
    harness; this module only calls it.
    """

    async def run(self, ctx: ReentryContext) -> CandidateAction: ...


# ---------------------------------------------------------------------------
# DSPy signatures
# ---------------------------------------------------------------------------


class GenerateRubric(dspy.Signature):
    """Turn one pushback episode into a small rubric of pass/fail criteria.

    You get the ORIGINAL logged episode: the prefix the agent was working in, the
    user's instruction, what the agent did, the correction the user pushed back
    with, and the user's later messages (their taste/intent). Distill what a
    CORRECT action at that exact moment would have to satisfy.

    This is the answer key, built ONLY from this original evidence. It will be used
    to score regenerated candidate actions you do not see. Do not write criteria by
    imagining a specific better patch; write the properties any correct action must
    have, however it gets there.

    Rules:
    - 1-3 criteria. Center them on the thing the pushback was actually about. Do
      not pad with generic code-quality wishes the user never raised.
    - Positive phrasing only (see Criterion.requirement). Each must be checkable
      against a candidate that took a totally different route to the goal.
    - Each criterion must be self-contained and independently true/false from the
      candidate action alone. Do not rely on another criterion, rationale, or a
      phrase like "the set" to resolve what correctness means.
    - For entity, membership, classification, or set errors, name the exact
      required entities and explicit false positives inside the requirement.
    - Avoid process-only criteria that can pass while the central pushback flaw
      still recurs. If a candidate could satisfy a criterion while still making
      the user's correction necessary, rewrite or drop that criterion.
    - A criterion is SATISFIED when the candidate exhibits the good property. Never
      phrase it so that "1" means the bad thing happened.
    """

    history: str = dspy.InputField(
        desc='h_e: prefix transcript m[0..j-1] -- what the agent was working on. '
        'Context only; do not write criteria about it.'
    )
    instruction: str = dspy.InputField(
        desc='u_e: the user instruction the agent was responding to.'
    )
    original_action: str = dspy.InputField(
        desc='a_e: what the logged agent actually did and said -- the action that '
        'drew the pushback.'
    )
    pushback: str = dspy.InputField(
        desc='p_e: the real user correction reacting to a_e. Primary signal for '
        'what went wrong.'
    )
    downstream_user_messages: str = dspy.InputField(
        desc='The user\'s later messages (turns j+1..n) -- use to infer INTENT. Do '
        'NOT write criteria that merely replay these turns. Empty string if none.'
    )

    reasoning: str = dspy.OutputField(
        desc='What was the real failure, and what must a correct action get right? '
        'Why these criteria and not others?'
    )
    criteria: list[Criterion] = dspy.OutputField(
        desc='1-3 positive, independently-checkable criteria. The rubric.'
    )


class JudgeCriterion(dspy.Signature):
    """Decide whether ONE candidate action satisfies ONE criterion.

    You see the forked prefix (what came before) plus the candidate's turn. Judge
    only against the criterion text. Be evidence-grounded: cite what in the
    candidate action does or doesn't satisfy it. Do not reward intentions or
    partial gestures.

    You are deliberately NOT shown the original mistake or the user's pushback. The
    criterion already encodes what "correct" means; judge the candidate on its own
    merits, not by comparison to the original. A different-but-correct approach
    passes.
    """

    history: str = dspy.InputField(
        desc='h_e: the prefix transcript m[0..j-1], for context on what the agent '
        'was doing.'
    )
    instruction: str = dspy.InputField(desc='u_e: what the user asked for.')
    criterion: str = dspy.InputField(
        desc='The single property to check (Criterion.requirement).'
    )
    candidate_action: str = dspy.InputField(
        desc="a-hat: the agent's regenerated action -- tool calls, edits, final "
        'response. May solve the task differently from the original; that is fine.'
    )

    passed: bool = dspy.OutputField(
        desc="True iff the candidate clearly exhibits the criterion's property."
    )
    reasoning: str = dspy.OutputField(
        desc='One or two sentences citing the specific evidence for the verdict.'
    )


# ---------------------------------------------------------------------------
# DSPy modules
# ---------------------------------------------------------------------------


class CriterionVerdict(BaseModel):
    criterion_id: int
    passed: bool
    reasoning: str


class ScoredCandidate(BaseModel):
    """One candidate action scored against a full rubric."""

    score: float  # fraction of criteria satisfied, in [0, 1]
    verdicts: list[CriterionVerdict]


_REFERENTIAL_CRITERION_PHRASES = (
    "external contributor set",
    "the contributor set",
    "the correct set",
    "the actual set",
    "the right set",
    "the set of",
    "the relevant set",
    "correct contributors",
    "actual contributors",
    "right contributors",
    "only the external contributors",
)


def _criterion_admission_failure(criterion: Criterion) -> str | None:
    requirement = " ".join(criterion.requirement.lower().split())
    if not requirement:
        return "empty criterion requirement"
    for phrase in _REFERENTIAL_CRITERION_PHRASES:
        if phrase in requirement:
            has_named_entity = "@" in criterion.requirement or "`" in criterion.requirement
            if not has_named_entity:
                return (
                    f"criterion `{criterion.requirement}` uses referential phrase "
                    f"`{phrase}` without naming the concrete entities"
                )
    if " if " in requirement:
        return (
            f"criterion `{criterion.requirement}` appears conditional rather than "
            "independently true/false"
        )
    return None


def _normalize_criterion_ids(
    criteria: list[Criterion],
) -> tuple[list[Criterion], list[str]]:
    """Admit self-contained criteria and force dense 0..N-1 ids."""
    admitted: list[Criterion] = []
    failures: list[str] = []
    for criterion in criteria:
        failure = _criterion_admission_failure(criterion)
        if failure:
            failures.append(failure)
            continue
        admitted.append(criterion)
        if len(admitted) == MAX_CRITERIA:
            break
    normalized = [
        Criterion(
            id=i,
            requirement=c.requirement,
            admission_condition=c.admission_condition,
            rationale=c.rationale,
        )
        for i, c in enumerate(admitted)
    ]
    return normalized, failures


class RubricGenerator(dspy.Module):
    """G: OraclePacket -> Rubric."""

    MODEL_VERSION = 'rubric-gen-v1'

    def __init__(self, lm: dspy.LM | None = None) -> None:
        super().__init__()
        if lm is None and lm_registry is None:
            raise ValueError('RubricGenerator requires an explicit dspy.LM.')
        self._lm = lm or lm_registry.rubric_generation()
        self._predict = dspy.Predict(GenerateRubric)

    async def generate(self, oracle: OraclePacket) -> Rubric:
        with dspy.context(lm=self._lm):
            res = await self._predict.acall(
                history=oracle.history,
                instruction=oracle.instruction,
                original_action=oracle.original_action,
                pushback=oracle.pushback,
                downstream_user_messages=oracle.downstream_user_messages,
            )
        criteria, admission_failures = _normalize_criterion_ids(res.criteria or [])
        logger.info(
            'rubric.generated',
            n_criteria=len(criteria),
            n_admission_failures=len(admission_failures),
            reasoning=(res.reasoning or '')[:200],
        )
        return Rubric(
            criteria=criteria,
            reasoning=res.reasoning or '',
            admission_failures=admission_failures,
        )


class Judge(dspy.Module):
    """J: scores a candidate action against a rubric, one criterion at a time.

    Per-criterion (not all-at-once) so each gets full attention, parallelizes, and
    yields clean per-criterion verdicts for debugging.
    """

    MODEL_VERSION = 'judge-v1'

    def __init__(self, lm: dspy.LM | None = None) -> None:
        super().__init__()
        if lm is None and lm_registry is None:
            raise ValueError('Judge requires an explicit dspy.LM.')
        self._lm = lm or lm_registry.judge()
        self._predict = dspy.Predict(JudgeCriterion)

    async def _one(
        self,
        history: str,
        instruction: str,
        criterion: Criterion,
        candidate: CandidateAction,
    ) -> CriterionVerdict:
        with dspy.context(lm=self._lm):
            res = await self._predict.acall(
                history=history,
                instruction=instruction,
                criterion=criterion.requirement,
                candidate_action=candidate.rendered,
            )
        return CriterionVerdict(
            criterion_id=criterion.id,
            passed=bool(res.passed),
            reasoning=res.reasoning or '',
        )

    async def score(
        self,
        history: str,
        instruction: str,
        candidate: CandidateAction,
        rubric: Rubric,
    ) -> ScoredCandidate:
        if not rubric.criteria:
            return ScoredCandidate(score=0.0, verdicts=[])
        verdicts = await asyncio.gather(
            *(self._one(history, instruction, c, candidate) for c in rubric.criteria)
        )
        passed = sum(1 for v in verdicts if v.passed)
        return ScoredCandidate(score=passed / len(verdicts), verdicts=list(verdicts))


# ---------------------------------------------------------------------------
# Per-episode control flow
# ---------------------------------------------------------------------------


class EpisodeResult(BaseModel):
    """The counterfactual for one episode: cold vs warm, same fixed agent A."""

    episode_id: str
    cold_score: float  # mean rubric score over n_samples, no memory  (score_e^0)
    warm_score: float  # mean rubric score over n_samples, with memory (score_e^k)
    lift: float  # warm_score - cold_score
    reproduced: (
        bool  # cold_score < tau: the flaw is present, so memory has something to fix
    )
    rescued: bool  # reproduced AND warm_score >= tau: memory fixed it
    rubric: Rubric
    cold_samples: list[ScoredCandidate]
    warm_samples: list[ScoredCandidate]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


async def score_episode(
    *,
    episode_id: str,
    oracle: OraclePacket,
    cold_ctx: ReentryContext,
    warm_ctx: ReentryContext,
    agent: CandidateAgent,
    rubric_generator: RubricGenerator,
    judge: Judge,
    n_samples: int = DEFAULT_N_SAMPLES,
    tau: float = DEFAULT_TAU,
) -> EpisodeResult:
    """Run the single-step counterfactual for one episode.

    cold_ctx and warm_ctx are built by the HARNESS: identical workspace/history/
    instruction, except warm_ctx.workspace_path has the memory artifact written in.
    That localizes the workspace-(+)-memory overlay upstream and keeps this function
    pure w.r.t. the firewall: `agent` only ever touches a ReentryContext.
    """
    rubric = await rubric_generator.generate(oracle)

    # A is stochastic -> sample each arm n_samples times and average.
    cold_runs, warm_runs = await asyncio.gather(
        asyncio.gather(*(agent.run(cold_ctx) for _ in range(n_samples))),
        asyncio.gather(*(agent.run(warm_ctx) for _ in range(n_samples))),
    )

    cold_scored = await asyncio.gather(
        *(judge.score(oracle.history, oracle.instruction, a, rubric) for a in cold_runs)
    )
    warm_scored = await asyncio.gather(
        *(judge.score(oracle.history, oracle.instruction, a, rubric) for a in warm_runs)
    )

    cold_score = _mean([s.score for s in cold_scored])
    warm_score = _mean([s.score for s in warm_scored])
    reproduced = cold_score < tau
    rescued = reproduced and warm_score >= tau

    logger.info(
        'episode.scored',
        episode_id=episode_id,
        cold_score=round(cold_score, 3),
        warm_score=round(warm_score, 3),
        reproduced=reproduced,
        rescued=rescued,
    )

    return EpisodeResult(
        episode_id=episode_id,
        cold_score=cold_score,
        warm_score=warm_score,
        lift=warm_score - cold_score,
        reproduced=reproduced,
        rescued=rescued,
        rubric=rubric,
        cold_samples=list(cold_scored),
        warm_samples=list(warm_scored),
    )


# ---------------------------------------------------------------------------
# Eval-set aggregation (the numbers you actually report)
# ---------------------------------------------------------------------------


class EvalReport(BaseModel):
    """Headline metrics. Report repro_rate and rescue_rate SEPARATELY, not just the
    product -- they answer different questions:

      repro_rate  = |reproduced| / N
          fraction of logged corrections your agent reproduces cold. Diagnostic of
          whether the agent class matches the corpus. With Claude Code as A on a
          Claude-Code-logged corpus this should be high; if it's low, your labels
          and your agent are decoupled and the rest is uninterpretable.

      rescue_rate = |rescued| / |reproduced|
          GIVEN a flaw was present, how often memory fixed it. This is the real
          "does the memory work" number -- the treatment effect on the treated.

      preemption_rate = |rescued| / N  ==  repro_rate * rescue_rate
          the end-to-end number; fine to show, but don't let it hide which factor
          is driving it.

      mean_lift_reproduced
          average (warm - cold) over reproduced episodes only. Computed over the
          reproduced set so episodes with no flaw to fix don't dilute it toward 0.
    """

    n_episodes: int
    repro_rate: float
    rescue_rate: float
    preemption_rate: float
    mean_lift_reproduced: float


def aggregate(results: list[EpisodeResult]) -> EvalReport:
    n = len(results)
    if n == 0:
        return EvalReport(
            n_episodes=0,
            repro_rate=0.0,
            rescue_rate=0.0,
            preemption_rate=0.0,
            mean_lift_reproduced=0.0,
        )

    reproduced = [r for r in results if r.reproduced]
    rescued = [r for r in reproduced if r.rescued]

    return EvalReport(
        n_episodes=n,
        repro_rate=len(reproduced) / n,
        rescue_rate=(len(rescued) / len(reproduced)) if reproduced else 0.0,
        preemption_rate=len(rescued) / n,
        mean_lift_reproduced=_mean([r.lift for r in reproduced]),
    )
