---
name: lesson
description: Build a short, beautiful, cited HTML lesson (or a printable reference page) for one node cluster of the active track, from the shared components in assets/. Use when a node is knowledge-heavy and the track's README says it gets a lesson, when the learner says "ders sayfası", "okuyacak bir şey ver", "yazılı anlat", at wrap-up to prepare the next session's pre-reading, or when a lesson quiz result line ("ders sonucu …") is pasted into chat.
---

# Lesson

A lesson is one self-contained HTML page in `tracks/<t>/lessons/NNNN-<slug>.html`, short enough to finish in 10–15 minutes, teaching one tightly scoped cluster of nodes (1–3) tied to the learner's goal. It is the **expository channel** of this system, adapted from Matt Pocock's `teach` skill: knowledge arrives here with low difficulty, beauty, citations and interactive simulations. **Measurement stays in chat**: every graded question still goes through `tools/learn` and `AskUserQuestion` (`teach/questions.md`). The lesson's in-page quiz is retrieval practice plus a diagnostic signal, not a grade.

## Two uses, decided per track in its README ("How this track teaches")

- **Pre-reading (flipped).** At wrap-up, after the goodbye, build the lesson for the next node(s). The learner reads it alone before the next session; that session opens with graded checks in chat on exactly those nodes. Best for knowledge-heavy nodes (history, definitions, mechanisms) and for short sessions: the 15 minutes go to retrieval, not to narration.
- **Consolidation.** After a cluster reached `checked` in chat, build the lesson as the durable record the learner returns to. Best when the chat covered a lot of ground or when a simulation would make the idea concrete.

Skill-heavy nodes (writing a proof, writing code) get no *pre-reading* lesson: chat + `task`. Don't produce a pre-reading lesson because you can; produce it because this node reads better than it talks. Separately, every done node ends up in one **consolidation** lesson per cluster of 2–4 nodes (written after the cluster is done; `status` → Notes gaps lists the missing ones), so the learner has one page to return to.

## Before writing

1. Read the track's `README.md` (goal, constraints, language rule), `map.md` (the nodes, their dependencies, the unconditional truths underneath), `misconceptions.md`, `RESOURCES.md`, `glossary.md`, and `learner/profile.md` → Observed (what lands for this learner).
2. Read `assets/components.js` (the header lists every component and its data format) and any existing lesson in the track, so the new one looks like the same course and reuses the components.
3. **Ground every claim.** Facts, dates, quotes, numbers and API behavior come from `RESOURCES.md` sources or from the `researcher` agent; never from memory. If a needed source isn't in `RESOURCES.md`, find one and add it there (Knowledge) first. A lesson with no citations is the model teaching from memory.
4. Get the cards: `tools/learn cards --track <t> --node <n> [--node <n2>]`. If the cluster has no cards yet, write them with `add-card` first (they are the questions the chat will ask too). `--html` emits the quiz skeletons in the stored (shuffled) order.

## Structure (same skeleton every time; see `tools/lesson-template.html`)

A lesson is the dashboard's **lesson mode**: same app, same visual language, one step then one check.

