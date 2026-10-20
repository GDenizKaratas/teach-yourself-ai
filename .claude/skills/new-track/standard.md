# Track quality standard

Every track must meet this standard, whatever the topic. Items marked ⚙ are checked by `tools/learn validate`. The rest are your honest self-review before presenting the plan.

## Goal
- [ ] ⚙ `intake.md` records why the track exists: the request, the goal answers, the diagnosis, the named proposal and the learner's decision (starter pack, `intake.md` in this folder).
- [ ] The goal is an observable capability ("can do X"), in the learner's words, plus a concrete success criterion.
- [ ] The track serves the learner's stated goal, and the motivation for each section points back to it.
- [ ] Examples are clear and topic-native. Analogies to prior knowledge are used only where structurally accurate, with their break point stated.
- [ ] The scope is cut to the goal. Every node is needed for the goal or for a node that is.
- [ ] `README.md` states constraints and what is out of scope.

## Foundations
- [ ] The roots are unconditional truths **for this learner**: accepted at face value, no caveats.
- [ ] No root is a disguised theorem that derives from something simpler.
- [ ] Facts that need a caveat ("usually…") are derived nodes, not roots.
- [ ] Every derived node has a motivation: why we need it, and how someone could have discovered it.

## Map ⚙
- [ ] ⚙ `map.md` has a mermaid DAG and a node table in the parseable format of `tools/track-template/map.md` (`tools/learn map --track <t>` reads it): node ids are slugs, the table ids and the mermaid ids are the same set, the graph is acyclic, and every card/task node is in the map.
- [ ] 8–15 nodes. Bigger goals are split into a chain of tracks.
- [ ] Each node names how its mastery will be evidenced (a question type and/or a task).

## Accuracy
- [ ] The field and the APIs were researched with the `researcher` agent, not from memory.
- [ ] For libraries, the version and the API match the current official docs. Sources are listed in `RESOURCES.md` (Knowledge / Wisdom / Gaps) and pointed to from `README.md`.
- [ ] Every lesson page cites `RESOURCES.md` sources for its claims and names one primary source to read.

## Misconceptions ⚙
- [ ] ⚙ `misconceptions.md` defines `m-…` ids.
- [ ] Every risky node has ≥ 2 anticipated misconceptions (belief / why tempting / correction) **by the time it is taught**.

## Questions ⚙
- [ ] ⚙ Every option card has exactly one correct option and a misconception id on every distractor. New cards have at most 3 options; the fourth answer slot is always "Bilmiyorum".
- [ ] ⚙ No length tells, no justification inside options, no asymmetric bold.
- [ ] Each node gets several card types over time (MCQ → predict/spot-the-bug → recall/explain), and cards climb `cue` distance (`lesson` → `adjacent` → `far`). Confusable neighbours get `"mode": "discriminate"` cards.
- [ ] Every check applies the idea to a new case and is self-contained (tables, code, matrices inside the question).

## Practice ⚙
- [ ] A PRIMM task ladder is planned per code node (predict → investigate → modify → make).
- [ ] ⚙ Every task folder has `TASK.md` plus `test_*.py` (code) or `CHECK.md` (non-code).
- [ ] The tests were verified with `tools/learn verify-task` before handing the task over.
- [ ] Shortcut-hunted: the task can't be passed without the target node (no hard-coded output, no untaught construct, tests that check enough).

## Lessons ⚙
- [ ] `README.md` → "How this track teaches" says which nodes get a lesson page and which run as chat + task.
- [ ] ⚙ Lesson and reference pages load `../../../assets/` and quizzes carry `data-card` ids from `tools/learn cards --html` (required in new lessons, so the result line can be recorded).
- [ ] Anything a second lesson could reuse is a component in `assets/`, documented in the header of `components.js`.

## Learner fit
- [ ] Session-sized steps fit the time budget in `profile.md`.
- [ ] A beginner gets worked examples first and fading support.
- [ ] The plan was presented in plain language and the learner gave the go-ahead.
