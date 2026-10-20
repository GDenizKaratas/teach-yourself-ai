---
name: wrap-up
description: Close a learning session cleanly so the next one resumes exactly where this one stopped. Use when the learner says "bugünlük bu kadar", "bitir", "yoruldum", "sonra devam", or when the session reaches the learner's time budget.
---

# Wrap-up (about 5 minutes)

0. **Retest today's misses.** `tools/learn due --today-misses`. For each node listed, ask a **different** card (an existing one, or a fresh variant via `add-card`), graded normally. Never the same card: a fresh surface shows whether the fix took. In 5- and 15-minute sessions retest at most 2 nodes and put the rest in "Next step".
1. **Exit question.** Ask one concrete open question about today's most important node ("Kendi cümlelerinle: değişken nedir?"). Record it on that node's recall card, creating one with `add-card` if none exists. Don't store meta-questions like "bugün ne öğrendin?" as cards; they mean nothing when they come back days later.
2. **Update the files.** Do this silently; don't narrate it:
   - `tracks/<t>/handoff.md`:
     - **Next step**: exactly what to do first next time (node, task, or question to revisit). Be specific enough that a fresh session can start without asking anything. This is the **only** resume point; don't write one into `profile.md` or anywhere else.
     - **Öğrenci için**: replace this section's content with ONE warm sentence in the learner's language saying what comes next ("Sıradaki: oyun türlerinden dengeye geçiyoruz."). The dashboard shows it to the learner, so no card ids, no answers, no tutor notes. Create the section above "Session log" if the file doesn't have it yet.
     - **Session log**: *append* one line, newest first (`- 2026-10-09 · 40 dk · nodes: … · task 02 passed · note: …`). Don't overwrite the history; it's how the next session and the mentor see the trajectory.
     - **Open questions**: doubts the learner raised that weren't resolved.
   - If the next session reaches new nodes, prepare their details now (misconceptions, a first task idea). See `new-track` §4.
   - **Map revision.** Did today show a missing foundation (a node failed because something under it isn't held) or a node they already hold cold? Then fix `map.md` (node table and mermaid together), run `tools/learn validate --track <t>`, and put the why in the session-log line.
   - `glossary.md`: terms that came up today.
   - **Notes for every node that reached done** (retained / owned; `tools/learn status` → "Notes gaps" lists them): a `## <node id>` section in `cheatsheet.md` in the cheatsheet skill's shape, from the learner's own recorded answers (`answer_text` in attempts: their wording) and their recorded misconception. Next session, when time allows, let them read it and correct it in their words (cheatsheet skill). A new map node always gets its `tanım (öğrenci)`. The dashboard's node card shows both, so a gap is visible to the learner.
   - `misconceptions.md`: observed / new.
   - `learner/profile.md` → Observed: run `tools/learn signals`. Add only patterns that hold across sessions (calibration, what kind of explanation landed, pace, strong and weak question types), each with a date and the evidence. Not a diary.
3. **Tell the learner** in 2–3 lines (end with the link to [learner/dashboard.html](learner/dashboard.html): "panon güncel"): what they can do now that they couldn't before (concrete), what comes next time, and roughly how many review questions will be waiting (`tools/learn due --ahead 1 --limit 0` → `due_total`). End warmly but without empty praise.
4. **Teaser.** If the session ended on a good note (and the last one didn't already end with a teaser), close with a one-sentence curious hint about the next node (`engagement.md` §3). Log it with `tools/learn moment --kind teaser`.
5. If 3+ new nodes reached `checked` since the last cheatsheet update, or a node reached `owned` that isn't in `cheatsheet.md` yet, offer the `cheatsheet` skill next time (not now; the session is over).
6. **After the goodbye, outside the learner's time:** if the track's README gives the next node(s) a lesson page (pre-reading), build it now with the `lesson` skill, link it in `handoff.md` → "Next step" ("önce [0003-….html] oku, sonra sohbette kontrol"), and tell the learner in one line where it is. Next session then opens with graded checks on it instead of narration.
7. **Last, silently:** run `tools/learn refresh --quiet` so `learner/export.json`, the dashboard and the lessons' mini maps are current; don't mention it.

## Wrap-up lite (5-minute sessions)

Step 0 (cap 2), then append one session-log line to `handoff.md` and update "Next step" only if it changed. One warm line to close. Skip the rest.
