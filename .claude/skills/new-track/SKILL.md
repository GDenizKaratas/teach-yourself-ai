---
name: new-track
description: Design a new learning track (any topic) to the repo's quality standard. Opens with the starter pack (goal batch, critical follow-ups, diagnosis, a named track proposal, go-ahead), then prerequisite check, research, unconditional truths, dependency map, misconception inventory, task ladder, validation, and the learner's go-ahead. Use when the learner wants to learn something new ("X öğrenmek istiyorum", "yeni konu", "start", "başla") or when a planned next track (e.g. after python-basics) is about to start.
---

# New track

A track is one coherent learning path toward one concrete capability. Every track, whatever the topic, is built to the same standard (`standard.md` in this folder), and `tools/learn validate` checks the mechanical parts.

## 0. Starter pack first, folder after the go-ahead

The topic the learner names is a request, not yet the track. Run the starter pack in `intake.md` (this folder): goal batch → critical follow-ups → diagnosis and a named proposal → the learner's go-ahead. Never open a track straight from a topic name. Only after the go-ahead:

```bash
tools/learn new-track <kebab-name> --title "<Human title>"
```

then fill the new track's `intake.md` (request, answers, diagnosis, proposal, decision).

## 1. Goal (from the intake; sharpen, don't re-interview)

The starter pack already asked the goal questions. Carry the answers over; ask again only what is still missing. What the goal must contain:

- What do they want to be able to **do**? Push until it's concrete and observable. "Lineer cebir öğrenmek" is not a goal. "Bir matrisin neden ve ne zaman tersinir olduğunu açıklayıp hesaplayabilmek" is. "Bir kütüphaneyi öğrenmek" is not a goal. "O kütüphaneyle kendi verimi açıp tek bir analizi baştan sona yapabilmek" is.
- Why? What real situation will they use it in? This decides the scope and keeps the motivation visible.
- Time budget and deadline, if any.

- **Constraints** (session length, background to lean on, language rule) and **out of scope** (adjacent topics they explicitly don't chase now). Out-of-scope protects the zone of proximal development and gives you a place to send tangents.

Write the answers into the track's `README.md` (goal in their words, a concrete success criterion, constraints, out of scope).

## 2. Prerequisites and order

- What does this goal depend on? Compare against existing tracks (`tools/learn progress`).
- If a prerequisite is missing, propose doing it first as its own track, or as a short opening section, and **scope the prerequisite to the goal**. Example: Python as a prerequisite for a data-analysis library needs variables, types, lists, dicts, loops, functions, imports, files/paths, arrays and reading errors. It doesn't need classes, decorators or web frameworks.
- **Scope by how the skill will really be used.** Ask yourself what the learner will do with their own judgment in the real setting, and what tools (including AI assistants) will produce for them. Teach the first deeply: reading, understanding, running, verifying, debugging, interpreting results, and knowing when output is wrong. Teach the second only as far as they need to check it. Rote production of things a tool reliably produces is low value. Understanding what the tool produced is high value.
- **Touch the goal early.** Long prerequisite chains kill motivation. Order tracks so the learner reaches a first real step toward the goal as soon as the foundations allow. Before that, show now and then where the current node will be used in the goal (`teach/engagement.md`).
- Big goals split into a chain of tracks of roughly 8–15 nodes each.

## 3. Research (researcher subagent, always)

Launch the `researcher` agent **in the background** with a precise brief, and keep talking with the learner meanwhile:

- the field's real first principles and standard teaching order;
- **common beginner misconceptions** (education research, official tutorials' FAQ, forums);
- for libraries: the **current stable API and version** from the official docs (the `stable` docs, not a blog), plus what changed recently, deprecated functions to avoid, and the datasets available for practice;
- canonical beginner pitfalls and error messages.

- **trusted sources and communities** for the track's `RESOURCES.md`: 5–10 high-trust Knowledge sources (primary texts, official docs, lecture series, encyclopedias) each with one line on what it covers and when to reach for it; 2–3 moderated communities (Wisdom) where the learner can test their work on real people; and explicit **Gaps** (what the goal needs and no good source was found for).

Don't plan from memory. Write the researcher's sources into `RESOURCES.md` and point to it from `README.md` under "Sources". Lessons cite from `RESOURCES.md`; a claim with no source there doesn't go into a lesson.

## 4. Build the track, incrementally

Build the **outline** now and the **details** just in time. The learner shouldn't wait 20 minutes on day 1.

- **`map.md`, now:** all nodes as a mermaid DAG plus a node table (one-line statement, a learner-facing `tanım (öğrenci)` in the learner's language, dependencies, how mastery will be evidenced), in the format of `tools/track-template/map.md` so `tools/learn map` can parse it. Unconditional truths are the roots and the goal is the sink. Stress-test every root: is it truly unconditional for this learner?
- **Details for the first 2–3 nodes only:** their misconceptions in `misconceptions.md` (belief / why tempting / correction / `seen: anticipated`) and their first task idea. Add the next nodes' details as teaching reaches them, usually at the end of a session for the next one.
- **Task ladder** in `README.md`: a short list of planned tasks per node. Create task folders only when you reach them.
- **Lesson ratio** in `README.md` → "How this track teaches": which nodes are knowledge-heavy and get an HTML lesson page as pre-reading (`lesson` skill), which are skill-heavy and run as chat + task, and which `assets/` components carry the simulations (payoff matrix, truth table, or a new one). A history or definitions track leans to lessons; a proof-writing or coding track leans to tasks.
- **Probe:** only if the learner has some experience. Write probe cards one at a time as you ask them. An unasked card on a node nobody has worked on is never scheduled, and a complete beginner gets no probe.

Run `tools/learn validate --track <name>` until there are no errors. Treat warnings as defects to fix.

## 5. Check against `standard.md`, then present

Go through the checklist in `standard.md` honestly. Then present the plan to the learner in their language: what we'll learn, in what order, why that order, and what they'll be able to do at the end. Keep it simple for a beginner. **Wait for their go-ahead**, then hand over to `teach`.

Write `handoff.md` → "Next step".
