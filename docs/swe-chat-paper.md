
License: CC BY 4.0
arXiv:2604.20779v1 [cs.AI] 22 Apr 2026
\minted@def@optcl

envname-P envname#1
SWE-chat: Coding Agent Interactions From Real Users in the Wild
Joachim Baumann, Vishakh Padmakumar, Xiang Li, John Yang,
Diyi Yang∗ & Sanmi Koyejo
Stanford University {baumann,diyiy,sanmi}@cs.stanford.edu
[Uncaptioned image] Data    [Uncaptioned image] Website [Uncaptioned image] Code Equal advising.
Abstract

AI coding agents are being adopted at scale, yet we lack empirical evidence on how people actually use them and how much of their output is useful in practice. We present SWE-chat, the first large-scale dataset of real coding agent sessions collected from open-source developers in the wild. The dataset currently contains 6,000 sessions, comprising more than 63,000 user prompts and 355,000 agent tool calls. SWE-chat is a living dataset; our collection pipeline automatically and continually discovers and processes sessions from public repositories. Leveraging SWE-chat, we provide an initial empirical characterization of real-world coding agent usage and failure modes. We find that coding patterns are bimodal: in 41% of sessions, agents author virtually all committed code (“vibe coding”), while in 23%, humans write all code themselves. Despite rapidly improving capabilities, coding agents remain inefficient in natural settings. Just 44% of all agent-produced code survives into user commits, and agent-written code introduces more security vulnerabilities than code authored by humans. Furthermore, users push back against agent outputs—through corrections, failure reports, and interruptions—in 44% of all turns. By capturing complete interaction traces with human vs. agent code authorship attribution, SWE-chat provides an empirical foundation for moving beyond curated benchmarks towards an evidence-based understanding of how AI agents perform in real developer workflows.
Refer to caption
Figure 1: We present SWE-chat, a continually growing dataset of real human-coding agent interactions collected from public GitHub repositories. Developers opt in via installing Entire.io, an open-source tool that automatically logs coding agent sessions and links them to code commits with line-level human vs. agent attribution. As of April 2026, SWE-chat contains 2.7M logged events from 200+ repositories, including 63,000+ user prompts and 355,000+ tool calls.
1 Introduction

AI coding agents have taken the world by storm. Enhancing Large Language Models (LLMs) with a simple set of actions for interacting with a coding environment autonomously—so-called tool calls for editing files, executing terminal commands, and invoking subagents—has accelerated their ability to complete long and difficult programming tasks (Yang et al., 2024a). Lately, AI agents are reported to succeed on 50% of coding tasks that humans take 12 hours to complete (METR, 2026; Kwa et al., 2025). As a result, developers increasingly delegate coding to agents (Mürtz and Müller, 2025; Anthropic, 2026), with unprecedented impacts on the global workforce (Peng et al., 2023; Demirci et al., 2025; Massenkoff et al., 2026).

Despite massive adoption, our understanding of how humans and AI coding agents interact remains largely anecdotal. While recent work has begun evaluating code completion models in realistic settings (Chi et al., 2025), no comparable effort exists for full agentic coding sessions. No public dataset captures how developers prompt, steer, override, and ultimately commit (or discard) agent-produced code. When it comes to software engineering (SWE) tasks, most AI benchmarks consist of a fairly limited set of curated problems with well-defined, verifiable solutions (Jimenez et al., 2024; Yang et al., 2024b; Deng et al., 2026; Kottamasu et al., 2026). Even more recent benchmarks fixate on task difficulty (Merrill et al., 2026), but still neglect the human-agent interaction dimension (Wang et al., 2026b). But strong performance on curated GitHub issues with meticulous instructions does not translate to real-world, iterative usage (Pan et al., 2025; Wang et al., 2026a). There is growing recognition that the next frontier lies in evaluating agents on the collaborative workflows that characterize actual development (Patwardhan et al., 2025; Cursor Research Team, 2026; Anthropic, 2025; 2026). Understanding how developers use coding agents in practice is a prerequisite for building genuinely helpful agents. Collecting real usage data in the wild is the only way to close this gap:

    RQ1

    How do users interact with coding agents in real-world coding tasks?

Coding agents are increasingly deployed as autonomous problem solvers, even though we have no empirical evidence on how much of their output developers actually use, how often they fail, or how users cope when they do.

    RQ2

    How do coding agents fail in practice, and how do users respond?

Refer to caption
Figure 2: Usage patterns and failure modes in SWE-chat. Using the SWE-chat dataset, we analyze how people use coding agents in the wild (left) and when and how they fail (right). Text colorings correspond to figure components. Results reflect the SWE-chat population of open-source developers using public repositories and opting into session logging.
1.1 Our contributions

We present SWE-chat, the first large-scale dataset of real coding agent sessions from actual users on real repositories (Figure 1). SWE-chat includes complete interaction traces between humans and AI coding agents, with full tool-call trajectories and code diffs with human vs. agent authorship attribution (Table 1). This enables researchers to study not just what code agents produce, but how users prompt, steer, and override them. We describe the data collection pipeline and aggregate statistics in Section 2.

Using SWE-chat, we contribute an initial sweep of empirical insights from real-world coding agent usage, summarized in Figure 2. Our analysis of interaction behavior in Section 3 (addressing RQ1) reveals that humans rely on coding agents for a broad range of tasks beyond writing patches to fix bugs or implement features: Understanding existing code is the most common user intent, and agents spend a third of their tool calls executing bash commands rather than editing files (Figures 19a and 19b). This suggests that benchmarks focused narrowly on patch generation underestimate the operational diversity and complexity of real agent workflows. Users’ coding mode is extremely bimodal: in most sessions, the AI agent either writes none or all of the code (Figure 5). But despite the emerging trend toward vibe coding (Figure 25), fully autonomous one-shot problem-solving remains far from reality. In fact, interactions typically span multiple turns, and users are often very nitpicky about what they want an agent to do and how they want it done (Figures 4 and 24).

Our analysis of failure modes and user responses in Section 4 (addressing RQ2) reveals lots of room for improvement. We identify sessions with a low success rating, revealing cases where agents fail to complete the user requests appropriately (Figure 6). In addition to that, we find that less than half of all agent-produced code survives into user commits (Table 3). Vibe coding is particularly inefficient, consuming roughly 3× more tokens and dollars per committed line than collaborative coding (Figures 7 and 29). Vibe-coded code is also substantially less safe. It introduces roughly 9× more security vulnerabilities per committed line than code that humans write themselves and about 5× more than code they co-author with the agent (Table 4). Agents are working autonomously for longer—the 99.9th-percentile turn duration now exceeds 100 minutes—yet they rarely stop to ask users for clarification (Figure 30). Users compensate by interrupting agents in 5% of turns and by pushing back against agent outputs in 39% of turns, often providing corrections and failure reports (Figure 8).

In Section 5.1, we outline a roadmap of how SWE-chat can help close some of these gaps—be it through realistic benchmarks, better interaction designs, or open-source user simulators evaluated on real session data.
Table 1: Comparison of SWE-chat with existing AI agent datasets. SWE-chat is the first dataset combining real user interactions with coding agent trajectories and rich contextual information, including detailed code authorship attribution.
Dataset 	Human prompts 	Agent tool-use trajectories 	Code diffs 	Code attribution
SWE-smith-trajectories (Yang et al., 2025) 	✗ 	✓ 	✓ 	✗
CoderForge-Preview (Ariyak et al., 2026) 	✗ 	✓ 	✓ 	✗
SERA (Shen et al., 2026) 	✗ 	✓ 	✓ 	✗
nex-agi-agent-sft (Cai et al., 2025) 	✗ 	✓ 	✓ 	✗
SWE-rebench-openhands-trajectories (Trofimova et al., 2025) 	✗ 	✓ 	✓ 	✗
Agent Trajectories (Bouzenia and Pradel, 2025) 	✗ 	✓ 	✓ 	✗
Multi-SWE-bench_trajs (Zan et al., 2025) 	✗ 	✓ 	✓ 	✗
Agent Data Protocol (Song et al., 2025) 	✗ 	✓ 	✓ 	✗
AIDev (Li et al., 2025) 	✗ 	✗ 	✓ 	✗
AgentPack (Zi et al., 2025) 	✗ 	✗ 	✓ 	✗
SWE-chat (ours) 	✓ 	✓ 	✓ 	✓
2 SWE-chat
2.1 Data collection

We build the dataset from public GitHub repositories whose developers have opted into Entire.io’s CLI checkpoint logging, which records coding agent session transcripts on a dedicated branch. Each checkpoint is linked to a commit with line-level code authorship attribution. When enabled by the developer, Entire automatically records session transcripts for various coding agents (Claude Code, OpenCode, Gemini CLI, Cursor, and Factory AI Droid). These session logs capture user prompts, agent responses, tool calls (file edits, shell commands, code searches, etc.), and token usage. We provide more details on the data collection pipeline and its rapid growth trajectory in Appendix C.1.
[Uncaptioned image]
Figure 3: Structure of a coding agent session in SWE-chat. Each session consists of alternating user prompts and agent responses with tool calls (file reads, edits, shell commands) and text output.

