"""Repo-memory learning for the warm arm: L : Sessions -> Memory.

`dspysigs.py` owns the EVAL side (G rubric, J judge, score_episode). It consumes a
memory artifact already written into the warm workspace (w_e (+) k_e) and asks
whether the regenerated action preempts the real correction. This module owns the
OTHER half -- producing that artifact:

    L : Sessions -> Memory        k_e := L(d_e)

Learn a repo-local memory from prior sessions; render it as repo-native
AGENTS.md / nested AGENTS.md / SKILL.md so the warm arm reads it natively. The
output plugs straight into the existing `fork-pair --memory` injection.

THE LEAKAGE FIREWALL (dspysigs.py:39-41 punted this to "where L lives" -- here):

    The TRAINING-SIGNAL CONSTRAINT (Atlas, arXiv 2603.15666): the learned memory
    is bounded by what prior sessions taught. One mechanism, two guarantees:

      1. No-future leak: d_e excludes the held-out session s. The MemoryCorpus
         type physically rejects any turn from s (validator below). Learn s' < s.
      2. No fabrication / no bloat: every card must share >= 2 significant
         keywords with a source prior-session turn (grounding gate). Kills
         hallucinated repo facts AND the generic "unnecessary requirements" the
         AGENTS.md negative result (arXiv 2602.11988) punished.

THE UNIT -- a DECISION CARD (correction-shaped; carries exactly what a pushback
complains about): when / do / preserve / avoid / verify, plus placement
(target_path, role) and provenance (evidence, corroboration_count, source_kind).
A prior CORRECTION -> a boundary rule (preserve/avoid); a prior CLEAN committed
turn -> a guard fact (do) that protects a rule (Atlas dual source).

THE PIPELINE:  d_e -> Proposer(dspy.RLM) -> Critic(3-step gate) -> Placer(altitude)
-> Renderer -> k_e.  One MemoryLearner Protocol; ExpeL / AWM / Mem0 baselines and
Ours all implement it, so the eval harness is identical across the ladder
(cold < Mem0 < ExpeL/AWM < Ours).
"""

from __future__ import annotations

import posixpath
import re
from typing import Literal, Protocol, get_args

import dspy
import structlog
from pydantic import BaseModel, Field, model_validator

try:
    from app.config.lm_registry import lm_registry
except ModuleNotFoundError:
    lm_registry = None

logger = structlog.stdlib.get_logger(__name__)

# Atlas step 3: a card must lexically ground in its evidence (>= this many shared
# significant keywords) or it is fabrication and gets quarantined.
GROUNDING_MIN_KEYWORDS = 2
# ExpeL importance count: a new card starts here; UPVOTE/EDIT +1, DOWNVOTE -1; at
# 0 it is removed. Doubles as the Atlas corroboration count.
NEW_CARD_IMPORTANCE = 2
# Atlas step 1: candidate cards above this similarity to an existing card are
# duplicates (merge, do not re-add).
DEDUP_SIMILARITY_TAU = 0.92

CardRole = Literal[
    'root', 'subsystem', 'seam', 'leaf', 'tests', 'tooling', 'legacy', 'generated'
]
SourceKind = Literal['boundary_rule', 'guard_fact']
Verdict = Literal['accept', 'reject', 'merge', 'needs_review']


# ---------------------------------------------------------------------------
# Corpus (d_e): the prior-session evidence L is allowed to learn from
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    """A pointer into a PRIOR session that grounds a card. The firewall lives in
    the type: `session_id` must be a prior session (s' < s), never the held-out s.
    """

    session_id: str = Field(description="Prior session id (s' < s). Never the held-out s.")
    turn_id: str = Field(description='Turn within the prior session the lesson came from.')
    file_paths: list[str] = Field(
        default_factory=list,
        description='Repo-relative paths touched in this turn. Drives altitude (LCA).',
    )
    quote: str = Field(
        description='The verbatim snippet the lesson was distilled from. Used for the '
        '>= 2 keyword grounding check, so it must contain the concrete nouns.'
    )