1. **Top bar** (`<header class="lesson-bar">`, sticky): `← Pano` (relative link `../../../learner/dashboard.html`), `TEACH · <track title from README> · DERS N`, the step chip and `◐ Tema` (same `teach-theme` preference and `?theme=light|dark` as the dashboard). `components.js` fills the chip ("ADIM 3 · <step title>", updated while scrolling; no "3/6" fractions anywhere) and the thin progress line. Copy the block from the template; change only the track title and N. The dashboard shows lessons inside its own shell (course tab → lesson tab → the lesson in an iframe, `?embed=1&theme=…`); there `components.js` adds `<html class="embed">`, which hides `← Pano`, the title and `◐ Tema` (the shell has them), keeps the step chip, progress line and result bar, follows the dashboard's theme, and hands links to other lessons / `reference/` pages to the shell. Nothing to add per lesson; never break the standalone page.
2. **Kicker + title + subtitle** (the question the lesson answers), then the **goal card** (`<section class="goal">`): "Bu dersin sonunda: …" = one observable outcome ("… bulabileceksin."), duration and links to the track's `reference/` pages (no step / check counts: the chip already shows progress; inside the dashboard the links are hidden because the notes column has them). Learner-facing rules everywhere: no scores or fractions (the one % is the dashboard's memory-freshness share), no %-progress in lessons, no empty-state filler, every label in the fewest words; yellow only on the next node of a map.
3. **Mini map**: write only the comment and an empty SVG inside the slot: `<!-- lesson-map: --track <t> --nodes <a>,<b>[,<c>] -->` then `<div class="lmap-slot" data-track data-nodes><svg class="lmap"></svg></div>` (no caption). `tools/learn refresh` fills the SVG from the comment (it runs automatically after your edit) and keeps it current as the learner progresses; never hand-edit or paste it. `--nodes` = the lesson's 1–3 nodes, drawn with solid ink borders; the only yellow node is the track's real next node. An old `--current` flag is accepted and ignored. Until it is filled the page shows plain node chips. On wide screens the slot sits fixed in the right margin; inside the dashboard it is hidden (the Harita tab shows the map).
4. **Steps**: every section is a `<section class="step" data-title="Short name">` with one `h2`. JS writes "ADIM i" above each `h2`. Order:
   - **Warm-up** (from lesson 2 on): one quiz on an *earlier* node. Retrieval across time.
   - **Motivation**: why are we doing this, what problem sends us here (Principle ii in `teach`). A story, a case, a failing example. A purely motivating step may end without a check.
   - **The unconditional truth(s)** this cluster rests on, stated plainly, then the derived step(s). One idea per step; make the dependency on earlier nodes explicit.
   - **Do it**: an interactive component (`payoff-game` in `nash` mode, `truth-table`, or a new component in `assets/`) where the learner acts before the answer is shown. "Önce kendin dene" before any reveal button. These widgets are unbound practice; they don't replace the step's check.
   - **Model changes / variant**: one twist that shows which detail carries the result, its explanation inside `<details class="recall">` so they commit first.
   - **Transfer to the goal**: where this exact idea shows up in the learner's goal (`README.md`), then a **mini görev** they bring to chat (it becomes a `task`).
   - **Geri çağırma**: only 1–2 items (a card quiz or a `cards --html` `<details class="recall" data-card>`), `<div class="score"></div>`, and the "Yarın için" `<details class="recall">`.
5. **Step → check rhythm**: every teaching step ends with exactly **one** short check: a card quiz `<div class="quiz check" data-card="…" data-answer="N" data-label="Kontrol">` from `cards --html`, on that step's idea. If no card fits the step, write the card first (`add-card`), never a hand-made quiz. After the first answered card quiz a sticky **result bar** appears at the bottom ("2/4 cevaplandı · Kopyala → sohbete yapıştır" + the result line so far); the full line also appears in `.score` once every card quiz is answered.
6. After the last step: the **primary source** block (one high-trust source, what to read and how long), the **ask-your-teacher** block, numbered **references**, and **lesson-nav** links to the previous and next lesson.

Side remarks are **inline collapsible notes**, never floating: `<details class="note"><summary>Short title</summary><p>…</p></details>` (CSS adds the "NOT" chip). The old `.sidenote` still renders (inline, no float) but don't use it in new lessons.

Keep it inside working memory: ~15 minutes, 1–3 nodes, one tangible win. Think Tufte: typography does the work, no decoration.

## Rules