The resulting SWE-chat dataset provides a comprehensive look into real-world human-agent collaboration, comprising almost 6,000 coding sessions across more than 200 repositories (Figure 1). At the time of writing, the data includes more than 13,000 checkpoints, 63,000 user prompts, and 355,000 agent tool calls. The full dataset contains 2.7 million logged events—these also include streamed progress events, return values from tool calls, and a small set of reasoning traces from 200 sessions with extended thinking. This trend is clearly visible in the steep trajectory shown in Figure 1. We plan to update our Website and Data frequently as we continue to collect new data. An example SWE-chat session is shown in Figure 3 to illustrate the session structure. Because SWE-chat captures only developers who actively opt into Entire’s public checkpoint logging, the dataset reflects an early-adopter population and may not generalize to all coding agent users; we discuss this and other limitations in Appendix A.
2.2 Data statistics
Refer to caption
Figure 4: SWE-chat user-agent interaction statistics. (a) Distribution of turns per session. (b) Distribution of agent tool calls per turn. (c) Top 15 file types touched by agent tool calls.

SWE-chat consists of multi-turn coding agent sessions, collected from hundreds of real users in the wild (Figure 4)1, interacting with five widely used coding agents.2 Agents often make multiple tool calls for any user request (Figure 4b) and interact with a wide variety of programming languages, as reflected by the file types touched during sessions (Figure 4c). We present more detailed dataset statistics in Appendix D.1 and explore task topic distributions in Appendix D.2.
2.3 Data analysis methodology

The true value of SWE-chat lies in unlocking an understanding of complex human-agent behaviors at scale, going beyond aggregate statistics to characterize how developers interact with coding agents in the long tail and why sessions succeed or fail. To facilitate this, we enrich the dataset with annotations that provide signal for both researchers studying human-AI collaboration (RQ1) and model developers seeking to build more helpful agents (RQ2). We classify sessions and user prompts using the annotation rubrics listed in Table 2, each designed to capture a specific dimension of real-world agent usage.

We developed clear annotation codebooks for each task and evaluated inter-annotator agreement, which was moderate to high across all tasks (see Appendix E for details). We rely on LLM judges to annotate the full dataset. It is important to note that LLMs can make mistakes and are thus not reliable data annotators (Baumann et al., 2025). However, we chose this approach for its scalability, enabling continuous annotation as new data is collected. For each task, we evaluated the zero-shot performance of various open-weight and proprietary LLMs using multiple prompt paraphrases against human expert gold labels, and then annotated the full dataset with the best-performing model and prompt. We describe the full LLM-as-a-judge validation approach in Appendix E.1.

Additionally, we leverage rich information from raw session logs and code attribution data, which capture all agent events—what tools they call, how much code they produce, and how long they take. To quantify how efficiently they do it, we define a suite of metrics (detailed in Appendix C.2) that quantify the fraction of agent-produced code that survives into user commits (code survival rate), the overhead of agent self-rewrites (coding efficiency), and the tokens, cost, time, and user effort required per committed line of code. To assess code safety, we additionally run the static-analysis tool Semgrep3 on the pre- and post-commit snapshots of each committed change and count the security findings introduced by the commit. This lets us compare the rate of introduced vulnerabilities per committed line across coding modes (see Section 4.3 and details in Appendix D.5). These metrics allow us to answer RQ2 by revealing where agents waste effort and where their output falls short of what developers actually commit.
Table 2: Annotations applied to the SWE-chat dataset. We show different examples in Appendix B. See Appendix E for implementation details and LLM annotator validations.

Level Task Description Classification input Why this matters Session Session success Rates each session’s overall success on a 0–100 scale. Full conversation with a summary of all tool calls. Enables identification of failure patterns, helpful as a training signal for reward modeling. User persona Assigns each session one of four behavioral personas (expert nitpicker, vague requester, mind changer, or other). Chronological summary of session events with descriptions (conversations & tool calls). Characterizes how developers interact with agents, which could inform the design of more adaptive agent interfaces. User prompt Prompt intent Labels prompts with primary user intent: create new code, refactor, debug, understand, connect, git, test, or other. Raw prompt text without context. Reveals operational diversity of real workflows. User pushback Classifies non-interruption prompts into pushback categories: correction, rejection, failure report, or non-pushback. Full conversation transcript preceding the prompt. Directly measures friction points that degrade the user experience, signaling where agents fall short.
3 How do humans interact with coding agents in the wild? (RQ1)
3.1 Task types: agents assist with a broad range of tasks beyond writing code
User requests are diverse

Figure 19a illustrates the distribution of user intents. While a large portion of prompts (26.6%) falls into a broad “other” category, the most common specific request is to understand existing code or behavior, accounting for 19.0% of all prompts. Creating new code is another frequent intent at 13.4%. Routine development, such as git operations (13.4%) and debugging (13.0%), is also prevalent, while code refactoring, writing tests, and setting up connections occur less frequently.

Coding agents must be optimized not only for code generation, but for code comprehension and routine development tasks. These capabilities are underrepresented in existing benchmarks, which focus narrowly on patch generation.
Agents invoke many tools within a single turn

One third of all agent tool calls are bash commands—predominantly git operations—followed by file reads, edits, and grep searches (see Figure 19b and Table 5). Agent trajectories typically begin with reading and searching tools before transitioning to file modifications and build commands (Figure 21(a)).
3.2 Coding modes: vibe coding is increasingly common

55.8% of all committed lines of code are written by coding agents, but this distribution is extremely bimodal—see Figure 5. We therefore introduce three different coding modes:

    •

    Human-only coding (22.7% of sessions): All committed code is written by the human. The agent serves as an assistant for code comprehension, debugging, or git operations.
    •

    Collaborative coding (36.5% of sessions): Human and agent jointly contribute to committed code, with the agent authoring >0% but <99% of lines.
    •

    Vibe coding (40.8% of sessions): More than 99% of the committed code is authored by the agent.

Vibe coding is becoming more prevalent: over our three-month observation window, its share has doubled from 20% to over 40% of sessions (Figure 25).
Refer to caption
Figure 5: Vibe coding in the wild. % of agent-authored code, structured into three coding modes: human-only (0% agent-authored code), collaborative (0–99%), and vibe coding (≥99%).
3.3 User types: expert nitpicking behavior dominates

To characterize how users interact with agents beyond single prompts, we classify each session into a behavioral persona based on the full transcript (Table 2): expert nitpickers who meticulously correct agent output while maintaining a stable goal, vague requesters who underspecify tasks and delegate decisions to the agent, and mind changers who redirect goals mid-session. Most users act as expert nitpickers (Figure 24). This holds even in vibe coding sessions (47%). Mind changing is less common during vibe coding (5% vs. 10% in other modes). This stands in contrast to current benchmarks, which provide complete instructions up front. In reality, users iteratively refine their instructions after seeing the agent’s outputs.
4 How do coding agents fail and how do users respond? (RQ2)
4.1 Most coding agent sessions successfully complete user requests
Refer to caption
Figure 6: Distribution of LLM-annotated session success rating. The distribution is left-skewed, indicating that most sessions are rated as largely successful.

Figure 6 shows that 90% of sessions receive success ratings of 50+, indicating that coding agents generally fulfill users’ requests. Human-only sessions have a slightly lower average session success rating than collaborative and vibe coding sessions.

The tail of the distribution with low success ratings is more interesting, which is why we manually inspected the 50 sessions with the lowest success ratings (2–15). The most common failure modes in these sessions are user interruptions that end the session before the agent can deliver meaningful output, and agents producing work or commits that are entirely unrelated to the user’s actual request. We provide one such example in Figure B.1.
4.2 Coding agents are inefficient
Users discard most AI-written code

Less than half (44.3%) of all agent-produced code survives into user commits (Table 3). During vibe coding sessions, users are more accepting, committing 59% of AI-authored lines of code on average. However, this higher survival rate is difficult to interpret causally: it may reflect genuinely better-targeted agent output, or it may reflect lower user scrutiny.

The main source of inefficiency is agent-authored code that the human decides not to commit (see human deletions in Table 3). If the user directly changes the code themselves, it is captured under human overwrites. Note that agents’ self-overwrites typically occur when the user pushes back and instructs the agent to reimplement something before committing.
Coding mode 	Coding 	Code survival 	Detailed attribution breakdown
efficiency 	rate
All modes 	44.3% 	50.3% 	44.3%9.3%42.2%
Collaborative 	38.2% 	44.1% 	38.2%10.1%46.9%
Vibe coding 	59.0% 	64.6% 	59.0%7.1%30.9%

Survived   Agent self-overwrite   Human overwrite   Human deletion
Table 3: Agent coding efficiency, code survival rate, and detailed attribution of agent-produced code by coding mode, excluding human-only. Coding efficiency measures what fraction of total agent effort ended up in the commit; survival rate measures what fraction of the agent’s net output the human kept (i.e., it does not penalize agent self-overwrites).
Vibe coding is costly and slow

While more of the agent’s output survives into commits in vibe-coding mode, this comes at a substantially higher cost per committed line. Vibe-coded sessions consume a median of 204K tokens per 100 committed lines of code—roughly 3× more than collaborative sessions and 2× more than human-only sessions. Translated to dollar costs, vibe coding has a median cost of $0.13 per 100 committed lines, compared to $0.07 for human-only and $0.05 for collaborative sessions. Furthermore, users invest more effort in prompting when vibe coding (Figures 7 and 29).
Refer to caption
Figure 7: Cost efficiency per 100 committed lines of code. μ indicates means.

In terms of time, collaborative sessions are the most efficient at a median of 4.8 minutes per 100 committed lines, while vibe coding (12.6 minutes) and human-only sessions (8.6 minutes) are slower in comparison. The agent runtime metric, which excludes time spent waiting for user input, closely tracks session runtime across all modes. However, it is important to note that both time and agent runtime are imperfect proxies, as they do not account for the user’s time spent coding before or after a coding session.
4.3 Vibe coding introduces more security vulnerabilities per line