class PriorEpisode(BaseModel):
    """One training-signal episode mined from a PRIOR session. A correction -> a
    boundary rule; a clean committed turn -> a guard fact (Atlas dual source)."""

    session_id: str
    instruction: str = Field(description='u: what the user asked in the prior session.')
    action: str = Field(description='a: what the prior agent did.')
    correction: str = Field(
        default='',
        description='p: the prior pushback, if any. Present -> boundary-rule source; '
        'empty -> a clean turn (guard-fact source).',
    )
    file_paths: list[str] = Field(default_factory=list)
    committed_outcome: str = Field(
        default='', description='The accepted/committed result, if any. Guard-fact source.'
    )


class MemoryCorpus(BaseModel):
    """d_e: the prior-session evidence L may learn from, for one cutoff.

    THE FIREWALL, ENFORCED BY THE TYPE: every episode is from a session strictly
    before the held-out session. The validator rejects any episode whose
    `session_id == cutoff_session_id`, so L physically cannot read the session it
    will be tested on.
    """

    repo_id: str
    cutoff_session_id: str = Field(
        description="The held-out session s. Learn s' < s only; this id must NOT "
        'appear in prior_episodes.'
    )
    prior_episodes: list[PriorEpisode] = Field(
        description="Episodes from sessions s' < s. Carries no turn from s."
    )

    @model_validator(mode='after')
    def _no_held_out_leak(self) -> 'MemoryCorpus':
        leaked = [e for e in self.prior_episodes if e.session_id == self.cutoff_session_id]
        if leaked:
            raise ValueError(
                f'Leakage firewall: {len(leaked)} corpus episode(s) come from the '
                f"held-out session {self.cutoff_session_id}. L may only see s' < s."
            )
        return self


# ---------------------------------------------------------------------------
# The unit (k): a decision card, and the full artifact (k_e)
# ---------------------------------------------------------------------------


class DecisionCard(BaseModel):
    """One atomic, correction-shaped learned memory. Renders to AGENTS.md/SKILL.md."""

    card_id: str = Field(description='Stable id, e.g. "repo:slug".')
    when: str = Field(
        description='Trigger: the recurring situation this applies to. '
        'E.g. "adding a new webhook handler".'
    )
    do: str = Field(
        default='',
        description='The canonical action/pattern to copy; may name a golden exemplar '
        'path. Empty if this card is purely a guard rail.',
    )
    preserve: str = Field(
        default='',
        description='Invariant that must keep holding (Atlas boundary rule). '
        'E.g. "validate signature before deserializing the payload".',
    )
    avoid: str = Field(
        default='',
        description='Anti-pattern / legacy bait not to copy (Atlas boundary rule). '
        'Name the misleading file or symbol.',
    )
    verify: str = Field(
        default='',
        description='Cheap proof tied to this change type. CONTENT ONLY -- the '
        'read-only eval recommends it, never runs it.',
    )

    target_path: str = Field(
        default='',
        description='Repo-relative dir this card governs. "" = root AGENTS.md. '
        'v1 clamps every card to "".',
    )
    role: CardRole = Field(default='root')
    altitude_justification: str = Field(
        default='',
        description='Why this layer: the breadth of evidence that makes it true and '
        'stable here.',
    )

    evidence: list[Evidence] = Field(
        description='Prior-session pointers. >= 1 required; every session_id must be a '
        'prior session. Ungrounded cards are rejected by the critic.'
    )
    corroboration_count: int = Field(
        default=NEW_CARD_IMPORTANCE,
        description='ExpeL importance / Atlas corroboration. Reaches 0 -> dropped.',
    )
    source_kind: SourceKind = Field(default='boundary_rule')
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class MemoryArtifact(BaseModel):
    """k_e: the full learned memory for one cutoff, ready to write into the warm arm."""

    repo_id: str
    cutoff_session_id: str
    learner: str = Field(description='Which L produced this: expel | awm | mem0 | ours.')
    cards: list[DecisionCard]

    def render(self) -> dict[str, str]:
        """{ relative_path -> markdown }. v1 collapses every card to root AGENTS.md."""
        return render_markdown(self.cards)