- **Quizzes come from cards only.** Every quiz in a new lesson carries its `data-card` id (validate warns without it): that id is what lets the pasted result line be recorded with `--source lesson`. Keep the stored option order from `tools/learn cards --html`. Never hand-order options; never make the correct one longer or the only reasoned one. Write every `data-why` in the learner's language: for the correct option, the one-line reason from `explanation`; for a distractor, the belief behind it and what breaks it (from `misconceptions.md`).
- **Quiz card markup** is only the `cards --html` skeleton: `<div class="quiz" data-card="ID" data-answer="N">` with `.q`, `.opts > button.opt[data-why]`, `.feedback`. Optional `data-label="Tahmin"` changes the card's mono label (default "Soru"). `components.js` adds the rest itself on every `data-card` quiz: radio rows, a dashed "Bilmiyorum" row (always last), a 3-level confidence selector (Tahmin = 1, Emin değilim = 2, Eminim = 3), an optional one-line "Neden?" input and a "Cevapla" button; after answering it shows the same correct/incorrect feedback. Never hand-write those controls. Quizzes without `data-card` keep the old click-to-answer behaviour, are labelled "Alıştırma", and never appear in the result line; they exist only in 0001–0002, where no card covered that idea yet. Don't add new ones.
- **Math (opt-in, offline)**: if the lesson needs formulas, keep the three KaTeX lines from the template's `<head>` (`../../../assets/vendor/katex/…`) and write `\( … \)` inline, `\[ … \]` or `$$ … $$` for display. No single `$`. Without those lines the source text stays readable. Lessons without math drop the three lines.
- **Diagrams**: hand-written inline SVG in the plan style, never images or libraries: `<figure class="diagram-wrap"><svg class="diagram" viewBox="…" role="img" aria-label="…">` with `<g class="node [visited|current|dim]"><rect …/><text x y>…</text></g>` (text x,y = box centre) and `<path class="edge [dim] [dashed]" d="…"/>` (arrowheads automatic), plus a `<figcaption>`. `current` (bold ink outline) marks only this lesson's node or the step being discussed; `visited` = earlier nodes, `dim` = later ones. Colours come from tokens, so one SVG works in light and dark. Full convention: the "Diyagram" section of `assets/style.css`.
- **Look**: the shared `assets/style.css` (LearnHarness visual language: mono uppercase labels, sans prose, serif titles, black / white / grey only; yellow is reserved for the highlighted next node in map DAGs (lesson-map, dashboard maps); red only marks a wrongly chosen quiz option, and the correct option is shown white-filled). Use its classes and tokens (`var(--muted)` etc., listed at the top of the file); no inline colours or fonts.
- **Terms per `glossary.md`**, following the track's language rule (e.g. English term first, Turkish in parentheses on first use). New terms go into `glossary.md` and into the track's reference glossary page.
- **Every factual claim has a citation** (`<span class="cite"><a href="#rN">N</a></span>` → references list). Numbers that are the analyst's model (payoffs, estimates) say so in the page.
- **Shared assets only**: `<link rel="stylesheet" href="../../../assets/style.css">` and `<script src="../../../assets/components.js">`. Something a second lesson could reuse goes into `assets/` as a component, never inline. Document its data format in the header comment of `components.js`.
- **Turkish text inside single-quoted `data-*` JSON**: write the apostrophe as `&#39;`. In JS strings use the typographic `’`.
- `main` carries `data-lesson="NNNN"` so the result line names the lesson.
- Run `tools/learn validate --track <t>` (it checks asset paths and `data-card` presence). **Open the page for the learner yourself**, with the repo-relative path so the pre-allowed rule matches: `open tracks/<t>/lessons/NNNN-slug.html` on macOS, `start tracks/<t>/lessons/NNNN-slug.html` on Windows. Also give the clickable link in chat, as the fallback if it didn't open.
- Log it: `tools/learn moment --kind lesson --note "<NNNN slug, nodes>"` and a line in `handoff.md`.

## Reference pages (`tracks/<t>/reference/*.html`)

Lessons are rarely reopened; reference pages are. Keep the compressed essence there: the glossary, a procedure/checklist that *is* the target skill and grows with each node (e.g. an analysis checklist), syntax tables, formulas. Same rule as `cheatsheet.md`: only nodes at `checked` or higher, and the learner recalls before you write (`cheatsheet` skill). The Markdown cheatsheet stays the recall exercise; the reference page is its printable form.

## When a result line is pasted ("ders sonucu …")

Current format (one item per `data-card` quiz, items separated by `; `):

```
ders sonucu 0003: gt-012=B/3 "çünkü ikisi de sapmak ister"; gt-013=?/1; gt-014=A/2
```

Item = `CARD=CHOICE/CONFIDENCE`, then optionally a space and the learner's "Neden?" text in double quotes (single line; any `"` inside became `'`). CHOICE is the option letter in stored order, or `?` for "Bilmiyorum"; CONFIDENCE is 1 (Tahmin), 2 (Emin değilim) or 3 (Eminim). For each item:

- letter: `tools/learn record --card <id> --choice <letter> --confidence <n> --source lesson [--answer-text "<neden text>"]`
- `?`: `tools/learn record --card <id> --dont-know --source lesson [--answer-text "<neden text>"]`

Old format (lessons built before the quiz card, no confidence, no text): `ders sonucu 0002: pts-010=B pts-015=C` (space-separated `card=letter`). Record each as `tools/learn record --card <id> --choice <letter> --source lesson`.

Either way the engine stores which distractor was chosen (misconception diagnosis) but does **not** reschedule the card and does not count it as mastery (open book). A high-confidence wrong item (`/3`) is the first thing to talk about; the "Neden?" text tells you which belief is behind it. Then, in one or two lines: what held, which belief showed up; mark that misconception `seen: observed` in `misconceptions.md` if it did. **Re-ask every missed node in chat** with a different card during the session, graded normally. Never grade the pasted line as if it were a chat answer.

If `tools/learn status` lists a lesson whose result isn't recorded yet, ask once for its "ders sonucu" line (or, if they didn't do the quiz, open the page for them).
