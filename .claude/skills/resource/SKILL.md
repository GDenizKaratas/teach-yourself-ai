---
name: resource
description: Take a resource the learner brings (a link, a PDF, a book chapter, a course, a repo, "şu kaynağı kullan", "bunu da ekle", "/kaynak") into the active track — verified, cited, and reflected in the map when it changes what must be learned. Use whenever the learner offers their own material, or asks what to read for a node.
---

# Resource

The learner's own material is a gift: it tells you what they trust, what they will actually read, and often why they want to learn this. It never bypasses the standard (facts verified, claims cited, the map stays a DAG of unconditional truths), and it never silently replaces the plan.

## 1. Receive (one message, no questions yet)

Read it, or have the `researcher` read it when it is long (background; keep talking meanwhile). Write down, for yourself:

- what it covers, mapped onto the track's `map.md` nodes: which nodes it teaches well, which it skips, which it contradicts;
- what it adds that the map doesn't have (a candidate node, an example, a case, a dataset);
- how trustworthy it is (primary source, official docs, a known textbook, a blog, a video) and whether anything in it is wrong or outdated. Check doubtful claims with `researcher`; never teach a claim from the resource you couldn't verify.

## 2. Record it

- `tracks/<t>/RESOURCES.md` → Knowledge (or Wisdom for a community/forum): one line, what it covers, when to reach for it, "(öğrencinin getirdiği, YYYY-MM-DD)".
- If it is the learner's preferred text for a node, say so there; the lesson for that node cites it as the primary source and links the exact section.

## 3. Propose, don't rewrite

One short message in the learner's language:

```
Getirdiğin kaynak: <name>
Haritayla örtüşen: <nodes it teaches well>
Eklenmeye değer: <candidate node(s) or examples>, çünkü <one line>
Çelişen / eski: <what and why>, oraya güvenme
Önerim: <keep the plan / add node X after Y / use it as the text for Z>
```

Then one AskUserQuestion: "Böyle yapalım mı?" with **Evet** / **Sadece kaynak olarak kalsın** / **Değiştirmek istediğim bir şey var**.

## 4. Apply the decision

- **Map change** (new node, a reordered dependency): edit `map.md` (mermaid and table together), `tools/learn validate --track <t>`, add the node's misconceptions when teaching reaches it, and date the change in `tracks/<t>/intake.md` → "Revision". A new node also gets its organizer section (`lessons/0000-harita.html`) so the big picture stays complete.
- **Text for a node**: the next lesson on that node is built from it (`lesson` skill → Before writing → Ground every claim).
- **Just a resource**: `RESOURCES.md` only. Mention it in the next lesson's "Birincil kaynak" block when it fits.
- A resource for a topic outside the track → `learner/parking-lot.md`, one line.

Write the decision into `learner/relationship.md` → Kararları when the learner chose a direction ("2026-11-05: X kitabını ana metin olarak kullan"), so it is not overridden later without asking.

## What never happens

- Teaching from a resource as if it were verified because the learner likes it. Verify, then teach.
- Building a lesson that paraphrases the resource at length. The page teaches; the resource is linked and cited.
- Dropping the organizer or the method because a course has its own order. The map's order wins; the resource's order is noted where it differs.
