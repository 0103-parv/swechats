yeah. second pass: i’d make **the pushback episode** the center of the notation, not the conversation. once we name one episode (e), almost everything becomes “the thing for episode (e).” that lets the concepts breathe instead of making everyone juggle (C, C_f, M_j, M_{j+1}, E_f), etc.

the reason this fits SWE-chat is that the data is already turn-ish: it has real coding-agent sessions with user prompts, agent responses, tool calls, diffs, attribution, and user pushback annotations. pushback is explicitly a user-prompt-level label with categories like correction, rejection, failure report, and non-pushback. 

## the core reframe

do **not** start with:

[
C \rightarrow C_f
]

start with:

[
e = \text{one held-out pushback episode}
]

an episode is a r[<43;183;23M[<43;184;23Meal moment where the logged agent did something, and the next user message pushed back.

formally:

[
e := (r, s, i)
]

where:

[
r = \text{repository}
]

[
s = \text{session}
]

[
i = \text{turn index whose agent action received pushback}
]

then, after this point, mostly stop writing (r,s,i). use the episode handle (e).

## minimal objects

for episode (e), use these:

[
h_e = \text{history before the trigger instruction}
]

[
w_e = \text{workspace state before the trigger instruction}
]

[
u_e = \text{trigger user instruction}
]

[
a_e = \text{logged original agent action}
]

[
p_e = \text{observed pushback}
]

these five are the backbone.

the causal shape is:

[
(h_e, w_e, u_e)
\longrightarrow
a_e
\longrightarrow
p_e
]

read this as:

> given the prior history, workspace, and user instruction, the original agent produced (a_e), and the user then pushed back with (p_e).

that is the thing you are evaluating against.

## turn structure

a session can be thought of as:

[
S_s =
\big((u_0,a_0), (u_1,a_1), \ldots, (u_n,a_n)\big)
]

where:

[
u_i = \text{user instruction at turn } i
]

[
a_i = \text{agent action/trajectory after } u_i
]

important: (a_i) means the whole agent action, not just text. it can include tool calls, edits, terminal commands, reads, diffs, and final response.

for a pushback episode (e=(r,s,i)):

[
u_e := u_i
]

[
a_e := a_i
]

[
p_e := u_{i+1}
]

so the pushback is not “the thing that caused the action.” the pushback is the **next user message**, reacting to the previous agent action.

the clean English version:

> (u_e) is the prompt being rerun.
> (a_e) is the logged action on trial.
> (p_e) is the real user’s complaint about (a_e).

this is the load-bearing distinction.

## context

bundle what the candidate agent gets into one object:

[
x_e := (w_e, h_e, u_e)
]

call this the **re-entry context**.

it is exactly the stuff needed to ask:

> what would an agent do at this moment?

so:

[
x_e = \text{same state, same prior transcript, same user instruction}
]

no pushback. no future. no answer key.

## memory

let the memory corpus be prior sessions from the same repo:

[
d_e := {S_{r,s'} : s' < s}
]

where (e=(r,s,i)).

then the memory learner is:

[
k_e := L(d_e)
]

where:

[
L = \text{memory learner}
]

[
k_e = \text{learned memory artifact}
]

for your system, (k_e) is something like AGENTS.md content, nested AGENTS.md files, skills, or some other repo-readable memory.

define memory injection as:

[
w_e \oplus k_e
]

where:

[
w_e \oplus k_e
==============

\text{workspace } w_e \text{ with memory artifact } k_e \text{ inserted}
]

this is cleaner than saying “forked environment.” the workspace is the same, except memory has been overlaid onto it.

## cold vs warm contexts

cold context:

[
x_e^0 := (w_e, h_e, u_e)
]

warm context:

[
x_e^k := (w_e \oplus k_e, h_e, u_e)
]

where:

[
0 = \text{no learned memory}
]

[
k = \text{with learned memory}
]

now the agent runner:

[
A = \text{fixed candidate agent/model/config}
]

cold candidate:

[
\hat a_e^0 := A(x_e^0)
]

warm candidate:

[
\hat a_e^k := A(x_e^k)
]

this is the counterfactual. not a whole forked conversation. just a regenerated candidate action.

the hat matters:

[
a_e = \text{logged original action}
]

[
\hat a_e^0 = \text{new cold candidate action}
]

[
\hat a_e^k = \text{new warm candidate action}
]

so (a_e) is historical evidence. (\hat a_e^0) and (\hat a_e^k) are experimental outputs.

## oracle evidence

now define what the rubric generator is allowed to inspect.

[
o_e := (u_e, a_e, p_e, \mathrm{tail}_e, \Delta_e)
]

where:

[
\mathrm{tail}_e = \text{optional logged continuation after the pushback}
]

[
\Delta_e = \text{optional final accepted diff / committed outcome}
]

call (o_e) the **oracle packet**.

this packet is not given to the candidate agent. it is only used to understand what went wrong.

the key distinction:

[
x_e = \text{what the candidate agent sees}
]

[
o_e = \text{what the evaluator sees}
]

the user’s future messages can live inside (\mathrm{tail}_e), but they are evidence for the judge, not dialogue to replay. this matches the earlier methodological point from the attached chat: the downstream turns help interpret intent and resolution, but they should not be fed as if they happened in the counterfactual branch. 

## rubric/spec

i’d slightly rename “rubric” to **case spec** in the mental model, but keep (\mathcal R_e) as the symbol because it’s familiar.

[
\mathcal R_e := G(o_e)
]

where:

[
G = \text{rubric/spec generator}
]

[
\mathcal R_e = {c_{e,1}, c_{e,2}, \ldots, c_{e,m_e}}
]

each criterion is a predicate over a candidate action:

[
c_{e,j} : \mathsf{Action} \rightarrow {0,1}
]

with the positive convention:

[
c_{e,j}(\hat a) = 1
\quad\Longleftrightarrow\quad
\hat a \text{ satisfies criterion } j
]

do not make (1) mean “bad flaw recurs.” make (1) mean “passes.” otherwise your scores become cursed little swamp numbers.

example criterion:

[
c_{e,1}(\hat a)=1
]

means:

> the candidate identifies the container animation timing as the issue, rather than again changing the individual item stagger.

this lines up with your whiteboard’s “RubricGen → list[Criteria] → Judge → score 0/1” shape. 

## judge and score

let:

[
J(c,\hat a) \in {0,1}
]

where (J) applies criterion (c) to candidate action (\hat a).

then:

[
\operatorname{score}*e^z
:=
\frac{1}{|\mathcal R_e|}
\sum*{c \in \mathcal R_e}
J(c,\hat a_e^z)
]

where:

[
z \in {0,k}
]

so:

[
\operatorname{score}_e^0
========================

\text{cold score}
]

[
\operatorname{score}_e^k
========================

\text{warm score}
]

## effect of memory

for one episode:

[
\operatorname{lift}_e
:=
\operatorname{score}_e^k
------------------------

\operatorname{score}_e^0
]

over an eval set (\mathcal E):

[
\operatorname{MeanLift}(\mathcal E)
:=
\frac{1}{|\mathcal E|}
\sum_{e \in \mathcal E}
\operatorname{lift}_e
]

binary preemption:

[
\operatorname{preempt}_e
:=
\mathbf 1
\left[
\operatorname{score}_e^0 < \tau
;\land;
\operatorname{score}_e^k \ge \tau
\right]
]

and:

[
\operatorname{PreemptionRate}(\mathcal E)
:=
\frac{1}{|\mathcal E|}
\sum_{e \in \mathcal E}
\operatorname{preempt}_e
]

where (\tau) is the pass threshold. for a quick binary setup:

[
\tau = 1
]

meaning: warm only counts as passing if it satisfies all criteria.

## whole system in one block

this is the version i’d put on the board:

[
\boxed{
\begin{aligned}
e &:= (r,s,i) [1mm]
x_e &:= (w_e,h_e,u_e) [1mm]
d_e &:= {S_{r,s'} : s' < s} [1mm]
k_e &:= L(d_e) [1mm]
x_e^0 &:= (w_e,h_e,u_e) [1mm]
x_e^k &:= (w_e \oplus k_e,h_e,u_e) [1mm]
\hat a_e^0 &:= A(x_e^0) [1mm]
\hat a_e^k &:= A(x_e^k) [1mm]
o_e &:= (u_e,a_e,p_e,\mathrm{tail}_e,\Delta_e) [1mm]
\mathcal R_e &:= G(o_e) [1mm]
\operatorname{score}*e^z
&:=
\frac{1}{|\mathcal R_e|}
\sum*{c \in \mathcal R_e}
J(c,\hat a_e^z) [1mm]
\operatorname{lift}_e
&:=
\operatorname{score}_e^k
------------------------

\operatorname{score}_e^0
\end{aligned}
}
]

that is the clean spine.

## type signatures

for reasoning, i’d also write the system as type signatures:

[
L : \mathsf{Sessions} \rightarrow \mathsf{Memory}
]

[
\oplus : \mathsf{Workspace} \times \mathsf{Memory}
\rightarrow
\mathsf{Workspace}
]

[
A : \mathsf{Context} \rightarrow \mathsf{Action}
]

[
G : \mathsf{OraclePacket} \rightarrow \mathsf{Rubric}
]

[
J : \mathsf{Criterion} \times \mathsf{Action}
\rightarrow
{0,1}
]

the conceptual flow is:

[
\text{past sessions}
\rightarrow
\text{memory}
\rightarrow
\text{warm context}
\rightarrow
\text{candidate action}
\rightarrow
\text{rubric score}
]

## leakage firewall

this is worth making explicit:

[
L \text{ may see } d_e
]

[
A \text{ may see } x_e^0 \text{ or } x_e^k
]

[
G \text{ may see } o_e
]

[
J \text{ may see } \mathcal R_e \text{ and } \hat a_e^z
]

but:

[
A \not\gets
{a_e,p_e,\mathrm{tail}_e,\Delta_e,\mathcal R_e}
]

and:

[
L \not\gets
{S_{r,s},p_e,\mathrm{tail}_e,\Delta_e,\mathcal R_e}
]

that is the actual methodological guardrail.

## what i would stop using

i would drop these:

[
C
]

because it ambiguously means conversation, context, criteria, candidate, etc.

[
C_f
]

because the fork is not a full conversation. it is a candidate action:

[
\hat a_e^k
]

i would also drop:

[
M_j
]

because (M) is too overloaded between message, model, and memory.

instead:

[
u_e = \text{user instruction}
]

[
a_e = \text{agent action on trial}
]

[
p_e = \text{pushback}
]

and i’d replace “environment” with:

[
w_e = \text{workspace state}
]

unless you truly mean runtime dependencies/shell/build environment. then use:

[
\rho_e = \text{runtime environment}
]

but don’t introduce (\rho_e) unless you actually need it. for this eval, you mostly need workspace state.

## final naming table

| concept                      |                     symbol | name to use         |
| ---------------------------- | -------------------------: | ------------------- |
| eval item                    |                        (e) | pushback episode    |
| repo                         |                        (r) | repository          |
| session                      |                        (s) | session             |
| turn index                   |                        (i) | turn                |
| prior transcript             |                      (h_e) | history prefix      |
| repo/file state              |                      (w_e) | workspace state     |
| user instruction being rerun |                      (u_e) | trigger instruction |
| original logged agent output |                      (a_e) | action on trial     |
| real user correction         |                      (p_e) | observed pushback   |
| prior sessions for learning  |                      (d_e) | memory corpus       |
| learned memory               |                      (k_e) | memory artifact     |
| memory insertion             |                   (\oplus) | memory overlay      |
| candidate agent output       |               (\hat a_e^z) | candidate action    |
| evaluator-only evidence      |                      (o_e) | oracle packet       |
| generated criteria           |             (\mathcal R_e) | case rubric         |
| single criterion             |                        (c) | criterion           |
| score                        | (\operatorname{score}_e^z) | episode score       |
| warm minus cold              |    (\operatorname{lift}_e) | memory lift         |

the tiny sentence version:

[
\boxed{
\text{memory works if } A(w_e \oplus k_e,h_e,u_e)
\text{ avoids the flaw that made the real user say } p_e
\text{ better than } A(w_e,h_e,u_e).
}
]

that’s the whole system, minus the fog machine.

