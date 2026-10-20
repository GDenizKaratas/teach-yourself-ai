# Starter pack: intake → diagnosis → proposal

Every new track starts here, whether the learner says "başla" / "start" on day one or later "X öğrenmek istiyorum". The topic they name is a **request**, not yet the track. The track is what their real goal needs, and that can differ from the request: a different name, a narrower scope, a prerequisite first, or two tracks in a chain.

No folder is created and no teaching starts before step 4 (the go-ahead).

## 1. Batch 1: the goal (one AskUserQuestion call, 3–4 questions)

Ask all of them at once, with concrete options plus "Other". These are the questions whose answers change the plan:

1. **Amaç:** "Bunu öğrendiğinde neyi yapabiliyor olmak istiyorsun?" Give 3 options typical for this topic (e.g. for Python: "kendi verimi analiz etmek", "iş akışımı otomatikleştirmek", "yazılımcı olarak işe girmek").
2. **Neden şimdi / nerede kullanacaksın:** the real situation: a job, a project, an exam, curiosity, a decision.
3. **Bu konudaki yerin:** their identity relative to the topic: complete beginner, used it a bit, use it at work, studied it before and forgot.
4. **Zaman:** session length (5/15/30/45) and whether there is a deadline. Skip this question if `learner/profile.md` already says it.

Don't ask what the profile already records (background, language, OS). Confirm it in one line instead.

## 2. Batch 2: only the critical follow-ups (0–3 questions, one call)

Ask only where Batch 1 left the plan undecided. Typical cases:

- **The goal is vague** ("genel olarak öğrenmek"): "Bir ay sonra bunu bildiğini neyle anlarsın?" with 3 observable options. This becomes the success criterion.
- **The goal names a different skill than the topic** (they ask for Python but want "verimi anlamak"): "Asıl istediğin X mi, yoksa Y mi?"
- **There is a hidden prerequisite**: "Şunu daha önce yaptın mı?" (one check, not a quiz).
- **The scope is open**: "Şunlardan hangisi şimdilik dışarıda kalabilir?" This sets the out of scope.

Two batches at most. If something is still unclear, decide it yourself and say so in the proposal; the learner corrects it there.

## 3. Diagnosis and proposal (one message)

Think through the following before you write anything. Three strategy lenses keep the diagnosis honest:

- **Right problem.** Is the named topic the problem, or a means to it? Solving the wrong problem well is still a failure. ("Python" → "understand my own data".)
- **Wish vs reality.** Size the goal to the time they actually have (Batch 1). A wish dressed as a goal ("machine learning in a month, 15 min a day") gets cut to a first reachable capability, and you say so plainly.
- **Trade-off.** A plan that keeps everything is no choice at all. Name what this track will *not* teach now; that list is the proposal's "Dışarıda kalan" line.

Then work out:

- What capability does the goal actually require? Scope it by how the skill will really be used (`SKILL.md` §2).
- Is the named topic that capability, a part of it, or a detour?
- What prerequisites are missing, given the learner's level and the existing tracks (`tools/learn progress`)?
- What should the track be called? Name it after the capability, not only the topic. For example, "Veri analizi için Python" instead of "Python".

Start the `researcher` in the background as soon as the direction is clear (`SKILL.md` §3), so the research runs while the learner reads the proposal.

Then present the proposal in the learner's language, in this shape:

```
İstediğin: <their request, their words>
Asıl hedefin: <the capability, observable>
Önerim: <track name>  (+ <second track>, if a chain)
Neden bu: <one or two sentences tying it to their goal; say plainly where it differs from the request>
İlk adımlar: 1. … 2. … 3. …
Sonunda: <what they will be able to do = success criterion>
Dışarıda kalan (şimdilik): <out of scope>
```

Close with one AskUserQuestion: "Bu planla başlayalım mı?" with the options **Evet, başlayalım** / **Değiştirmek istediğim bir şey var** / **İlk istediğim haliyle açalım**. The learner has the final say. If they choose their original request, open it as asked and note your concern in `intake.md` → Decision.

## 4. Go-ahead → create and record

- `tools/learn new-track <kebab-name> --title "<name>"` creates the folder with `intake.md` from the template.
- Fill `tracks/<t>/intake.md`: the date, the request, both batches (question → answer, short), the diagnosis, the proposal and the decision. This is the record of *why this track exists*. It never changes later; a re-scope gets a new dated "Revision" section.
- Carry the goal, success criterion, constraints and out of scope into `README.md` (`SKILL.md` §1), then continue with §2 onward.
- If the learner wanted something you parked instead (a second track in the chain, a later topic), add it to `learner/parking-lot.md`.

## When not to run the full pack

- A track in a chain the learner already approved (e.g. the second track of a proposal): confirm the goal in one question and reuse the chain's `intake.md` reasoning (link it).
- `learner/intake.md` exists (a mentor wrote it): use it as Batch 1, confirm in one question, and go to Batch 2 only for gaps.