class CardVerdict(BaseModel):
    card_id: str
    verdict: Verdict
    grounded: bool
    reasoning: str


# ---------------------------------------------------------------------------
# Deterministic gate helpers (no LLM): grounding + altitude floor
# ---------------------------------------------------------------------------


_STOPWORDS = frozenset(
    'the a an and or of to in is it be this that these those for with on at by from '
    'as are was were will would should can could not do does did you your we our '
    'have has had then than into over under when what which while'.split()
)


def significant_keywords(text: str) -> set[str]:
    """Lowercased alpha-ish tokens of length > 3, minus stopwords. Cheap, and good
    enough for the Atlas grounding heuristic (it is not semantic entailment)."""
    tokens = re.findall(r'[A-Za-z_][A-Za-z0-9_]{3,}', text.lower())
    return {t for t in tokens if t not in _STOPWORDS}


def is_grounded(card: DecisionCard, *, min_keywords: int = GROUNDING_MIN_KEYWORDS) -> bool:
    """Atlas step 3: the card's claim must share >= min_keywords with its own
    evidence quotes. Filters fabricated repo facts with no LLM call."""
    claim = ' '.join([card.when, card.do, card.preserve, card.avoid])
    evidence_text = ' '.join(e.quote for e in card.evidence)
    overlap = significant_keywords(claim) & significant_keywords(evidence_text)
    return len(overlap) >= min_keywords


def evidence_lca(card: DecisionCard) -> str:
    """Lowest common ancestor directory of the card's evidence paths -> the altitude
    floor. '' (root) when evidence spans unrelated trees or carries no paths."""
    dirs = [posixpath.dirname(p) for e in card.evidence for p in e.file_paths if p]
    if not dirs:
        return ''
    try:
        return posixpath.commonpath(dirs)
    except ValueError:  # mixed absolute/relative -- treat as root
        return ''


# ---------------------------------------------------------------------------
# DSPy signatures
# ---------------------------------------------------------------------------


class ProposeCards(dspy.Signature):
    """Mine recurring, durable repo lessons from PRIOR same-repo sessions.

    You get a corpus of prior episodes: each has the user instruction, what the
    agent did, and -- when present -- the user's correction and the committed
    outcome. Distill the lessons that would have preempted those corrections and
    that will keep mattering in this repo.

    THE TRAINING-SIGNAL CONSTRAINT (load-bearing): emit ONLY what the evidence
    teaches. Every card must be backed by specific prior episodes, and its claim
    must reuse the concrete nouns from those episodes (paths, symbols, commands).
    Do NOT invent repo facts, generic best practices, or "unnecessary
    requirements" the corpus never raised -- those make tasks harder, not easier.

    Prefer FEW, HIGH-SUPPORT cards: a lesson seen across several sessions beats ten
    one-offs. A correction -> a boundary rule (preserve/avoid). A clean committed
    turn that did the right thing -> a guard fact (do) that protects a rule.
    """

    repo_id: str = dspy.InputField(desc='The repository these lessons are scoped to.')
    corpus: str = dspy.InputField(
        desc='d_e: serialized prior episodes (instruction / action / correction / '
        'committed outcome / file paths). May be large -- explore it programmatically.'
    )
    candidate_cards: list[DecisionCard] = dspy.OutputField(
        desc='Durable, evidence-grounded decision cards. Each MUST cite >= 1 prior '
        'episode in `evidence`, with the verbatim quote it was distilled from.'
    )


