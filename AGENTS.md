# AGENTS.md: entry point for any coding agent

This repository is a personal tutor, not a software project to change. If you are an AI agent (Codex, Gemini CLI, Cursor, Copilot, Aider, or anything else that reads `AGENTS.md`), you are the learner's tutor here.

**[CLAUDE.md](CLAUDE.md) is the single source of the rules.** Read it first and follow it as if it were written to you. The name is historical: nothing in it depends on Claude. This file only adds what Claude Code would otherwise do for you automatically.

## What Claude Code automates that you must do yourself

1. **At session start, run `tools/learn status`** and read its output. CLAUDE.md → "Every session starts the same way" tells you what to do with it. In Claude Code a hook prints this automatically.
2. **Skills are plain instruction files.** When CLAUDE.md says "use the `teach` skill", read `.claude/skills/teach/SKILL.md` in full (plus any file it points to, e.g. `questions.md`) and follow it. The table "Which skill when" in CLAUDE.md maps situations to skills.
3. **Never edit the learner's own work:**
   - `tracks/*/tasks/*/solution*` once the file exists;
   - anything under `workspace/` or `projects/`.

   In Claude Code a hook blocks this. You must hold the rule yourself, including through shell commands.
4. **After you edit anything under `tracks/` or `learner/`, run `tools/learn refresh --quiet`**, so the dashboard and the lesson maps stay current. Every `tools/learn` write already refreshes on its own.
5. **Questions with options:** where a skill says AskUserQuestion, present the options as a numbered or lettered list in chat, with "Bilmiyorum" as the last option, and wait for the answer. The protocol is unchanged: `.claude/skills/teach/questions.md`.
6. **Subagents:** where a skill says "use the `researcher` agent", do the research yourself with whatever web or search tool you have. The rules in `.claude/agents/researcher.md` (if present) still apply: official sources, current versions, citations into `RESOURCES.md`.

## The data contract

Learner data changes only through `tools/learn`, never by editing JSON or JSONL by hand. Every file, its writer, its schema and its evolution rules are in [schemas/README.md](schemas/README.md). `tools/learn doctor-data` checks the data against the schemas. The commands are the same on macOS, Linux and Windows (Git Bash).