Table 4 reports the rate at which each coding mode introduces security vulnerabiliti[<35;95;11Mes. For every commit we run the static analyzer Semgrep on the pre- and post-commit repository snapshots and count findings that appear in post but not in pre, restricted to files the commit modified (details in Appendix D.5). Vibe-coded commits introduce vulnerabilities at a rate of 0.76 per 1,000 committed lines, roughly 9× higher than human-only (0.08) and 5× higher than collaborative (0.14) commits. Vibe-coded commits also fix vulnerabilities at a higher rate (0.52 per 1K lines vs. 0.04 for human-only and 0.08 for collaborative), reflecting more security-relevant code-changes overall. But there are more introductions than fixes in every mode, and the difference is biggest for vibe coding.
Table 4: Security-relevant findings per coding mode. Introduced counts Semgrep findings present after a commit but not before; Fixed counts findings present before but not after. Rates are per 1,000 added lines. Vibe-coded commits introduce vulnerabilities at roughly 9× the human-only rate and 5× the collaborative rate, but also fix more vulnerabilities.
	Vulnerabilities fixed 	Vulnerabilities introduced
Coding mode 	(per 1K lines) 	(per 1K lines)
Human-only 	0.04 	0.08
Collaborative 	0.08 	0.14
Vibe coding 	0.52 	0.76
Overall 	0.06 	0.11

We observe a range of vulnerability types, including path traversal, command injection, unsafe format strings, and SQL injection (see Appendix Figures 26 and 27). If vibe coding continues to grow as a share of real-world development (Figure 25), the absolute volume of newly introduced se[<35;96;11Mcurity issues might increase, making production code less safe.
4.4 Agents work autonomously for longer, but users push back frequently

We now turn to session stops initiated by either the agent or the user. For comparability with McCain et al. (2026), we only include data from Claude Code for the results in Figure 8.
Agents work autonomously for longer

Most Claude Code interactions are short. The median turn lasts under one minute, and even the 90th percentile stays below seven minutes (Figure 30). This is broadly consistent with the trends reported by McCain et al. (2026). While the 99.9th percentile turn duration remains well below the 12-hour human-equivalent task difficulty that METR estimates Claude Code can solve at a 50% success rate (Kwa et al., 2[<35;97;11M025), we observe a clear upward trend over the data-collection period.
Humans frequently interrupt the agent and push back

Figure 8 breaks down agent-initiated stops, user interruptions, and user pushback by coding mode. Across all modes, Claude Code rarely proactively asks the user for clarification (1.1%–2.6%). The higher agent autonomy of vibe coding sessions is reflected in fewer agent questions. Surprisingly, the share of agent stops is much lower than what McCain et al. (2026) report.

In contrast, users interrupt the agent more frequently (3.3%–6.0%). This effect is stable over time (see Figure 31) and across coding modes (Figure 8). When users interrupt an ongoing trajectory, the interruption most frequently occurs when the agent exits the plan mode[<35;98;12M, makes a git operation, or edits a file (Figure 21(c)).

Even more common than hard user interruptions are soft user pushbacks in the form of correction prompts after an agent’s turn has finished. Overall, users push back after 39% of turns, regardless of coding mode. The observation that vibe coding sessions still exhibit substantial pushback rates suggests that users are not entirely passive, even when fully relying on the AI agent for code writing.
Refer to caption
Figure 8: Turn-level oversight in Claude Code sessions. Fraction of turns in which the agent stops to ask for clarification, the user interrupts the agent, or the user pushes back against the agent’s response—broken down by coding mode.
5 Discussion

Together, our findings suggest that coding [<35;99;12M[<35;100;12Magents, despite their enormous potential, have substantial room for improvement in efficiency and human-agent collaboration. Our analysis of SWE-chat offers an empirical grounding for this understanding: we surface interaction patterns, efficiency gaps, and failure modes that are invisible in controlled evaluations. These findings are not meant to be definitive. Rather, they are a starting point for a broader research agenda around in-the-wild agent evaluation and human-agent interaction studies.
Autonomy is outpacing oversight

Vibe coding is becoming the new norm. In more than 40% of cases, agents author more than 99% of committed code (Figure 5). At the same time, agents like Claude Code stop to ask users a clarifying question in only 1.4% of turns. Users[<35;101;12M, on the other hand, interrupt and push back frequently, in roughly 44% of turns (Figure 8). This asymmetry suggests that agents may be gaining autonomy faster than they are learning when to seek guidance, leaving users to compensate through manual oversight.
Agents are powerful but brittle

Agents are working independently for longer and writing more code (Figure 30), but more autonomy does not translate into more efficient delivery. Agents author more than half of all committed code, yet less than half of their total output survives into commits (Table 3). Agents rarely signal uncertainty, and errors are typically caught only when users actively inspect outputs (Section E.2.4). This is consistent with the broader observation that AI models often fail silen[<35;102;12Mtly (Potts and Sudhof, 2026). Notably, collaborative sessions where humans and agents co-author code are the most cost-efficient mode we observe (Figure 29), suggesting that the current push toward full autonomy may be counterproductive. Importantly, these findings do not argue against the use of coding agents. Rather, they reveal that agents are less efficient than they could be.
Agent-written code introduces more security vulnerabilities

Prior work has shown that LLMs can produce insecure code even from benign prompts (Pearce et al., 2025; Bhatt et al., 2023; Fu et al., 2025). Developers using AI assistants are more likely to produce insecure code while feeling more confident about its security (Perry et al., 2023). SWE-chat extends this to real developer[<35;103;12M workflows with coding agents: vibe-coded commits introduce Semgrep-detected vulnerabilities at roughly 9× the human-only rate and 5× the collaborative rate (Table 4). Combined with our finding that agents rarely signal uncertainty (Figure 8), this suggests that as autonomy grows, the burden of catching unsafe patterns shifts entirely to the user. Existing mitigations, such as secure fine-tuning and system-prompt hardening (He and Vechev, 2023; He et al., 2024; Xu et al., 2025), have largely been evaluated on synthetic benchmarks. SWE-chat provides a natural testbed for whether such interventions are effective for realistic coding agent tasks.
5.1 Outlook: implications for building better coding agents
Realistic benchmarks grounded in real workflows

Current benchmarks evaluate agents on isolated, curated tasks that reward one-shot patch generation. But the most common real-world intent we observe is understanding existing code, not writing it, and most sessions involve iterative multi-turn interaction rather than single-shot problem solving. SWE-chat enables the construction of benchmarks grounded in actual developer workflows (Zhou et al., 2026). For example, session trajectories can be used to evaluate whether an agent proposes appropriate next actions given real conversation context.
Designing more adaptive human-agent interaction

Users push back against agent output in nearly every other turn, yet they rarely abandon sessions entirely. They correct, redirect, and steer agents iteratively until the result is acceptable. At the same time, agents proactively ask for clarification in <2% of turns. SWE-chat captures these correction-response cycles at scale, providing researchers with the data needed to study how human oversight actually unfolds in practice and where current agent interaction design falls short (Guan et al., 2025).
User simulators for offline evaluation

Evaluating coding agents currently requires either curated benchmarks or live user studies, both of which are expensive and limited in scope (Naous et al., 2025; Buening et al., 2026). SWE-chat provides the raw material for a new evaluation paradigm: training user simulators on real interaction trajectories. The dataset captures a wide range of the diverse behavioral patterns that a realistic simulator would need to reproduce.

Benchmarks are fixed at the moment of their creation, but how developers use coding agents is changing rapidly. SWE-chat is designed as a living dataset that evolves with the technology it measures. By providing continual updates, it enables longitudinal analysis and ensures our understanding of agents remains grounded in how they are actually used.
Ethics statement

All data in SWE-chat is collected from public GitHub repositories where developers have explicitly opted in to Entire CLI tracking and pushed session logs to public branches. We only include repositories whose licenses allow redistribution. We do not collect images attached to user prompts. Before release, we remove personally identifiable information (PII) from [<35;102;12Mevery user prompt and assistant response in the dataset, following the WildChat data processing pipeline (Zhao et al., 2024). First, we run Microsoft Presidio’s named-entity recognizer with a SpaCy transformer model over every user/assistant turn to redact PII (e.g., email addresses, phone numbers, person names). Second, we remove credentials (API keys, OAuth tokens, database URIs, etc.) with TruffleHog. The study procedure was reviewed and deemed exempt by the Stanford Institutional Review Board (IRB).
Acknowledgments

We are thankful to the members of SALT Lab, the STAIR Lab, the Stanford NLP Group, and the MilaNLP Lab for their helpful feedback, particularly Chenglei Si, David Anugraha, Hao Zhu, Ricardo Dominguez-Olmedo, and Steven Dillmann. This work is [<35;100;11Mpartially supported by Open Philanthropy, ONR N000142412532, Schmidt Sciences, NSF 2046795 and 2205329, IES R305C240046, the MacArthur Foundation, Stanford HAI, and the Swiss National Science Foundation (SNSF grant 235328).
References

    Anthropic (2025) How anthropic teams use claude code. Note: https://claude.com/blog/how-anthropic-teams-use-claude-codeCompanion technical report available at https://www-cdn.anthropic.com/58284b19e702b49db9302d5b6f135ad8871e7658.pdf. Accessed: 2026-03-31 Cited by: §1.
    Anthropic (2026) 2026 agentic coding trends report: how coding agents are reshaping software development. Note: https://resources.anthropic.com/hubfs/2026%20Agentic%20Coding%20Trends%20Report.pdf Cited by: §C.1, §1, §1.
    A. Ariyak, J. Zhang, J. Wang, [<35;97;11M[<35;96;11MS. Zhu, F. Bianchi, S. Srivastava, A. Panda, S. Bharti, C. Xu, J. Heo, X. S. Wu, J. Zhou, P. Liang, L. Song, C. Zhang, B. Athiwaratkun, Z. Zhou, and Q. Wu (2026) CoderForge-preview: sota open dataset for training efficient agents. TogetherAI Blog. Note: Project core leads: Alpay Ariyak; Zhongzhu Zhou; Qingyang Wu External Links: Link Cited by: Table 1.
    J. Baumann, P. Röttger, A. Urman, A. Wendsjö, F. M. Plaza-del-Arco, J. B. Gruber, and D. Hovy (2025) Large language model hacking: quantifying the hidden risks of using llms for text annotation. arXiv preprint arXiv:2509.08825. Cited by: Appendix A, §2.3.
    J. Becker, N. Rush, E. Barnes, and D. Rein (2025) Measuring the impact of early-2025 ai on experienced open-source developer productivity. arXiv prep[<35;95;10Mrint arXiv:2507.09089. Cited by: §C.1, Appendix E.
    M. Bhatt, S. Chennabasappa, C. Nikolaidis, S. Wan, I. Evtimov, D. Gabi, D. Song, F. Ahmad, C. Aschermann, L. Fontana, et al. (2023) Purple llama cyberseceval: a secure coding benchmark for language models. arXiv preprint arXiv:2312.04724. Cited by: §5.
    I. Bouzenia and M. Pradel (2025) Understanding software engineering agents: a study of thought-action-result trajectories. arXiv preprint arXiv:2506.18824. Cited by: Table 1.
    T. K. Buening, J. Hübotter, B. Pásztor, I. Shenfeld, G. Ramponi, and A. Krause (2026) Aligning language models from user interactions. arXiv preprint arXiv:2603.12273. Cited by: §5.1.
    Y. Cai, L. Chen, Q. Chen, Y. Ding, L. Fan, W. Fu, Y. Gao, H. Guo, P. Guo, Z. Han, et al. [<35;94;10M(2025) Nex-n1: agentic models trained via a unified ecosystem for large-scale environment construction. arXiv preprint arXiv:2512.04987. Cited by: Table 1.
    R. J. Campello, D. Moulavi, and J. Sander (2013) Density-based clustering based on hierarchical density estimates. In Pacific-Asia conference on knowledge discovery and data mining, pp. 160–172. Cited by: §D.2.1.
    W. Chi, V. Chen, A. N. Angelopoulos, W. Chiang, A. Mittal, N. Jain, T. Zhang, I. Stoica, C. Donahue, and A. Talwalkar (2025) Copilot arena: a platform for code llm evaluation in the wild. arXiv preprint arXiv:2502.09328. Cited by: §1.
    J. Cohen (1960) A coefficient of agreement for nominal scales. Educational and Psychological Measurement 20 (1), pp. 37–46. External Links: Document, Li[<35;92;10Mnk, https://doi.org/10.1177/001316446002000104 Cited by: §E.1.
    Cursor Research Team (2026) Composer 2 Technical Report. External Links: Link Cited by: §1.
    O. Demirci, J. Hannane, and X. Zhu (2025) Who is ai replacing? the impact of generative ai on online freelancing platforms. Management Science 71 (10), pp. 8097–8108. External Links: Document, Link, https://doi.org/10.1287/mnsc.2024.05420 Cited by: §1.
    X. Deng, J. Da, E. Pan, Y. Y. He, C. Ide, K. Garg, N. Lauffer, A. Park, C. Rane, K. Sampath, M. Krishnan, S. R. Kundurthy, S. M. Hendryx, Z. Wang, C. B. C. Zhang, N. Jacobson, B. Liu, and B. Kenstler (2026) SWE-bench pro: can AI agents solve long-horizon software engineering tasks?. External Links: Link Cited by: §1.
    Y. Fu, P. Liang, A. Tahir, Z. Li, M. Shahin, J. Yu, and J. Chen (2025) Security weaknesses of copilot-generated code in github projects: an empirical study. ACM Trans. Softw. Eng. Methodol. 34 (8). External Links: ISSN 1049-331X, Link, Document Cited by: §5.
    M. Y. Guan, M. Wang, M. Carroll, Z. Dou, A. Y. Wei, M. Williams, B. Arnav, J. Huizinga, I. Kivlichan, M. Glaese, et al. (2025) Monitoring monitorability. arXiv preprint arXiv:2512.18311. Cited by: §5.1.
    J. He and M. Vechev (2023) Large language models for code: security hardening and adversarial testing. In Proceedings of the 2023 ACM SIGSAC Conference on Computer and Communications Security, CCS ’23, New York, NY, USA, pp. 1865–1879. External Links: ISBN 9798400700507, Link, Document Cited by: §5.
    J. He, M. Vero, G.[<35;93;10M Krasnopolska, and M. Vechev (2024) Instruction tuning for secure code generation. In Proceedings of the 41st International Conference on Machine Learning, ICML’24. Cited by: §5.
    C. E. Jimenez, J. Yang, A. Wettig, S. Yao, K. Pei, O. Press, and K. R. Narasimhan (2024) SWE-bench: can language models resolve real-world github issues?. In The Twelfth International Conference on Learning Representations, External Links: Link Cited by: §1.
    A. Kottamasu, A. Datta, A. Barthwal, C. Mahapatra, A. Arun, A. Hiremath, B. Foody, and B. Vidgen (2026) APEX-swe. arXiv preprint arXiv:2601.08806. Cited by: §1.
    T. Kwa, B. West, J. Becker, A. Deng, K. Garcia, M. Hasin, S. Jawhar, M. Kinniment, N. Rush, S. Von Arx, et al. (2025) Measuring ai ability to complete long t[<35;97;10M[<35;99;10Masks. arXiv preprint arXiv:2503.14499. Cited by: §1, §4.4.
    H. Li, H. Zhang, and A. E. Hassan (2025) The rise of ai teammates in software engineering (se) 3.0: how autonomous coding agents are reshaping software engineering. External Links: 2507.15003, Link Cited by: Table 1.
    R. A. Martin and S. Barnum (2008) Common weakness enumeration (cwe) status update. Ada Lett. XXVIII (1), pp. 88–91. External Links: ISSN 1094-3641, Link, Document Cited by: §D.5.
    M. Massenkoff, E. Lyubich, P. McCrory, R. Appel, and R. Heller (2026) External Links: Link Cited by: §1.
    M. McCain, T. Millar, S. Huang, J. Eaton, K. Handa, M. Stern, A. Tamkin, M. Kearney, E. Durmus, J. Shen, J. Hong, B. Calvert, J. S. Chan, F. Mosconi, D. Saunders, T. Neylon, G. Nicholas, S. Po[<35;104;10Mllack, J. Clark, and D. Ganguli (2026) Measuring ai agent autonomy in practice. External Links: Link Cited by: §4.4, §4.4, §4.4.
    K. O. McGraw and S. P. Wong (1996) Forming inferences about some intraclass correlation coefficients.. Psychological methods 1 (1), pp. 30–46. External Links: Document Cited by: §E.1.
    L. McInnes, J. Healy, S. Astels, et al. (2017) Hdbscan: hierarchical density based clustering.. J. Open Source Softw. 2 (11), pp. 205. Cited by: §D.2.1.
    M. A. Merrill, A. G. Shaw, N. Carlini, B. Li, H. Raj, I. Bercovich, L. Shi, J. Y. Shin, T. Walshe, E. K. Buchanan, et al. (2026) Terminal-bench: benchmarking agents on hard, realistic tasks in command line interfaces. arXiv preprint arXiv:2601.11868. Cited by: §1.
    METR (2026) Time hori[<35;105;10Mzon 1.1. Note: https://metr.org/blog/2026-1-29-time-horizon-1-1/ Cited by: §1.
    C. Mürtz and M. N. Müller (2025) Agents in the wild - dashboard. Note: Interactive web dashboard. Code available at https://github.com/logic-star-ai/insightshttps://insights.logicstar.ai External Links: Document, Link Cited by: §1.
    T. Naous, P. Laban, W. Xu, and J. Neville (2025) Flipping the dialogue: training and evaluating user language models. arXiv preprint arXiv:2510.06552. Cited by: §5.1.
    J. Pan, R. Shar, J. Pfau, A. Talwalkar, H. He, and V. Chen (2025) When benchmarks talk: re-evaluating code LLMs with interactive feedback. In Findings of the Association for Computational Linguistics: ACL 2025, W. Che, J. Nabende, E. Shutova, and M. T. Pilehvar (Eds.), Vienna, [<35;107;10M[<35;108;10MAustria, pp. 24672–24700. External Links: Link, Document, ISBN 979-8-89176-256-5 Cited by: §1.
    T. Patwardhan, R. Dias, E. Proehl, G. Kim, M. Wang, O. Watkins, S. P. Fishman, M. Aljubeh, P. Thacker, L. Fauconnet, et al. (2025) Gdpval: evaluating ai model performance on real-world economically valuable tasks. arXiv preprint arXiv:2510.04374. Cited by: §1.
    H. Pearce, B. Ahmad, B. Tan, B. Dolan-Gavitt, and R. Karri (2025) Asleep at the keyboard? assessing the security of github copilot’s code contributions. Commun. ACM 68 (2), pp. 96–105. External Links: ISSN 0001-0782, Link, Document Cited by: §5.
    S. Peng, E. Kalliamvakou, P. Cihon, and M. Demirer (2023) The impact of ai on developer productivity: evidence from github copilot. arXiv preprint arXiv:2[<35;110;10M302.06590. Cited by: §1.
    N. Perry, M. Srivastava, D. Kumar, and D. Boneh (2023) Do users write more insecure code with ai assistants?. In Proceedings of the 2023 ACM SIGSAC Conference on Computer and Communications Security, CCS ’23, New York, NY, USA, pp. 2785–2799. External Links: ISBN 9798400700507, Link, Document Cited by: §5.
    C. Potts and M. Sudhof (2026) Invisible failures in human-ai interactions. arXiv preprint arXiv:2603.15423. Cited by: §5.
    N. Reimers and I. Gurevych (2019) Sentence-BERT: sentence embeddings using Siamese BERT-networks. In Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing and the 9th International Joint Conference on Natural Language Processing (EMNLP-IJCNLP), K. Inui, J. Jiang, V. N[<35;111;10Mg, and X. Wan (Eds.), Hong Kong, China, pp. 3982–3992. External Links: Link, Document Cited by: §D.2.1.
    S. K. Sarkar (2025) Ai agents, productivity, and higher-order thinking: early evidence from software development. Available at SSRN 5713646. Cited by: §C.1.
    E. Shen, D. Tormoen, S. Shah, A. Farhadi, and T. Dettmers (2026) SERA: soft-verified efficient repository agents. arXiv preprint arXiv:2601.20789. Cited by: Table 1.
    P. E. Shrout and J. L. Fleiss (1979) Intraclass correlations: uses in assessing rater reliability.. Psychological bulletin 86 (2), pp. 420–428. External Links: Document Cited by: §E.1.
    Y. Song, K. Ramaneti, Z. Sheikh, Z. Chen, B. Gou, T. Xie, Y. Xu, D. Zhang, A. Gandhi, F. Yang, et al. (2025) Agent data protocol: unifying d[<35;112;10Matasets for diverse, effective fine-tuning of llm agents. arXiv preprint arXiv:2510.24702. Cited by: Table 1.
    C. Spearman (1961) The proof and measurement of association between two things.. pp. 45–58. Cited by: §E.1.
    M. Trofimova, A. Shevtsov, B. Ibragim, K. Pyaev, S. Karasik, and A. Golubev (2025) OpenHands trajectories with qwen3-coder-480b-a35b-instruct. Nebius blog. Note: Cited by: Table 1.
    Z. Z. Wang, S. Vijayvargiya, A. Chen, H. Zhang, V. A. Arangarajan, J. Chen, V. Chen, D. Yang, D. Fried, and G. Neubig (2026a) How well does agent development reflect real-world work?. arXiv preprint arXiv:2603.01203. Cited by: §1.
    Z. Z. Wang, J. Yang, K. Lieret, A. Tartaglini, V. Chen, Y. Wei, Z. W. L. Zhang, K. Narasimhan, L. Schmidt, G. Neubig, D. F[<35;110;10Mried, and D. Yang (2026b) Position: humans are missing from ai coding agent research. https://zorazrw.github.io/files/position-haicode.pdf. Cited by: Appendix E, §1.
    X. Xu, Z. Su, J. Guo, K. Zhang, Z. Wang, and X. Zhang (2025) ProSec: fortifying code LLMs with proactive security alignment. In Forty-second International Conference on Machine Learning, External Links: Link Cited by: §5.
    J. Yang, C. E. Jimenez, A. Wettig, K. Lieret, S. Yao, K. Narasimhan, and O. Press (2024a) SWE-agent: agent-computer interfaces enable automated software engineering. External Links: 2405.15793, Link Cited by: §1.
    J. Yang, C. E. Jimenez, A. L. Zhang, K. Lieret, J. Yang, X. Wu, O. Press, N. Muennighoff, G. Synnaeve, K. R. Narasimhan, D. Yang, S. I. Wang, and O. Press [<35;107;10M(2024b) SWE-bench multimodal: do ai systems generalize to visual software domains?. External Links: 2410.03859, Link Cited by: §1.
    J. Yang, K. Lieret, C. E. Jimenez, A. Wettig, K. Khandpur, Y. Zhang, B. Hui, O. Press, L. Schmidt, and D. Yang (2025) SWE-smith: scaling data for software engineering agents. In The Thirty-ninth Annual Conference on Neural Information Processing Systems Datasets and Benchmarks Track, External Links: Link Cited by: Table 1.
    D. Zan, Z. Huang, W. Liu, H. Chen, L. Zhang, S. Xin, L. Chen, Q. Liu, X. Zhong, A. Li, S. Liu, Y. Xiao, L. Chen, Y. Zhang, J. Su, T. Liu, R. Long, K. Shen, and L. Xiang (2025) Multi-swe-bench: a multilingual benchmark for issue resolving. External Links: 2504.02605, Link Cited by: Table 1.
    W. Zhao, [<35;105;10MX. Ren, J. Hessel, C. Cardie, Y. Choi, and Y. Deng (2024) WildChat: 1m chatGPT interaction logs in the wild. In The Twelfth International Conference on Learning Representations, External Links: Link Cited by: Ethics statement.
    X. Zhou, W. Sun, Q. Ma, Y. Xie, J. Liu, W. Du, S. Welleck, Y. Yang, G. Neubig, S. T. Wu, et al. (2026) Mind the sim2real gap in user simulation for agentic tasks. arXiv preprint arXiv:2603.11245. Cited by: §5.1.
    Y. Zi, Z. Wu, A. Boruch-Gruszecki, J. Bell, and A. Guha (2025) AgentPack: a dataset of code changes, co-authored by agents and humans. External Links: 2509.21891, Link Cited by: Table 1.

Appendix A Limitations

SWE-chat is a first-of-its-kind dataset (Figure 1). However, it only contains data from developers who use th[<35;104;10M[<35;103;10Me Entire CLI with public repositories and opt into checkpoint logging. This selects for early adopters of a new open-source tool and does not cover proprietary enterprise codebases. Agent performance and interaction patterns may differ substantially in such settings (e.g., agents may struggle more with undocumented legacy code, or less with well-structured internal libraries). At this stage, findings based on SWE-chat may not generalize. Additionally, a large fraction of data comes from Entire.io’s own code repository. However, as more open-source developers adopt the tool, the dataset becomes increasingly diverse (see Appendix D.1.4).

Most failed sessions are not captured by our data. If the user abandons the agent’s output entirely, session logs are not committed and thus not captured by our data. This likely leads to an overestimation of session success rates and agent efficiency. On the other hand, we treat agent-authored code that is deleted by the human as inefficient output. However, some of this code may survive semantically, for instance, when a user rewrites an agent suggestion in a different file or refactors it into a different form. Our line-level attribution approach does not capture such cases, potentially underestimating the true usefulness of agent contributions.

The diversity of our data makes it difficult to assess the quality of the code produced. Some of the metrics we use (e.g., number of committed lines) should be understood only as proxies of users’ satisfaction with AI-generated outpu[<35;101;10Mts. Similarly, our efficiency metrics capture only what is observable in the session logs and may not reflect the full picture. For instance, cognitive efficiency, measured as prompt characters per committed line does not account for the time users spend reading and reviewing agent output, or planning their instructions. Future research can build on this to develop more robust measurements that can be used as optimization objectives.

LLMs are imperfect data annotators (see Appendix E.1). For results based on LLM-generated labels, we do not draw conclusive statements, given the inherent unreliability of such annotations and the risk of LLM hacking [Baumann et al., 2025]. Rather, we use these annotations to enable easy filtering of the large dataset we introduce, for example, to surface specific cases of unsuccessful sessions such as the one presented in the Appendix B.1. We caution against taking these labels at face value and recommend further validation before using them in downstream analyses.
Appendix B SWE-chat examples

This appendix presents representative examples from SWE-chat illustrating key interaction patterns between users and coding agents. Each example is drawn from a real session in the dataset.
B.1 Low session success score
Session score: 10/100 Repository: nuttycc/LuminTime User: Fix the slow appearance of history list card blocks. The animation feels sluggish when scrolling. Agent: I’ll fix the animation performance. ⊳ Read HistoryListView.swift
 ⊳ Edit HistoryListView.swift — removed unused variable, adjusted stagger delay I’ve optimized the stagger timing for the card animations. The delay between each card appearing has been reduced. User: That’s the wrong parameter — the container animation is the slow part, not the individual card stagger. Agent: I see, let me adjust the container timing instead. ⊳ Edit HistoryListView.swift — modified item animation duration I’ve updated the animation timing parameters. User: You changed the item timing again, not the container! Please verify which parameter actually controls the container appearance before making more changes. No commits made. Session ended without resolution.
Figure 9: Example of a low-success session (score: 10/100). The agent repeatedly modified the wrong animation parameter despite user corrections, failing to verify its assumptions before making edits.
B.2 User pushback

User pushback captures moments where the user redirects, corrects, or rejects the agent’s output. We distinguish three subtypes: corrections (the user provides missing information or redirects the approach), rejections (the user explicitly undoes or refuses the agent’s work), and failure reports (the user reports that the agent’s output is broken or incorrect).
B.2.1 Correction
Pushback type: correction Repository: entireio/cli Agent: The challenge is that PrepareCommitMsg doesn’t have access to the transcript path — that’s passed to the Stop hook by Claude Code. What we do have in PrepareCommitMsg: session state (FilesTouched, BaseCommit, etc.) and staged changes from git. So we’d need to find another approach to access the transcript content. User: but we do have access to the session.CondensedTranscriptLines …?
Figure 10: Example of user correction pushback. The user points out that the agent overlooked an available API field, redirecting the approach without rejecting the overall goal.
B.2.2 Rejection
Pushback type: rejection Repository: armelhbobdad/bmad-module-skill-forge Agent: Done. Issue #53 committed (766901b) and closed. Ready for the next one. User: I undid the commit. We need to find a better approach from scratch. Activate the party mode.
Figure 11: Example of user rejection pushback. The user explicitly reverts the agent’s committed work and requests a completely different approach.
B.2.3 Failure report
Pushback type: failure_report Repository: obsessiondb/rudel Agent: Now instead of adding padding to the element (which breaks the chart layout), it wraps the element in a temporary container div with 24px padding, captures that, then restores the DOM. The chart content stays untouched. ⊳ Edit ChartExport.tsx — wrapped capture target in padding container User: This is broken [User sends screenshot]
Figure 12: Example of user failure report pushback. The agent reports a successful fix, but the user observes the feature is still broken and reports it with a screenshot.
B.3 Hard user interruptions
Event: hard interruption Repository: pskoett/pskoett-ai-skills User: ok, now update the readme. also make sure the install information is in the new skill Agent: I’ll verify the install steps first. ⊳ Bash brew tap entireio/tap && brew install entire
 ⊳ Bash entire –version
 ⊳ Bash entire enable –agent claude-code
 ⊳ Bash entire status [Request interrupted by user] User: ok, now update the readme
Figure 13: Example of a hard user interruption. The user asked to update a README file, but the agent began executing shell installation commands instead of editing the file. The user interrupted and repeated the original request verbatim.
B.4 Agent stops to ask for clarification (AskUserQuestion)
Event: agent stops to ask for clarification Repository: navapbc/lockpick-xlator User: The tool currently outputs .graph.md files wrapping mermaid in markdown fences. I want it to output raw .mmd files instead. Agent:
 ⊳ Read tools/generate-graph.ts
 ⊳ Read commands/graph.ts The change looks straightforward. Currently the tool writes a .graph.md file wrapping mermaid in markdown fences (with a header and generated date). The .mmd file should contain raw mermaid only — no markdown wrapper. Two command files also reference .graph.md and will need updating. Should I skip brainstorming and go straight to planning? Yes, go to planning Brainstorm first Just implement it User: Yes, go to planning
Figure 14: Example of agent-initiated clarification (AskUserQuestion). The agent pauses execution to confirm the user’s preferred workflow, presenting structured options.
B.5 Prompt intent categories

Each user prompt is classified by its primary developer intent. Below we show one representative prompt per [<35;99;10Mcategory, drawn from entireio/cli.
Intent: create User: “Perfect let’s add support for those agents as well”
Intent: refactor User: “I’d also like to remove all instances of ‘does the result contain A?’ — instead, replace those assertions with a single comparison to what the result should be, literally.”
Intent: debug User: “did our timeout kill and retry work? it looks like it just got killed and we failed?”
Intent: understand User: “What would happen if we keep the hooks going if he continues after the warning was shown?”
Intent: connect User: “give steps for setting this up in slack / github”
Intent: git User: “commit this — but let’s test out making some changes after”
Intent: test User: “add test cases to manual_commit_condensation_test.go which use the[<35;96;10M[<35;95;10M following cursor sample:”
Intent: other User: “I don’t like ‘turn’, any other suggestions?”
Figure 15: Example user prompts for each intent category. Notice that the last prompt lacks context, which is why it is classified as ’other’.
B.6 User persona categories

Each session’s user is classified into a behavioral persona based on their interaction patterns across the full session.
Persona: Expert Nitpicker Repository: marin-community/marin User: instead of arg hash for the name, let’s just get short uuid Agent: [edits remote.py: replaces arg hash with short UUID…] User: don’t create separate function for _short_uuid Agent: [removes helper function, inlines uuid4() call…] User: change DEFAULT_JOB_NAME to “remote_job” Agent: [renames constant in remote.py…] [<35;94;10MUser: In the base_name let’s include current user name
Figure 16: Example of the Expert Nitpicker persona. The user maintains a stable goal while issuing a series of precise, targeted corrections to the implementation. Each prompt refines how the agent executes, not what it builds.
Persona: Vague Requester Repository: entireio/cli User: pull comments on PR and if real issues the fix Agent: [fetches PR comments, applies 3 fixes across 2 workflow files…] User: commit and push
Figure 17: Example of the Vague Requester persona. The user provides broad, underspecified instructions and delegates all implementation decisions to the agent.
Persona: Mind Changer Repository: entireio/cli User: let’s make the “entire start” command hidden Agent: [edits start.go: sets command hidden, verifies build…] User: thinking again: let’s completely remove the start command
Figure 18: Example of the Mind Changer persona. The user reverses the overall goal mid-session — from hiding a CLI command to removing it entirely — changing what should be built, not just how.
Appendix C Experimentation details
C.1 Data processing pipeline

Raw session log data from AI agents is stored on each repository’s entire/checkpoints/v1 branch, containing checkpoint and session metadata, user prompts, and full conversation transcripts. From each transcript, we extract structured conversation turns (user prompts, assistant responses, thinking traces, tool calls, and tool results), per-turn token usage, and tool-call metadata, including file paths and shell[<35;93;10M commands.
SWE-chat data growth trajectory

As coding agents make it increasingly easy to generate large volumes of code, developers face growing challenges in reviewing, understanding, and validating AI-generated contributions [Sarkar, 2025, Becker et al., 2025, Anthropic, 2026]. Entire addresses this need by letting developers track how their codebase evolved not only as a function of commits, but as a function of prompts, creating a searchable record of every AI-assisted change. This utility incentivizes continued adoption, and we expect the dataset to keep growing, a trend already visible in the steep trajectory shown in Figure 1. Our pipeline discovers Entire-enabled public repositories by querying the GitHub Code Search API and, for each repository, downloads all checkpoint directories from the metadata branch and parses the raw transcripts into structured tables.
C.2 Metrics

Session duration, tool call duration, number of in- and output tokens, and files touched during agent actions are all measured directly from coding agent session logs. We quantify coding agent efficiency using several complementary approaches, all computed from raw data without the need for annotations.
Agent-authored code percentage

The Entire CLI computes code attribution at commit time using temporary checkpoints on shadow branches. It constructs checkpoints stored on a shadow branch to obtain all committed human vs. agent-written lines.
	
Agent-authored %=agent lines survivedtotal committed lines×100
		(1)
Agent coding efficiency and code survival

To measure the fraction of agent-produced code that survives into the final commit, we perform a post-hoc analysis, since the agent-authored code percentage does not record per-tool-call provenance or agent self-overwrites. We analyze three states for all changed files: the base version (parent commit), the agent actions (sequential tool calls), and the committed version. We reconstruct agentic changes by replaying every file-modifying tool call (e.g., write, edit) in chronological order. After each tool call, we compute a line-level diff between the file’s previous and new state using Python’s difflib.SequenceMatcher. Each line carries a provenance tag—either base (present before the agent acted) or agent (introduced by the agent)—which is updated as we proceed along the agent trajectory. With this approach, we can track all agentic code additions, edits, and deletions—and compute which changes survive, as measured by the file state at the time of commit.

We derive two rates from the per-commit aggregate counts:
	Coding efficiency 	=agent lines survivedagent cumulative lines produced×100 		(2)
	Code survival rate 	=agent lines survivedagent lines in final state×100 		(3)

Coding efficiency measures the fraction of the agent’s total effort (including lines it later rewrote) that ended up in the commit. The code survival rate measures the fraction of the agent’s net output (after self-overwrites) that the human kept unchanged. Note that concurrent changes, where the human and the agent modify the same file simultaneously, may cause the transcript to reflect inconsistent file states and attributions.
Token, cost, and cognitive efficiency

We also quantify several cost-per-output metrics that capture the resources consumed to produce each committed line of code. For each session with a clean mapping to committed code (see Appendix C.3), we compute:
	Token efficiency 	=total tokens (in + out + cache)total committed lines×100 		(4)
	Cost efficiency 	=∑API calltokens×pricemodeltotal committed lines×100 		(5)
	Cognitive efficiency 	=∑user prompt characterstotal committed lines×100 		(6)
	Time efficiency 	=∑session runtimestotal committed lines×100 		(7)
	Agent runtime efficiency 	=∑agent runtimestotal committed lines×100 		(8)

For time efficiency, we consider complete session runtimes but exclude all idle periods lasting more than 2 minutes, i.e., when neither the agent nor the user performs any action. For agent runtime efficiency, we sum the completion times of all agent turns, where a turn starts with a user prompt and ends with an agent response.
C.3 Combining session-level statistics with commit-level outcomes

Sessions may span multiple commits, and multiple sessions may contribute to the same commit (checkpoint). To combine session-level statistics with commit-level results, we restrict the analyses in Table 3 and Figure 29 to sessions where the commit-level lines can be unambiguously attributed. This includes 48.6% of sessions.
Appendix D Additional results
D.1 Dataset statistics
Refer to caption
Figure 19: Distributions of human user intents (a), agent tool calls (b), repository domains (c), repository audiences (d), and coding modes (e).
D.1.1 Prompt languages

User prompts are predominantly in English (Figure 20). We detect the language of each user prompt using lingua-py4 and retain languages appearing in at least 100 prompts. We manually verified 2,000 classifications where the detector reported low confidence or predicted an extremely low-resource language. In most such cases, the prompt mixed code snippets with English instructions, causing misclassification, and we corrected the label accordingly.
Refer to caption
Figure 20: Top 6 prompt languages.
D.1.2 Tool calls

Table 5 provides a full breakdown of agent tool call types. We group some of the tool calls into aggregate categories for simplicity.
Table 5: Tool call type distribution across all agent tool calls.
Rank 	Category 	Count 	% 	Includes
1 	read 	60,855 	19.8% 	Read, read_file
2 	grep 	31,238 	10.1% 	Grep, bash grep/rg
3 	glob 	4,318 	1.4% 	Glob
4 	bash:file 	21,130 	6.9% 	cd, ls, cat, find, mkdir, rm, bd, echo, tail, wc, lsof, head, …
5 	bash:build 	24,699 	8.0% 	mise, bun, go, npx, cargo, pnpm, uv, python, npm, xcodebuild, node, make, …
6 	bash:net 	3,541 	1.2% 	curl, ssh, dig, scp, nc, rsync, nslookup, ping, nmap
7 	bash 	16,527 	5.4% 	sleep, gcloud, for, source, docker, agent-browser, sed, nix, vendor/bin/phpunit, which, ./gradlew, rtk, …
8 	git/gh 	36,537 	11.9% 	git, gh
9 	write 	9,025 	2.9% 	Write, write_file
10 	edit 	60,20[<35;94;10M5 	19.6% 	Edit, MultiEdit
11 	web 	1,435 	0.5% 	WebFetch, WebSearch
12 	agent 	20,495 	6.7% 	Task, TaskCreate, TaskUpdate, Agent, TaskOutput, SendMessage, …
13 	mcp 	6,001 	1.9% 	mcp__* (user-installed MCP server tools)
14 	TodoWrite 	3,217 	1.0% 	TodoWrite
15 	ToolSearch 	2,804 	0.9% 	ToolSearch
16 	AskUserQuestion 	2,171 	0.7% 	AskUserQuestion
17 	Skill 	1,679 	0.5% 	Skill
18 	EnterPlanMode 	300 	0.1% 	EnterPlanMode
19 	ExitPlanMode 	1,089 	0.4% 	ExitPlanMode
20 	other 	511 	0.2% 	miscellaneous (apply_patch, LSP, KillShell, …)
D.1.3 Agent trajectories

Figure 21(a) shows the tool call composition at each sequential position within an agent trajectory after a user makes a request. In early positions, the agent often uses research tools (read, grep, glob, an[<35;96;10Md git/gh) as it orients itself in the codebase. As the trajectory progresses, action tools such as edit, write, and bash:build become more prominent.

Figure 21(b) examines the same trajectories from the opposite direction, showing tool call composition counting backward from the natural end of a turn (position −1 = last tool call before the agent writes its text response, shown in the rightmost bar). The last tool calls in natural turns are most frequently git/gh commands (committing or pushing results), bash:build (executing bash commands), and edit (final code modifications). Notably, AskUserQuestion rarely appears at position −1, because it is non-blocking, i.e., a turn is completed only with an agent response.

Figure 21(c) applies the same reverse traj[<35;98;10Mectory but for a turn that ended with a hard user interruption. ExitPlanMode is the most frequent last tool call (32%), indicating that users often interrupt right at the transition from planning to execution. In such cases, the agent has just finalized its plan, and the user decides to redirect before any code changes are made.
Refer to caption
(a) Tool call composition by position within the agent trajectory (left to right).
Refer to caption
(b) Tool call composition counting from the end of natural (non-interrupted) turns.
Refer to caption
(c) Tool call composition counting from the end of interrupted turns.
Figure 21: Agent tool call trajectories. (a) Tool composition by sequential position within a single agent trajectory. (b, c) Tool composition counti[<35;100;9Mng backward from the end of the trajectory, split by natural vs. interrupted turns.
D.1.4 Code repository types

To further contextualize the environment in which these interactions occur, we analyze the domains and target audiences of the repositories. We classify each repository into one of three domains (application, devtools, other) and one of four audiences (enduser, developer, researchers, education) based on its name, description, and README file. As shown in Figures 19c and 19d, most repositories are user-facing applications or developer tools. This distribution highlights that SWE-chat primarily reflects practical, software-engineering-focused environments rather than purely academic or exploratory programming tasks.
D.1.5 Dataset diversity over tim[<35;101;9M[<35;102;9Me

Following the public launch of Entire.io on February 10, 2026, open-source developers quickly started using the tool and pushing their coding agent session data to public GitHub repositories. Figure 22 tracks the cumulative fraction of sessions originating from Entire.io’s own repository. At the time of writing, this repository contributes less than 20% of all sessions in SWE-chat, and the share declines with continuing adoption.
Refer to caption
Figure 22: Cumulative fraction of sessions originating from the entireio/cli repository over time. Each point shows the running proportion of all sessions collected up to that date that came from this single repository. The dashed red line marks the public launch of the Entire.io tool (February 10, 2026).
D.2 Top[<35;103;9Mic distribution

To characterize the range of tasks users bring to AI coding assistants, we perform a topic analysis on all English user prompts in SWE-chat.
D.2.1 Topic clustering methodology

Starting from all English prompts, we first remove interruption signals (e.g., “[Request interrupted by user]”), system-injected messages (identified by XML-tag prefixes such as and ), Claude skill invocations, and image references. We then stripped fenced and inline code blocks from all remaining prompts and excluded prompts whose stripped text is shorter than 30 or exceeds 1,500 characters. Finally, we deduplicate prompts on case-insensitive stripped content.

We generate sentence embeddings using the all-mpnet-base-v2 model from SentenceTransformers [Reimers and Gurevych, 2019]. We embed the code-stripped prompt text rather than the raw text so that embeddings reflect the user’s natural language intent rather than the syntactic structure of pasted code. Before clustering, we reduce the embedding dimensionality from 768 to 20 using UMAP

We cluster the reduced embeddings using HDBSCAN* [Campello et al., 2013, McInnes et al., 2017] with min_cluster_size=150 and min_samples=5. This yields 20 clusters covering 57.4% of all prompts, with cluster sizes ranging from 152 to 4,329 (median: 256). The remaining 8,265 prompts (42.6%) are classified as noise, reflecting the diversity of coding session prompts that do not form tight semantic groups.

For each cluster, we select the 100 prompts with the highest HDBSCAN* membership p[<35;104;9Mrobability to generate a topic description, which is shown in Figure 23. The descriptions are generated by gpt-5.4-2026-03-05, using the following prompt:
D.2.2 Findings

We identify 20 topic clusters that cover 57.4% of all prompts. The results are displayed in Figure 23.5 Frontend coding (cluster 3) has the largest pushback rate (75%). Cluster 17 mostly consists of very long prompts that often specify multiple tasks, explaining the large agent turn durations.
Refer to caption
Figure 23: Topic distribution of user prompts. Each bar represents one of the 20 clusters identified by HDBSCAN*, labeled with a GPT-generated topic summary. The remaining panels show, per cluster, pushback rate, agent turn duration in seconds, and session success score distribution for sessions in which at least 20% of prompts fall within the cluster. Several clusters (1, 8, 10, 15, 20) contain a disproportionate amount of prompts originating from Entire.io’s own repository.
D.3 Distribution of user personas

Figure 24 shows the full distribution of user personas across all sessions. In most sessions, users act as expert nitpickers.
Refer to caption
Figure 24: Distribution of user personas.
D.4 Coding mode distribution over time

Figure 25 shows the temporal evolution of coding modes. The share of vibe coding sessions has roughly doubled since the launch of Entire’s CLI tool, rising from approximately 20% to over 40%.
Refer to caption
Figure 25: 14-day rolling average of coding modes and agent-authored code.
D.5 Code vulnerability analy[<35;102;9Msis with Semgrep

We use Semgrep6, an open-source static analyzer that matches community-curated patterns against source code, and run it with its default --config=auto ruleset. This auto-selects rules based on the languages detected in each snapshot, including Common Weakness Enumeration (CWE), which includes known types of security weaknesses [Martin and Barnum, 2008]. For every commit, we extract the repository state before and after the commit, scan each state, and keep only findings inside files that the commit actually modified.
Distribution of introduced vulnerabilities

Figures 26 and 27 break down the introduced findings by Semgrep rule and by CWE category, respectively. One rule (JavaScript path joining without sanitization) accounts for most detec[<35;100;9M[<35;98;9Mted vulnerabilities, but the remaining findings include a long tail of rules and CWEs, including externally controlled format strings (CWE-134), missing integrity checks (CWE-353), OS command injection (CWE-78), and SQL injection (CWE-89). Hence, a broad set of vulnerability types is being introduced.
Refer to caption
Figure 26: Distribution of introduced vulnerabilities across Semgrep rule IDs (top 15 plus other).
Refer to caption
Figure 27: Distribution of introduced vulnerabilities across CWE categories (top 15 plus other).
Vulnerability example

Figure 28 shows a concrete Python example of a vulnerability introduced by a coding agent in our dataset, together with the Semgrep annotation that flags it.
1import subprocess
2
3def run_build(target: str) -> st[<35;97;9Mr:
4 """Run the project’s build step and return stdout."""
5 cmd = f"make {target}"
6 # Semgrep: python.lang.security.audit.subprocess-shell-true (CWE-78)
7 # "Found subprocess function with shell=True. ...
8 # A malicious actor can inject arbitrary shell commands.
9 # Use shell=False instead."
10 result = subprocess.run(
11 cmd, shell=True, capture_output=True, text=True)
12 return result.stdout
Figure 28: Example of a Python vulnerability introduced by an agent in SWE-chat. The agent builds a shell command by interpolating a user-controlled string (target) into an f-string and then calls subprocess.run with shell=True (line 10). The inline comment shows the Semgrep annotation, which flags a CWE-78 OS-Command-Injection risk because an attacker who can influ[<35;96;9Mence target could inject arbitrary shell commands (e.g. "rm -rf ˜"). The standard fix is to pass arguments as a list, e.g. subprocess.run(["make", target]) with shell=False, so they are not reparsed by a shell.
D.6 Agent efficiency

Figure 29 compares efficiency across coding modes along four dimensions. Vibe coding sessions are consistently less efficient: they consume roughly twice as many tokens and require more wall-clock time per 100 committed lines than collaborative sessions. Collaborative coding achieves the best trade-off across all metrics, suggesting that human guidance helps agents produce code more economically.
Refer to caption
Figure 29: Token, cognitive, and time efficiency per 100 committed lines of code (lower is better). Y-axis labels desc[<35;95;9Mribe the metrics used for the efficiency dimension. μ indicates means.
D.7 Agent turn duration over time

Figure 30 tracks agent turn duration over time. While median turn durations have remained relatively stable, the tail has grown since the beginning of the data collection: the 99.9th percentile now exceeds 100 minutes. This trend suggests a gradual shift toward longer autonomous agent runs.
Refer to caption
Figure 30: Turn-level autonomy in Claude Code sessions. Agent turn duration in interactive Claude Code sessions. Showing 7-day rolling average of different percentiles (p50, p90, p99, p99.9) over time.
D.8 Oversight rates over time

Over the entire data collection period (from January to March, 2026), the shares of agent-initiated stops, user interruptions, and user pushback remain relatively stable. We visualize this with average fractions of turn using a 7-day rolling window in Figure 31.
Refer to caption
Figure 31: Agent stops for clarification, user interruptions, and soft user pushback over time.
D.9 Development activities

To examine whether agent behavior differs across development activities, we group intents into code writing (create, refactor, connect) and code reviewing (understand, test) prompts. As visible in Figure 32, on average, code writing prompts trigger longer agent turns (mean 4.1 vs. 2.4 minutes) and more file writes (4% of tool calls create a new file from scratch) and edits (24% of tool calls edit an existing file). Furthermore, writing prompts also elicit more friction than code reviewing prompts: agents stop to ask questions nearly three times as often (6.0% vs. 2.6% of turns), and users also interrupt and push back more frequently (see Section 4.4 for more details).
Refer to caption
Figure 32: Agent behavior by development activity (code writing vs. code reviewing).
Appendix E Data annotation

Here we provide all prompts used for the final dataset annotation. We include all validation details and prompts for the annotation tasks we crafted. The prompt intent task is inspired by [Becker et al., 2025] and the user persona task is inspired by Wang et al. [2026b].
E.1 Validation
Annotation codebook development and annotator agreement

To develop the annotation codebook and a dataset to test LLM annotation performance, we proceeded in [<35;96;9Mthree stages for each annotation task:

    1.

    First, two annotators iteratively refined the codebook until they agreed on all labels for 10 data points.
    2.

    Second, the same two humans proceeded to independently annotate NIAA=90 additional data points. We computed inter-annotator agreement metrics using the results from this stage. The results in Tables 6 and  7 show that agreement was moderate-high for all tasks. This includes a binary version of the prompt pushback tasks that collapses all classification classes except the non-pushback class. Figure 33 shows the full confusion matrices for all tasks. For session success ratings, we discuss all cases where humans disagree by more than 20 points.
    3.

    Finally, the same two humans discussed all disagreements and decided on the most appropriate gold label for each data point. Together with the 10 data points from stage 1, this yielded Ngold=100 gold labels for evaluating LLM annotation performance.

We use Cohen’s κ to measure human-human and LLM-human agreement for multi-class annotation tasks, and additionally report percentage agreement in Table 6 [Cohen, 1960]. Session success is labeled with a 0–100 score, which is why measure absolute agreement with a two-way random effect, single measurement Intraclass Correlation Coefficient, commonly referred to as ICC(2,1) [Shrout and Fleiss, 1979, McGraw and Wong, 1996]. We additionally report Spearman ρ in Table 7 and Figures 33–34 [Spearman, 1961]. We use the average of the two human annotators’ [<35;97;9Msession success ratings as the gold standard against which we compare the LLMs. If human ratings differ by >20, the human annotators collectively decide on the most appropriate gold rating. For the LLM vs. human gold rating comparison, we additionally report consistency using a two-way mixed effect, single measurement ICC, abbreviated ICC(3,1) [Shrout and Fleiss, 1979].

For the repository-level annotations, we take a slightly different approach. Namely, during stage 2, human annotator 2 reviewed the 100 repository domains and repository audience labels set by annotator 1 and either agreed with or overrode them.

All annotators are authors of this paper.
Table 6: Inter-annotator agreement for multi-class tasks.
Task 	𝐍IAA 	Categories 	Annotators 	Agreement 	Cohen’s κ
Prompt intent 	90 	7 	2 	68/90 (75.6%) 	0.709
Prompt pushback 	90 	4 	2 	80/90 (88.9%) 	0.832
Prompt pushback (binary) 	90 	2 	2 	85/90 (94.4%) 	0.888
User persona 	90 	4 	2 	71/90 (78.9%) 	0.662
Table 7: Inter-annotator agreement for continuous session success rating task.
Task 	𝐍IAA 	Rating scale 	Annotators 	Spearman ρ 	ICC(2,1)
Session success 	90 	0–100 	2 	0.757 	0.503
Refer to caption
Figure 33: Inter-annotator agreement confusion matrices.
LLM annotation performance

We tested 9-11 LLMs and 2-4 prompt paraphrases for each task and evaluated them against the 100 human-annotated gold labels. Table 8 shows the performance results, showing only the best-performing prompt for each model-task combination. We then selected the model with the hig[<35;98;8Mhest performance. The only exception is the prompt pushback task, where we defer to the second-best-performing model, since qwen-3.5-9b offers a much better cost-performance trade-off than gpt-5.4-2026-03-05. The high cost of this task is due to the large context: for each prompt pushback annotation, we provide not only the user message but also the full session transcript up to that point (see Table 2 and Appendix E.2.4).

Figure 34 shows the full confusion matrices for all tasks.
Table 8: Annotation model performance against human gold labels. For each task, we indicate the best-performing model and the chosen model, i.e., the one we used for full-dataset annotation. ‘∘’ indicates models that produced invalid labels and ‘—’ denotes models that were too expensive to run. We use accuracy (acc) for multi-class annotations and ICC(2,1) for numeric labeling tasks.
Model 	

Prompt intent (acc)
	

Prompt pushback (acc)
	

Pushback (binary) (acc)
	

User persona (acc)
	

Repository domain (acc)
	

Repository audience (acc)
	

Session success (ICC(2,1))
gpt-5.4-2026-03-05 	0.69 	0.74 	0.83 	0.69 	0.77 	0.79 	0.56
gpt-5-mini-2025-08-07 	0.74 	0.64 	0.73 	0.69 	0.75 	0.79 	0.46
gpt-5-nano-2025-08-07 	0.67 	0.63 	0.69 	0.62 	0.68 	0.79 	0.50
claude-opus-4-6 	0.70 	— 	— 	0.57 	0.81 	0.84 	—
claude-sonnet-4-6 	0.66 	— 	— 	0.46 	0.78 	0.83 	0.60
claude-haiku-4-5-20251001 	0.69 	∘ 	∘ 	0.60 	0.72 	0.79 	0.56
gpt-oss-120b 	0.71 	0.66 	0.74 	0.63 	0.66 	0.75 	0.51
gpt-oss-20b 	0.73 	0.63 	0.71 	0.59 	0.63 	0.69 	0.49
qwen-3.5-2[<35;97;8M7b 	0.76 	0.66 	0.73 	0.61 	0.62 	0.76 	0.52
qwen-3.5-9b 	0.72 	0.67 	0.79 	0.60 	0.55 	0.76 	0.47
olmo-3.1-32b 	0.59 	∘ 	∘ 	0.51 	0.62 	0.69 	0.43
Ngold 	100 	100 	100 	100 	100 	100 	100
Refer to caption
Figure 34: LLM annotation agreement with gold labels from human expert annotations.
E.2 Annotation prompts

We now list all LLM-based annotation tasks applied to the SWE-chat dataset.
E.2.1 Repository type classifier

Model: claude-opus-4-6.
We aggregate library and devtools into a single category called devtools, since human annotators often disagreed about which to assign.
E.2.2 Session persona classifier

Model: gpt-5.4-2026-03-05. Parameters: r​e​a​s​o​n​i​n​g​_​e​f​f​o​r​t=low.
E.2.3 Prompt intent classifier

Model: Qwen/Qwen3.5-27B. We use suggested decoding parameters: t​e​m​p​e​r​a​t​u​r​e= 0.7,t​o​p​_​p= 0.8,t​o​p​_​k= 20,p​r​e​s​e​n​c​e​_​p​e​n​a​l​t​y= 1.5.
E.2.4 User pushback classifier

Model: Qwen/Qwen3.5-9B. We use suggested decoding parameters: t​e​m​p​e​r​a​t​u​r​e= 0.7,t​o​p​_​p= 0.8,t​o​p​_​k= 20,p​r​e​s​e​n​c​e​_​p​e​n​a​l​t​y= 1.5.
E.2.5 Session success rating

Model: claude-sonnet-4-6.
BETA