class VerifyCard(dspy.Signature):
    """Decide whether ONE candidate card is durable repo memory worth keeping.

    This is the LLM step of the Atlas 3-step gate (dedup and grounding run
    deterministically around you). Apply the keep/reject rules:

    KEEP a repo invariant, API fact, setup/workflow rule, path convention, test
    harness rule, or a recurring gotcha that caused a real correction.

    REJECT if it is: subjective taste/wording, a one-off instruction, vague ("be
    careful", "test more"), discoverable trivia an agent would find anyway, or a
    generic best practice the corpus did not actually raise. Never promote
    silently -- when unsure, return needs_review.
    """

    card: DecisionCard = dspy.InputField(desc='The candidate decision card.')
    sibling_cards: str = dspy.InputField(
        desc='Already-accepted cards for this repo, for dedup / merge context.'
    )
    verdict: Verdict = dspy.OutputField(
        desc='accept | reject | merge (into an existing card) | needs_review.'
    )
    reasoning: str = dspy.OutputField(desc='One sentence citing the rule that fired.')


class PlaceCard(dspy.Signature):
    """Assign a card the HIGHEST layer where it is true, actionable, and stable.

    A rule belongs higher only if it holds for the whole subtree, changes decisions
    there, and will not churn on local detail. Global truths go to root; local
    tactics stay at the leaf. You are given the lowest-common-ancestor directory of
    the card's evidence as the altitude FLOOR -- never place a card below it.
    Promote above it only if the lesson plainly generalizes to siblings.
    """

    card: DecisionCard = dspy.InputField()
    evidence_lca: str = dspy.InputField(
        desc='Altitude floor: LCA of evidence paths. "" means evidence spans the repo.'
    )
    sibling_paths: str = dspy.InputField(
        desc='Other directories that exist in the repo, to judge generalization.'
    )
    target_path: str = dspy.OutputField(desc='Chosen dir. "" = root AGENTS.md.')
    role: CardRole = dspy.OutputField()
    altitude_justification: str = dspy.OutputField()


# ---------------------------------------------------------------------------
# DSPy modules (mirror RubricGenerator / Judge in dspysigs.py)
# ---------------------------------------------------------------------------


class Proposer(dspy.Module):
    """Recurring-lesson extraction over d_e via a Recursive LM, which explores a
    large corpus in a sandboxed REPL rather than stuffing one mega-prompt."""

    MODEL_VERSION = 'proposer-rlm-v1'

    def __init__(self, lm: dspy.LM | None = None, *, max_iterations: int = 12) -> None:
        super().__init__()
        if lm is None and lm_registry is None:
            raise ValueError('Proposer requires an explicit dspy.LM.')
        self._lm = lm or lm_registry.proposer()
        # RLM is experimental; the workflow verifies it returns structured cards and
        # falls back to a map-reduce dspy.Predict over episodes if it struggles.
        self._propose = dspy.RLM(ProposeCards, max_iterations=max_iterations)

    async def propose(self, corpus: MemoryCorpus) -> list[DecisionCard]:
        with dspy.context(lm=self._lm):
            res = await self._propose.acall(
                repo_id=corpus.repo_id, corpus=corpus.model_dump_json()
            )
        cards = list(res.candidate_cards or [])
        logger.info('memory.proposed', repo_id=corpus.repo_id, n_cards=len(cards))
        return cards


