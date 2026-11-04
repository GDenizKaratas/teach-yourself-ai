# The method (single source for how a day is shaped)

This page decides the *shape* of learning in this repo. `CLAUDE.md` and the skills point here; where a skill and this page disagree, this page wins. The pedagogy *inside* a step (unconditional truths, motivated discovery, the question protocol) stays in `teach/SKILL.md`.

Why it is shaped this way (the short version of a 2026-11-04 two-expert review of this repo against a breadth-first study set): for durability the literature rewards **retrieval spread over time** (testing effect, spacing: Roediger & Karpicke 2006; Cepeda et al. 2006; Dunlosky et al. 2013) and **generation before reveal** (Kornell, Hays & Bjork 2009), not sequential mastery gates; for learners who already hold a schema, long guided sequences backfire (expertise reversal, Kalyuga et al. 2003), while for true beginners bare problems backfire (worked-example effect, Sweller & Cooper 1985). So: **breadth first, criterion later, and the entry gate depends on what the learner already holds.**

## The five layers

0. **Organizer (unscored, 1–2 h).** The whole map on one page: every node in two plain sentences plus one hook question ("why would anyone need this?"). No grading. It gives the brain a place to hang everything that follows (advance organizer; Ausubel 1960, Mayer 1979). → `lessons/0000-harita.html` (`tools/organizer-template.html`).
1. **Reasoned-correct, then move on.** A node is `checked` once the learner answers at least one **generative** question on it (recall / explain / predict-output; an MCQ alone is not a gate) with a one-line "neden?". Then move to the next node. Don't camp on a node; durability comes from layer 4, not from sitting here.
2. **Bridged depth.** Each node returns in a harder context, and the page says explicitly which earlier idea it builds on ("Step 2'deki cache → prompt caching"). Transfer does not happen by itself; the analogy has to be pointed at (Gick & Holyoak 1980/83). Every node also gets a "mülakatta tek cümle" in the learner's own words (cheatsheet).
3. **Compound cases, write before reveal.** Multi-node problems (a design case, a proof, a program): the learner writes their answer, *then* sees the model answer, then ticks a checklist and notes what they missed. Some are timed and spoken (60 s / 45 min) when the goal is an interview or a talk.
4. **Time and mixing — where learning actually becomes durable.**
   - **Append-only record.** Every answer is kept; a retry is a new attempt, never an overwrite.
   - **Delayed retest.** A node is `retained` only after a correct answer on a *different day*; `owned` after a far-cue or task success; `durable` after three spread days. Nothing is "done" after one correct answer.
   - **Mixed review.** Due cards from all tracks, interleaved, with no topic names on the page (`tools/learn due --html`).
   - **Calibration.** Confidence on every answer; the dashboard shows "when you say 'eminim' you are right N% of the time".

**Rule: speed is won by removing friction, never by removing measurement.** A fast session with no confidence, no record and no delayed retest is a fluency illusion (Koriat & Bjork 2005; Soderstrom & Bjork 2015).

## Two entry modes, one engine

The engine (cards, SRS, attempts, misconception-tagged distractors, hypercorrection flags, calibration signals, the learner's own questions feeding the map) never changes. What changes with the learner's measured level is the **shape of the day**.

**How the mode is set.** Not from the intake. After the organizer page, three easy *generative* questions in chat: 0–1 right → **novice day**; 2–3 right → **expert day**. Record it in `learner/profile.md` → "Entry mode (measured)" with the date and evidence. It is per track (a strong programmer can be a novice in proofs).

**How it moves.** `tools/learn signals` → `band` = accuracy over the last 10 scheduled answers. `< 0.5` → step down (smaller steps, worked example first, more hints). `> 0.95` with n ≥ 10 → step up (skip the exposition, probe, go to cases). Otherwise hold. The healthy band for practice is roughly 70–85% correct: below it the learner is drowning, above it they are coasting.

### Novice day (no prior schema in this kind of thinking)

1. **Read** the lesson page: motivation → the unconditional truth → **a fully worked example → a half-worked example the learner completes → "kendin yap"** → one check per step. Generous hints. (`lesson` skill, novice sections of the template.)
2. **Paste** the result block. The teacher reads it with one command (`record-lesson`), then speaks only to the wrong+sure items and 1–2 of the written answers.
3. **Climb** in chat: a few questions rising from recognition to own-words, inside the 70–85% band; drop a level the moment it falls below 50%.
4. **Do** a small task (PRIMM order for code).
5. **Wrap-up** builds the next page; the next page opens with a warm-up from an earlier node.

**Hard rule for a novice: no graded question before a page has been read on that node.** A battery of unanswerable questions is not pretesting; it is demoralizing and tells us nothing (pretesting works as 1–2 hooks with immediate feedback, Richland, Kornell & Kao 2009 — not as a diagnostic exam).

### Expert day (schema present: a working engineer learning system design, a mathematician learning Python)

1. **Read** a short page (or skip it when the organizer already covered the node).
2. **Probe**: 3–5 generative questions in chat, with confidence. Right → the node is `checked`, move on. Wrong+sure → a short targeted explanation and a variant question (hypercorrection moment).
3. **Compound case** (layer 3), written before the model answer.
4. **Wrap-up** builds the next page, which may cover 2–3 nodes.

## The day, in one line each

| | novice | expert |
|---|---|---|
| before chat | organizer, then one page (worked → half → own) | organizer, then a short page or none |
| opening | paste the block; wrong+sure first | 3–5 generative probes |
| gate to the next node | one generative check right + "neden?" | same |
| chat cost per question | 1 turn | 1 turn |
| when it feels too hard | step down the band: worked example, smaller step | add a page |
| when it feels easy | step up: skip exposition, probe | go to cases |
| later days | mixed review page; delayed retest decides retained/owned | same |

## What never changes, whatever the mode

- Every graded question is a card and returns in spaced review; a lesson-page answer with confidence is scheduled like a chat answer (`record-lesson`).
- Confidence on every answer; wrong+sure is the first thing discussed.
- The 2×2 sort (right/wrong × sure/unsure) is shown **once, at the end of the session**, not after every block.
- The learner's questions (the page's "sormak istediğim" box, chat) are answered and, when they reveal a missing node, change the map. The learner's own resources are welcome (`resource` skill).
- The relationship layer (`learner/relationship.md`): how they want to be addressed, their decisions, what is going on in their life, one evidence-based piece of advice per session at most, one "yanında olma" sentence at most, none while they struggle.

## How to know the method is working (not just feeling fast)

Four tests, every couple of weeks: (1) rewrite a case from a week ago with the draft hidden; (2) a case never seen; (3) a timed, spoken answer; (4) confidence before, accuracy after. `signals` tracks the numbers: `generation_gap`, `delayed_recall`, `band`, calibration. Save a baseline on day one (`tools/learn signals > docs/baseline-<date>.md`) and compare against it.
