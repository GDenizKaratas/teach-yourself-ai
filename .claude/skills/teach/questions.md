# Question protocol

Used by `teach`, `review`, `task` and `new-track`. A question with a right answer is a measurement, so every graded question is stored, graded by the script and scheduled for spaced review.

## Why questions matter this much

- **Retrieval practice and spacing** are the two best-established learning effects. A question asked once and never again wastes most of its value, which is why every graded question becomes a card.
- **Which wrong option they chose is diagnostic.** Each distractor encodes one specific misconception, so a wrong choice tells you *what* they believe, not just that they're wrong.
- **Wrong options can teach the wrong thing** if no feedback follows. Always give feedback right after the answer.
- **Confidence matters.** A high-confidence error is a "hypercorrection" moment: corrected well, it sticks better than anything else. A correct guess is not evidence of knowledge.

## Card types

| type | use for | graded by |
|---|---|---|
| `mcq` | diagnosis, distinguishing near-neighbors | script |
| `predict-output` | "what does this code print?" (options are possible outputs) | script |
| `spot-the-bug` | "which line is wrong?" / "why does this fail?" | script |
| `recall` | "what is X?" in their own words (generation beats recognition) | you, against `answer` |
| `explain` | "why does…?", connect two nodes | you, against `answer` |

Mix them. Multiple-choice is efficient for locating edges. Open recall/explain locks things in harder. Once a node is checked, prefer open types in later reviews.

Optional card fields: `"cue"` (`lesson` = the context it was taught in, the default; `adjacent` = new surface, same kind of situation; `far` = a situation that doesn't name the node, so the learner must recognize which idea applies) and `"mode"` (`recall` = the idea comes to mind; `discriminate` = it wins against a confusable neighbour; `compose` = it runs as one step of a longer chain). `review` uses them to climb.

## What a check must be

- **Apply, don't paraphrase.** A check puts the idea to work on a case the learner hasn't seen: predict, apply, spot what breaks. Never ask them to recognize the sentence you just said; that measures reading, not understanding.
- **Answerable from what was covered.** If they have no route to it, it's a coin flip, not a check.
- **Self-contained.** Every table, matrix, code snippet or definition the question depends on goes inside the question text (or the option `preview`), never only in earlier chat. Reviews come back days later, without that chat.

## Building multiple-choice options (construction procedure)

Don't audit options after the fact. **Build them so that the correct one can't stand out:**

1. **Every option is a bare claim, with no justification anywhere.** The number-one giveaway is the correct option carrying its own reasoning ("…, because…") while the distractors are bare. All reasoning goes in `explanation`, which the learner sees only after answering.
2. **Commit before posing.** Solve the question yourself and write the correct answer plus why each distractor is wrong (that's `explanation`) *before* the card exists. If you can't, the question isn't ready.
3. **Write the correct claim first, then mutate it into each distractor.** Take one specific misconception or easily confused neighbor and state what someone holding it would claim, in the *same* skeleton, length, and register. Parallelism then comes for free.
4. **Each distractor is a real error this learner might make**, so which one they pick is diagnostic. Make it tempting, not tricky. It must be unambiguously wrong on the intended reading.
5. **Each distractor carries a `misconception` id** (`m-…`) defined in the track's `misconceptions.md`. If the id doesn't exist, add it there first: belief / why tempting / correction / `seen: anticipated`.
6. **No asymmetric bolding or formatting.**
7. **2–3 options.** The fourth answer slot is always `Bilmiyorum` (see step 2 below).

If you can tell which option is right by reading the set cold without knowing the material, regenerate it. Don't patch.

## The flow (always these steps)

**1. Store the card first:**

```bash
tools/learn add-card --track <track> <<'EOF'
{"node": "<map node id>", "type": "mcq",
 "prompt": "…", "code": "optional code shown with the question",
 "options": [
   {"text": "…", "correct": true},
   {"text": "…", "misconception": "m-…"},
   {"text": "…", "misconception": "m-…"}
 ],
 "explanation": "why the right one is right, and why each tempting one is wrong, in terms of the foundations"}
EOF
```

For `recall`/`explain`: no `options`, but include `"answer": "reference answer"`.

For `predict-output` and every code-behavior claim, **run the code first** (`uv run python -c "…"`) and take the correct option from the real output. Never use memory for this.

The script validates the card, **shuffles the options** (you never choose where the correct one sits), assigns an id, and returns the public view with letters A–D. If it rejects the card, fix the card and retry. Treat warnings as tells, and regenerate.

**2. Ask with AskUserQuestion**, in the returned order:

- Question 1 is the question itself. Use the option labels `"A) <text>"` exactly as returned, then add **`Bilmiyorum`** as the last option. (An old card with 4 options has no free slot: the learner can type "bilmiyorum" in "Other".) If an option has code or is long, put the full question, code and options in your chat message first and use the labels `"A"`, `"B"`, … For "which code is correct" questions, use the `preview` field to show each option's code. Anything the question depends on goes in the question or `preview` too, not only in chat.
- Question 2 is confidence, in the same call (in `teach` checks; optional in quick `review` warm-ups): "Ne kadar eminsin?" with the options `Tahmin ettim` / `Emin değilim` / `Eminim`, which map to `--confidence 1/2/3`. **Pass `--confidence` only when you asked**; omitted means "not asked", which is honest. Never invent a 2.
- **Never** add "(Recommended)" to any option, and never hint.
- For `recall`/`explain`, ask in plain chat ("Kendi cümlelerinle: …") and let them type.

**3. Grade through the script:**

```bash
tools/learn record --card <id> --choice <A-D> [--confidence <1-3>] [--answer-text "<their one-line why>"]
tools/learn record --card <id> --dont-know          # they chose "Bilmiyorum" (or typed it in "Other"); ignore any confidence answer
# open answers: --correct yes|partial|no --answer-text "<their words>" [--misconception m-…]
```

If they typed something else in "Other", judge whether it matches an option or reasoning, and say what you decided.

**"Neden?" (one line, only here).** Before revealing, ask "Neden? Tek satırla." when: (a) the answer is wrong and they said `Eminim`, (b) it's right and they said `Tahmin ettim`, or (c) it's the first check on this node. (Option cards only; open answers already carry their words.) Store their line with `--answer-text`. Never more than one line, and never on other questions: it's a probe of their model, not a toll.

**4. Feedback, immediately and briefly:**

- Correct: ✓, then one sentence connecting it to the foundation it rests on. If the `flag` says they guessed, say a guess counts as not-yet-known, and plan a different question on this node soon.
- Wrong: ✗, the correct answer, then **name the belief behind their choice** (from the misconception, or from their "neden?" line) and why it's tempting. Show which foundation it contradicts. On a high-confidence error, dislodge that model before moving on.
- Bilmiyorum: no ✗. It located the edge; teach the step, then ask a different card later.
- Then return to the node with a **different** question later in the session. Never repeat the same card in the same session.

**5. Update `misconceptions.md`.** Switch `seen: anticipated` to `observed` when a learner actually holds it. Add new ones you diagnosed from open answers.

## Predict questions ("Tahminin ne?")

A guess *before* teaching a step, rare and optional (when to use one is in `teach`). Store it as a normal card, ask it the same way, framed as a guess ("Henüz anlatmadım, tahminin ne?"), and record with `--source predict`: diagnostic only, never rescheduled, never mastery. No confidence, no ✓/✗ tone; the teaching that follows opens by resolving the guess.