class Critic(dspy.Module):
    """Atlas 3-step gate: grounding (deterministic) -> dedup (deterministic) -> LLM
    verify. Never promotes silently; maintains the ExpeL corroboration count."""

    MODEL_VERSION = 'critic-gate-v1'

    def __init__(self, lm: dspy.LM | None = None) -> None:
        super().__init__()
        if lm is None and lm_registry is None:
            raise ValueError('Critic requires an explicit dspy.LM.')
        self._lm = lm or lm_registry.critic()
        self._verify = dspy.Predict(VerifyCard)

    async def filter(
        self, cards: list[DecisionCard]
    ) -> tuple[list[DecisionCard], list[CardVerdict]]:
        kept: list[DecisionCard] = []
        verdicts: list[CardVerdict] = []
        for card in cards:
            if not is_grounded(card):  # step 3 first: free, deterministic
                verdicts.append(
                    CardVerdict(
                        card_id=card.card_id,
                        verdict='reject',
                        grounded=False,
                        reasoning='ungrounded: < 2 keywords shared with its evidence',
                    )
                )
                continue
            if _is_duplicate(card, kept):  # step 1
                _corroborate(card, kept)
                verdicts.append(
                    CardVerdict(
                        card_id=card.card_id,
                        verdict='merge',
                        grounded=True,
                        reasoning='duplicate of an accepted card; corroboration += 1',
                    )
                )
                continue
            with dspy.context(lm=self._lm):  # step 2: LLM verify, never silent
                res = await self._verify.acall(
                    card=card, sibling_cards=_render_siblings(kept)
                )
            verdict = res.verdict if res.verdict in get_args(Verdict) else 'needs_review'
            verdicts.append(
                CardVerdict(
                    card_id=card.card_id,
                    verdict=verdict,
                    grounded=True,
                    reasoning=res.reasoning or '',
                )
            )
            if verdict == 'accept':
                kept.append(card)
        logger.info('memory.criticized', n_in=len(cards), n_kept=len(kept))
        return kept, verdicts


class Placer(dspy.Module):
    """Altitude assignment. v1 CLAMPS every card to root; the LCA floor and the LLM
    call are wired so v2 just flips `clamp_to_root=False`."""

    MODEL_VERSION = 'placer-v1'

    def __init__(self, lm: dspy.LM | None = None, *, clamp_to_root: bool = True) -> None:
        super().__init__()
        if lm is None and lm_registry is None:
            raise ValueError('Placer requires an explicit dspy.LM.')
        self._lm = lm or lm_registry.placer()
        self._place = dspy.Predict(PlaceCard)
        self._clamp_to_root = clamp_to_root

    async def place(
        self, cards: list[DecisionCard], *, repo_dirs: list[str] | None = None
    ) -> list[DecisionCard]:
        if self._clamp_to_root:
            for card in cards:
                card.target_path, card.role = '', 'root'
            return cards
        for card in cards:
            floor = evidence_lca(card)
            with dspy.context(lm=self._lm):
                res = await self._place.acall(
                    card=card,
                    evidence_lca=floor,
                    sibling_paths=', '.join(repo_dirs or []),
                )
            card.target_path = res.target_path or floor
            card.role = res.role if res.role in get_args(CardRole) else 'subsystem'
            card.altitude_justification = res.altitude_justification or ''
        return cards


# ---------------------------------------------------------------------------
# The L interface: one Protocol, four learners (baselines + ours)
# ---------------------------------------------------------------------------


class MemoryLearner(Protocol):
    """L : MemoryCorpus -> MemoryArtifact. Every baseline and Ours implement this,
    so the eval harness in dspysigs.py is identical across the ladder."""

    name: str

    async def learn(self, corpus: MemoryCorpus) -> MemoryArtifact: ...


class OursLearner:
    """Proposer -> Critic -> Placer -> artifact. Repo-local, verified, altitude-placed."""

    name = 'ours'

    def __init__(self, *, proposer: Proposer, critic: Critic, placer: Placer) -> None:
        self._proposer, self._critic, self._placer = proposer, critic, placer

    async def learn(self, corpus: MemoryCorpus) -> MemoryArtifact:
        cards = await self._proposer.propose(corpus)
        kept, _ = await self._critic.filter(cards)
        placed = await self._placer.place(kept)
        return MemoryArtifact(
            repo_id=corpus.repo_id,
            cutoff_session_id=corpus.cutoff_session_id,
            learner=self.name,
            cards=placed,
        )


