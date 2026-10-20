# Engine and structure (for maintainers)

A personal tutor that runs inside Claude Code (VS Code extension or CLI). It can teach any topic to any learner to the same standard: it starts from unconditional truths, builds by motivated discovery, uses diagnostic multiple-choice questions where every wrong option maps to a known misconception, schedules spaced repetition, assigns hands-on tasks with tests, and records everything in files so each session resumes exactly where the last one stopped.

It knows nothing about the learner up front beyond what they or a mentor tell it. It gets to know them from their answers: which wrong option they choose, how calibrated their confidence is, what kind of explanation lands, and how fast they move. That evidence shapes the teaching.

- Installing for a learner: [KURULUM.md](../KURULUM.md) (Turkish checklist, about 15 minutes).
- Learner-facing guide: [BASLA.md](../BASLA.md) (Turkish).

## How it is built

| Part | Where | Role |
|---|---|---|
| Entry point | `CLAUDE.md` | session protocol, skill routing, hard rules, beginner communication |
| Skills | `.claude/skills/` | `onboarding`, `new-track`, `teach` (+ `questions.md`, `engagement.md`), `review`, `task`, `lesson`, `cheatsheet`, `wrap-up`, `setup` |
| Lesson pages | `assets/` + `tools/lesson-template.html` | shared stylesheet and components (quiz with result line, payoff matrix, truth table) for HTML lessons and reference pages in `tracks/<t>/lessons/`, `tracks/<t>/reference/` |
| Track standard | `.claude/skills/new-track/standard.md` | the quality checklist every track must pass |
| Researcher | `.claude/agents/researcher.md` | verifies facts and APIs before they are taught |
| Engine | `tools/learn` (stdlib Python) | spaced repetition (SM-2 variant, confidence-aware), deterministic grading, option shuffling, attempt log, mastery levels, validation |
| Hooks | `.claude/settings.json` | SessionStart injects `learn status`; PreToolUse stops Claude from editing the learner's solutions, `workspace/` and `projects/` (fails closed for those paths) |
| Learner state | `learner/`, `tracks/<track>/` | profile, map, misconceptions, cards, attempts, tasks, lessons, reference, RESOURCES, cheatsheet, glossary, handoff |

**Data format rule:** JSON(L) only where code computes on it (`cards.jsonl`, `attempts.jsonl`, `moments.jsonl`, `state.json`). Everything Claude or a human reads and interprets is Markdown: the profile and its observations, handoff with its session log, map, misconceptions, glossary, cheatsheet. The numbers behind an observation already live in `attempts.jsonl`, and `signals` / `journey` compute them on demand.

The split is deliberate. The LLM does what LLMs are good at: explaining, adapting, and writing questions and tasks. Code does what has to be exact: dates, intervals, grading, where the correct option sits, and whether a track meets the standard.

**Two channels.** Knowledge that reads better than it talks (history, mechanisms, definitions with cases) goes into short, cited, interactive HTML lesson pages built from `assets/` (the lesson format and the Knowledge/Wisdom/Gaps `RESOURCES.md` come from Matt Pocock's `teach` skill). Measurement stays in chat and in the engine: graded questions, spaced review, tasks. A lesson quiz reports back through a result line the learner pastes, recorded as diagnostic only. Each track's README says which nodes get a lesson and which run as chat + task.

## Setting it up for someone

Follow [KURULUM.md](../KURULUM.md). In short: VS Code + Claude Code (paid plan) + Git for Windows on Windows; clone; copy `learner/intake.example.md` → `learner/intake.md` and fill it in; install uv and run `uv sync` **before** the first session, because the engine and hooks need Python; open the folder, start a new chat, and say "Merhaba".

Learner data (`learner/`, `tracks/`, `workspace/`, `projects/`) is git-ignored so the template stays clean. In a learner's private copy, remove those lines from `.gitignore` to version their progress.

`.vscode/settings.json` hides engine files (`tools/`, `.claude/`, `*.jsonl`) from the Explorer to keep a beginner's view clean and to keep answers out of sight. Remove `files.exclude` entries if you're maintaining the system.

## Engine cheat sheet

```bash
tools/learn status                       # what the session-start hook prints
tools/learn new-track python-basics --title "Python Temelleri"
tools/learn add-card --track python-basics < card.json
tools/learn cards --track t --node n [--html]  # cards with answers, or quiz skeletons for a lesson page
tools/learn due [--track t] [--limit 6] [--ahead 1]
tools/learn due --today-misses           # today's wrong / heavily hinted cards, for the wrap-up retest
tools/learn record --card pb-001 --choice B [--confidence 3] [--answer-text "why"]   # confidence only if asked
tools/learn record --card pb-001 --dont-know                  # "Bilmiyorum": wrong, confidence 1
tools/learn record --card pb-001 --choice B --source lesson   # pasted from a lesson quiz: diagnostic, not scheduled
tools/learn record --card pb-001 --choice B --source predict  # a guess before teaching: diagnostic, not scheduled
tools/learn verify-task --dir tracks/t/tasks/01-x < reference.py   # check tests in a temp copy
tools/learn task --track t --task 01-x --node n --status passed --hints 1
tools/learn map --track t [--json]      # parsed node table + mermaid graph of map.md
tools/learn progress [--track t]         # every map node: new → checked → retained → owned (+ slipping)
tools/learn signals                      # how this learner learns: calibration, question types, generation_gap, trend, hints
tools/learn journey                      # then-vs-now evidence for recaps
tools/learn moment --kind recap          # log an engagement moment (pacing: recap/teaser/value/milestone)
tools/learn validate [--track t]         # checks the mechanical parts of the standard
tools/learn refresh [--quiet]            # regenerate learner/export.json → dashboard.html → lesson mini maps (auto after every write and tracks/learner edits; TEACH_NO_DASHBOARD=1 disables)
tools/learn dashboard [--open]           # read-only learner page: learner/dashboard.html
tools/learn backup                       # copy learner data before anything risky
tools/learn migrate [--dry-run]          # bring old learner data to the current format
tools/learn doctor-data [--fix]          # find (and repair) inconsistent learner data
tools/learn export --json                # read-only contract for any UI (teach.export/1); never contains card text or answers
tools/doctor                             # learner's environment
```
