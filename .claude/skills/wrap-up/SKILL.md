---
name: wrap-up
description: Close a learning session cleanly so the next one resumes exactly where this one stopped. Use when the learner says "bugünlük bu kadar", "bitir", "yoruldum", "sonra devam", or when the session reaches the learner's time budget.
---

# Wrap-up (about 5 minutes)

0. **Retest today's misses.** `tools/learn due --today-misses`. For each node listed, ask a **different** card (an existing one, or a fresh variant via `add-card`), graded normally. Never the same card: a fresh surface shows whether the fix took. In 5- and 15-minute sessions retest at most 2 nodes and put the rest in "Next step".
1. **Exit question.** Ask one concrete open question about today's most important node ("Kendi cümlelerinle: değişken nedir?"). Record it on that node's recall card, creating one with `add-card` if none exists. Don't store meta-questions like "bugün ne öğrendin?" as cards; they mean nothing when they come back days later.
1b. **The sort, once.** Show today's 2×2 (right/wrong × sure/unsure, page answers included) in one short table, with one line under it: what held, what was fragile. This is the only place the table appears.
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
   - `learner/profile.md` → Observed: run `tools/learn signals`. Add only patterns that hold across sessions (calibration, what kind of explanation landed, pace, strong and weak question types), each with a date and the evidence. Not a diary. If the entry mode changed today (band `up`/`down` held for the session), update "Entry mode (measured)" with the date.
   - **`tracks/<t>/inbox.md`**: every written answer was either graded in chat or used for the cheatsheet; every question was answered, became a map node (`map.md` + validate), or went to `learner/parking-lot.md`. Tell the learner in one line what happened to their question ("Sorduğun 'iki denge varsa' sorusunu Perşembe dersine koydum"). Then delete the handled sections.
   - **`learner/relationship.md`**: a decision they made today → "Kararları" with the date; something they told you about their life → "Hayatından" with its date; a "Hayatından" line whose date passed and was asked about → delete; a reaction to how you taught ("bunu sevdim", "böyle yapma") → "Ne iyi geldi / ne gelmedi".
3. **Tell the learner**, short. First the **position, three lines** (`engagement.md` → Position; from `tools/learn status` → Konum, re-run it now): where we are, which direction, what is next and why in one clause. Then one line: what they can do now that they couldn't before (concrete), and roughly how many review questions will be waiting (`tools/learn due --ahead 1 --limit 0` → `due_total`). End with the link to [learner/dashboard.html](learner/dashboard.html) ("panon güncel"). No paragraph, no praise.
4. **Close like a person.** Their name once. The `closing` from `relationship.md` only if the next session is really tomorrow (`rhythm`); otherwise the real next time ("Perşembe görüşürüz"). One personal forward look when there is a fact for it ("Cuma mülakat; Perşembe 15 dakika sesli prova yapalım mı?"). Never the same closing sentence as yesterday (the session log shows it).
4b. **Teaser.** If the session ended on a good note (and the last one didn't already end with a teaser), close with a one-sentence curious hint about the next node (`engagement.md` §3). Log it with `tools/learn moment --kind teaser`.
5. If 3+ new nodes reached `checked` since the last cheatsheet update, or a node reached `owned` that isn't in `cheatsheet.md` yet, offer the `cheatsheet` skill next time (not now; the session is over).
6. **After the goodbye, outside the learner's time:** build the next page (`docs/method.md`). Size it by `tools/learn status` → Tempo → `band`: `down` → one node, novice sections (worked → half → own), more checks; `hold` → 1–2 nodes; `up` → 2–3 nodes, expert sections only. If the next node(s) are knowledge-bearing, build the lesson now with the `lesson` skill, link it in `handoff.md` → "Next step" ("önce [0003-….html] oku, Kopyala ile bloğu getir"), and tell the learner in one line where it is. Next session then opens with the pasted block. Only a skill-heavy next step (a task) gets no page. If ≥ 4 cards will be due tomorrow (`due --ahead 1 --limit 0`), also build the mixed review page (`tools/learn due --html --ahead 1`) and link it first. A track whose organizer page (`0000-harita.html`) is missing gets it before any other page.
7. **Last, silently:** run `tools/learn refresh --quiet` so `learner/export.json`, the dashboard and the lessons' mini maps are current; don't mention it.

## Wrap-up lite (5-minute sessions)

Step 0 (cap 2), then append one session-log line to `handoff.md` and update "Next step" only if it changed. One warm line to close. Skip the rest.