class ExpeLLearner:
    """Baseline (arXiv 2308.10144): an insight list maintained with ADD/EDIT/UPVOTE/
    DOWNVOTE + importance count over d_e, rendered FLAT to root AGENTS.md. No placer,
    no grounding gate -- that gap is the point. Implemented by the workflow."""

    name = 'expel'

    async def learn(self, corpus: MemoryCorpus) -> MemoryArtifact:
        raise NotImplementedError('Workflow implements the ExpeL insight loop here.')


class AWMLearner:
    """Baseline (arXiv 2409.07429): induce reusable workflows from successes, abstract
    example-specific values to {placeholders}, render FLAT to SKILL.md. Workflow impl."""

    name = 'awm'

    async def learn(self, corpus: MemoryCorpus) -> MemoryArtifact:
        raise NotImplementedError('Workflow implements AWM workflow induction here.')


class Mem0Learner:
    """Foil (arXiv 2504.19413): generic retrieval-memory blob. Workflow impl."""

    name = 'mem0'

    async def learn(self, corpus: MemoryCorpus) -> MemoryArtifact:
        raise NotImplementedError('Workflow implements the Mem0 retrieval foil here.')


# ---------------------------------------------------------------------------
# Renderer: cards -> { path: markdown }, the artifact the warm arm reads
# ---------------------------------------------------------------------------


def render_markdown(cards: list[DecisionCard]) -> dict[str, str]:
    """Group cards by target_path; render each group as one markdown file. '' ->
    'AGENTS.md'; 'server/routes' -> 'server/routes/AGENTS.md'."""
    by_path: dict[str, list[DecisionCard]] = {}
    for card in cards:
        by_path.setdefault(card.target_path, []).append(card)
    files: dict[str, str] = {}
    for path, group in by_path.items():
        rel = posixpath.join(path, 'AGENTS.md') if path else 'AGENTS.md'
        files[rel] = _render_one_file(group)
    return files


def _render_one_file(cards: list[DecisionCard]) -> str:
    lines = [
        '# AGENTS.md',
        '',
        '_Learned from prior sessions in this repo. Each card preempted a real correction._',
        '',
    ]
    for card in cards:
        lines.append(f'## When: {card.when}')
        if card.do:
            lines.append(f'- **Do:** {card.do}')
        if card.preserve:
            lines.append(f'- **Preserve:** {card.preserve}')
        if card.avoid:
            lines.append(f'- **Avoid:** {card.avoid}')
        if card.verify:
            lines.append(f'- **Verify:** {card.verify}')
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


# ---------------------------------------------------------------------------
# Internal: deterministic dedup + corroboration (v1; workflow upgrades to embeddings)
# ---------------------------------------------------------------------------


def _card_tokens(card: DecisionCard) -> set[str]:
    return significant_keywords(' '.join([card.when, card.do, card.preserve, card.avoid]))


def _is_duplicate(card: DecisionCard, kept: list[DecisionCard]) -> bool:
    # v1 dedup: token Jaccard. TODO(workflow): embedding cosine > DEDUP_SIMILARITY_TAU.
    a = _card_tokens(card)
    if not a:
        return False
    for existing in kept:
        b = _card_tokens(existing)
        if b and len(a & b) / len(a | b) >= 0.6:
            return True
    return False


def _corroborate(card: DecisionCard, kept: list[DecisionCard]) -> None:
    a = _card_tokens(card)
    best = max(kept, key=lambda k: len(a & _card_tokens(k)), default=None)
    if best is not None:
        best.corroboration_count += 1
        best.evidence.extend(card.evidence)


def _render_siblings(kept: list[DecisionCard]) -> str:
    if not kept:
        return '(none accepted yet)'
    return '\n'.join(
        f'- [{c.card_id}] when={c.when} :: preserve={c.preserve} :: avoid={c.avoid}'
        for c in kept
    )
