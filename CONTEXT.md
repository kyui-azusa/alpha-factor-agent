# Alpha Factor Agent Context

This context describes the shared language for the five-day alpha-factor research project and its lightweight collaboration platform.

## Language

**Research Project**:
The main deliverable: an explainable A-share alpha factor agent whose numerical claims are produced by deterministic code, not by an LLM. Since ADR-0022 the research question is narrowed to a falsifiable increment test — when structured data already discloses the key numbers of an event, does reading the announcement text add anything? — using A-share performance forecasts (2015-2021) as the testing ground.
_Avoid_: final platform, social site, side project

**Increment Test**:
The falsifiable core of the narrowed research question: whether semantic features an LLM extracts from performance-forecast text carry cross-sectional predictive power *beyond* the structured forecast fields already available in 聚源 (magnitude, type, range). The structured-field factor is the control group. A null result is a complete answer, not a failure, because the project's asset is the judging apparatus rather than any single factor.
_Avoid_: proving the factor works, LLM beats humans, headline alpha

**Five-Day Delivery Line**:
The compressed delivery target for the five-day build: M0-M3 must be real and tested, M4-M5 may be lightweight or mocked where necessary, and M6 must produce defense and paper-ready materials.
_Avoid_: full six-week scope, demo-only build

**Defense Bundle**:
The internally defined final deliverable set for the five-day project: short paper, defense slides, and reproducible code package. This is a planning target because no formal page-count or slide-count requirement has been found in the local materials.
_Avoid_: official page requirement, social packet collection

**Audience Split**:
The rule that defense materials and social materials are generated separately from the same research artifacts: defense explains the full trustworthy chain, while social packets present short shareable progress.
_Avoid_: one-size-fits-all copy, social feed as paper

**Defense Narrative**:
The final presentation line: the project does not let an LLM trade or compute alpha; it lets the LLM propose hypotheses, then uses a trustworthy deterministic backtest to judge them.
_Avoid_: LLM stock picker, black-box trading bot

**Core Market Data**:
The official numerical data source for backtesting and research claims, expected to be the SUFE-provided 聚源 database once access is available.
_Avoid_: scraped backtest data, unverified market data

**Research Crawler**:
A supporting tool for collecting public references, field explanations, examples, or background material. It is not the authoritative source for core alpha backtest numbers.
_Avoid_: core data pipeline, replacement for 聚源

**Synthetic Data**:
Artificial sample data used before 聚源 access is available to verify engineering correctness: point-in-time merge, no-look-ahead tests, date-based out-of-sample splits, metrics, and report generation.
_Avoid_: research evidence, empirical finding

**LLM Backend**:
The configurable language-model provider used only for proposing ideas, validating semantics, and reading results. The default is the user's available Codex/OpenAI-compatible API, with MiniMax as an optional fallback or text-generation provider and mock backends for tests.
_Avoid_: backtest engine, numerical calculator

**Candidate Factor Proposal**:
A structured LLM output containing a factor name, abstract expression, economic rationale, required fields, and risk notes. It is a hypothesis to be checked by deterministic code, not a numerical conclusion.
_Avoid_: proven alpha, LLM-computed result

**Project Spine**:
The research project is the primary organizing line for time, evidence, and presentation; other artifacts must derive from it.
_Avoid_: parallel platform, equal-track build

**Platform Byproduct**:
A lightweight sharing and feedback surface generated from research progress, not a separate product with its own content workload.
_Avoid_: collaboration product, full workflow system

**Idea Packet**:
A shareable intermediate artifact aimed at outside classmates: a short, sharp, easy-to-forward progress note, method note, pitfall, visualization, or experiment prompt derived from the research process. The project should produce at least two per day during the five-day build, using the default format: title, one-sentence progress or insight, one redacted visual or pseudo-formula, and one follow-up question.
_Avoid_: final result, team task, complete report, share node

**Packet Source Priority**:
The highest-value idea packets should come from the trustworthy base of the research project: data contract, point-in-time alignment, no-look-ahead tests, date-based out-of-sample split, backtest metrics, and baseline-factor visualizations. These are prioritized for sharing, but only after real progress creates something honest to show.
_Avoid_: invented progress, forced daily content

