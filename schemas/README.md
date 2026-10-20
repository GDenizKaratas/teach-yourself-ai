# Data contract

The learning record is plain files. This page says which file holds what, who may write it, and which rules every writer keeps. The rules hold for any agent (Claude or another LLM) and any human.

## Rule zero

**Learner data changes only through `tools/learn`.** The engine validates every write, shuffles the options, assigns ids, grades, and schedules reviews. Writes are atomic and locked, so a crash never leaves a half-written file. An agent runs commands. It never edits a `.jsonl` file or `learner/export.json` by hand.

## Machine data (JSON, schema-checked)

| File | One line / object = | Written by | Schema |
|---|---|---|---|
| `tracks/<t>/cards.jsonl` | a question card + its review schedule (`srs`) | `add-card`, `record`, `retire` | [card.schema.json](card.schema.json) |
| `tracks/<t>/attempts.jsonl` | one answer (`kind: card`) or task event (`kind: task`); **append-only evidence** | `record`, `task` | [attempt.schema.json](attempt.schema.json) |
| `learner/moments.jsonl` | an engagement moment (recap, teaser, milestone, lesson, …) | `moment` | [moment.schema.json](moment.schema.json) |
| `learner/export.json` | the generated snapshot the dashboard and lesson maps read | `refresh` / `export` only | [export.schema.json](export.schema.json) |
| `learner/state.json` | `{"active_track": "<t>"}` | `use`, `new-track` | – |
| `learner/format.json` | `{"version": N}`: the data format version | `migrate` | – |

How the contract is enforced:

- **At runtime.** `tools/learn doctor-data` reports unreadable lines and rows that break a schema (`contract`). `tools/learn status` prints a `DATA WARNING` line at session start when any exist. Contract problems are reported, never auto-fixed: the evidence stays as it is.
- **In tests.** `tests/engine` checks that every row the engine writes, and the export, match these schemas.

Schemas are JSON Schema 2020-12. The engine checks them with a small built-in validator, so it needs no extra package. The validator supports the subset these files use: `$ref`, `type`, `const`, `enum`, `required`, `properties`, `items`, `minItems`/`maxItems`, `minLength`, `minimum`, `pattern` and `oneOf`.

## Evolution

- **Rows may carry unknown fields.** Readers ignore what they don't know, and writers keep it.
- **Old rows stay valid.** A legacy variant gets documented in the schema rather than rewritten. Example: `choice: "X"` for "Bilmiyorum" in rows written before `dont_know` existed.
- **Breaking change to stored data:** bump `FORMAT_VERSION` in `tools/learn.py` and add a migration step (`tools/learn migrate`). It backs up first. An engine refuses data newer than itself.
- **`export.json` has the id `teach.export/1`.** Changes within it are additive: new keys may appear, but existing keys keep their meaning and type. Anything else is `teach.export/2`.
- **What never enters the export:** card prompts, options, answers, explanations, misconception ids and profile text. The dashboard is learner-facing.

## Prose files with a fixed shape (Markdown, read by the engine)

| File | Shape the engine reads | Checked by |
|---|---|---|
| `tracks/<t>/map.md` | `<!-- map-format: 1 -->`, a mermaid `graph TD`, and a node table with the columns `id`, `kind`, `statement`, `tanım (öğrenci)`, `depends on` and `mastery evidence` (`tools/track-template/map.md`) | `validate`, `map` |
| `tracks/<t>/cheatsheet.md` | one `## <node id or title>` section per done node | `status` → Notes gaps |
| `tracks/<t>/handoff.md` | `## Next step`, then `## Öğrenci için` (one line shown on the dashboard), then `## Session log` with lines starting `- YYYY-MM-DD` | `status` (resume point, UNLOGGED SESSIONS) |
| `tracks/<t>/intake.md` | why the track exists: request, goal answers, diagnosis, proposal, decision | `validate` |
| `tracks/<t>/lessons/NNNN-*.html` | a `<!-- lesson-map: --track t --nodes a,b -->` comment and `data-card` quizzes | `validate`, `refresh` |

Everything else in a track (`misconceptions.md`, `glossary.md`, `RESOURCES.md`, `README.md`) is free prose for the tutor. `misconceptions.md` must define every `m-…` id that a card uses (checked by `validate`).
