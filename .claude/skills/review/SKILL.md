---
name: review
description: Spaced-repetition review of cards that are due. Use at the start of a session when `tools/learn status` shows cards due, when the learner says "tekrar", "tekrar yapalım", "soru sor", "hatırlatma", or as interleaved retrieval in the middle of a lesson.
---

# Review

The goal is retrieval spread over time, the most reliable way to make learning last. Keep it brisk: a warm-up is **at most 2–3 short cards**, a few minutes. It is a reminder, not a lesson. Cards left due roll over to the next session; the scheduler handles that.

## Flow

1. `tools/learn due --limit 3`. The script returns at most one card per node (mastery is per node), most overdue first, interleaving tracks. Keep its order. A handoff may name one card it wants first; the rest come from the script. A correct answer moves the node's other due cards forward by itself.
2. Say one line to frame it ("Önce kısa bir ısınma: 2 soru."). Nothing more.
3. Ask each card with the question protocol (`.claude/skills/teach/questions.md`, steps 2–4). The card is already stored, so skip `add-card` and go straight to asking and `record`. Confidence is optional here; pass `--confidence` only if you asked.
4. **One answer turn per card.** Grade what they gave, as given: missing parts (no reason, no computed values) make it `partial`. Record it, with `--misconception` when you can name it, then give a 1–2 sentence correction and go to the next card. No follow-up rounds in the warm-up; the gap becomes a variant card (below), not a second question now.
5. After the batch, give one sentence: what held and what slipped. No scores and no grades.

## When a card goes wrong

- **Cheatsheet first.** If the node is already in `cheatsheet.md`, send them there ([section](…)), then let them try a variant. Log it with `tools/learn moment --kind cheatsheet`. This builds the habit of using their own reference.

- **Re-teach small, from the foundation.** Restate the unconditional truth the node rests on and re-derive the step, in 2–3 sentences, without asking anything back. If the node needs more than that, note it in `handoff.md` under "Next step" and let `teach` handle it properly. Don't hijack the warm-up.
- **Add a fresh variant card** for the same node with `add-card` only for a real miss: a wrong answer, or a partial that shows a wrong model or a new misconception. Different surface, same idea; target the misconception. A partial that only skipped a reason or a value needs no new card: the `record` (with `--answer-text`) keeps it on file and the same card comes back sooner. More cards per node only grow the backlog. Ask the variant later in the session as interleaved retrieval, or let it come due on a later day, not right now.
- If the same node has failed twice across sessions (`tools/learn progress` shows `struggling`, `slipping` or rising lapses), the foundation under it is probably wrong. Flag it in `handoff.md`, and next time probe the node it depends on.

## Avoiding "memorized the question": climb the cue distance

After a card has been answered correctly twice, the learner may be recognizing the wording rather than knowing the idea. Instead of asking it again:

- write a **transfer card** one step further from how it was taught: `lesson` → `"cue": "adjacent"` (new surface, same kind of situation) → `"cue": "far"` (a situation that never names the node; they must recognize which idea applies). The prompt never announces the target;
- `tools/learn retire --card <old> --reason "replaced by transfer card <new>"`.

**Confusable neighbours** (two nodes the learner mixes up, or a misconception that is really the other node): write a `"mode": "discriminate"` card, near-twin situations where one feature decides which idea applies, the distractor being the neighbour's answer.

Prefer open `recall`/`explain`/`predict-output` types for nodes that are already checked, and always when `tools/learn signals` shows a high `generation_gap` (they recognize much better than they produce). Tag every new card with `cue` and `mode` (`questions.md` → Card types).

## A lesson result line is pasted ("ders sonucu 0003: pts-010=B …")

That comes from a lesson page's quiz. Record each with `tools/learn record --card <id> --choice <letter> --source lesson` (diagnostic only: no rescheduling, no mastery). Say in one line what slipped, then **ask a different card on each missed node in chat**, graded normally. Details in the `lesson` skill.

## A 5-minute day ("sadece tekrar")

Review is the whole session: 2–3 due cards, then wrap-up lite (`wrap-up`). No new material.

## Mid-lesson use

`teach` asks for one old question every 2–3 new nodes. Pick a due or soon-due card from an *earlier* node (`tools/learn due --limit 3`). If nothing is due, write a fresh question on an earlier node.