**Opening Packet**:
A day-one idea packet that shows research engineering setup rather than results, such as a data contract diagram, look-ahead timeline, leakage-prevention test sketch, or five-day route map.
_Avoid_: result packet, fake progress, placeholder post

**Redacted Core**:
The removed or abstracted part of an idea packet that would expose the final formula, exact ranking, sensitive field detail, or other high-value result.
_Avoid_: teaser, hidden trick, censorship

**Social Audience**:
Students outside the immediate team — especially stronger classmates from better universities in other groups — who are the primary audience for shared idea packets and the priority for friend-making.
_Avoid_: internal teammates, evaluator, anonymous public

**Packet Feed**:
The static site's first-screen experience for the social audience: a stream of idea packets rather than a project introduction or marketing page. It may include one lightweight identity line for the research theme, but the feed remains the main first-screen object.
_Avoid_: homepage hero, project overview first, report index

**Packet Source File**:
A repository Markdown or YAML content file that stores an idea packet and its metadata for static-site generation.
_Avoid_: database row, manual website-only content

**Light Interaction**:
The packet feed's interaction model: mostly read-only, limited to viewing and forwarding/copying. Questions and suggestions are not submitted on the feed itself; they go through the intake form when its link is shared.
_Avoid_: likes, comment wall, ranking, submit box on packets, social network features

**Feedback Issue**:
A raw suggestion, bug report, or question submitted through the intake form and converted into an issue — primarily by teammates, though the form link may also be shared with outside classmates. Submitters are not expected to split or scope it correctly; the handling skill/AI decides how to break it into implementation tasks later.
_Avoid_: implementation task, scoped engineering ticket

**Submitter Name**:
The name entered by the person who leaves a question or suggestion through the platform. GitHub issues may be created through the project owner's account, but the submitter name is preserved in the issue body.
_Avoid_: GitHub author, required GitHub identity

**Intake Form**:
The lightweight form used to collect questions and suggestions — primarily from teammates, with the link shareable to outside classmates — modeled after intelligrow-style structured intake. The reference form fields are title, description, attachment, product, type, priority, and version; this project adapts that shape to idea-packet feedback while requiring submitter name and keeping the form quick to fill from WeChat.
_Avoid_: free-form chat, full project-management form

**Intake Fields**:
The accepted field set for the project intake form: submitter name, title, description, attachment, screenshot, related issues, needs-review flag, type, and priority. The version field from the reference form is omitted, and product is replaced by related issues.
_Avoid_: product version, oversized survey, related idea packet

**Needs Review**:
A flag the submitter sets to say the ticket's content is not verified — typically a conclusion reached in discussion with an AI — and should be reviewed by another member before anyone acts on it. It becomes the `待审核` GitHub label and a stated line in the issue body, and the site can filter on it.
_Avoid_: approval workflow, blocking gate, reviewer assignment

**Related Issues**:
Numbers of earlier intake tickets that a new ticket points at, typed by hand or picked with the 「引用」 button on the history list (at most five). They are written into the issue body as `#N` so GitHub creates the cross-reference itself. Referencing is the only relation the platform offers — there is deliberately no in-site reply thread or parent/child hierarchy.
_Avoid_: reply thread, sub-issue, comment feature

**Convenience Intake**:
The issue intake flow as a practical convenience for teammates, not the main proof of capability or the main social artifact.
_Avoid_: core platform value, main deliverable

**Handling Skill**:
A reusable AI workflow instruction that interprets raw feedback issues, decides the task split, and guides implementation while keeping the human in the loop.
_Avoid_: teammate judgment, manual triage checklist

**Result Boundary**:
The rule that final research results and sensitive data are kept out of the public repository and public sharing surfaces. Shareable content may include methods, pitfalls, visual explanations, failure cases, and abstracted factor hypotheses, but must not include complete reproducible alpha expressions, stock/ranking conclusions, final metric tables, raw 聚源 data, or sensitive field-level details.
_Avoid_: hidden branch, private final answer in public repo
