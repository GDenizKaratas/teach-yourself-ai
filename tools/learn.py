#!/usr/bin/env python3
"""learn.py — the deterministic half of the learning system.

The LLM teaches; this script owns everything that must be exact:
scheduling (spaced repetition), grading multiple-choice answers,
recording every attempt, and validating tracks against the standard.

Stdlib only. Run through the `tools/learn` wrapper.

Data layout (per track, under tracks/<track>/):
  cards.jsonl     one card per line (content + srs state)
  attempts.jsonl  append-only log of every answer
  misconceptions.md  inventory; ids look like `m-some-slug`
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import datetime as dt
import hashlib
import heapq
import html as _html
import json
import os
import random
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
TEMPLATE = ENGINE_DIR / "track-template"  # ships with the engine, not with the data


def set_root(root: Path):
    """Point every data path at `root`. Default: the repo this file lives in.
    TEACH_ROOT=<dir> overrides it (test seam: tests run against temp dirs, never the real learner/ or tracks/)."""
    global ROOT, TRACKS, LEARNER, STATE, MOMENTS, FORMAT_FILE, LOCK
    ROOT = Path(root).resolve()
    TRACKS = ROOT / "tracks"
    LEARNER = ROOT / "learner"
    STATE = LEARNER / "state.json"
    MOMENTS = LEARNER / "moments.jsonl"
    FORMAT_FILE = LEARNER / "format.json"
    LOCK = LEARNER / ".lock"


set_root(os.environ.get("TEACH_ROOT") or ENGINE_DIR.parent)

CARD_TYPES = {"mcq", "predict-output", "recall", "explain", "spot-the-bug"}
GRADED_BY_SCRIPT = {"mcq", "predict-output", "spot-the-bug"}  # have options
LETTERS = "ABCD"
MISC_RE = re.compile(r"\bm-[a-z0-9][a-z0-9-]*\b")
DEFAULT_EASE = 2.5
MIN_EASE = 1.3
CUES = {"lesson", "adjacent", "far"}            # card "cue": how far the prompt is from how it was taught (absent = lesson)
MODES = {"recall", "discriminate", "compose"}   # card "mode": what the card exercises
GENERATIVE_TYPES = {"recall", "explain", "predict-output", "spot-the-bug"}  # the learner produces, not recognizes
UNSCHEDULED_SOURCES = {"lesson", "predict"}     # diagnostic answers: never rescheduled, never mastery evidence
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")

# Honest mastery: attempts on/after this local date need stronger evidence for retained/owned (see node_progress).
# Attempts before it keep the old rules, so nothing already earned disappears.
MASTERY_RULES_SINCE = "2026-10-20"

# Data format version. learner/format.json holds {"version": N}; no file means version 1.
# Reads never create the stamp; `migrate` writes it last. Bump together with a new entry in MIGRATIONS.
FORMAT_VERSION = 1
LOCK_STALE_SECONDS = 30


# ── helpers ────────────────────────────────────────────────────────────────

def today() -> dt.date:
    # Test seam: TEACH_TODAY=YYYY-MM-DD pins "today" (scheduling, due, streaks, timestamps' date).
    pinned = os.environ.get("TEACH_TODAY")
    return dt.date.fromisoformat(pinned) if pinned else dt.date.today()


def now() -> dt.datetime:
    """Local time, timezone-aware. Honours TEACH_TODAY (keeps the time of day, swaps the date)."""
    n = dt.datetime.now().astimezone()
    if os.environ.get("TEACH_TODAY"):
        n = dt.datetime.combine(today(), n.time().replace(tzinfo=None)).astimezone()
    return n


def now_iso() -> str:
    """Timestamp for new rows: ISO 8601 with UTC offset, e.g. 2026-10-20T01:52:00+03:00."""
    return now().isoformat(timespec="seconds")


def parse_ts(ts) -> dt.datetime:
    """Read a row's `ts`. Old rows are naive (local time, no offset) and are treated as local."""
    try:
        t = dt.datetime.fromisoformat(str(ts))
    except ValueError:
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    return t.astimezone() if t.tzinfo is None else t


def ts_day(ts) -> str:
    """Local calendar day of a timestamp (naive or aware)."""
    t = parse_ts(ts)
    if t.year == 1:  # unparseable
        return str(ts)[:10]
    return t.astimezone().date().isoformat()


def die(msg: str, code: int = 1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def rel(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def track_dir(track: str) -> Path:
    d = TRACKS / track
    if not d.is_dir():
        die(f"track '{track}' not found under tracks/ (create it with: new-track {track})")
    return d


def all_tracks() -> list[str]:
    if not TRACKS.is_dir():
        return []
    return sorted(p.name for p in TRACKS.iterdir() if p.is_dir() and (p / "cards.jsonl").exists())


# ── reading data: tolerant but loud ───────────────────────────────────────
# A line that is not a JSON object (bad JSON, bad UTF-8, a bare value) is skipped and remembered,
# never silently lost: `status` shows it, `doctor-data` lists and quarantines it, and every command
# that REWRITES that file refuses until it is fixed (so lines it can't understand are never dropped).

BLANK, BAD = object(), object()
UNREADABLE: dict[str, list[int]] = {}  # relpath -> line numbers skipped by read_jsonl in this run


def split_lines(data: bytes) -> list[bytes]:
    """Lines with their endings, split on \n only (so U+2028 inside a JSON string never breaks a row)."""
    return [ln for ln in re.split(rb"(?<=\n)", data) if ln]


def parse_line(raw: bytes):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return BAD
    if not text.strip():
        return BLANK
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return BAD
    return obj if isinstance(obj, dict) else BAD


def scan_jsonl(path: Path) -> tuple[list[dict], list[int]]:
    """(rows, unreadable line numbers)."""
    if not path.exists():
        return [], []
    rows, bad = [], []
    for i, raw in enumerate(split_lines(path.read_bytes()), 1):
        obj = parse_line(raw)
        if obj is BAD:
            bad.append(i)
        elif obj is not BLANK:
            rows.append(obj)
    return rows, bad


def read_jsonl(path: Path, strict: bool = False) -> list[dict]:
    """Rows of a JSONL file. Unreadable lines are skipped and recorded in UNREADABLE;
    strict=True dies on the first one instead (the old behaviour)."""
    rows, bad = scan_jsonl(path)
    if bad:
        if strict:
            die(f"{rel(path)} line {bad[0]}: unreadable (not a JSON object) → run: tools/learn doctor-data")
        UNREADABLE[rel(path)] = bad
    return rows


def ensure_rewritable(path: Path):
    """Refuse to rewrite a file that has lines this engine can't read: rewriting would drop them."""
    _, bad = scan_jsonl(path)
    if bad:
        die(f"{rel(path)} has unreadable line(s) {bad[:10]}; refusing to rewrite it (that would drop them). "
            "Run: tools/learn doctor-data (then doctor-data --fix to quarantine them)")


def atomic_write_bytes(path: Path, data: bytes):
    """Write via a unique temp file in the same directory + os.replace: readers see old or new, never half."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_jsonl(path: Path, rows: list[dict]):
    ensure_rewritable(path)
    atomic_write_bytes(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8"))


def append_bytes(path: Path, data: bytes):
    """Append, first closing an unterminated last line so the new row never glues onto it."""
    with path.open("ab") as f:
        if f.tell() > 0:
            with path.open("rb") as r:
                r.seek(-1, os.SEEK_END)
                if r.read(1) != b"\n":
                    f.write(b"\n")
        f.write(data)


def append_jsonl(path: Path, row: dict):
    append_bytes(path, (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))


def read_state() -> tuple[dict, bool]:
    """(state, readable)."""
    if not STATE.exists():
        return {}, True
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, False
    return (st, True) if isinstance(st, dict) else ({}, False)


def load_state() -> dict:
    st, ok = read_state()
    if not ok:
        UNREADABLE[rel(STATE)] = [0]
    return st


def save_state(state: dict):
    if not read_state()[1]:
        die("learner/state.json is unreadable; refusing to overwrite it. Run: tools/learn doctor-data")
    atomic_write_bytes(STATE, (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


# ── safety: format stamp, write lock, data scan ───────────────────────────

def format_version() -> int | None:
    """Stamped data format version; 1 when learner/format.json is absent; None when it is unreadable."""
    if not FORMAT_FILE.exists():
        return 1
    try:
        v = json.loads(FORMAT_FILE.read_text(encoding="utf-8")).get("version")
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return None
    return v if isinstance(v, int) else None


def ensure_format_writable():
    v = format_version()
    if v is None:
        die("learner/format.json is unreadable; refusing to write. Fix it by hand (it should be {\"version\": N}).")
    if v > FORMAT_VERSION:
        die(f"learner data is format version {v}, newer than this engine ({FORMAT_VERSION}); "
            "refusing to write. Update tools/ (the engine) first.")


@contextlib.contextmanager
def write_lock():
    """Cross-process lock (learner/.lock, O_CREAT|O_EXCL: works on macOS, Linux and Windows).
    A lock older than LOCK_STALE_SECONDS is considered left over from a crash and taken over.
    TEACH_LOCK_WAIT=<seconds> sets how long to wait for a live lock (default 10; test seam)."""
    LEARNER.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + float(os.environ.get("TEACH_LOCK_WAIT", "10"))
    token = f"{os.getpid()} {secrets.token_hex(8)}"
    while True:
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except (FileExistsError, PermissionError):  # Windows may say PermissionError while it is being deleted
            try:
                age = time.time() - LOCK.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > LOCK_STALE_SECONDS:
                with contextlib.suppress(OSError):
                    LOCK.unlink()
                continue
            if time.monotonic() >= deadline:
                die("another tools/learn command is writing (learner/.lock is held); try again in a moment. "
                    f"If nothing is running, the lock expires after {LOCK_STALE_SECONDS}s.")
            time.sleep(0.1)
    try:
        os.write(fd, token.encode("utf-8"))
    finally:
        os.close(fd)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            if LOCK.read_text(encoding="utf-8") == token:
                LOCK.unlink()


def data_files() -> list[Path]:
    """Every JSONL data file: learner/*.jsonl and tracks/*/*.jsonl."""
    files = sorted(LEARNER.glob("*.jsonl")) if LEARNER.is_dir() else []
    if TRACKS.is_dir():
        for d in sorted(p for p in TRACKS.iterdir() if p.is_dir()):
            files += sorted(d.glob("*.jsonl"))
    return files


def scan_data() -> list[dict]:
    """Unreadable lines across all data files, plus unreadable state.json / format.json."""
    problems = []
    for f in data_files():
        for n in scan_jsonl(f)[1]:
            problems.append({"file": rel(f), "line": n})
    if not read_state()[1]:
        problems.append({"file": rel(STATE), "line": 0, "note": "whole file is not a JSON object"})
    if format_version() is None:
        problems.append({"file": rel(FORMAT_FILE), "line": 0, "note": "whole file unreadable; fix by hand"})
    return problems


# ── data contract: schemas/*.schema.json (JSON Schema 2020-12 subset, checked here without dependencies) ──
SCHEMA_OF = {"cards.jsonl": "card", "attempts.jsonl": "attempt", "moments.jsonl": "moment"}


def load_schema(name: str) -> dict | None:
    f = ENGINE_DIR.parent / "schemas" / f"{name}.schema.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def schema_errors(obj, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """Violations of `schema` by `obj`. Supports what schemas/ uses: $ref (#/$defs/…), type, const, enum, required,
    properties, items, min/maxItems, minLength, minimum, pattern, oneOf. Unknown keywords are ignored."""
    root = root or schema
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            target = target[part]
        return schema_errors(obj, target, root, path)
    errs = []
    names = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
    def is_type(t):
        if t == "integer":
            return isinstance(obj, int) and not isinstance(obj, bool)
        if t == "number":
            return isinstance(obj, (int, float)) and not isinstance(obj, bool)
        return isinstance(obj, names[t])
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(is_type(t) for t in types):
            return [f"{path}: expected {'/'.join(types)}, got {type(obj).__name__}"]
    if "const" in schema and obj != schema["const"]:
        errs.append(f"{path}: must be {schema['const']!r}")
    if "enum" in schema and obj not in schema["enum"]:
        errs.append(f"{path}: {obj!r} not in {schema['enum']}")
    if isinstance(obj, str):
        if len(obj) < schema.get("minLength", 0):
            errs.append(f"{path}: empty")
        if "pattern" in schema and not re.search(schema["pattern"], obj):
            errs.append(f"{path}: {obj!r} does not match {schema['pattern']}")
    if isinstance(obj, (int, float)) and not isinstance(obj, bool) and obj < schema.get("minimum", obj):
        errs.append(f"{path}: below {schema['minimum']}")
    if isinstance(obj, dict):
        errs += [f"{path}: missing {k!r}" for k in schema.get("required", []) if k not in obj]
        for k, sub in schema.get("properties", {}).items():
            if k in obj:
                errs += schema_errors(obj[k], sub, root, f"{path}.{k}")
    if isinstance(obj, list):
        if len(obj) < schema.get("minItems", 0) or len(obj) > schema.get("maxItems", len(obj)):
            errs.append(f"{path}: {len(obj)} items")
        if "items" in schema:
            for i, x in enumerate(obj):
                errs += schema_errors(x, schema["items"], root, f"{path}[{i}]")
    if "oneOf" in schema:
        ok = [b for b in schema["oneOf"] if not schema_errors(obj, b, root, path)]
        if len(ok) != 1:
            errs.append(f"{path}: matches {len(ok)} of the oneOf branches (expected exactly 1)")
    return errs


def scan_contract() -> list[dict]:
    """Readable data rows that break the data contract (schemas/). Reported, never auto-fixed: the evidence stays."""
    problems = []
    for f in data_files():
        name = SCHEMA_OF.get(f.name)
        schema = load_schema(name) if name else None
        if not schema:
            continue
        for i, raw in enumerate(split_lines(f.read_bytes()), 1):
            obj = parse_line(raw)
            if obj is BAD or obj is BLANK:
                continue
            errs = schema_errors(obj, schema)
            if errs:
                problems.append({"file": rel(f), "line": i, "errors": errs[:3]})
    return problems


def known_misconceptions(track: str) -> set[str]:
    f = TRACKS / track / "misconceptions.md"
    return set(MISC_RE.findall(f.read_text(encoding="utf-8"))) if f.exists() else set()


def find_card(card_id: str) -> tuple[str, list[dict], int]:
    for t in all_tracks():
        cards = read_jsonl(TRACKS / t / "cards.jsonl")
        for i, c in enumerate(cards):
            if c.get("id") == card_id:
                return t, cards, i
    die(f"card '{card_id}' not found")


def public_view(card: dict) -> dict:
    """What gets shown while asking: no correctness, no explanation."""
    v = {k: card[k] for k in ("id", "track", "node", "type", "prompt") if k in card}
    if card.get("code"):
        v["code"] = card["code"]
    if card.get("options"):
        v["options"] = {LETTERS[i]: o["text"] for i, o in enumerate(card["options"])}
    v["due"] = card["srs"]["due"]
    v["reviews"] = card["srs"]["reps"]
    return v


def lesson_card_ids(html: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r'data-card="([^"]+)"', html)))


def lesson_status(track: str) -> tuple[list[str], list[str]]:
    """(lessons whose quiz results were never recorded, lessons with no data-card quiz): file stems."""
    d = TRACKS / track / "lessons"
    if not d.is_dir():
        return [], []
    recorded = {at.get("card") for at in read_jsonl(TRACKS / track / "attempts.jsonl") if at.get("source") == "lesson"}
    unrecorded, unbound = [], []
    for html in sorted(d.glob("*.html")):
        refs = lesson_card_ids(html.read_text(encoding="utf-8"))
        if not refs:
            unbound.append(html.stem)
        elif not recorded & set(refs):
            unrecorded.append(html.stem)
    return unrecorded, unbound


# ── validation (the "same standard" for every track) ──────────────────────

def check_card(card: dict, track: str, miscs: set[str]) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    cid = card.get("id", "?")
    for field in ("node", "type", "prompt", "explanation"):
        if not str(card.get(field, "")).strip():
            errors.append(f"{cid}: missing '{field}'")
    ctype = card.get("type")
    if ctype and ctype not in CARD_TYPES:
        errors.append(f"{cid}: type '{ctype}' not in {sorted(CARD_TYPES)}")
    opts = card.get("options") or []
    if ctype in GRADED_BY_SCRIPT:
        if not 2 <= len(opts) <= 4:
            errors.append(f"{cid}: needs 2-4 options (has {len(opts)}); the UI adds its own 'Other'")
        correct = [o for o in opts if o.get("correct")]
        if len(correct) != 1:
            errors.append(f"{cid}: exactly one option must have correct=true (has {len(correct)})")
        for o in opts:
            if not str(o.get("text", "")).strip():
                errors.append(f"{cid}: option with empty text")
            if o.get("correct"):
                continue
            m = o.get("misconception")
            if not m:
                errors.append(f"{cid}: distractor '{o.get('text', '')[:40]}' has no misconception id")
            elif miscs and m not in miscs:
                errors.append(f"{cid}: misconception '{m}' is not defined in misconceptions.md")
        # tells: the correct option should not stand out
        if correct and len(opts) >= 2:
            c_len = len(correct[0].get("text", ""))
            others = [len(o.get("text", "")) for o in opts if not o.get("correct")]
            avg = sum(others) / len(others) if others else c_len
            if avg and c_len > 1.5 * avg and c_len - avg > 15:
                warnings.append(f"{cid}: correct option is much longer than distractors (length tell)")
        for o in opts:
            if re.search(r"\b(because|since|çünkü|zira|bu yüzden)\b", o.get("text", ""), re.I):
                warnings.append(f"{cid}: option contains justification ('{o['text'][:40]}…'); move reasoning to explanation")
            if "**" in o.get("text", ""):
                warnings.append(f"{cid}: bold inside an option (asymmetric highlighting tell)")
    elif ctype in ("recall", "explain"):
        if not str(card.get("answer", "")).strip():
            errors.append(f"{cid}: recall/explain cards need a reference 'answer'")
    if "cue" in card and card["cue"] not in CUES:
        errors.append(f"{cid}: cue '{card['cue']}' not in {sorted(CUES)}")
    if "mode" in card and card["mode"] not in MODES:
        errors.append(f"{cid}: mode '{card['mode']}' not in {sorted(MODES)}")
    return errors, warnings


# ── the map (tracks/<t>/map.md): node table + mermaid graph ──────────────────
# Canonical format: see tools/track-template/map.md. The parser is lenient (it reads the maps written
# before the format was pinned) and reports what it can't read as problems instead of failing.

MAP_FORMAT_MARK = "<!-- map-format: 1 -->"  # maps carrying it (new tracks) get strict validation
_MERMAID_NODE = re.compile(r'^([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*(?:(\[\[|\[\(|\(\(|\[|\(|\{)\s*"?(.*?)"?\s*(\]\]|\)\]|\)\)|\]|\)|\}))?$')
_NONE_CELL = {"", "-", "–", "—", "none", "yok"}


def _table_cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip() for c in body.split("|")]


def parse_map(text: str) -> dict:
    """{nodes: [{id, kind?, statement?, title?, evidence?, depends_on, line}], edges: [{from, to}],
    mermaid_ids: [...], problems: ["line N: …"]}. Nodes come from the first table whose first header is `id`
    (the node table; other tables, e.g. coverage notes, are ignored), in table order."""
    lines = text.splitlines()
    problems: list[str] = []
    # mermaid block
    edges, mermaid_ids, labels = [], [], {}
    in_block, saw_block = False, False
    for no, raw in enumerate(lines, 1):
        ln = raw.strip()
        if not in_block:
            if ln.startswith("```mermaid"):
                in_block = saw_block = True
            continue
        if ln.startswith("```"):
            in_block = False
            continue
        if not ln or ln.startswith("%%") or re.match(r"^(graph|flowchart)\b", ln) or ln.startswith(("classDef", "class ", "style ", "linkStyle", "subgraph", "end", "direction")):
            continue
        ln = re.sub(r"--\s*\|[^|]*\|\s*>|-->\s*\|[^|]*\|", "-->", ln)  # edge labels: a -->|x| b, a --|x|> b
        parts = [p.strip() for p in ln.split("-->")]
        ids = []
        for part in parts:
            m = _MERMAID_NODE.match(part.rstrip(";").strip())
            if not m:
                problems.append(f"line {no}: can't read mermaid node '{part[:40]}'")
                ids = None
                break
            nid = m.group(1)
            ids.append(nid)
            if nid not in mermaid_ids:
                mermaid_ids.append(nid)
            if m.group(3) and nid not in labels:
                label = m.group(3).strip()
                labels[nid] = label[len(nid) + 1:].strip() if label.startswith(nid + ":") else label
        if ids:
            edges += [{"from": a, "to": b} for a, b in zip(ids, ids[1:])]
    if not saw_block:
        problems.append("map.md has no ```mermaid block")
    # node table
    nodes, header, start = [], None, None
    for no, raw in enumerate(lines, 1):
        ln = raw.strip()
        if header is None:
            if ln.startswith("|") and _table_cells(ln)[0].lower() == "id":
                header = [h.lower() for h in _table_cells(ln)]
                start = no
            continue
        if not ln.startswith("|"):
            break
        cells = _table_cells(ln)
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue  # separator row
        if len(cells) != len(header):
            problems.append(f"line {no}: node table row has {len(cells)} cells, header has {len(header)}")
        row = dict(zip(header, cells))
        node = {"id": row.get("id", ""), "line": no}
        for h, v in row.items():
            if h == "kind" and v:
                node["kind"] = v
            elif h.startswith("statement") and v:
                node["statement"] = v
            elif (h.startswith("tanım") or h.startswith("definition")) and v:
                node["definition"] = v
            elif h == "title" and v:
                node["title"] = v
            elif h.startswith("mastery") and v:
                node["evidence"] = v
        dep = next((v for h, v in row.items() if h.startswith("depends")), "")
        node["depends_on"] = [] if dep.strip().lower() in _NONE_CELL else [d.strip() for d in re.split(r"[,;]", dep) if d.strip()]
        nodes.append(node)
    if header is None:
        problems.append("map.md has no node table (a markdown table whose first column header is `id`)")
    ids = [n["id"] for n in nodes]
    for n in nodes:
        if "title" not in n and n["id"] in labels:
            n["title"] = labels[n["id"]]
        if not SLUG_RE.fullmatch(n["id"]):
            problems.append(f"line {n['line']}: node id '{n['id']}' is not a slug (lowercase letters, digits, '-')")
        if ids.count(n["id"]) > 1 and ids.index(n["id"]) != nodes.index(n):
            problems.append(f"line {n['line']}: duplicate node id '{n['id']}'")
        for d in n["depends_on"]:
            if d not in ids:
                problems.append(f"line {n['line']}: '{n['id']}' depends on '{d}', which is not in the node table")
    if header is not None and saw_block:
        only_table = [i for i in ids if i not in mermaid_ids]
        only_graph = [i for i in mermaid_ids if i not in ids]
        if only_table:
            problems.append(f"line {start}: in the node table but not in the mermaid graph: {', '.join(only_table)}")
        if only_graph:
            problems.append(f"line {start}: in the mermaid graph but not in the node table: {', '.join(only_graph)}")
        graph_deps = {(e["from"], e["to"]) for e in edges}
        table_deps = {(d, n["id"]) for n in nodes for d in n["depends_on"]}
        for a, b in sorted(table_deps - graph_deps):
            problems.append(f"line {next(n['line'] for n in nodes if n['id'] == b)}: '{b}' depends on '{a}' in the table but the graph has no {a} --> {b}")
        for a, b in sorted(graph_deps - table_deps):
            if a in ids and b in ids:
                problems.append(f"line {next(n['line'] for n in nodes if n['id'] == b)}: the graph has {a} --> {b} but the table row of '{b}' doesn't list '{a}'")
    if not edges:
        edges = [{"from": d, "to": n["id"]} for n in nodes for d in n["depends_on"]]
    cycle = find_cycle(edges)
    if cycle:
        problems.append(f"the graph has a cycle: {' --> '.join(cycle)}")
    return {"nodes": nodes, "edges": edges, "mermaid_ids": mermaid_ids, "problems": problems}


def find_cycle(edges: list[dict]) -> list[str] | None:
    succ: dict[str, list[str]] = {}
    for e in edges:
        succ.setdefault(e["from"], []).append(e["to"])
    state: dict[str, int] = {}  # 1 = on the stack, 2 = done
    for root in list(succ):
        if state.get(root):
            continue
        stack, path = [(root, iter(succ.get(root, [])))], [root]
        state[root] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
                path.pop()
            elif state.get(nxt) == 1:
                return path[path.index(nxt):] + [nxt]
            elif not state.get(nxt):
                state[nxt] = 1
                stack.append((nxt, iter(succ.get(nxt, []))))
                path.append(nxt)
    return None


def track_map(track: str) -> dict | None:
    """Parsed map.md of a track, or None when there is no map.md."""
    f = TRACKS / track / "map.md"
    return parse_map(f.read_text(encoding="utf-8")) if f.exists() else None


def map_node_ids(track: str) -> list[str]:
    m = track_map(track)
    return [n["id"] for n in m["nodes"]] if m else []


REQUIRED_TRACK_FILES = ["README.md", "map.md", "misconceptions.md", "cards.jsonl",
                        "attempts.jsonl", "handoff.md", "cheatsheet.md"]


def validate_track(track: str) -> tuple[list[str], list[str]]:
    d = track_dir(track)
    errors, warnings = [], []
    for f in REQUIRED_TRACK_FILES:
        if not (d / f).exists():
            errors.append(f"{track}: missing {f}")
    if (d / "map.md").exists():
        m = (d / "map.md").read_text(encoding="utf-8")
        if "```mermaid" not in m:
            errors.append(f"{track}: map.md has no mermaid dependency graph")
    for f in ("README.md", "map.md"):
        if (d / f).exists() and "TODO" in (d / f).read_text(encoding="utf-8"):
            warnings.append(f"{track}: {f} still contains TODO")
    if not (d / "RESOURCES.md").exists():
        warnings.append(f"{track}: no RESOURCES.md (trusted sources, communities, gaps)")
    if not (d / "intake.md").exists():
        warnings.append(f"{track}: no intake.md (why this track exists: request, goal, diagnosis, decision; new-track starter pack)")
    elif "TODO" in (d / "intake.md").read_text(encoding="utf-8"):
        warnings.append(f"{track}: intake.md still contains TODO")
    all_ids = {c.get("id") for t in all_tracks() for c in read_jsonl(TRACKS / t / "cards.jsonl")}
    for html in sorted((d / "lessons").glob("*.html")) + sorted((d / "reference").glob("*.html")):
        text = html.read_text(encoding="utf-8")
        if "assets/" in text and "../../../assets/" not in text:
            errors.append(f"{track}/{html.parent.name}/{html.name}: must load ../../../assets/ (shared components at the repo root)")
        if html.parent.name != "lessons":
            continue
        refs = lesson_card_ids(text)
        if not refs:
            if 'class="quiz"' in text:
                warnings.append(f"{track}/lessons/{html.name}: quiz without data-card ids; results can't be recorded (build quizzes with `tools/learn cards --html`)")
            else:
                warnings.append(f"{track}/lessons/{html.name}: no data-card quiz; results can't be recorded (build quizzes with `tools/learn cards --html`)")
        for cid in refs:
            if cid not in all_ids:
                errors.append(f"{track}/lessons/{html.name}: data-card '{cid}' is not a card")
    miscs = known_misconceptions(track)
    if not miscs:
        warnings.append(f"{track}: misconceptions.md defines no m-… ids yet")
    for f in ("cards.jsonl", "attempts.jsonl"):
        for n in scan_jsonl(d / f)[1]:
            errors.append(f"{track}: {f} line {n} unreadable → run: tools/learn doctor-data")
    ids = set()
    for c in read_jsonl(d / "cards.jsonl"):
        if c.get("id") in ids:
            errors.append(f"{c.get('id')}: duplicate id")
        ids.add(c.get("id"))
        e, w = check_card(c, track, miscs)
        errors += e
        warnings += w
    tasks = d / "tasks"
    if tasks.is_dir():
        for t in sorted(p for p in tasks.iterdir() if p.is_dir()):
            if not (t / "TASK.md").exists():
                errors.append(f"{track}/tasks/{t.name}: missing TASK.md")
            if not list(t.glob("test_*.py")) and not (t / "CHECK.md").exists():
                errors.append(f"{track}/tasks/{t.name}: needs test_*.py (code) or CHECK.md (non-code rubric)")
    if (d / "map.md").exists():
        e, w = validate_map(track)
        errors += e
        warnings += w
    return errors, warnings


def validate_map(track: str) -> tuple[list[str], list[str]]:
    """Map findings: slug ids, acyclic, table ids == mermaid ids, every card/task node in the map.
    Errors only for maps in the pinned format (they carry MAP_FORMAT_MARK, as new tracks do) that are filled in
    (no TODO); for older maps and unfinished ones the same findings are warnings, so existing tracks keep passing."""
    d = TRACKS / track
    text = (d / "map.md").read_text(encoding="utf-8")
    m = parse_map(text)
    found = [f"{track}: map.md {p}" for p in m["problems"]]
    ids = {n["id"] for n in m["nodes"]}
    if ids:
        missing: dict[str, list[str]] = {}
        for c in read_jsonl(d / "cards.jsonl"):
            if c.get("node") and c["node"] not in ids and not c.get("retired"):
                missing.setdefault(c["node"], []).append(f"card {c.get('id')}")
        for at in read_jsonl(d / "attempts.jsonl"):
            if at.get("kind") == "task" and at.get("node") and at["node"] not in ids:
                ref = f"task {at.get('task')}"
                if ref not in missing.setdefault(at["node"], []):
                    missing[at["node"]].append(ref)
        for node, refs in missing.items():
            found.append(f"{track}: node '{node}' ({', '.join(refs[:5])}{'…' if len(refs) > 5 else ''}) is not in map.md")
    strict = MAP_FORMAT_MARK in text and "TODO" not in text
    return (found, []) if strict else ([], found)


# ── scheduling (SM-2 variant, confidence-aware) ───────────────────────────
# quality: 1 = wrong, 3 = right but guessed, 4 = right but unsure, 5 = right and sure

def quality(correct: str, confidence: int | None) -> int:
    if correct == "no":
        return 1
    if correct == "partial":
        return 3
    return {1: 3, 2: 4, 3: 5, None: 4}[confidence]  # not asked (None) schedules like "unsure"


def schedule(srs: dict, q: int) -> dict:
    srs = dict(srs)
    ease = srs.get("ease", DEFAULT_EASE)
    if q < 3:
        srs["reps"] = 0
        srs["lapses"] = srs.get("lapses", 0) + 1
        srs["interval"] = 1
    else:
        reps = srs.get("reps", 0)
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 3
        else:
            interval = round(srs.get("interval", 1) * ease)
        if q == 3:  # a guess is not evidence of memory: grow slowly
            interval = max(1, min(interval, srs.get("interval", 1) + 1))
        srs["interval"] = interval
        srs["reps"] = reps + 1
    srs["ease"] = round(max(MIN_EASE, ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))), 2)
    srs["due"] = (today() + dt.timedelta(days=srs["interval"])).isoformat()
    srs["last"] = today().isoformat()
    return srs


# ── commands ───────────────────────────────────────────────────────────────

def cmd_new_track(a):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", a.track):
        die("track name must be kebab-case, e.g. python-basics")
    d = TRACKS / a.track
    if d.exists():
        die(f"tracks/{a.track} already exists")
    d.mkdir(parents=True)
    (d / "tasks").mkdir()
    for src in TEMPLATE.iterdir():
        text = src.read_text(encoding="utf-8").replace("{{TRACK}}", a.track) \
            .replace("{{TITLE}}", a.title or a.track).replace("{{DATE}}", today().isoformat())
        (d / src.name).write_text(text, encoding="utf-8")
    state = load_state()
    state["active_track"] = a.track
    save_state(state)
    out({"created": f"tracks/{a.track}", "active_track": a.track,
         "next": "fill README.md, map.md, misconceptions.md per the new-track skill, then run validate"})


def cmd_use(a):
    track_dir(a.track)
    state = load_state()
    state["active_track"] = a.track
    save_state(state)
    out({"active_track": a.track})


def cmd_add_card(a):
    track_dir(a.track)
    raw = sys.stdin.read().strip()
    if not raw:
        die("pass card JSON (object or array) on stdin")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON on stdin: {e}")
    items = data if isinstance(data, list) else [data]
    path = TRACKS / a.track / "cards.jsonl"
    ensure_rewritable(path)
    cards = read_jsonl(path)
    in_track = {c.get("id") for c in cards}
    # ids are unique across ALL tracks (record/retire find a card by id alone)
    existing = in_track | {c.get("id") for t in all_tracks() if t != a.track
                           for c in read_jsonl(TRACKS / t / "cards.jsonl")}
    miscs = known_misconceptions(a.track)
    stubbed = []
    for item in items:
        for o in item.get("options") or []:
            m = o.get("misconception")
            if m and not o.get("correct") and MISC_RE.fullmatch(m) and m not in miscs:
                with (TRACKS / a.track / "misconceptions.md").open("a", encoding="utf-8") as f:
                    f.write(f"\n## {m}\n- belief: {o.get('text', '')}\n- why tempting: TODO\n- correction: TODO\n"
                            "- seen: anticipated (auto-added by add-card)\n")
                miscs.add(m)
                stubbed.append(m)
    prefix = "".join(w[0] for w in a.track.split("-"))[:4]
    n = len(cards)
    added, all_warnings, renamed = [], [], {}
    for item in items:
        item = dict(item)
        item["track"] = a.track
        asked = item.get("id")
        if asked and asked in existing and asked not in in_track:
            item["id"] = None  # taken by another track: give it a fresh id instead (existing ids never change)
        if not item.get("id"):
            n += 1
            while f"{prefix}-{n:03d}" in existing:
                n += 1
            item["id"] = f"{prefix}-{n:03d}"
            if asked:
                renamed[asked] = item["id"]
        if item["id"] in existing:
            die(f"id '{item['id']}' already exists")
        if item.get("options"):
            random.shuffle(item["options"])  # position of the correct answer is never chosen by the LLM
        errors, warnings = check_card(item, a.track, miscs)
        if errors:
            die("card rejected:\n  " + "\n  ".join(errors))
        all_warnings += warnings
        item["created"] = today().isoformat()
        item["srs"] = {"due": today().isoformat(), "interval": 0, "ease": DEFAULT_EASE, "reps": 0, "lapses": 0}
        cards.append(item)
        existing.add(item["id"])
        in_track.add(item["id"])
        added.append(public_view(item))
    write_jsonl(path, cards)
    res = {"added": added, "warnings": all_warnings}
    if renamed:
        res["renamed_ids"] = renamed
        res["renamed_note"] = "those ids are used by another track; the cards were stored under the new ids"
    if stubbed:
        res["misconceptions_stubbed"] = f"{stubbed}: added to misconceptions.md; fill in 'why tempting' and 'correction' when convenient"
    if any("options" in c for c in added):
        res["note"] = "present options in exactly this order with these letters; grade only via `record`"
    out(res)


def today_misses(tracks: list[str]) -> tuple[list[dict], list[dict]]:
    """(cards, nodes) missed today: a wrong or "don't know" scheduled answer (chat/review, not lesson/predict),
    or a task attempt with 2+ hints. Read-only; for the wrap-up retest."""
    day, cards, nodes = today().isoformat(), [], {}
    for t in tracks:
        by_id = {c.get("id"): c for c in read_jsonl(TRACKS / t / "cards.jsonl")}
        for at in read_jsonl(TRACKS / t / "attempts.jsonl"):
            if ts_day(at.get("ts")) != day:
                continue
            if at.get("kind") == "card" and at.get("source") not in UNSCHEDULED_SOURCES and at.get("correct") == "no":
                why = f"{at.get('card')}: {'dont-know' if at.get('dont_know') or at.get('choice') == 'X' else 'wrong'}"
                c = by_id.get(at.get("card"))
                if c and not c.get("retired") and c not in cards:
                    cards.append(c)
            elif at.get("kind") == "task" and (at.get("hints_used") or 0) >= 2:
                why = f"task {at.get('task')}: {at.get('hints_used')} hints"
            else:
                continue
            n = nodes.setdefault((t, at.get("node")), {"track": t, "node": at.get("node"), "why": []})
            if why not in n["why"]:
                n["why"].append(why)
    return cards, list(nodes.values())


def due_cards(track: str, horizon: str | None = None, ahead: bool = False) -> list[dict]:
    """Cards of one track due by `horizon` (default today). A card answered today is not due again today (unless
    looking ahead). A never-asked card counts only once its node has been worked on and it was written on an
    earlier day (a variant after a miss); a probe for an untaught node stays out."""
    horizon = horizon or today().isoformat()
    rows, started = [], None
    for c in read_jsonl(TRACKS / track / "cards.jsonl"):
        if c.get("retired"):
            continue
        if not c["srs"].get("last"):
            if started is None:
                started = {n for n, v in node_progress(track).items() if v.get("level", "new") != "new"}
            if c["node"] not in started or str(c.get("created") or "") >= today().isoformat():
                continue
        if c["srs"]["due"] <= horizon and (ahead or c["srs"].get("last") != today().isoformat()):
            rows.append(c)
    return rows


def cmd_due(a):
    tracks = [a.track] if a.track else all_tracks()
    if a.today_misses:
        cards, nodes = today_misses(tracks)
        picked = [public_view(c) for c in cards[:a.limit]]
        out({"due_total": len(cards), "showing": len(picked), "cards": picked, "nodes": nodes,
             "note": "retest each node with a DIFFERENT card (another existing one or a fresh variant), graded normally"})
        return
    horizon = (today() + dt.timedelta(days=a.ahead)).isoformat()
    rows = [c for t in tracks for c in due_cards(t, horizon, bool(a.ahead))]
    # most overdue first; mastery is per node, so a review asks ONE card per node (the most overdue, then the one
    # with most lapses); the node's other due cards wait (a correct answer pushes them forward, see record)
    rows.sort(key=lambda c: (c["srs"]["due"], -c["srs"].get("lapses", 0)))
    per_node, seen = [], set()
    for c in rows:
        if (c["track"], c["node"]) not in seen:
            seen.add((c["track"], c["node"]))
            per_node.append(c)
    picked, seen_nodes = [], []
    pool = per_node[:]
    while pool and len(picked) < a.limit:
        idx = next((i for i, c in enumerate(pool) if c["node"] not in seen_nodes[-2:]), 0)
        c = pool.pop(idx)
        picked.append(public_view(c))
        seen_nodes.append(c["node"])
    out({"due_total": len(rows), "due_nodes": len(per_node), "showing": len(picked), "cards": picked})


def cmd_record(a):
    track, cards, i = find_card(a.card)
    card = cards[i]
    result = {"card": card["id"], "node": card["node"]}
    misconception = a.misconception
    if a.dont_know:
        if a.choice or a.correct:
            die("--dont-know is the answer itself; don't pass --choice or --correct with it")
        correct = "no"
        result["chosen"] = "dont-know"
        if card.get("options"):
            right = next(j for j, o in enumerate(card["options"]) if o.get("correct"))
            result["correct_option"] = f"{LETTERS[right]}) {card['options'][right]['text']}"
        else:
            result["reference_answer"] = card.get("answer")
    elif card.get("options"):
        if not a.choice:
            die("this card has options: pass --choice A/B/C/D (or --choice X for 'I don't know')")
        letter = a.choice.upper()
        if letter == "X":
            correct = "no"
            result["chosen"] = "dont-know"
        else:
            idx = LETTERS.find(letter)
            if idx < 0 or idx >= len(card["options"]):
                die(f"choice must be one of {LETTERS[:len(card['options'])]} or X")
            chosen = card["options"][idx]
            correct = "yes" if chosen.get("correct") else "no"
            result["chosen"] = f"{letter}) {chosen['text']}"
            misconception = misconception or chosen.get("misconception")
        right = next(j for j, o in enumerate(card["options"]) if o.get("correct"))
        result["correct_option"] = f"{LETTERS[right]}) {card['options'][right]['text']}"
    else:
        if not a.correct:
            die("open-answer card: pass --correct yes|partial|no (your judgement against the reference answer)")
        correct = a.correct
        result["reference_answer"] = card.get("answer")
    old_srs = card["srs"]
    lesson = a.source in UNSCHEDULED_SOURCES
    if a.dont_know:
        confidence = 1  # "Bilmiyorum": any confidence answer is ignored
    elif lesson:
        # lesson: in-page quiz in an HTML lesson, open book. predict: a guess before the step is taught.
        # Both are diagnostic (which distractor), not evidence of retention → the card is NOT rescheduled and
        # the row is excluded from mastery. A lesson page collects confidence (Tahmin/Emin değilim/Eminim), so it
        # is kept when given (diagnosis: a sure wrong answer is the first thing to talk about); predict stores none.
        confidence = a.confidence if a.source == "lesson" else None
    else:
        confidence = a.confidence  # None = not asked
    if not lesson:
        ensure_rewritable(TRACKS / track / "cards.jsonl")  # check before appending anything
        card["srs"] = schedule(old_srs, quality(correct, confidence))
        cards[i] = card
        if correct == "yes":  # the node was just retrieved: its other due cards move forward (no new evidence)
            for j, c in enumerate(cards):
                if j != i and c.get("node") == card["node"] and not c.get("retired") and c["srs"].get("last") \
                        and c["srs"]["due"] <= today().isoformat():
                    c["srs"] = dict(c["srs"], due=(today() + dt.timedelta(days=max(1, c["srs"].get("interval", 1)))).isoformat())
    delayed = old_srs.get("last") is not None and old_srs.get("last") != today().isoformat()
    attempt = {"ts": now_iso(), "kind": "card", "card": card["id"],
               "node": card["node"], "type": card["type"], "correct": correct, "confidence": confidence,
               "misconception": misconception if correct != "yes" else None,
               "delayed": delayed, "session": a.session}
    if lesson:
        attempt["source"] = a.source
    if a.answer_text:
        attempt["answer_text"] = a.answer_text
    if a.dont_know:
        attempt["choice"] = None
        attempt["dont_know"] = True
    elif a.choice:
        attempt["choice"] = a.choice.upper()
    # Order matters: the attempt (the evidence) is appended first, then the card is rewritten.
    # A crash in between leaves a logged answer with an unchanged schedule (re-asked early), never the reverse.
    append_jsonl(TRACKS / track / "attempts.jsonl", attempt)
    if not lesson:
        write_jsonl(TRACKS / track / "cards.jsonl", cards)
    result.update({"correct": correct, "confidence": confidence, "misconception": attempt["misconception"],
                   "explanation": card.get("explanation"), "next_due": card["srs"]["due"]})
    if a.source == "lesson":
        result["note"] = "lesson answer: recorded for diagnosis only; not scheduled, not counted as mastery. Re-ask this node in chat."
    elif a.source == "predict":
        result["note"] = "prediction: recorded for diagnosis only; not scheduled, not counted as mastery. Open the teaching by resolving the guess."
    if correct == "no" and confidence == 3:
        result["flag"] = "high-confidence error: dig into the belief behind it before moving on (hypercorrection moment)"
    elif correct == "yes" and confidence == 1:
        result["flag"] = "correct but guessed: not evidence of knowledge; re-check this node soon with a different question"
    out(result)


def misconception_beliefs(track: str) -> dict[str, str]:
    f = TRACKS / track / "misconceptions.md"
    if not f.exists():
        return {}
    return dict(re.findall(r"^## (m-[a-z0-9-]+)\s*\n- belief: (.*)$", f.read_text(encoding="utf-8"), re.M))


def html_escape(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def cmd_cards(a):
    """Cards of a track/node for building a lesson: full view (correct option, misconceptions, explanation)."""
    d = track_dir(a.track)
    beliefs = misconception_beliefs(a.track)
    rows = []
    for c in read_jsonl(d / "cards.jsonl"):
        if c.get("retired") or (a.node and c["node"] not in a.node):
            continue
        row = {k: c.get(k) for k in ("id", "node", "type", "cue", "mode", "prompt", "code", "explanation", "answer") if c.get(k) is not None}
        if c.get("options"):
            row["options"] = [{"letter": LETTERS[i], "text": o["text"], "correct": bool(o.get("correct")),
                               "misconception": o.get("misconception"), "belief": beliefs.get(o.get("misconception"), None)}
                              for i, o in enumerate(c["options"])]
        rows.append(row)
    if not a.html:
        out({"track": a.track, "cards": rows})
        return
    # HTML skeleton for assets/components.js: option order = stored (shuffled) order; data-why left for you to
    # write in the learner's language (correct: from `explanation`; distractor: from the misconception).
    parts = []
    for r in rows:
        if r.get("options"):
            right = next(i for i, o in enumerate(r["options"]) if o["correct"])
            parts.append(f'<div class="quiz" data-card="{r["id"]}" data-answer="{right}">')
            parts.append(f'  <p class="q">{html_escape(r["prompt"])}</p>')
            if r.get("code"):
                parts.append(f'  <pre><code>{html_escape(r["code"])}</code></pre>')
            parts.append('  <div class="opts">')
            for o in r["options"]:
                why = "TODO: " + (f"neden doğru ({html_escape(r.get('explanation') or '')[:80]}…)" if o["correct"]
                                  else f"{o['misconception']}: {html_escape(o['belief'] or '')}")
                parts.append(f'    <button class="opt" data-why="{why}">{html_escape(o["text"])}</button>')
            parts.append('  </div>\n  <div class="feedback"></div>\n</div>\n')
        else:
            parts.append(f'<details class="recall" data-card="{r["id"]}">')
            parts.append(f'  <summary>{html_escape(r["prompt"])}</summary>')
            parts.append(f'  <p>{html_escape(r.get("answer") or "")}</p>\n</details>\n')
    if any(r.get("options") for r in rows):
        parts.append('<div class="score"></div>')
    print("\n".join(parts))


def cmd_retire(a):
    track, cards, i = find_card(a.card)
    ensure_rewritable(TRACKS / track / "cards.jsonl")
    cards[i]["retired"] = {"on": today().isoformat(), "reason": a.reason}
    write_jsonl(TRACKS / track / "cards.jsonl", cards)
    out({"retired": a.card, "reason": a.reason})


def cmd_verify_task(a):
    """Run a task's tests against a reference solution (stdin) in a temp copy; the learner's files are untouched."""
    d = Path(a.dir).resolve()
    if not (d / "TASK.md").exists():
        die(f"{a.dir} has no TASK.md")
    reference = sys.stdin.read()
    if not reference.strip():
        die("pass the reference solution on stdin")
    with tempfile.TemporaryDirectory() as tmp:
        for f in d.iterdir():
            if f.is_file() and not f.name.startswith("solution"):
                shutil.copy(f, tmp)
        Path(tmp, a.solution).write_text(reference, encoding="utf-8")
        uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
        cmd = [uv, "run", "--quiet", "pytest", "-q", tmp] if Path(uv).exists() or shutil.which("uv") \
            else [sys.executable, "-m", "pytest", "-q", tmp]
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out({"passed": r.returncode == 0, "output": (r.stdout + r.stderr)[-2000:],
         "note": "reference solution was used only in a temp dir and is gone; never put it in the learner's files"})


def cmd_task(a):
    track_dir(a.track)
    if a.status not in {"started", "passed", "failed", "explained"}:
        die("status must be started|passed|failed|explained")
    row = {"ts": now_iso(), "kind": "task", "task": a.task,
           "node": a.node, "status": a.status, "hints_used": a.hints, "note": a.note}
    append_jsonl(TRACKS / a.track / "attempts.jsonl", row)
    out({"recorded": row})


LEVELS = ["new", "struggling", "learning", "checked", "retained", "owned", "durable"]  # rank order for "the higher of"
DURABLE_DAYS, DURABLE_SPAN = 3, 21  # durable = owned + counted delayed correct answers on 3+ days spanning 21+ days


def _empty_node() -> dict:
    return {"cards": 0, "attempts": 0, "correct": 0, "delayed_correct": 0,
            "lapses": 0, "tasks_passed": 0, "explained": 0}


def _ladder(attempts: int, correct: int, partial: int, tasks: int, retained: bool, owned: bool) -> str:
    # mastery ladder: seen → checked (right in-session) → retained (right after a delay) → owned
    if attempts == 0 and tasks == 0:
        return "new"
    if owned:
        return "owned"
    if retained:
        return "retained"
    if correct:
        return "checked"
    if partial:
        return "learning"
    return "struggling"


def node_progress(track: str, with_map: bool = False, until: str | None = None) -> dict:
    """Per-node evidence and mastery level. with_map=True also lists every map node (no evidence → "new"),
    map order first, then evidence nodes missing from the map (flagged not_in_map).

    Levels. Old rules (all attempts before MASTERY_RULES_SINCE): retained = any delayed correct card answer;
    owned = retained + a passed task. New rules (attempts on/after it): a delayed correct answer counts only if
    the confidence was not 1 (a guess) and the card is generative (recall/explain/predict-output/spot-the-bug)
    or the node has a passed task (the task shows the learner can produce it); owned = retained + passed task,
    or such a delayed correct on a card with cue adjacent/far (recognized the idea away from how it was taught).
    Final level = the higher of the old-rule level from pre-date evidence and the new-rule level from all
    evidence, so nothing earned before the change disappears. `slipping` marks a node whose most recent delayed
    answer was wrong (level unchanged). `until` (YYYY-MM-DD) counts only the attempts up to that local day."""
    cards = read_jsonl(TRACKS / track / "cards.jsonl")
    attempts = read_jsonl(TRACKS / track / "attempts.jsonl")
    if until is not None:
        attempts = [at for at in attempts if ts_day(at.get("ts")) <= until]
    card_by_id = {c.get("id"): c for c in cards}
    nodes: dict[str, dict] = {}
    for c in cards:
        n = nodes.setdefault(c["node"], _empty_node())
        n["cards"] += 1
        n["lapses"] += c["srs"].get("lapses", 0)
    pre = {}      # node -> [attempts, correct, partial, tasks, delayed_correct]  (before MASTERY_RULES_SINCE)
    delayed = {}  # node -> [(ts, row)] delayed scheduled card answers, for the new rules and slipping
    for at in attempts:
        node = at.get("node") or "?"
        n = nodes.setdefault(node, _empty_node())
        old = ts_day(at.get("ts")) < MASTERY_RULES_SINCE
        p = pre.setdefault(node, [0, 0, 0, 0, 0])
        if at["kind"] == "card":
            if at.get("source") == "lesson":
                n["lesson_answers"] = n.get("lesson_answers", 0) + 1
                continue
            if at.get("source") == "predict":
                n["predict_answers"] = n.get("predict_answers", 0) + 1
                continue
            n["attempts"] += 1
            p[0] += old
            if at.get("delayed"):
                delayed.setdefault(node, []).append(at)
            if at["correct"] == "yes":
                n["correct"] += 1
                p[1] += old
                if at.get("delayed"):
                    n["delayed_correct"] += 1
                    p[4] += old
            elif at["correct"] == "partial":
                n["partial"] = n.get("partial", 0) + 1
                p[2] += old
        elif at["kind"] == "task":
            if at["status"] in ("passed", "explained"):
                n["tasks_passed"] += 1
                p[3] += old
            if at["status"] == "explained":
                n["explained"] += 1
    for node, n in nodes.items():
        p = pre.get(node, [0, 0, 0, 0, 0])
        old_level = _ladder(p[0], p[1], p[2], p[3], bool(p[4]), bool(p[4] and p[3]))
        has_task = n["tasks_passed"] > 0
        good = []  # delayed correct answers that count under the rules of their date
        for at in delayed.get(node, []):
            if at["correct"] != "yes":
                continue
            if ts_day(at.get("ts")) < MASTERY_RULES_SINCE or (
                    at.get("confidence") != 1 and (at.get("type") in GENERATIVE_TYPES or has_task)):
                good.append(at)
        far = any((card_by_id.get(at.get("card")) or {}).get("cue") in ("adjacent", "far") for at in good)
        new_level = _ladder(n["attempts"], n["correct"], n.get("partial", 0), n["tasks_passed"],
                            bool(good), bool(good and (has_task or far)))
        n["level"] = max(old_level, new_level, key=LEVELS.index)
        days = sorted({ts_day(at.get("ts")) for at in good})
        if n["level"] == "owned" and len(days) >= DURABLE_DAYS and \
                (dt.date.fromisoformat(days[-1]) - dt.date.fromisoformat(days[0])).days >= DURABLE_SPAN:
            n["level"] = "durable"  # spaced retrieval held over weeks, not only once
        if delayed.get(node):
            last = max(delayed[node], key=lambda r: parse_ts(r.get("ts")))
            if last["correct"] == "no":
                n["slipping"] = True
    ids = map_node_ids(track) if with_map else []
    if not ids:  # no map (or nothing parseable in it): evidence nodes only, as before
        return nodes
    ordered = {}
    for nid in ids:
        ordered[nid] = nodes.pop(nid, None) or dict(_empty_node(), level="new")
    for nid, n in nodes.items():
        n["not_in_map"] = True
        ordered[nid] = n
    return ordered


def cmd_map(a):
    track_dir(a.track)
    m = track_map(a.track)
    if m is None:
        die(f"tracks/{a.track}/map.md not found")
    res = {"track": a.track, "nodes": [{k: v for k, v in n.items() if k != "line"} for n in m["nodes"]],
           "edges": m["edges"], "problems": m["problems"]}
    if a.json:
        out(res)
        return
    lines = [f"# map {a.track}: {len(res['nodes'])} nodes, {len(res['edges'])} edges"]
    for n in res["nodes"]:
        deps = ", ".join(n["depends_on"]) or "–"
        lines.append(f"- {n['id']} [{n.get('kind', '?')}] ← {deps}: {n.get('statement') or n.get('title') or ''}")
    lines += ["", "problems:"] + [f"- {p}" for p in m["problems"]] if m["problems"] else ["", "problems: none"]
    print("\n".join(lines))


def cmd_progress(a):
    tracks = [a.track] if a.track else all_tracks()
    report = {}
    for t in tracks:
        attempts = read_jsonl(TRACKS / t / "attempts.jsonl")
        misc_counts: dict[str, int] = {}
        for at in attempts:
            if at.get("misconception"):
                misc_counts[at["misconception"]] = misc_counts.get(at["misconception"], 0) + 1
        report[t] = {"nodes": node_progress(t, with_map=True),
                     "recurring_misconceptions": dict(sorted(misc_counts.items(), key=lambda x: -x[1])[:8])}
    out(report)


def generation_gap(rows: list[dict]) -> dict:
    """Recognition vs production: MCQ accuracy minus generative accuracy. None = not enough data (not zero)."""
    mcq = [r for r in rows if r.get("type") == "mcq"]
    gen = [r for r in rows if r.get("type") in GENERATIVE_TYPES]

    def rate(rs):
        return round(sum(r.get("correct") == "yes" for r in rs) / len(rs), 2) if rs else None
    m, g = rate(mcq), rate(gen)
    gap = round(m - g, 2) if m is not None and g is not None else None
    return {"mcq_accuracy": m, "generative_accuracy": g, "gap": gap, "n_mcq": len(mcq), "n_generative": len(gen),
            "flag": (gap > 0.3) if len(mcq) >= 8 and len(gen) >= 8 else None}


def cmd_signals(a):
    """How this learner learns, computed from their answers across all tracks."""
    cards_att, tasks, lesson_att, predict_att = [], [], [], []
    for t in all_tracks():
        for at in read_jsonl(TRACKS / t / "attempts.jsonl"):
            if at["kind"] != "card":
                tasks.append(at)
            elif at.get("source") == "lesson":
                lesson_att.append(at)
            elif at.get("source") == "predict":
                predict_att.append(at)
            else:
                cards_att.append(at)
    if not cards_att:
        out({"note": "no answers recorded yet"})
        return

    def acc(rows):
        return {"n": len(rows), "correct_rate": round(sum(r["correct"] == "yes" for r in rows) / len(rows), 2)} if rows else {"n": 0}

    names = {1: "guessed", 2: "unsure", 3: "sure"}
    calib = {names[c]: acc([r for r in cards_att if r.get("confidence") == c]) for c in (1, 2, 3)}
    sure, unsure = calib["sure"], calib["unsure"]
    if sure.get("n", 0) >= 5 and sure["correct_rate"] < 0.7:
        reading = "overconfident: 'sure' answers are often wrong → ask why they are sure, more explain cards, slow down"
    elif unsure.get("n", 0) >= 5 and unsure["correct_rate"] > 0.8:
        reading = "underconfident: 'unsure' answers are mostly right → point out the evidence, fade support faster"
    else:
        reading = "roughly calibrated (or too little data)"
    by_type = {}
    for r in cards_att:
        by_type.setdefault(r["type"], []).append(r)
    recent, earlier = cards_att[-20:], cards_att[-40:-20]
    passed = [t for t in tasks if t["status"] in ("passed", "explained")]
    out({
        "answers": len(cards_att),
        "calibration": calib, "calibration_reading": reading,
        "high_confidence_errors": sum(r["correct"] == "no" and r.get("confidence") == 3 for r in cards_att),
        "dont_know_rate": round(sum(r.get("choice") == "X" or bool(r.get("dont_know")) for r in cards_att) / len(cards_att), 2),
        "by_question_type": {k: acc(v) for k, v in by_type.items()},
        "delayed_recall": acc([r for r in cards_att if r.get("delayed")]),
        "lesson_quiz": acc(lesson_att),
        "predictions": acc(predict_att),
        "generation_gap": generation_gap(cards_att),
        "trend": {"last_20": acc(recent), "previous_20": acc(earlier)},
        "tasks": {"events": len(tasks), "passed": len(passed),
                  "avg_hints_when_passed": round(sum(t.get("hints_used", 0) for t in passed) / len(passed), 1) if passed else None},
        "use": "update the Observed sections of learner/profile.md only with patterns that hold across sessions; cite the evidence",
    })


# ── engagement pacing ("chocolate"): when to recap, tease, celebrate ─────────
# The LLM decides what to say; this decides *when*, so it is neither every message nor never.

MOMENT_KINDS = {"recap", "cheatsheet", "teaser", "value", "milestone", "lesson"}
RECAP_EVERY_NODES = 4      # newly checked nodes since the last recap


def all_attempts() -> list[dict]:
    rows = []
    for t in all_tracks():
        for at in read_jsonl(TRACKS / t / "attempts.jsonl"):
            at["track"] = t
            rows.append(at)
    return sorted(rows, key=lambda r: parse_ts(r.get("ts")))


def checked_nodes() -> int:
    return sum(1 for t in all_tracks() for n in node_progress(t).values()
               if n["level"] in ("checked", "retained", "owned", "durable"))


def study_days(attempts: list[dict]) -> list[str]:
    return sorted({ts_day(r.get("ts")) for r in attempts})


def streak(days: list[str]) -> int:
    if not days:
        return 0
    d = dt.date.fromisoformat(days[-1])
    if (today() - d).days > 1:
        return 0
    have, n = set(days), 0
    while d.isoformat() in have:
        n += 1
        d -= dt.timedelta(days=1)
    return n


def achieved_milestones(attempts: list[dict]) -> list[str]:
    m = []
    cards = [r for r in attempts if r["kind"] == "card" and r.get("source") != "predict"]  # a guess is no achievement
    tasks = [r for r in attempts if r["kind"] == "task"]
    if any(r["correct"] == "yes" for r in cards):
        m.append("first-correct-answer")
    if any(r["correct"] == "yes" and r.get("delayed") for r in cards):
        m.append("first-remembered-after-a-delay")
    if any(t["status"] in ("passed", "explained") for t in tasks):
        m.append("first-task-passed")
    if any(n["level"] in ("owned", "durable") for t in all_tracks() for n in node_progress(t).values()):
        m.append("first-node-owned")
    c = checked_nodes()
    m += [f"{k}-nodes-learned" for k in (5, 10, 20, 40) if c >= k]
    s = streak(study_days(attempts))
    m += [f"{k}-day-streak" for k in (3, 7, 14, 30) if s >= k]
    for t in all_tracks():
        nodes = node_progress(t, with_map=True)  # every map node must be retained, not only the ones touched
        if len(nodes) >= 5 and all(n["level"] in ("retained", "owned", "durable") for n in nodes.values()):
            m.append(f"track-{t}-retained")
    return m


def engagement_hints() -> list[str]:
    moments = read_jsonl(MOMENTS)
    attempts = all_attempts()
    hints = []

    def last(kind):
        return next((r for r in reversed(moments) if r["kind"] == kind), None)

    r = last("recap")
    new_nodes = checked_nodes() - (r.get("checked_nodes", 0) if r else 0)
    if new_nodes >= RECAP_EVERY_NODES:
        hints.append(f"recap due: {new_nodes} nodes newly learned since the last recap → at a natural break, "
                     "'şimdiye kadar neler öğrendik' + link to cheatsheet (then: tools/learn moment --kind recap)")
    offered = " ".join(str(r.get("note") or "") for r in moments if r["kind"] == "cheatsheet")
    for t in all_tracks():
        owned = [k for k, n in node_progress(t).items() if n["level"] in ("owned", "durable")
                 and not re.search(rf"(?<![a-z0-9-]){re.escape(k)}(?![a-z0-9-])", offered)]
        if owned:
            hints.append(f"cheatsheet: {t}/{owned[0]} reached owned → offer to add it to tracks/{t}/cheatsheet.md "
                         f"together (then: tools/learn moment --kind cheatsheet --note {t}/{owned[0]})")
            break
    celebrated = {r.get("note") for r in moments if r["kind"] == "milestone"}
    fresh = [m for m in achieved_milestones(attempts) if m not in celebrated]
    if fresh:
        hints.append(f"uncelebrated milestone: {fresh[0]} → acknowledge it with evidence, briefly "
                     f"(then: tools/learn moment --kind milestone --note {fresh[0]})")
    return hints


def cmd_moment(a):
    if a.kind not in MOMENT_KINDS:
        die(f"kind must be one of {sorted(MOMENT_KINDS)}")
    LEARNER.mkdir(exist_ok=True)
    row = {"ts": now_iso(), "kind": a.kind, "note": a.note,
           "checked_nodes": checked_nodes()}
    append_jsonl(MOMENTS, row)
    out({"recorded": row})


def cmd_journey(a):
    """Then-vs-now facts for a recap: concrete evidence of growth."""
    attempts = all_attempts()
    if not attempts:
        out({"note": "nothing recorded yet"})
        return
    days = study_days(attempts)
    cards = [r for r in attempts if r["kind"] == "card" and r.get("source") != "predict"]  # guesses before teaching
    first10, last10 = cards[:10], cards[-10:]

    def rate(rows):
        return round(sum(r["correct"] == "yes" for r in rows) / len(rows), 2) if rows else None

    per_track = {}
    for t in all_tracks():
        nodes = node_progress(t)
        per_track[t] = {"learned": sorted(k for k, n in nodes.items() if n["level"] in ("checked", "retained", "owned", "durable")),
                        "owned": sorted(k for k, n in nodes.items() if n["level"] in ("owned", "durable")),
                        "struggling": sorted(k for k, n in nodes.items() if n["level"] == "struggling")}
    out({"started": days[0], "study_days": len(days), "current_streak": streak(days),
         "answers": len(cards), "accuracy_first_10": rate(first10), "accuracy_last_10": rate(last10),
         "tasks_passed": sum(1 for r in attempts if r["kind"] == "task" and r["status"] in ("passed", "explained")),
         "tracks": per_track})


def handoff_next(track: str) -> str:
    f = TRACKS / track / "handoff.md"
    if not f.exists():
        return ""
    text = f.read_text(encoding="utf-8")
    m = re.search(r"##\s*Next step\s*\n(.*?)(\n##|\Z)", text, re.S | re.I)
    return (m.group(1) if m else text).strip()[:600]


def data_warning_lines(limit: int = 12) -> list[str]:
    """The DATA WARNING block for status: empty when all data reads cleanly."""
    problems = scan_data()
    lines = []
    for p in problems[:limit]:
        what = f"line {p['line']} unreadable" if p["line"] else f"unreadable ({p['note']})"
        lines.append(f"DATA WARNING: {p['file']} {what} → run: tools/learn doctor-data")
    if len(problems) > limit:
        lines.append(f"DATA WARNING: … and {len(problems) - limit} more → run: tools/learn doctor-data")
    if problems:
        lines.append("(unreadable lines are skipped below; commands that rewrite those files refuse until fixed. "
                     "Tell the maintainer; don't edit data files by hand.)")
    contract = scan_contract()
    if contract:
        lines.append(f"DATA WARNING: {len(contract)} row(s) break the data contract (schemas/), first: "
                     f"{contract[0]['file']} line {contract[0]['line']} → run: tools/learn doctor-data")
    v = format_version()
    if v is not None and v > FORMAT_VERSION:
        lines.append(f"DATA WARNING: learner/format.json is version {v}, newer than this engine ({FORMAT_VERSION}) "
                     "→ update tools/ before recording anything; writes are refused until then.")
    return ["", "## DATA WARNING"] + lines + [""] if lines else []


def cmd_status(a):
    """Short, human-readable; printed into Claude's context at session start."""
    lines = ["# Learning system status",
             f"session started: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} (check `date` later to keep to the time budget)"]
    lines += data_warning_lines()
    profile = LEARNER / "profile.md"
    if not profile.exists():
        lines += ["learner: NO PROFILE YET → run the onboarding skill first (greet, explain how this works, build learner/profile.md)."]
        if (LEARNER / "intake.md").exists():
            lines.append("mentor notes: learner/intake.md exists → read it and confirm with the learner instead of re-asking.")
        print("\n".join(lines))
        return
    state = load_state()
    active = state.get("active_track")
    tracks = all_tracks()
    if not tracks:
        lines.append("tracks: none yet → use the new-track skill once the learner's goal is clear.")
    for t in tracks:
        cards = read_jsonl(TRACKS / t / "cards.jsonl")
        due_rows = due_cards(t)
        due = f"{len(due_rows)} cards on {len({c['node'] for c in due_rows})} nodes"
        mark = " (ACTIVE)" if t == active else ""
        levels: dict[str, int] = {}
        for n in node_progress(t).values():
            levels[n["level"]] = levels.get(n["level"], 0) + 1
        n_lessons = len(list((TRACKS / t / "lessons").glob("*.html"))) if (TRACKS / t / "lessons").is_dir() else 0
        extra = f", {n_lessons} lessons" if n_lessons else ""
        lines.append(f"- track {t}{mark}: {len(cards)} cards, due for review today: {due}{extra}, nodes {levels or '{}'}")
    lesson_lines = []
    for t in tracks:
        unrecorded, unbound = lesson_status(t)
        bits = ([f"sonucu kaydedilmedi: {', '.join(unrecorded)}"] if unrecorded else []) + \
               ([f"quiz bağlı değil: {', '.join(unbound)}"] if unbound else [])
        if bits:
            lesson_lines.append(f"- {t}: " + "; ".join(bits))
    if lesson_lines:
        lines += ["", "## Lessons (record quiz results: record --source lesson; bind quizzes: cards --html)"] + lesson_lines
    if active:
        nxt = handoff_next(active)
        if nxt:
            lines += ["", f"## Resume point ({active}/handoff.md)", nxt]
    unlogged = unlogged_days()
    if unlogged:
        lines += ["", "## UNLOGGED SESSIONS (the session ended without a wrap-up; do this first, silently)"] + \
                 [f"- {u}" for u in unlogged]
    gaps = notes_gaps()
    if gaps:
        lines += ["", "## Notes gaps (fill before wrap-up ends; the dashboard's node cards show these)"] + [f"- {g}" for g in gaps]
    hints = engagement_hints()
    if hints:
        lines += ["", "## Engagement (see teach/engagement.md; never during struggle)"] + [f"- {h}" for h in hints]
    print("\n".join(lines))


def unlogged_days() -> list[str]:
    """Study days with recorded answers or tasks but no line in the track's handoff session log (dates read from
    lines starting "- YYYY-MM-DD"). Today counts too: status runs at session start, so answers from today with no
    log line belong to an earlier session today that closed without a wrap-up."""
    out = []
    for t in all_tracks():
        f = TRACKS / t / "handoff.md"
        logged = set(re.findall(r"^- (\d{4}-\d{2}-\d{2})", f.read_text(encoding="utf-8"), re.M)) if f.exists() else set()
        rows = [r for r in read_jsonl(TRACKS / t / "attempts.jsonl") if r.get("ts")]
        days = sorted({ts_day(r["ts"]) for r in rows} - logged)
        days = [d for d in days if d <= today().isoformat() and (not logged or d > min(logged))]
        for d in days:
            n = sum(1 for r in rows if ts_day(r["ts"]) == d)
            out.append(f"{t}: {d} has {n} recorded answers/tasks but no session-log line → rebuild it from "
                       f"tracks/{t}/attempts.jsonl (answer_text, misconception, task notes): append the log line, "
                       f"update \"Next step\" and misconceptions.md, then continue")
    return out


def notes_gaps() -> list[str]:
    """Per track: done nodes (retained / owned) taught in no lesson or with no cheatsheet section, and map nodes
    with no `tanım (öğrenci)`.
    The node card on the dashboard shows both, so a gap is visible to the learner."""
    out = []
    for t in all_tracks():
        m = track_map(t)
        if not m:
            continue
        sheet = cheatsheet_sections(TRACKS / t / "cheatsheet.md")
        prog = node_progress(t, True)
        no_sum = [n["id"] for n in m["nodes"] if (prog.get(n["id"]) or {}).get("level") in DONE
                  and _norm_heading(n["id"]) not in sheet and _norm_heading(n.get("title") or "") not in sheet]
        no_def = [n["id"] for n in m["nodes"] if not n.get("definition")]
        taught = set()
        lessons_dir = TRACKS / t / "lessons"
        if lessons_dir.is_dir():
            cards = {c.get("id"): c.get("node") for c in read_jsonl(TRACKS / t / "cards.jsonl")}
            for f in sorted(lessons_dir.glob("*.html")):
                text = f.read_text(encoding="utf-8")
                taught |= set(lesson_facts(f, text, lesson_card_ids(text), cards, [])["nodes"])
        no_les = [n["id"] for n in m["nodes"] if (prog.get(n["id"]) or {}).get("level") in DONE and n["id"] not in taught]
        if no_les:
            out.append(f"{t}: done but in no lesson: {', '.join(no_les)} → one lesson per cluster of 2–4 related nodes "
                       f"(lesson skill; declare them in the lesson-map comment)")
        if no_sum:
            out.append(f"{t}: done without a cheatsheet section: {', '.join(no_sum)} → write `## <id>` in "
                       f"tracks/{t}/cheatsheet.md from their own recorded answers (cheatsheet skill)")
        if no_def:
            out.append(f"{t}: map nodes without `tanım (öğrenci)`: {', '.join(no_def)} → add it in tracks/{t}/map.md")
    return out


def cmd_validate(a):
    tracks = [a.track] if a.track else all_tracks()
    report, failed = {}, False
    for t in tracks:
        e, w = validate_track(t)
        report[t] = {"errors": e, "warnings": w, "ok": not e}
    if not a.track:
        # record/retire find a card by id alone, so an id must be unique across tracks
        owners: dict[str, list[str]] = {}
        for t in tracks:
            for cid in dict.fromkeys(c.get("id") for c in read_jsonl(TRACKS / t / "cards.jsonl")):
                owners.setdefault(cid, []).append(t)
        for cid, ts in owners.items():
            if len(ts) > 1:
                for t in ts:
                    report[t]["errors"].append(f"{cid}: duplicate id across tracks ({', '.join(ts)})")
                    report[t]["ok"] = False
    failed = any(not r["ok"] for r in report.values())
    out(report)
    sys.exit(1 if failed else 0)


# ── export: the one read-only data contract for any UI ─────────────────────
# `export --json` is the only thing a UI (the dashboard below, or anything later) may build on.
# It carries structure and evidence counts, never what would spoil a question: no card prompts, options,
# answers, explanations, misconceptions, srs ease/interval/dates, accuracy rates or profile text.
# Unknown values are null, never 0.

EXPORT_SCHEMA = "teach.export/1"
DONE_LEVELS = ("checked", "retained", "owned", "durable")
TRACK_FILES = (("handoff", "handoff.md"), ("cheatsheet", "cheatsheet.md"), ("glossary", "glossary.md"),
               ("map", "map.md"), ("resources", "RESOURCES.md"))


def first_heading(path: Path) -> str | None:
    if not path.exists():
        return None
    m = re.search(r"^#\s+(.+?)\s*$", path.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def lesson_title(text: str, stem: str) -> str:
    m = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
    t = _html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""
    return t if t and "{{" not in t else stem


def topo_order(ids: list[str], edges: list[tuple[str, str]]) -> list[str]:
    """Kahn's order, ties broken by the given order; nodes on a cycle follow in the given order."""
    idx = {n: i for i, n in enumerate(ids)}
    succ: dict[str, list[str]] = {n: [] for n in ids}
    indeg = {n: 0 for n in ids}
    for a, b in edges:
        succ[a].append(b)
        indeg[b] += 1
    heap = [idx[n] for n in ids if indeg[n] == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        n = ids[heapq.heappop(heap)]
        order.append(n)
        for m in succ[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                heapq.heappush(heap, idx[m])
    seen = set(order)
    return order + [n for n in ids if n not in seen]


def next_node(nodes: list[dict], edges: list[dict]) -> str | None:
    """The node to study next, in dependency order: an unfinished one already started (learning/struggling); else
    the first new node whose prerequisites are all checked or better (preferring one that has prerequisites, i.e.
    continues a learned chain, over a fresh root); else the first unfinished node. None = everything checked+."""
    pool = [n for n in nodes if n["in_map"]] or nodes
    ids = [n["id"] for n in pool]
    level = {n["id"]: n["level"] for n in pool}
    pairs = [(e["from"], e["to"]) for e in edges if e["from"] in level and e["to"] in level and e["from"] != e["to"]]
    order = topo_order(ids, list(dict.fromkeys(pairs)))
    deps = {n: [a for a, b in pairs if b == n] for n in ids}
    for n in order:
        if level[n] in ("learning", "struggling"):
            return n
    ready = [n for n in order if level[n] == "new" and all(level[d] in DONE_LEVELS for d in deps[n])]
    if ready:  # one that builds on something already learned first, then a fresh root
        return next((n for n in ready if deps[n]), ready[0])
    return next((n for n in order if level[n] not in DONE_LEVELS), None)


def cheatsheet_sections(path: Path) -> dict[str, str]:
    """`## <heading>` sections of a cheatsheet, keyed by the normalised heading ("Implication" → "implication")."""
    if not path.exists():
        return {}
    out, key, buf = {}, None, []
    for ln in re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S).splitlines():
        m = re.match(r"##\s+(.+?)\s*$", ln)
        if m or re.match(r"#\s", ln):
            if key and "".join(buf).strip():
                out[key] = "\n".join(buf).strip()
            key, buf = (_norm_heading(m.group(1)) if m else None), []
        elif key:
            buf.append(ln)
    if key and "".join(buf).strip():
        out[key] = "\n".join(buf).strip()
    return out


def _norm_heading(s: str) -> str:
    return " ".join(re.sub(r"[*_`]", "", s).replace("-", " ").lower().split())


def track_export(t: str) -> dict:
    d = TRACKS / t
    m = track_map(t)
    by_id = {n["id"]: n for n in m["nodes"]} if m else {}
    sheet = cheatsheet_sections(d / "cheatsheet.md")
    nodes = []
    for nid, n in node_progress(t, with_map=True).items():
        mn = by_id.get(nid, {})
        summary = sheet.get(_norm_heading(nid)) or (sheet.get(_norm_heading(mn["title"])) if mn.get("title") else None)
        nodes.append({"id": nid, "title": mn.get("title"), "statement": mn.get("statement"), "kind": mn.get("kind"),
                      "definition": mn.get("definition"), "summary": summary,
                      "depends_on": list(mn.get("depends_on", [])), "in_map": nid in by_id,
                      "level": n["level"], "slipping": bool(n.get("slipping")),
                      "evidence": {k: n[k] for k in ("attempts", "correct", "delayed_correct", "tasks_passed")}})
    edges = [{"from": e["from"], "to": e["to"]} for e in (m["edges"] if m else [])]
    problems = list(m["problems"]) if m else ["no map.md"]
    cards = read_jsonl(d / "cards.jsonl")
    day, tomorrow = today().isoformat(), (today() + dt.timedelta(days=1)).isoformat()
    live = [c.get("srs") or {} for c in cards if not c.get("retired") and (c.get("srs") or {}).get("last")]
    due_now = due_cards(t)
    studied = {n["id"] for n in nodes if n["level"] != "new"}
    stale = ({c["node"] for c in due_now} | {n["id"] for n in nodes if n["slipping"]}) & studied
    due = {"today": len(due_now), "tomorrow": sum(1 for s in live if s.get("due") == tomorrow),
           "nodes_today": len({c["node"] for c in due_now}), "studied": len(studied), "fresh": len(studied - stale)}
    attempts = read_jsonl(d / "attempts.jsonl")
    recorded = {at.get("card") for at in attempts if at.get("source") == "lesson"}
    tasks: dict[str, dict] = {}
    if (d / "tasks").is_dir():
        for p in sorted(x for x in (d / "tasks").iterdir() if x.is_dir()):
            tasks[p.name] = {"id": p.name, "node": None, "last_status": None}
    for at in attempts:
        if at.get("kind") == "task" and at.get("task"):
            row = tasks.setdefault(str(at["task"]), {"id": str(at["task"]), "node": None, "last_status": None})
            row["node"], row["last_status"] = at.get("node"), at.get("status")
    title = first_heading(d / "README.md") or t
    task_rows = [tasks[k] for k in sorted(tasks)]
    files = {k: (rel(d / f) if (d / f).exists() else None) for k, f in TRACK_FILES}
    docs = export_docs(t, title, files, task_rows)
    node_of_card = {c.get("id"): c.get("node") for c in cards}
    lessons = []
    if (d / "lessons").is_dir():
        for f in sorted((d / "lessons").glob("*.html")):
            text = f.read_text(encoding="utf-8")
            refs = lesson_card_ids(text)
            row = {"path": rel(f), "title": lesson_title(text, f.stem),
                   "result_recorded": bool(recorded & set(refs)) if refs else None}
            lessons.append(dict(row, **lesson_facts(f, text, refs, node_of_card, docs)))
    for i, les in enumerate(lessons):
        les["number"] = lesson_number(les, lessons)
    days = study_days(attempts)
    resume = re.sub(r"[*_`]", "", handoff_first_sentence(t)) or None
    return {"id": t, "title": title,
            "map": {"nodes": nodes, "edges": edges, "problems": problems},
            "next": next_node(nodes, edges), "due": due, "lessons": lessons,
            "tasks": task_rows, "files": files, "docs": docs,
            "last_studied": days[-1] if days else None, "resume": resume}


DOC_TYPES = (("cheatsheet", "cheatsheet"), ("glossary", "glossary"), ("resources", "resources"), ("map", "map"))


def md_title(path: Path, track_title: str) -> str:
    """A note's title: its first heading minus a trailing " — <track title>"."""
    m = re.search(r"^#\s+(.+?)\s*$", path.read_text(encoding="utf-8"), re.M)
    title = m.group(1) if m else path.stem
    for sep in (" — ", " – ", " - "):
        if title.endswith(sep + track_title):
            title = title[: -len(sep + track_title)]
    return title


def md_body(path: Path) -> str:
    """A note's body as escaped HTML, without its first heading (the side panel shows the title)."""
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    if m:
        text = text[: m.start()] + text[m.end():]
    return md_to_html(text)


def export_docs(t: str, track_title: str, files: dict, tasks: list[dict]) -> list[dict]:
    """The notes & documents of a track, in order: cheatsheet, glossary, RESOURCES.md, map.md, reference/*.html
    (title = <h1>, else <title>), tasks/*/TASK.md. Never handoff, misconceptions, cards or solutions."""
    docs = []
    for key, typ in DOC_TYPES:
        path = files.get(key)
        if path and (ROOT / path).is_file():
            docs.append({"id": key, "type": typ, "title": "Harita (metin)" if key == "map" else md_title(ROOT / path, track_title),
                         "path": path})
    ref = TRACKS / t / "reference"
    if ref.is_dir():
        for f in sorted(ref.glob("*.html")):
            text = f.read_text(encoding="utf-8")
            h1 = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S | re.I)
            title = _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h1.group(1)))).strip() if h1 else ""
            docs.append({"id": "ref-" + f.stem, "type": "reference", "title": title or lesson_title(text, f.stem),
                         "path": rel(f)})
    for tk in tasks:
        f = TRACKS / t / "tasks" / tk["id"] / "TASK.md"
        if f.is_file():
            docs.append({"id": "task-" + tk["id"], "type": "task", "title": md_title(f, track_title), "path": rel(f),
                         "node": tk["node"]})
    return docs


def lesson_map_args(text: str) -> dict | None:
    """The arguments of a lesson's <!-- lesson-map: --track t --nodes a,b [--current c] --> comment."""
    m = re.search(r"<!--\s*lesson-map:(.*?)-->", text, re.S)
    if not m:
        return None
    out = {}
    for opt in ("track", "nodes", "current"):
        mm = re.search(rf"--{opt}\s+([\w,-]+)", m.group(1))
        if mm:
            out[opt] = mm.group(1)
    return out if out.get("track") and out.get("nodes") else None


def lesson_facts(f: Path, text: str, refs: list[str], node_of_card: dict, docs: list[dict]) -> dict:
    """What the dashboard needs about one lesson: its slug, the nodes it teaches (lesson-map comment, map slot,
    its cards' nodes), the track documents that belong to it (the ones it links to, tasks on its nodes) and its
    sources (the .source block and the refs list: external links)."""
    nodes = set()
    args = lesson_map_args(text)
    if args:
        nodes |= {x for x in (args["nodes"] + "," + args.get("current", "")).split(",") if x}
    for m in re.finditer(r'data-(?:nodes|current)="([^"]*)"', text):
        nodes |= {x.strip() for x in m.group(1).split(",") if x.strip()}
    nodes |= {node_of_card.get(r) for r in refs}
    nodes.discard(None)
    linked = set()
    for h in re.findall(r'href="([^"#]+)', text):
        if not re.match(r"[a-z][\w+.-]*:", h, re.I):
            linked.add(os.path.normpath(f.parent / _html.unescape(h).split("?")[0]))
    mine = [d["id"] for d in docs if (d["type"] != "task" and os.path.normpath(ROOT / d["path"]) in linked)
            or (d["type"] == "task" and d.get("node") in nodes)]
    sources, seen = [], set()
    for blk in re.findall(r'<div class="source">(.*?)</div>|<ol class="refs">(.*?)</ol>', text, re.S):
        for href, label in re.findall(r'<a href="(https?://[^"]+)"[^>]*>(.*?)</a>', "".join(blk), re.S):
            href = _html.unescape(href)
            if href not in seen:
                seen.add(href)
                sources.append({"title": _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", label))).strip() or href,
                                "href": href})
    return {"slug": re.sub(r"[^\w-]", "-", f.stem, flags=re.A) or "ders", "nodes": sorted(nodes), "docs": mine,
            "sources": sources}


def export_gains() -> list[dict]:
    """Then-vs-now evidence: nodes missed on the first try and answered right later (after a delay = stronger).
    Newest first, strongest first. Node ids only; never card text."""
    found = []
    for t in all_tracks():
        rows = [r for r in read_jsonl(TRACKS / t / "attempts.jsonl")
                if r.get("kind") == "card" and r.get("source") != "predict" and r.get("node")]
        rows.sort(key=lambda r: parse_ts(r.get("ts")))
        by_node: dict[str, list[dict]] = {}
        for r in rows:
            by_node.setdefault(r["node"], []).append(r)
        for node, rs in by_node.items():
            later = [r for r in rs[1:] if r.get("correct") == "yes"]
            if rs[0].get("correct") == "yes" or not later:
                continue
            delayed = [r for r in later if r.get("delayed")]
            found.append((bool(delayed), parse_ts((delayed or later)[-1].get("ts")),
                          {"track": t, "node": node, "delayed": bool(delayed)}))
    found.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [x[2] for x in found]


DONE = ("retained", "owned", "durable")
MARK = {"retained": "✓", "owned": "✓✓", "durable": "✓✓✓"}  # the done badge: öğrenildi / uygulandı / kalıcı


def export_recent(limit: int = 14) -> list[dict]:
    """The last `limit` (day, track) study pairs, newest first, each with what changed that day: nodes that reached
    done (retained / owned), nodes started, nodes that began slipping, nodes remembered after a first miss (a delayed
    correct answer), the number of chat answers, and that day's milestones (on the day's first row). Node ids only."""
    stones: dict[str, list[str]] = {}
    for r in read_jsonl(MOMENTS):
        if r.get("kind") == "milestone" and r.get("note"):
            stones.setdefault(ts_day(r.get("ts")), []).append(str(r["note"]))
    order = {t: i for i, t in enumerate(all_tracks())}
    pairs, rows_of = [], {}
    for t in order:
        rows = [r for r in read_jsonl(TRACKS / t / "attempts.jsonl") if r.get("ts")]
        rows.sort(key=lambda r: parse_ts(r.get("ts")))
        rows_of[t] = rows
        pairs += [(d, t) for d in sorted({ts_day(r["ts"]) for r in rows})]
    pairs.sort(key=lambda x: (x[0], -order[x[1]]), reverse=True)
    out, seen_day = [], set()
    for d, t in pairs[:limit]:
        prev = (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()
        before, after = node_progress(t, True, until=prev), node_progress(t, True, until=d)
        lv = lambda nodes, n: (nodes.get(n) or {}).get("level", "new")
        done = [{"node": n, "level": lv(after, n)} for n in after
                if lv(after, n) in DONE and LEVELS.index(lv(after, n)) > LEVELS.index(lv(before, n))]
        started = [n for n in after if lv(before, n) == "new" and lv(after, n) != "new" and n not in {x["node"] for x in done}]
        slipping = [n for n in after if (after[n].get("slipping") and not (before.get(n) or {}).get("slipping"))]
        cards = [r for r in rows_of[t] if r.get("kind") == "card" and r.get("source") not in ("lesson", "predict")]
        first: dict[str, dict] = {}
        for r in cards:
            first.setdefault(r.get("node"), r)
        remembered = []
        for n in after:
            if n not in first or first[n].get("correct") == "yes" or ts_day(first[n]["ts"]) >= d:
                continue
            hits = [r for r in cards if r.get("node") == n and r.get("delayed") and r.get("correct") == "yes"]
            if hits and ts_day(hits[0]["ts"]) == d:
                remembered.append(n)
        out.append({"day": d, "track": t, "done": done, "started": started, "slipping": slipping,
                    "remembered": remembered, "answers": sum(1 for r in cards if ts_day(r["ts"]) == d),
                    "milestones": [] if d in seen_day else stones.get(d, [])})
        seen_day.add(d)
    return out


def build_export() -> dict:
    """The one data source of the dashboard (and anything later). `generated: true` — never edited by hand."""
    days = study_days(all_attempts())
    stones = [{"day": ts_day(r.get("ts")), "id": str(r["note"])} for r in read_jsonl(MOMENTS)
              if r.get("kind") == "milestone" and r.get("note")]
    return {"schema": EXPORT_SCHEMA, "generated": True, "format_version": format_version(), "generated_at": now_iso(),
            "data_warnings": [{"file": p["file"], "line": p["line"]} for p in scan_data()],
            "learner": {"active_track": load_state().get("active_track"), "study_days": days,
                        "streak": streak(days), "started": days[0] if days else None,
                        "gains": export_gains(), "milestones": stones, "recent": export_recent()},
            "tracks": [track_export(t) for t in all_tracks()]}


def cmd_export(a):
    out(build_export())


# ── dashboard: one self-contained static page, built only from the export + Markdown files ─────────────────
# Offline (no network, no CDN), deterministic (same data + same TEACH_TODAY → same bytes, except the one
# "güncellendi" line). Colours come from the token block of assets/style.css, inlined.

LEVEL_TR = {"new": "yeni", "struggling": "öğreniliyor", "learning": "öğreniliyor", "checked": "öğreniliyor",
            "retained": "oturdu", "owned": "senin", "durable": "senin"}
STATE_TR = {"new": "henüz değil", "struggling": "işleniyor", "learning": "işleniyor", "checked": "temeli atıldı",
            "retained": "öğrenildi", "owned": "uygulandı", "durable": "kalıcı"}  # what the learner reads (tooltips, node card)
LEVEL_CLASS = {"new": "new", "struggling": "learn", "learning": "learn", "checked": "learn",
               "retained": "kept", "owned": "own", "durable": "own"}
NODE_FONT_PX, NODE_CHAR_W, NODE_PAD_X, NODE_LINE_H, NODE_PAD_Y = 12, 6.5, 10, 15, 8
NODE_PIP_H = 7  # room at the bottom of every box for the progress pips
PIPS = {"learning": 0, "struggling": 0, "checked": 1, "retained": 2, "owned": 3}  # steps of 3 on the ladder
ARROW_HEAD = ("M48,55.2C49.4,54.6 50.2,53.4 50.2,52C50.2,50.6 49.4,49.4 48,48.8C38.2,45.6 29.2,38.8 21,28.4C15.2,21.4 "
              "11.4,13.2 9.6,3.8C9,1.2 7.4,0 4.8,0C1.6,0 0,1.6 0,5L0.2,5.6C3.6,23 12.6,36.8 27.2,47.2L27.2,56.8C12.6,67.2 "
              "3.6,81 0.2,98.4L0,99C0,102.4 1.6,104 4.8,104C7.4,104 9,102.8 9.6,100.2C11.4,90.8 15.2,82.6 21,75.6C29.2,65.2 "
              "38.2,58.4 48,55.2Z")  # LearnHarness plan arrowhead (CM long-arrow head)
# One calm, low-saturation hue per track, by track order (never yellow: yellow is the next node). Used only for
# that track's cloud / dots / legend chip in the concept network and a tiny chip on its course tab.
TRACK_HUES = ["#6f9f7f", "#6f8fb8", "#9585b8", "#5f9e9a", "#b8848f", "#8f9aa6"]
HEAD_H = 10.0
HEAD_W = 50.2 * HEAD_H / 104
HEAD_OVERHANG = (50.2 - 27.2) * HEAD_H / 104


def esc(s) -> str:
    return _html.escape(str(s), quote=True)


def node_label(n: dict) -> str:
    return n.get("title") or n["id"].replace("-", " ")


def wrap_label(text: str, width: int = 20, max_lines: int = 2) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(w) > width:
            w = w[:width - 1] + "…"
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = (lines[-1][:width - 1].rstrip() + "…")
    return lines or [""]


def fmt(v: float) -> str:
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def dag_layout(ids: list[str], edges: list[tuple[str, str]], sizes: dict[str, tuple[float, float]],
               gap_x: float = 22, gap_y: float = 46, pad: float = 24, sweeps: int = 12) -> dict:
    """Layered (Sugiyama-style) layout, deterministic. Layers: longest path from the roots (every drawn edge goes
    to a later layer); edges spanning several layers get dummy points. Order within a layer: barycenter sweeps
    (down, up, …), keeping the ordering with the fewest crossings. x: average of a left-push and a right-push
    placement toward the neighbours' mean (keeps the minimum gap, so boxes never overlap).
    Returns {pos: id->(x, y) top-left, layer: id->int, routes: [(from, to, [(x, y), …])], back: [(from, to)],
    width, height}. Back edges (only on a cycle) are not drawn."""
    E = [(a, b) for a, b in dict.fromkeys(edges) if a in sizes and b in sizes and a != b]
    order = topo_order(ids, E)
    rank = {n: i for i, n in enumerate(order)}
    fwd = [(a, b) for a, b in E if rank[a] < rank[b]]
    back = [e for e in E if rank[e[0]] >= rank[e[1]]]
    layer: dict[str, int] = {}
    for n in order:
        layer[n] = max((layer[a] + 1 for a, b in fwd if b == n), default=0)
    nl = max(layer.values(), default=-1) + 1
    layers: list[list[str]] = [[] for _ in range(nl)]
    for n in order:
        layers[layer[n]].append(n)
    w = {n: sizes[n][0] for n in ids}
    lay_of = dict(layer)
    chains = {}  # (a, b) -> [a, dummies…, b]
    links: list[tuple[str, str]] = []
    for a, b in sorted(fwd, key=lambda e: (rank[e[0]], rank[e[1]])):
        chain = [a]
        for k in range(layer[a] + 1, layer[b]):
            dmy = f"\x00{a}\x00{b}\x00{k}"
            w[dmy] = 6
            lay_of[dmy] = k
            layers[k].append(dmy)
            chain.append(dmy)
        chain.append(b)
        chains[(a, b)] = chain
        links += list(zip(chain, chain[1:]))
    preds: dict[str, list[str]] = {n: [] for n in w}
    succs: dict[str, list[str]] = {n: [] for n in w}
    for a, b in links:
        preds[b].append(a)
        succs[a].append(b)

    def crossings(ls):
        pos = {n: i for L in ls for i, n in enumerate(L)}
        total = 0
        for L in ls[:-1]:
            es = sorted((pos[a], pos[b]) for a in L for b in succs[a])
            for i in range(len(es)):
                for j in range(i + 1, len(es)):
                    if es[i][0] < es[j][0] and es[i][1] > es[j][1]:
                        total += 1
        return total

    best, best_c = [L[:] for L in layers], crossings(layers)
    for it in range(sweeps):
        pos = {n: i for L in layers for i, n in enumerate(L)}
        rng_layers = range(1, nl) if it % 2 == 0 else range(nl - 2, -1, -1)
        for li in rng_layers:
            nb = preds if it % 2 == 0 else succs
            cur = {n: i for i, n in enumerate(layers[li])}

            def key(n):
                ps = [pos[p] for p in nb[n]]
                return (sum(ps) / len(ps) if ps else cur[n], cur[n])
            layers[li] = sorted(layers[li], key=key)
            for i, n in enumerate(layers[li]):
                pos[n] = i
        c = crossings(layers)
        if c < best_c:
            best, best_c = [L[:] for L in layers], c
    layers = best
    # x placement (centers)
    x: dict[str, float] = {}
    for L in layers:
        cx = 0.0
        for n in L:
            x[n] = cx + w[n] / 2
            cx += w[n] + gap_x

    def place(L, desired):
        sep = [(w[L[i]] + w[L[i + 1]]) / 2 + gap_x for i in range(len(L) - 1)]
        left = desired[:]
        for i in range(1, len(L)):
            left[i] = max(left[i], left[i - 1] + sep[i - 1])
        right = desired[:]
        for i in range(len(L) - 2, -1, -1):
            right[i] = min(right[i], right[i + 1] - sep[i])
        return [(p + q) / 2 for p, q in zip(left, right)]

    for it in range(16):
        down = it % 2 == 0
        seq = layers if down else layers[::-1]
        nb = preds if down else succs
        for L in seq:
            desired = []
            for n in L:
                ns = [x[m] for m in nb[n]]
                desired.append(sum(ns) / len(ns) if ns else x[n])
            for n, v in zip(L, place(L, desired)):
                x[n] = v
    left_edge = min((x[n] - w[n] / 2 for L in layers for n in L), default=0)
    for n in x:
        x[n] += pad - left_edge
    heights = [max((sizes[n][1] for n in L if n in sizes), default=0) for L in layers]
    tops, y = [], pad
    for hgt in heights:
        tops.append(y)
        y += hgt + gap_y
    height = (y - gap_y + pad) if layers else 2 * pad
    width = max((x[n] + w[n] / 2 for L in layers for n in L), default=0) + pad
    pos = {}
    for n in ids:
        li = layer[n]
        pos[n] = (round(x[n] - w[n] / 2, 1), round(tops[li] + (heights[li] - sizes[n][1]) / 2, 1))
    # ports: spread a node's outgoing (incoming) edges along its bottom (top) edge, ordered by the other end's x
    out_ports: dict[str, list] = {}
    in_ports: dict[str, list] = {}
    for (a, b), chain in chains.items():
        out_ports.setdefault(a, []).append((x[chain[1]], (a, b)))
        in_ports.setdefault(b, []).append((x[chain[-2]], (a, b)))

    def port(n, items, e):
        items = sorted(items)
        k = len(items)
        i = [it[1] for it in items].index(e)
        span = min(sizes[n][0] * 0.5, 14 * (k - 1))
        return x[n] + (0 if k == 1 else -span / 2 + span * i / (k - 1))

    routes = []
    for (a, b), chain in sorted(chains.items(), key=lambda kv: (rank[kv[0][0]], rank[kv[0][1]])):
        pts = [(port(a, out_ports[a], (a, b)), pos[a][1] + sizes[a][1])]
        for dmy in chain[1:-1]:
            k = lay_of[dmy]
            pts.append((x[dmy], tops[k] + heights[k] / 2))
        pts.append((port(b, in_ports[b], (a, b)), pos[b][1]))
        routes.append((a, b, [(round(px, 1), round(py, 1)) for px, py in pts]))
    return {"pos": pos, "layer": layer, "routes": routes, "back": back,
            "width": round(width, 1), "height": round(height, 1)}


def curve_path(pts: list[tuple[float, float]], end_gap: float) -> str:
    """Smooth path through the points with vertical tangents; the last point is pulled back by end_gap
    so the arrowhead's tip lands on the target's border."""
    pts = list(pts)
    (lx, ly), (px, py) = pts[-1], pts[-2]
    pts[-1] = (lx, ly - end_gap)
    d = [f"M{fmt(pts[0][0])},{fmt(pts[0][1])}"]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dy = (y1 - y0) / 2
        d.append(f"C{fmt(x0)},{fmt(y0 + dy)} {fmt(x1)},{fmt(y1 - dy)} {fmt(x1)},{fmt(y1)}")
    return " ".join(d)


def node_size(lines: list[str]) -> tuple[float, float]:
    widest = max(len(s) for s in lines)
    return (max(64.0, round(widest * NODE_CHAR_W + 2 * NODE_PAD_X)),
            float(len(lines) * NODE_LINE_H + 2 * NODE_PAD_Y + NODE_PIP_H))


def ancestors(nid: str | None, edges: list[tuple[str, str]]) -> set:
    """Every node with a path into `nid` (its prerequisite chain)."""
    preds: dict[str, list[str]] = {}
    for a, b in edges:
        preds.setdefault(b, []).append(a)
    seen, stack = set(), [nid] if nid else []
    while stack:
        for p in preds.get(stack.pop(), []):
            if p not in seen:
                seen.add(p)
                stack.append(p)
    return seen


def render_plan_svg(track: dict, uid: str, focus: set | None = None, current: str | None = None,
                    root_cls: str = "plan", extra: str = "", chips: dict | None = None,
                    attrs: dict | None = None) -> str:
    """The layered map of one track; visual priority next > learning > done > later. The glowing node is `current`
    (default: the track's next; the ONLY yellow). Learning boxes (learning / struggling / checked) carry 3 progress
    pips, done ones (retained / owned) a calm grey fill and ✓ / ✓✓, later ones (new) a dashed border; "!" = needs
    review (struggling or slipping). Without `focus`, edges into the next node are solid ink, edges along its
    prerequisite chain stay visible and the rest fade; with `focus` (lesson-map) the focus nodes are marked "focus",
    every other node "dim". `chips` maps node -> short corner chip ("D1"); `attrs` node -> extra <g> attributes.
    `extra` goes right after <svg …>."""
    nodes = track["map"]["nodes"]
    glow = current if current is not None else track["next"]
    chips, attrs = chips or {}, attrs or {}
    if not nodes:
        return '<p class="note">Bu konunun haritası henüz boş.</p>'
    labels = {n["id"]: wrap_label(node_label(n)) for n in nodes}
    sizes = {nid: node_size(ls) for nid, ls in labels.items()}
    ids = [n["id"] for n in nodes]
    edges = [(e["from"], e["to"]) for e in track["map"]["edges"]]
    lay = dag_layout(ids, edges, sizes)
    anc = ancestors(glow, edges)
    W, H = lay["width"], lay["height"] + 6
    marker = lambda s, c: (f'<marker id="{uid}-{s}" viewBox="0 0 50.2 104" refX="27.2" refY="52" markerWidth="{fmt(HEAD_W)}" '
                           f'markerHeight="{fmt(HEAD_H)}" markerUnits="userSpaceOnUse" orient="auto">'
                           f'<path class="ah{c}" d="{ARROW_HEAD}"/></marker>')
    parts = [f'<svg class="{root_cls}" viewBox="0 0 {fmt(W)} {fmt(H)}" width="{fmt(W)}" height="{fmt(H)}" role="img" '
             f'aria-label="{esc(track["title"])}: konu haritası">' + extra,
             "<defs>", marker("a", ""), marker("p", " path"), marker("d", " dim"),
             f'<filter id="{uid}-g" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="5"/></filter>',
             "</defs>"]
    for a, b, pts in lay["routes"]:
        if focus is not None:
            kind = "" if a in focus and b in focus else " dim"
        else:
            kind = "" if b == glow else (" path" if b in anc else " dim")
        parts.append(f'<path class="edge{kind}" d="{curve_path(pts, HEAD_OVERHANG + 2)}" '
                     f'marker-end="url(#{uid}-{ {"": "a", " path": "p", " dim": "d"}[kind]})"/>')
    for n in nodes:
        nid, lv = n["id"], n["level"]
        x0, y0 = lay["pos"][nid]
        w, h = sizes[nid]
        cls = ["node", "lv-" + LEVEL_CLASS.get(lv, "new")]
        if focus is not None:
            cls.append("focus" if nid in focus else "dim")
        if nid == glow:
            cls.append("next")
        warn = bool(n["slipping"]) or lv == "struggling"
        tip = [node_label(n)]
        if n.get("statement"):
            tip.append(n["statement"])
        tip.append(f"durum: {STATE_TR.get(lv, lv)}" + (" · tekrar lazım" if warn else ""))
        parts.append(f'<g class="{" ".join(cls)}" transform="translate({fmt(x0)},{fmt(y0)})" data-node="{esc(nid)}"'
                     f'{attrs.get(nid, "")}><title>{esc(chr(10).join(tip))}</title>')
        if nid == glow:
            parts.append(f'<rect class="glow" x="-8" y="-8" width="{fmt(w + 16)}" height="{fmt(h + 16)}" rx="8" '
                         f'filter="url(#{uid}-g)"/>')
        parts.append(f'<rect class="box" width="{fmt(w)}" height="{fmt(h)}" rx="3"/>')
        ls = labels[nid]
        ty = (h - NODE_PIP_H - len(ls) * NODE_LINE_H) / 2 + NODE_LINE_H / 2 + 1
        for i, line in enumerate(ls):
            parts.append(f'<text x="{fmt(w / 2)}" y="{fmt(ty + i * NODE_LINE_H)}">{esc(line)}</text>')
        if lv in ("learning", "struggling", "checked"):
            parts.append("".join(f'<circle class="pip{" on" if k < PIPS[lv] else ""}" cx="{fmt(w / 2 + (k - 1) * 7)}" '
                                 f'cy="{fmt(h - 6)}" r="2"/>' for k in range(3)))
        elif lv in DONE:  # a badge on the top-right corner: ✓ öğrenildi, ✓✓ uygulandı, ✓✓✓ kalıcı
            bw = {"retained": 15, "owned": 24, "durable": 32}[lv]
            parts.append(f'<g class="badge"><rect x="{fmt(w - bw + 5)}" y="-7" width="{fmt(bw)}" height="15" rx="7.5"/>'
                         f'<text x="{fmt(w - bw / 2 + 5)}" y="0.5">{MARK[lv]}</text></g>')
        if warn:
            parts.append(f'<text class="mk warn" x="{fmt(w - (34 if lv in DONE else 5))}" y="9">!</text>')
        if nid in chips:
            cw = 7 + 6.4 * len(chips[nid])
            parts.append(f'<g class="chip"><rect x="-6" y="-8" width="{fmt(cw)}" height="14" rx="2"/>'
                         f'<text x="{fmt(-6 + cw / 2)}" y="-1">{esc(chips[nid])}</text></g>')
        parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts)


def force_layout(keys: list, groups: dict, edges: list[tuple], width: float = 760, height: float = 440,
                 seed: int = 7, iterations: int = 300) -> dict:
    """Fruchterman–Reingold with a seeded start and a fixed number of iterations (deterministic), plus a weak pull
    of each node toward its group's anchor (anchors on a circle) so each track stays one calm cluster.
    Returns key -> (x, y) inside [0, width] × [0, height]."""
    import math
    rng = random.Random(seed)
    gs = list(dict.fromkeys(groups[k] for k in keys))
    cx, cy = width / 2, height / 2
    ring = min(width, height) * 0.28 if len(gs) > 1 else 0.0
    rx, ry = ring * 0.95, ring
    if len(gs) > 3:  # many tracks: anchors on a wider ellipse so the clusters don't pile up in the middle
        rx, ry = width * 0.34, height * 0.3
    anchor = {g: (cx + rx * math.cos(2 * math.pi * i / max(1, len(gs)) + math.pi),
                  cy + ry * math.sin(2 * math.pi * i / max(1, len(gs)) + math.pi)) for i, g in enumerate(gs)}
    pos = {k: [anchor[groups[k]][0] + rng.uniform(-40, 40), anchor[groups[k]][1] + rng.uniform(-40, 40)] for k in keys}
    n = max(1, len(keys))
    kk = 0.55 * math.sqrt(width * height / n)
    t0 = width / 10
    many, cut2 = len(gs) > 3, (2.5 * kk) ** 2
    E = [(a, b) for a, b in edges if a in pos and b in pos and a != b]
    for it in range(iterations):
        disp = {k: [0.0, 0.0] for k in keys}
        for i, a in enumerate(keys):
            pa = pos[a]
            for b in keys[i + 1:]:
                pb = pos[b]
                dx, dy = pa[0] - pb[0], pa[1] - pb[1]
                d2 = dx * dx + dy * dy
                if d2 < 1e-6:
                    dx, dy, d2 = 0.1, 0.1, 0.02
                if groups[a] == groups[b]:
                    f = kk * kk / d2
                elif many and d2 > cut2:  # many tracks: far clusters stop pushing (else they flatten each other)
                    continue
                else:
                    f = kk * kk / d2 * 1.6
                disp[a][0] += dx * f
                disp[a][1] += dy * f
                disp[b][0] -= dx * f
                disp[b][1] -= dy * f
        for a, b in E:
            dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
            d = math.sqrt(dx * dx + dy * dy) or 0.01
            f = d / kk
            disp[a][0] -= dx * f
            disp[a][1] -= dy * f
            disp[b][0] += dx * f
            disp[b][1] += dy * f
        temp = t0 * (1 - it / iterations) + 0.5
        for k in keys:
            ax, ay = anchor[groups[k]]
            disp[k][0] += (ax - pos[k][0]) * 0.9
            disp[k][1] += (ay - pos[k][1]) * 0.9
            dx, dy = disp[k]
            d = math.sqrt(dx * dx + dy * dy) or 1.0
            step = min(d, temp)
            pos[k][0] = min(width, max(0.0, pos[k][0] + dx / d * step))
            pos[k][1] = min(height, max(0.0, pos[k][1] + dy / d * step))
    return {k: (round(p[0], 1), round(p[1], 1)) for k, p in pos.items()}


def track_hues(tracks: list[dict]) -> dict:
    return {t["id"]: TRACK_HUES[i % len(TRACK_HUES)] for i, t in enumerate(tracks)}


GRAPH_BASE_NODES = 30  # up to this many nodes the concept network uses the base 760×460 canvas


def render_graph_svg(tracks: list[dict], tab: dict | None = None, hue: dict | None = None) -> tuple[str, str]:
    """(svg, legend html) for the concept network of all tracks. `tab` maps track id -> dashboard tab key; clouds,
    cloud labels, legend items and nodes carry data-go (and nodes data-node) so a click opens that track's tab."""
    tab = tab or {t["id"]: t["id"] for t in tracks}
    hue = hue or track_hues(tracks)
    import math
    keys, groups, label, level, stmt, edges = [], {}, {}, {}, {}, []
    nxt = {(t["id"], t["next"]) for t in tracks if t["next"]}
    for t in tracks:
        ids = {n["id"] for n in t["map"]["nodes"]}
        for n in t["map"]["nodes"]:
            k = (t["id"], n["id"])
            keys.append(k)
            groups[k] = t["id"]
            label[k] = node_label(n)
            level[k] = n["level"]
            stmt[k] = n.get("statement")
        edges += [((t["id"], e["from"]), (t["id"], e["to"])) for e in t["map"]["edges"]
                  if e["from"] in ids and e["to"] in ids]
    cross = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if groups[a] != groups[b] and (a[1] == b[1] or (stmt[a] and " ".join(stmt[a].lower().split())
                                                              == " ".join((stmt[b] or "").lower().split()))):
                cross.append((a, b))
    # the canvas grows with √(node count) past GRAPH_BASE_NODES, so spacing (and room for labels) stays constant; the
    # dashboard first shows all of it (labels smaller), and the reader zooms / pans inside the box (DASH_JS). Zooming by
    # k, each node and track title is scaled by k^-0.6 around its own point (CSS --ks), so it grows on screen only as
    # k^0.4 while the space between nodes grows as k: crowded areas open up instead of just getting bigger
    grow = max(1.0, math.sqrt(len(keys) / GRAPH_BASE_NODES))
    W, H = round(760.0 * grow), round(460.0 * grow)
    raw = force_layout(keys, groups, edges + cross, W, H)
    if raw:
        xs, ys = [p[0] for p in raw.values()], [p[1] for p in raw.values()]
        pad = 72
        sx = (W - 2 * pad) / max(1e-6, max(xs) - min(xs))
        sy = (H - 2 * pad) / max(1e-6, max(ys) - min(ys))
        s = min(sx, sy, 1.6)
        ox = (W - s * (max(xs) - min(xs))) / 2 - s * min(xs)
        oy = (H - s * (max(ys) - min(ys))) / 2 - s * min(ys)
        pos = {k: (round(ox + s * p[0], 1), round(oy + s * p[1], 1)) for k, p in raw.items()}
    else:
        pos = {}
    parts = [f'<svg class="graph" viewBox="0 0 {fmt(W)} {fmt(H)}" role="img" aria-label="Kavram ağı: bütün konular">',
             "<defs>" + "".join(
                 f'<radialGradient id="kg-c{i}"><stop offset="0" stop-color="{hue[t["id"]]}" stop-opacity=".26"/>'
                 f'<stop offset=".6" stop-color="{hue[t["id"]]}" stop-opacity=".09"/>'
                 f'<stop offset="1" stop-color="{hue[t["id"]]}" stop-opacity="0"/></radialGradient>'
                 for i, t in enumerate(tracks)) + "</defs>", f'<rect class="canvas" width="{fmt(W)}" height="{fmt(H)}" rx="12"/>']
    clouds = []
    for i, t in enumerate(tracks):
        mine = [pos[k] for k in keys if groups[k] == t["id"]]
        if not mine:
            continue
        mx = sum(p[0] for p in mine) / len(mine)
        my = sum(p[1] for p in mine) / len(mine)
        r = max(90.0, max(math.hypot(p[0] - mx, p[1] - my) for p in mine) * 1.45)
        clouds.append((t, mx, my, r))
        parts.append(f'<circle class="kg-cloud" data-go="{esc(tab[t["id"]])}" cx="{fmt(round(mx, 1))}" cy="{fmt(round(my, 1))}" '
                     f'r="{fmt(round(r, 1))}" fill="url(#kg-c{i})"><title>{esc(t["title"])}</title></circle>')
    for a, b in edges:
        parts.append(f'<line class="kg-e" x1="{fmt(pos[a][0])}" y1="{fmt(pos[a][1])}" x2="{fmt(pos[b][0])}" y2="{fmt(pos[b][1])}"/>')
    for a, b in cross:
        parts.append(f'<line class="kg-e cross" x1="{fmt(pos[a][0])}" y1="{fmt(pos[a][1])}" x2="{fmt(pos[b][0])}" y2="{fmt(pos[b][1])}"/>')
    # track titles first (always shown, up to two lines), then node labels by priority (next, learning, done,
    # later), each at the first free spot of below / above / right / left; a label with no free spot is left out
    # (its <title> tooltip stays). Boxes are estimated from character counts, so this stays deterministic.
    placed: list[tuple[float, float, float, float]] = []
    hit = lambda b: any(b[0] < q[2] and q[0] < b[2] and b[1] < q[3] and q[1] < b[3] for q in placed)
    title_parts = []
    for t, mx, my, r in clouds:
        lines = [short_title(t["title"])]
        top = min(pos[k][1] for k in keys if groups[k] == t["id"])
        ly = max(14.0, top - 14 - 11 * (len(lines) - 1))
        half = max(len(s) for s in lines) * 3.6 + 8  # ~ half the label's width at 10px mono, letter-spaced
        lx = min(W - half, max(half, mx))
        placed.append((lx - half, ly - 10, lx + half, ly + 11 * (len(lines) - 1) + 3))
        spans = "".join(f'<tspan x="{fmt(round(lx, 1))}" dy="{0 if i == 0 else 11}">{esc(s)}</tspan>' for i, s in enumerate(lines))
        title_parts.append(f'<text class="kg-label" data-go="{esc(tab[t["id"]])}" x="{fmt(round(lx, 1))}" y="{fmt(round(ly, 1))}" '
                           f'style="transform-origin:{fmt(round(lx, 1))}px {fmt(round(ly, 1))}px">'
                           f'{spans}<title>{esc(t["title"])}</title></text>')
    rank = {"learning": 1, "struggling": 1, "checked": 1, "retained": 2, "owned": 2, "durable": 2}
    order = sorted(keys, key=lambda k: (0 if k in nxt else rank.get(level[k], 3), keys.index(k)))
    radius = {k: 4.4 if k in nxt else (2.6 if level[k] == "new" else (3.8 if level[k] in DONE else 3.2))
              for k in keys}
    for k in keys:  # the dots themselves are obstacles too
        x, y = pos[k]
        placed.append((x - radius[k], y - radius[k], x + radius[k], y + radius[k]))
    text_at = {}
    for k in order:
        x, y = pos[k]
        r, w = radius[k], len(label[k]) * 5.2 + 2
        for anchor, tx, ty in (("middle", x, y + r + 9.5), ("middle", x, y - r - 3.5),
                               ("start", x + r + 3, y + 3.5), ("end", x - r - 3, y + 3.5)):
            x0 = tx - w / 2 if anchor == "middle" else (tx if anchor == "start" else tx - w)
            box = (x0, ty - 9, x0 + w, ty + 2)
            if box[0] >= 0 and box[2] <= W and not hit(box):
                placed.append(box)
                text_at[k] = (anchor, round(tx, 1), round(ty, 1))
                break
        if k in nxt and k not in text_at:  # the next node always keeps its label
            text_at[k] = ("middle", round(x, 1), round(y + r + 9.5, 1))
    for k in keys:
        x, y = pos[k]
        lv = level[k]
        state = " next" if k in nxt else (" new" if lv == "new" else (" done" if lv in DONE else " learn"))
        r = radius[k]
        tip = f"{label[k]} ({STATE_TR.get(lv, lv)})" + (f"\n{stmt[k]}" if stmt[k] else "")
        fill = "" if k in nxt else (f' style="stroke:{hue[k[0]]}"' if lv == "new" else
                                    (f' style="stroke:{hue[k[0]]};filter:drop-shadow(0 0 4px {hue[k[0]]})"'
                                     if lv in DONE else f' style="fill:{hue[k[0]]}"'))
        txt = ""
        if k in text_at:
            anchor, tx, ty = text_at[k]
            txt = f'<text x="{fmt(tx)}" y="{fmt(ty)}"{"" if anchor == "middle" else f" style={chr(34)}text-anchor:{anchor}{chr(34)}"}>{esc(label[k])}</text>'
        parts.append(f'<g class="kg-n{state}" style="transform-origin:{fmt(x)}px {fmt(y)}px" '
                     f'data-doc="{esc(_doc_id(tab[k[0]], "node-" + k[1]))}" data-node="{esc(k[1])}"><title>{esc(tip)}</title>'
                     f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="{fmt(r)}"{fill}/>{txt}</g>')
    parts += title_parts
    parts.append("</svg>")
    legend = '<span class="kg-key"><i class="dot-next"></i>sıradaki</span>' if nxt else ""
    return "\n".join(parts), legend


def md_inline(s: str) -> str:
    out_parts = []
    for i, chunk in enumerate(re.split(r"(`[^`]+`)", s)):
        if i % 2:
            out_parts.append(f"<code>{_html.escape(chunk[1:-1], quote=False)}</code>")
            continue
        t = _html.escape(chunk, quote=False)
        t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", lambda m: f'<a href="{_html.escape(_html.unescape(m.group(2)))}" target="_blank" rel="noopener">{m.group(1)}</a>', t)
        t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r"\1", t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t)
        t = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", t)
        out_parts.append(t)
    return "".join(out_parts)


def md_to_html(text: str) -> str:
    """Minimal Markdown: headings, lists, tables, fenced code, paragraphs; inline code/bold/em/links. HTML escaped."""
    lines = re.sub(r"<!--.*?-->", "", text, flags=re.S).splitlines()
    html_out, para, i = [], [], 0

    def flush():
        if para:
            html_out.append(f"<p>{md_inline(' '.join(para))}</p>")
            para.clear()
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            flush()
            i += 1
        elif s.startswith("```"):
            flush()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            html_out.append(f"<pre><code>{_html.escape(chr(10).join(lines[i + 1:j]), quote=False)}</code></pre>")
            i = j + 1
        elif re.match(r"#{1,6}\s", s):
            flush()
            lvl = min(6, len(s) - len(s.lstrip("#")) + 2)
            html_out.append(f"<h{lvl}>{md_inline(s.lstrip('#').strip())}</h{lvl}>")
            i += 1
        elif s.startswith("|") and i + 1 < len(lines) and re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", lines[i + 1].strip()):
            flush()
            head = _table_cells(s)
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(_table_cells(lines[j]))
                j += 1
            t = ["<div class=\"md-table\"><table><thead><tr>"] + [f"<th>{md_inline(c)}</th>" for c in head] + ["</tr></thead><tbody>"]
            for r in rows:
                t += ["<tr>"] + [f"<td>{md_inline(c)}</td>" for c in r] + ["</tr>"]
            html_out.append("".join(t + ["</tbody></table></div>"]))
            i = j
        elif re.match(r"([-*+]|\d+[.)])\s", s):
            flush()
            ordered = bool(re.match(r"\d", s))
            tag = "ol" if ordered else "ul"
            items = []
            j = i
            while j < len(lines):
                t = lines[j].strip()
                m = re.match(r"([-*+]|\d+[.)])\s+(.*)", t)
                if m:
                    depth = (len(lines[j]) - len(lines[j].lstrip())) // 2
                    items.append([depth, m.group(2)])
                elif t and items and not re.match(r"#{1,6}\s|\||```", t):
                    items[-1][1] += " " + t
                else:
                    break
                j += 1
            html_out.append(f"<{tag}>" + "".join(
                f'<li{" class=sub" if d else ""}>{md_inline(x)}</li>' for d, x in items) + f"</{tag}>")
            i = j
        else:
            if s.startswith(">"):
                s = s.lstrip("> ")
            para.append(s)
            i += 1
    flush()
    return "\n".join(html_out)


def handoff_first_sentence(track: str) -> str:
    """The learner-facing line of the handoff: first non-empty line of "## Öğrenci için" (written by
    wrap-up, in the learner's language), <= 240 chars. "Next step" is tutor-facing and can name card
    ids or hint at answers, so it is never shown; no such section -> ""."""
    f = TRACKS / track / "handoff.md"
    if not f.exists():
        return ""
    m = re.search(r"##\s*Öğrenci için[^\n]*\n(.*?)(\n##|\Z)", f.read_text(encoding="utf-8"), re.S | re.I)
    if not m:
        return ""
    first = next((ln.strip() for ln in m.group(1).splitlines() if ln.strip() not in {"", "–", "-"}), "")
    first = re.sub(r"^([-*+]|\d+[.)])\s+", "", first)
    return first if len(first) <= 240 else first[:239].rstrip() + "…"


def link(target: str, out_dir: Path) -> str:
    from urllib.parse import quote
    return quote(os.path.relpath(ROOT / target, out_dir).replace(os.sep, "/"), safe="/.-_~")


def style_tokens() -> str:
    css = ENGINE_DIR.parent / "assets" / "style.css"
    text = css.read_text(encoding="utf-8") if css.exists() else ""
    m = re.search(r"/\* @tokens-begin \*/(.*?)/\* @tokens-end \*/", text, re.S)
    if m:
        return m.group(1).strip()
    return (":root{--bg:#fafafa;--surface:#f1f1f1;--surface-2:#e7e7e7;--ink:#1a1a1a;--muted:#6b6b6b;--border:#cfcfcf;"
            "--border-soft:#e2e2e2;--current:#b88600;--current-soft:rgba(234,179,8,.16);--current-glow:rgba(234,179,8,.55);"
            "--good:#23743b;--bad:#b3261e;--done-fill:#fff;--done-ink:#1a1a1a;--done-glow:rgba(0,0,0,.12);--font-ui:ui-monospace,Menlo,Consolas,monospace;--font-prose:system-ui,sans-serif;"
            "--font-title:Georgia,serif;--text-xs:11px;--text-sm:12.5px;--text-base:14px;--text-prose:17px;--text-xl:20px;"
            "--text-2xl:25px;--text-3xl:32px;--tracking-ui:.08em;--r-sm:4px;--r-md:8px;--r-lg:12px}"
            ":root[data-theme=dark]{--bg:#141414;--surface:#1c1c1c;--surface-2:#2a2a2a;--ink:#e6e6e6;--muted:#8d8d8d;"
            "--border:#434343;--border-soft:#2c2c2c;--current:#facc15;--current-soft:rgba(250,204,21,.14);"
            "--current-glow:rgba(250,204,21,.45);--done-fill:#f2f2f2;--done-ink:#141414;--done-glow:rgba(255,255,255,.35)}")


DASH_CSS = """
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font-prose); font-size: 15px; line-height: 1.55; -webkit-font-smoothing: antialiased; overflow-x: hidden; }
a { color: inherit; text-decoration: underline; text-decoration-color: var(--border); text-underline-offset: 3px; }
a:hover { text-decoration-color: var(--ink); }
code { font-family: var(--font-ui); font-size: .86em; background: var(--surface); border: 1px solid var(--border-soft); border-radius: var(--r-sm); padding: .05em .35em; }
button { font: inherit; color: inherit; }
.lbl { font-family: var(--font-ui); font-size: 12px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
/* app shell: one slim bar, then the selected course; only the content area scrolls */
.js body { height: 100vh; height: 100dvh; display: flex; flex-direction: column; overflow: hidden; }
.bar { flex: none; display: flex; align-items: center; gap: 18px; padding: 10px 20px; border-bottom: 1px solid var(--border); background: var(--bg); }
.mark { flex: none; display: inline-flex; align-items: center; gap: 8px; font-family: var(--font-ui); font-size: 14px; font-weight: 700; letter-spacing: .16em; }
.mark .logo { width: 22px; height: 22px; overflow: visible; }
.theme-btn { flex: none; height: 42px; font-family: var(--font-ui); font-size: 13px; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); background: transparent; border: 1px solid var(--border); border-radius: var(--r-md); padding: 0 14px; cursor: pointer; white-space: nowrap; }
.theme-btn:hover { color: var(--ink); border-color: var(--ink); }
/* both tab rows: same height, mono uppercase, 1px borders; the selected one is inverted (ink on bg) */
.tabs, .ltabs { display: flex; gap: 6px; min-width: 0; overflow-x: auto; overflow-y: hidden; scrollbar-width: none; -webkit-overflow-scrolling: touch; }
.tabs::-webkit-scrollbar, .ltabs::-webkit-scrollbar { display: none; }
.tabs { flex: 1 1 auto; }
.tab { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 8px; height: 42px; max-width: 300px; font-family: var(--font-ui); font-size: 13px; font-weight: 500; letter-spacing: .05em; text-transform: uppercase; color: var(--ink); background: transparent; border: 1px solid var(--border); border-radius: var(--r-md); padding: 0 17px; cursor: pointer; white-space: nowrap; }
.tab .tl { overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.ltab { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 6px; height: 32px; font-family: var(--font-ui); font-size: 12px; font-weight: 500; letter-spacing: .03em; color: var(--ink); background: var(--bg); border: 1px solid var(--border); border-radius: var(--r-sm); padding: 0 10px; cursor: pointer; white-space: nowrap; }
.ltab .lt { max-width: 150px; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.ltab[data-view="harita"] { position: sticky; left: 0; z-index: 2; text-transform: uppercase; letter-spacing: .06em; box-shadow: 6px 0 0 var(--bg); }
.ltab.is-next .lt { text-decoration: underline; text-decoration-thickness: 1.5px; text-underline-offset: 4px; }
.lt-wrap { position: relative; flex: 1 1 0; min-width: 0; }
.lt-wrap .ltabs { max-width: 100%; }
.lt-wrap::before, .lt-wrap::after { content: ""; position: absolute; top: 0; bottom: 0; width: 28px; pointer-events: none; opacity: 0; transition: opacity .15s; z-index: 3; }
.lt-wrap::before { left: var(--pin, 80px); background: linear-gradient(to right, var(--bg), transparent); }
.lt-wrap::after { right: 0; background: linear-gradient(to left, var(--bg), transparent); }
.lt-wrap.fl::before, .lt-wrap.fr::after { opacity: 1; }
.tab:hover, .ltab:hover { border-color: var(--ink); background: var(--surface); }
.tab[aria-selected="true"], .ltab[aria-selected="true"] { color: var(--bg); background: var(--ink); border-color: var(--ink); }
.tab:focus-visible, .ltab:focus-visible { outline: 2px solid var(--muted); outline-offset: 2px; }
.hue { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 2px; }
.ltab .ln { font-weight: 700; }
.ltab .ln:not(:last-child)::after { content: " ·"; font-weight: 400; }
.panel:focus { outline: none; }
.js .panel { display: none; }
.js .panel.on { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; }
html:not(.js) .panel + .panel { margin-top: 40px; border-top: 1px solid var(--border); }
/* performance strip: the one line that matters */
.kpis { flex: 0 1 auto; display: flex; align-items: stretch; gap: 22px; margin-left: auto; }
.kpis .div { width: 1px; background: var(--border); }
.kpi { display: flex; flex-direction: column; justify-content: center; gap: 4px; min-width: 0; }
.kpi .num { font-family: var(--font-title); font-size: 36px; line-height: 1; font-weight: 700; color: var(--ink); }
.kpi .lbl { white-space: nowrap; }
.kpi.prog { width: 300px; gap: 8px; }
.psay { margin: 0; font-size: 15px; line-height: 1.35; color: var(--ink); }
.psay b { font-weight: 700; }
.psay .pm { color: var(--muted); }
.pbar { --pb-own: #111; --pb-learn: #a6a6a6; --pb-line: #c8c8c8; --pb-bg: #f0f0f0; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .pbar { --pb-own: #f2f2f2; --pb-learn: #7a7a7a; --pb-line: #3a3a3a; --pb-bg: #262626; } }
:root[data-theme="dark"] .pbar { --pb-own: #f2f2f2; --pb-learn: #7a7a7a; --pb-line: #3a3a3a; --pb-bg: #262626; }
.pbar { display: flex; height: 10px; border-radius: 999px; overflow: hidden; background: var(--pb-bg); box-shadow: inset 0 0 0 1px var(--pb-line); }
.pbar i { display: block; height: 100%; }
.pbar .pl { background: var(--pb-own); }
.pbar .pw { background: var(--pb-learn); }
.kpi.due { flex-direction: row; align-items: center; gap: 12px; padding: 12px 16px; border-radius: var(--r-md); background: var(--ink); color: var(--bg); }
.kpi.due .num { color: var(--bg); }
.kpi.due .dl { display: flex; flex-direction: column; gap: 2px; line-height: 1.25; }
.kpi.due .dl b { font-size: 17px; }
.kpi.due .dl small { font-size: 13px; opacity: .8; }
.dl { font-size: 15px; font-weight: 600; line-height: 1.25; max-width: 9em; }
/* Genel */
.gen { flex: 1 1 auto; min-height: 0; overflow: auto; }
.gen-in { max-width: 1320px; margin: 0 auto; padding: 22px 20px 28px; }
.gen-grid { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 28px; align-items: start; }
.side { display: flex; flex-direction: column; gap: 22px; }
.side .blk { margin: 0; }
.side .kpi.due { width: 100%; }
.side .kpi.prog { width: 100%; }
.side .kpi.days { flex-direction: row; align-items: baseline; justify-content: flex-start; gap: 8px; }
.side .kpi.days .num { font-size: 28px; }
.nc { display: flex; flex-direction: column; gap: 20px; padding: 18px 22px 28px; }
.nc .md { padding: 0; }
.nc-top { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
.nc-st { display: inline-flex; align-items: center; padding: 2px 10px; border-radius: 99px; font-family: var(--font-ui); font-size: 12px; font-weight: 600; border: 1px solid var(--ink); color: var(--ink); }
.nc-st.kept, .nc-st.own { background: var(--done-fill); color: var(--done-ink); border-color: var(--border); box-shadow: 0 0 6px var(--done-glow); }
.nc-st.next { background: var(--current-soft); border-color: var(--current); }
.nc-st.stale { border-color: var(--ink); background: var(--ink); color: var(--bg); }
.nc-st.new { border-style: dashed; border-color: var(--muted); color: var(--muted); font-weight: 400; }
.nc-deps { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.nc-deps .lbl { margin-right: 2px; }
.nc-chip { padding: 1px 8px; border-radius: var(--r-sm); background: var(--surface); font-size: 13px; }
.nc-sec h3.lbl { margin: 0 0 6px; }
.nc-def { margin: 0; font-size: 17px; line-height: 1.5; padding-left: 12px; border-left: 3px solid var(--ink); }
.nc-sum > :first-child { margin-top: 0; }
.nc-sum > :last-child { margin-bottom: 0; }
.nc-empty { margin: 0; color: var(--muted); font-size: 14px; }
.nc-go { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--r-md); background: var(--bg); color: var(--ink); font: inherit; font-size: 15px; text-align: left; cursor: pointer; }
.nc-go + .nc-go { margin-top: 6px; }
.nc-go:hover { border-color: var(--ink); background: var(--surface); }
.nc-go > span:last-child { margin-left: auto; color: var(--muted); }
.nc-num { font-family: var(--font-ui); font-size: 11px; font-weight: 700; padding: 1px 5px; border-radius: 2px; background: var(--ink); color: var(--bg); }
.recent { list-style: none; margin: 0; padding: 0 6px 0 0; display: flex; flex-direction: column; max-height: 320px; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; }
.recent li { padding: 10px 0; border-top: 1px solid var(--border-soft); }
.recent li:first-child { border-top: 0; padding-top: 2px; }
.recent .rc-h { display: flex; align-items: baseline; gap: 10px; margin-bottom: 3px; }
.recent .rc-d { flex: none; width: 46px; font-family: var(--font-ui); font-size: 12px; color: var(--muted); }
.recent .rc-t { display: inline-flex; align-items: center; gap: 6px; font-family: var(--font-ui); font-size: 11px; letter-spacing: var(--tracking-ui); text-transform: uppercase; color: var(--muted); }
.recent .rc-t .hue { width: 7px; height: 7px; border-radius: 2px; }
.recent .rc-x { padding-left: 56px; font-size: 14px; line-height: 1.45; color: var(--ink); }
.recent .rc-x b { font-weight: 600; }
.recent .rc-ok { white-space: nowrap; font-weight: 600; }
.recent .rc-tag { display: inline-block; margin-left: 6px; padding: 0 7px; border: 1px solid var(--border); border-radius: 99px; font-size: 12px; color: var(--muted); white-space: nowrap; }
.bh { font-family: var(--font-ui); font-size: 12px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); margin: 0 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border-soft); }
.warn { margin: 0; padding: 10px 12px; border: 1px dashed var(--border); border-radius: var(--r-md); color: var(--muted); font-size: 14px; }
.cal { display: grid; grid-template-columns: repeat(7, 13px); grid-auto-rows: 13px; gap: 4px; width: max-content; }
.cal i { display: block; border-radius: 3px; background: var(--surface-2); }
.cal i.on { background: var(--ink); }
.cal i.today { outline: 1.5px solid var(--ink); outline-offset: 1px; }
.cal i.fut { background: transparent; border: 1px dashed var(--border-soft); }
.cal-days { display: grid; grid-template-columns: repeat(7, 13px); gap: 4px; margin-bottom: 6px; font-family: var(--font-ui); font-size: 11px; color: var(--muted); text-align: center; }
.cal-h { margin: 0 0 10px; font-size: 16px; font-weight: 700; }
.cal-h .wk { font-weight: 400; color: var(--muted); }
.kg-wrap { position: relative; border: 1px solid var(--border-soft); border-radius: var(--r-lg); overflow: hidden; }
.kg-wrap svg.graph { max-height: calc(100vh - 170px); max-height: calc(100dvh - 170px); }
.js .kg-wrap svg.graph { cursor: grab; touch-action: none; -webkit-user-select: none; user-select: none; }
.js .kg-wrap.drag svg.graph, .js .kg-wrap.drag svg.graph * { cursor: grabbing; }
.kg-zoom { position: absolute; right: 10px; bottom: 10px; display: flex; flex-direction: column; gap: 4px; }
html:not(.js) .kg-zoom { display: none; }
.kg-zoom button { width: 30px; height: 30px; padding: 0; border: 1px solid var(--border-soft); border-radius: var(--r-md); background: var(--bg); color: var(--ink); font: 16px/1 var(--font-ui); cursor: pointer; }
.kg-zoom button:hover { background: var(--surface); }
svg.graph { display: block; width: 100%; height: auto; font-family: var(--font-prose); }
svg.graph .canvas { fill: var(--bg); }
svg.graph .kg-cloud, svg.graph .kg-n, svg.graph .kg-label { cursor: pointer; }
svg.graph .kg-e { stroke: var(--muted); stroke-opacity: .5; stroke-width: .8; vector-effect: non-scaling-stroke; }
.js svg.graph .kg-n, .js svg.graph .kg-label { transform-box: view-box; transform: scale(var(--ks, 1)); }
svg.graph .kg-e.cross { stroke: var(--ink); stroke-dasharray: 5 4; stroke-width: 1.2; stroke-opacity: .75; }
svg.graph .kg-n circle { fill: var(--ink); }
svg.graph .kg-n.learn circle { opacity: .8; }
svg.graph .kg-n.new circle { fill: var(--bg); stroke-width: 1.2; stroke-dasharray: 2 1.5; }
svg.graph .kg-n.done circle { fill: var(--done-fill); stroke-width: 1.6; }
svg.graph .kg-n.done text { fill: var(--ink); }
svg.graph .kg-n.next circle { fill: var(--current); filter: drop-shadow(0 0 5px var(--current-glow)); }
svg.graph .kg-n text { font-size: 10px; fill: var(--muted); text-anchor: middle; }
svg.graph .kg-n.new text { opacity: .8; }
svg.graph .kg-n.next text { fill: var(--ink); font-weight: 600; }
svg.graph .kg-n:hover text { fill: var(--ink); }
svg.graph .kg-label { font-family: var(--font-ui); font-size: 10px; letter-spacing: .08em; text-transform: uppercase; text-anchor: middle; fill: var(--ink); }
svg.graph .kg-label:hover { text-decoration: underline; }
.kg-h { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.kg-legend { display: flex; gap: 6px 18px; }
.kg-key { display: inline-flex; align-items: center; gap: 7px; font-family: var(--font-ui); font-size: 12px; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); background: none; border: 0; padding: 0; }
.kg-key i.dot-next { width: 9px; height: 9px; border-radius: 50%; display: inline-block; background: var(--current); box-shadow: 0 0 6px var(--current-glow); }
footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px 20px; margin-top: 24px; padding-top: 12px; border-top: 1px solid var(--border-soft); color: var(--muted); font-family: var(--font-ui); font-size: 12px; }
/* track: lesson tabs, then the reading area + notes column */
.lrow { flex: none; display: flex; flex-wrap: wrap; align-items: center; gap: 8px 10px; min-height: 56px; padding: 8px 20px; border-bottom: 1px solid var(--border); }
.lrow .kpis { flex: 0 1 auto; align-items: center; gap: 16px; margin-left: auto; }
.lrow .kpis .div { align-self: stretch; }
.lrow .kpi .num { font-size: 24px; }
.lrow .kpi.prog { width: 230px; gap: 5px; }
.lrow .psay { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.lrow .pbar { height: 8px; }
.lrow .kpi.last { gap: 2px; }
.lrow .kpi.last .ago { font-size: 15px; font-weight: 700; white-space: nowrap; }
.ltabs { flex: 0 1 auto; gap: 4px; }
.lt-tools { flex: none; display: flex; align-items: center; gap: 6px; }
.ext, .notes-btn { display: inline-flex; align-items: center; justify-content: center; height: 32px; min-width: 32px; font-family: var(--font-ui); font-size: 12px; letter-spacing: .05em; text-transform: uppercase; text-decoration: none; color: var(--muted); background: transparent; border: 1px solid var(--border); border-radius: var(--r-md); padding: 0 12px; cursor: pointer; }
.ext:hover, .notes-btn:hover { color: var(--ink); border-color: var(--ink); }
.ext { white-space: nowrap; }
.ext[hidden] { display: none; }
.notes-btn { display: none; }
.lt-tools [hidden] { display: none !important; }
.work { flex: 1 1 auto; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 320px; }
.views { min-height: 0; height: 100%; overflow: hidden; }
.work.solo { grid-template-columns: minmax(0, 1fr); }
.work.solo .docs { display: none; }
.view { display: none; min-height: 0; }
.view.on { display: block; height: 100%; }
html:not(.js) .view { display: block; }
.view.lesson { height: 100%; }
iframe.lesson-frame { display: block; width: 100%; height: 100%; border: 0; background: var(--bg); }
.js .nojs { display: none; }
.nojs { display: block; padding: 16px 20px; }
.view.map { overflow: auto; padding: 16px 20px 24px; }
.mapbox { position: relative; width: max-content; min-width: 100%; }
.mapbox .dir { font-family: var(--font-ui); font-size: 12px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); text-align: center; padding: 6px 0; }
.mlegend { position: absolute; top: 0; right: 0; display: flex; gap: 14px; font-family: var(--font-ui); font-size: 12px; color: var(--muted); }
.mlegend span { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.mlegend .lg-done { display: inline-grid; place-items: center; width: 15px; height: 15px; border-radius: 50%; background: var(--ink); color: var(--bg); font-size: 10px; font-weight: 700; }
.mlegend .lg-new { display: inline-block; width: 16px; height: 10px; border: 1px dashed var(--muted); border-radius: 2px; }
.mlegend i.nx { display: inline-block; width: 16px; height: 10px; border-radius: 2px; background: var(--current-soft); border: 2px solid var(--current); box-shadow: 0 0 8px var(--current-glow); }
.st { font-size: 16px; }
.ltab .okm { font-weight: 700; margin-left: 2px; }
svg.plan { display: block; margin: 0 auto; max-width: none; font-family: var(--font-prose); }
svg.plan .box { stroke-width: 1; }
svg.plan .node text { font-size: 12px; text-anchor: middle; dominant-baseline: central; }
svg.plan .lv-new .box { fill: var(--bg); stroke: var(--muted); stroke-dasharray: 4 3; }
svg.plan .lv-new text { fill: var(--muted); }
svg.plan .lv-learn .box { fill: var(--bg); stroke: var(--ink); }
svg.plan .lv-learn text { fill: var(--ink); font-weight: 600; }
svg.plan .lv-kept .box, svg.plan .lv-own .box { fill: var(--done-fill); stroke: var(--border); filter: drop-shadow(0 0 5px var(--done-glow)); }
svg.plan .lv-kept text, svg.plan .lv-own text { fill: var(--done-ink); }
svg.plan .badge rect { fill: var(--done-ink); stroke: var(--done-fill); stroke-width: 1; }
svg.plan .node .badge text { font-family: var(--font-ui); font-size: 10px; font-weight: 700; fill: var(--done-fill); }
svg.plan .pip { fill: none; stroke: var(--muted); stroke-width: 1; }
svg.plan .pip.on { fill: var(--ink); stroke: var(--ink); }
svg.plan .node text.mk { font-family: var(--font-ui); font-size: 13px; font-weight: 700; text-anchor: end; fill: var(--ink); opacity: .6; }
svg.plan .node text.mk.warn { fill: var(--ink); font-weight: 700; opacity: 1; }
svg.plan .node.next .box { stroke: var(--current); stroke-width: 2; stroke-dasharray: none; fill: var(--current-soft); }
svg.plan .node.next text { fill: var(--ink); font-weight: 700; }
svg.plan rect.glow { fill: var(--current-glow); opacity: .55; stroke: none; pointer-events: none; }
svg.plan .chip rect { fill: var(--ink); }
svg.plan .node .chip text { font-family: var(--font-ui); font-size: 10px; font-weight: 700; fill: var(--bg); }
svg.plan .node[data-go], svg.plan .node[data-doc] { cursor: pointer; }
svg.plan .node[data-go]:hover .box, svg.plan .node[data-doc]:hover .box { stroke-width: 2; }
svg.plan .edge { fill: none; stroke: var(--ink); stroke-width: 1.4; }
svg.plan .edge.path { stroke: var(--muted); stroke-width: 1; }
svg.plan .edge.dim { stroke: var(--border); stroke-width: 1; opacity: .7; }
svg.plan .ah { fill: var(--ink); }
svg.plan .ah.path { fill: var(--muted); }
svg.plan .ah.dim { fill: var(--border); }
svg.plan .node.flash .box { animation: flash 2.2s ease-out; }
@keyframes flash { 0%, 30% { stroke: var(--ink); stroke-width: 3; } 100% { stroke-width: 1; } }
.problems { font-family: var(--font-ui); font-size: 12px; color: var(--muted); margin: 12px 0 0; text-align: center; }
/* notes & documents column */
.docs { min-height: 0; overflow: auto; border-left: 1px solid var(--border); padding: 16px 14px 24px; background: var(--bg); }
.docs > .bh { margin-bottom: 4px; }
.dlist { display: none; list-style: none; margin: 0; padding: 0; }
.dlist.on, html:not(.js) .dlist { display: block; }
.doc { display: flex; align-items: center; gap: 10px; width: 100%; min-height: 50px; text-align: left; text-decoration: none; color: var(--ink); background: transparent; border: 0; border-bottom: 1px solid var(--border-soft); border-radius: 0; padding: 8px; cursor: pointer; }
.doc .t { flex: 1 1 auto; min-width: 0; font-size: 15px; font-weight: 600; line-height: 1.3; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; }
.doc .di { flex: none; width: 20px; height: 20px; color: var(--muted); }
.doc:hover .di { color: var(--ink); }
.dgrp ul .doc .di { width: 18px; height: 18px; }
.doc .k { flex: none; font-family: var(--font-ui); font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.ext-doc .k::after { content: " ↗"; }
.doc:hover { background: var(--surface); }
.doc:hover .t { text-decoration: underline; text-underline-offset: 3px; }
.doc:focus-visible { outline: 2px solid var(--muted); outline-offset: -2px; }
.doc[aria-current="true"] { background: var(--surface-2); }
.dgrp details > summary { list-style: none; }
.dgrp details > summary::-webkit-details-marker { display: none; }
.dgrp details > summary .k::after { content: " ▸"; }
.dgrp details[open] > summary .k::after { content: " ▾"; }
.dgrp ul { list-style: none; margin: 0; padding: 0 0 0 14px; border-left: 2px solid var(--border-soft); }
.dgrp ul .doc { min-height: 42px; }
.dgrp ul .doc .t { font-weight: 500; font-size: 14px; }
/* side panel (dialog), slides in from the right */
.scrim { position: fixed; inset: 0; z-index: 40; background: rgba(0, 0, 0, .42); opacity: 0; visibility: hidden; transition: opacity .18s, visibility 0s .18s; }
.scrim.on { opacity: 1; visibility: visible; transition: opacity .18s, visibility 0s; }
.sheet { position: fixed; top: 0; right: 0; bottom: 0; z-index: 50; width: min(640px, 94vw); display: flex; flex-direction: column; background: var(--bg); border-left: 1px solid var(--border); box-shadow: -18px 0 40px -24px rgba(0, 0, 0, .5); transform: translateX(102%); visibility: hidden; transition: transform .22s ease-out, visibility 0s .22s; }
.sheet.on { transform: none; visibility: visible; transition: transform .22s ease-out, visibility 0s; }
.sheet-h { flex: none; display: flex; align-items: center; gap: 12px; padding: 14px 18px; border-bottom: 1px solid var(--border); }
.sheet-h .ttl { flex: 1 1 auto; min-width: 0; }
.sheet-h h2 { margin: 2px 0 0; font-family: var(--font-title); font-size: 21px; line-height: 1.25; overflow-wrap: anywhere; }
.sheet-x { flex: none; width: 42px; height: 42px; font-size: 16px; background: transparent; border: 1px solid var(--border); border-radius: var(--r-md); color: var(--ink); cursor: pointer; }
.sheet-x:hover { border-color: var(--ink); }
.sheet-b { flex: 1 1 auto; min-height: 0; overflow: auto; }
.sheet-b:focus { outline: none; }
.sheet.frame .sheet-b { overflow: hidden; }
.sheet-b iframe { display: block; width: 100%; height: 100%; border: 0; background: var(--bg); }
.md { padding: 8px 22px 28px; font-size: 15px; line-height: 1.6; overflow-wrap: anywhere; }
.md h3, .md h4, .md h5, .md h6 { font-family: var(--font-title); margin: 20px 0 6px; font-size: 18px; }
.md p { margin: 8px 0; }
.md ul, .md ol { margin: 8px 0; padding-left: 22px; }
.md li { margin: 3px 0; }
.md li.sub { margin-left: 18px; }
.md-table { overflow-x: auto; margin: 10px 0; }
.md table { border-collapse: collapse; font-size: 14px; min-width: 100%; }
.md th, .md td { text-align: left; vertical-align: top; padding: 7px 10px; border-bottom: 1px solid var(--border-soft); }
.md th { font-family: var(--font-ui); font-size: 12px; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); font-weight: 500; }
.md pre { background: var(--surface); border: 1px solid var(--border-soft); border-radius: var(--r-md); padding: 10px 12px; overflow-x: auto; }
.md pre code { border: 0; background: none; padding: 0; }
@media (max-width: 900px) {
  .work { grid-template-columns: minmax(0, 1fr); }
  .notes-btn { display: inline-flex; }
  .docs { position: fixed; top: 0; right: 0; bottom: 0; z-index: 45; width: min(340px, 88vw); border-left: 1px solid var(--border); transform: translateX(102%); visibility: hidden; transition: transform .2s ease-out, visibility 0s .2s; }
  .docs.on { transform: none; visibility: visible; transition: transform .2s ease-out, visibility 0s; }
  html:not(.js) .docs { position: static; transform: none; visibility: visible; width: auto; }
  .gen-grid { grid-template-columns: minmax(0, 1fr); }
  .lrow .kpis { flex-basis: 100%; margin-left: 0; justify-content: space-between; }
  .lrow .kpi.prog { flex: 1 1 auto; width: auto; min-width: 0; }
}
@media (max-width: 640px) {
  .bar { gap: 10px; padding: 8px 12px; }
  .mark { display: none; }
  .kpis { margin-left: 0; width: 100%; gap: 14px; }
  .kpi .num { font-size: 30px; }
  .kpi.prog { flex: 1 1 auto; width: auto; }
  .lrow { padding: 8px 12px; }
  .tab { gap: 6px; padding: 0 11px; max-width: 160px; font-size: 12px; letter-spacing: .02em; }
  .tab .tl { overflow: hidden; text-overflow: ellipsis; }
  .lt-tools .ext { display: none !important; }
  .lrow .kpis { flex-wrap: nowrap; gap: 12px; }
  .lrow .kpi.last { flex-direction: row; align-items: baseline; gap: 6px; }
  .notes-btn { padding: 0 10px; }
  .ltab .lt { max-width: 110px; }
  .theme-btn .tt { display: none; }
  .kpis .div { display: none; }
  .kpi.due { padding: 8px 12px; }
  .gen-in { padding: 20px 14px 40px; }
}
"""

THEME_JS = """(function(){var r=document.documentElement,k="teach-theme",t=null;r.classList.add("js");
try{var q=new URLSearchParams(location.search).get("theme");if(q==="light"||q==="dark")t=q;}catch(e){}
if(!t){try{t=localStorage.getItem(k);}catch(e){}}
if(t==="light"||t==="dark")r.setAttribute("data-theme",t);
window.teachToggleTheme=function(){var c=r.getAttribute("data-theme");
if(!c){try{c=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";}catch(e){c="light";}}
var n=c==="dark"?"light":"dark";r.setAttribute("data-theme",n);try{localStorage.setItem(k,n);}catch(e){}};})();"""


LEVEL_KEYS = ("yeni", "öğreniliyor", "oturdu", "senin")


# Course tabs (Genel + one per track) → lesson tabs (Ders N…, Harita) → the lesson in an <iframe> that scrolls
# by itself (the shell stays fixed; the lesson's sticky step chip and result bar keep working in its own
# viewport). Route = URL hash "#<track>/<lesson-slug>" | "#<track>/harita" | "#genel"; last course in
# localStorage "teach-tab", last lesson per course in "teach-lesson:<track>". Notes open in a side panel (dialog).
# Lessons get "?embed=1&theme=…" and talk back with postMessage: {teach:"ready"} → parent sends {teach:"theme"};
# {teach:"nav", href} → parent opens that lesson tab / document, else navigates the frame.
SHELL_JS = """(function(){var d=document,root=d.documentElement,K="teach-tab";
function $(s,c){return (c||d).querySelector(s);}function $$(s,c){return [].slice.call((c||d).querySelectorAll(s));}
function get(k){try{return localStorage.getItem(k);}catch(e){return null;}}function put(k,v){try{localStorage.setItem(k,v);}catch(e){}}
function theme(){var t=root.getAttribute("data-theme");if(!t){try{t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";}catch(e){t="light";}}return t;}
function abs(u){try{var x=new URL(u,location.href);x.search="";x.hash="";return x.href;}catch(e){return u;}}
function src(f){var s=f.getAttribute("data-src");return s+(s.indexOf("?")<0?"?":"&")+"embed=1&theme="+theme();}
function load(f){if(!f.getAttribute("src")){f.style.colorScheme=theme();f.setAttribute("src",src(f));}}
function tell(f){f.style.colorScheme=theme();try{f.contentWindow.postMessage({teach:"theme",theme:theme()},"*");}catch(e){}}
var toggle=window.teachToggleTheme;window.teachToggleTheme=function(){toggle();$$("iframe[src]").forEach(tell);};
var bar=$(".tabs"),ctabs=$$("[role=tab]",bar);
function course(k){return ctabs.filter(function(b){return b.getAttribute("data-tab")===k;})[0];}
function ltabs(k){var p=d.getElementById("panel-"+k);return p?$$(".ltabs [role=tab]",p):[];}
function lesson(k,v){return ltabs(k).filter(function(b){return b.getAttribute("data-view")===v;})[0];}
function select(list,t){list.forEach(function(b){var on=b===t,p=d.getElementById(b.getAttribute("aria-controls"));
b.setAttribute("aria-selected",on?"true":"false");b.tabIndex=on?0:-1;if(p)p.classList.toggle("on",on);});
try{t.scrollIntoView({block:"nearest",inline:"nearest"});}catch(e){}}
function ctx(k,v){var p=d.getElementById("panel-"+k),w=p&&$(".work",p),n=$(".notes-btn",p),hit=null;if(!w)return;
$$(".dlist",p).forEach(function(l){var on=l.getAttribute("data-for")===v;l.classList.toggle("on",on);if(on)hit=l;});
w.classList.toggle("solo",!hit);if(n)n.hidden=!hit;}
function route(h,o){o=o||{};var i=h.indexOf("/"),k=i<0?h:h.slice(0,i),v=i<0?"":h.slice(i+1),t=course(k);if(!t)return false;
select(ctabs,t);closeDrawer();if(o.save)put(K,k);var full=k;
if(k!=="genel"){var b=lesson(k,v)||lesson(k,get("teach-lesson:"+k)||"");
if(!b){var row=$("#panel-"+k+" .ltabs");b=row&&lesson(k,row.getAttribute("data-default"));}
if(b){select(ltabs(k),b);v=b.getAttribute("data-view");full=k+"/"+v;if(o.save)put("teach-lesson:"+k,v);
var view=d.getElementById(b.getAttribute("aria-controls")),f=view&&$("iframe",view),x=$("#panel-"+k+" .ext");
if(f)load(f);if(x){x.hidden=!f;if(f)x.href=f.getAttribute("data-src");}ctx(k,v);var sb=b;if(window.requestAnimationFrame)requestAnimationFrame(function(){try{reveal(sb);fades();}catch(_){}});if(o.focus)b.focus();}}
else if(o.focus)t.focus();
if(o.save){try{history.replaceState(null,"","#"+full);}catch(e){}}return true;}
function fromHash(){var h="";try{h=decodeURIComponent(location.hash.slice(1));}catch(e){}return !!h&&route(h);}
if(!fromHash()&&!route(get(K)||""))route(bar.getAttribute("data-default")||"genel");
window.addEventListener("hashchange",fromHash);
function reveal(b){var r=b.parentNode,h=$('[data-view="harita"]',r),pin=h&&h!==b?h.offsetWidth+8:0;
if(b.offsetLeft-pin<r.scrollLeft)r.scrollLeft=b.offsetLeft-pin;
else if(b.offsetLeft+b.offsetWidth>r.scrollLeft+r.clientWidth)r.scrollLeft=b.offsetLeft+b.offsetWidth-r.clientWidth+28;}
function fades(){$$(".lt-wrap").forEach(function(w){var r=$(".ltabs",w),h=$('[data-view="harita"]',r),m=r.scrollWidth-r.clientWidth;
if(h)w.style.setProperty("--pin",(h.offsetWidth+4)+"px");w.classList.toggle("fl",r.scrollLeft>2);w.classList.toggle("fr",r.scrollLeft<m-2);});}
$$(".ltabs").forEach(function(r){r.addEventListener("scroll",fades,{passive:true});});window.addEventListener("resize",fades);fades();
function keys(e,list,go){var i=list.indexOf(d.activeElement),j=-1;if(i<0)return;
if(e.key==="ArrowRight")j=(i+1)%list.length;else if(e.key==="ArrowLeft")j=(i-1+list.length)%list.length;
else if(e.key==="Home")j=0;else if(e.key==="End")j=list.length-1;else return;e.preventDefault();go(list[j]);}
bar.addEventListener("keydown",function(e){keys(e,ctabs,function(b){route(b.getAttribute("data-tab"),{save:1,focus:1});});});
$$(".ltabs").forEach(function(row){var k=row.getAttribute("data-track");
row.addEventListener("keydown",function(e){keys(e,ltabs(k),function(b){route(k+"/"+b.getAttribute("data-view"),{save:1,focus:1});});});});
var sheet=$("#sheet"),scrim=$(".scrim"),body=$(".sheet-b",sheet),opener=null,drawer=null;
function openDrawer(k){var a=d.getElementById("docs-"+k),b=$("#panel-"+k+" .notes-btn");if(!a)return;drawer=a;opener=b;
a.classList.add("on");scrim.classList.add("on");if(b)b.setAttribute("aria-expanded","true");var f=$(".doc",a);if(f)f.focus();}
function closeDrawer(){if(!drawer)return;drawer.classList.remove("on");var b=$$(".notes-btn").filter(function(x){return x.getAttribute("aria-expanded")==="true";})[0];
if(b)b.setAttribute("aria-expanded","false");drawer=null;if(!sheet.classList.contains("on"))scrim.classList.remove("on");}
function openDoc(id,from){var t=d.getElementById("doc-"+id);if(!t)return false;var back=drawer?opener:(from||d.activeElement);closeDrawer();opener=back;
$("#sheet-kind").textContent=t.getAttribute("data-kind");$("#sheet-title").textContent=t.getAttribute("data-title");
body.innerHTML="";body.appendChild(d.importNode(t.content,true));body.scrollTop=0;var f=$("iframe",body);
sheet.classList.toggle("frame",!!f);if(f)load(f);
$$(".doc").forEach(function(b){b.setAttribute("aria-current",b.getAttribute("data-doc")===id?"true":"false");});
sheet.setAttribute("aria-hidden","false");sheet.classList.add("on");scrim.classList.add("on");$(".sheet-x",sheet).focus();return true;}
function closeDoc(){if(!sheet.classList.contains("on"))return;sheet.classList.remove("on");sheet.setAttribute("aria-hidden","true");scrim.classList.remove("on");
$$(".doc").forEach(function(b){b.setAttribute("aria-current","false");});var o=opener;opener=null;
setTimeout(function(){if(!sheet.classList.contains("on"))body.innerHTML="";},250);if(o&&o.focus)o.focus();}
$(".sheet-x",sheet).addEventListener("click",closeDoc);scrim.addEventListener("click",function(){closeDoc();closeDrawer();});
d.addEventListener("keydown",function(e){if(e.key==="Escape"){if(sheet.classList.contains("on"))closeDoc();else if(drawer){var o=opener;closeDrawer();if(o)o.focus();}return;}
if(e.key!=="Tab")return;var box=sheet.classList.contains("on")?sheet:drawer;if(!box)return;
var f=$$("button,a[href],iframe,input,[tabindex]:not([tabindex='-1'])",box).filter(function(x){return x.offsetParent!==null||x===d.activeElement;});
if(!f.length)return;var a=f[0],z=f[f.length-1];
if(!box.contains(d.activeElement)){e.preventDefault();a.focus();}else if(e.shiftKey&&d.activeElement===a){e.preventDefault();z.focus();}
else if(!e.shiftKey&&d.activeElement===z){e.preventDefault();a.focus();}});
d.addEventListener("click",function(e){var x=e.target.closest?e.target:null;if(!x)return;
var c=x.closest("[role=tab]");if(c){if(c.hasAttribute("data-tab"))route(c.getAttribute("data-tab"),{save:1});
else route(c.closest(".ltabs").getAttribute("data-track")+"/"+c.getAttribute("data-view"),{save:1});return;}
var doc=x.closest("[data-doc]");if(doc){openDoc(doc.getAttribute("data-doc"),doc);return;}
var nb=x.closest(".notes-btn");if(nb){openDrawer(nb.getAttribute("data-track"));return;}
var g=x.closest("[data-go]");if(!g)return;e.preventDefault();if(sheet.contains(g))closeDoc();var k=g.getAttribute("data-go"),n=g.getAttribute("data-node");
if(!route(k,{save:1})||!n)return;var p=d.getElementById("panel-"+k.split("/")[0]),el=null;if(!p)return;
$$("svg.plan [data-node]",p).forEach(function(y){if(y.getAttribute("data-node")===n)el=y;});if(!el)return;
setTimeout(function(){try{el.scrollIntoView({block:"center",inline:"center",behavior:"smooth"});}catch(_){el.scrollIntoView();}
el.classList.remove("flash");void el.getBoundingClientRect();el.classList.add("flash");setTimeout(function(){el.classList.remove("flash");},2400);},30);});
window.addEventListener("message",function(e){var m=e.data;if(!m||typeof m!=="object"||!m.teach)return;
var f=$$("iframe[src]").filter(function(x){return x.contentWindow===e.source;})[0];if(!f)return;
if(m.teach==="ready"){tell(f);return;}if(m.teach!=="nav"||typeof m.href!=="string")return;var u=abs(m.href),hit=null;
$$(".ltabs [role=tab]").forEach(function(b){var v=d.getElementById(b.getAttribute("aria-controls")),fr=v&&$("iframe",v);
if(!hit&&fr&&abs(fr.getAttribute("data-src"))===u)hit=b;});
if(hit){route(hit.closest(".ltabs").getAttribute("data-track")+"/"+hit.getAttribute("data-view"),{save:1});return;}
var t=$$("template[data-src]").filter(function(x){return abs(x.getAttribute("data-src"))===u;})[0];
if(t){openDoc(t.id.slice(4));return;}if(/^(file|https?):/.test(m.href))f.setAttribute("src",m.href);});
$$(".kg-wrap").forEach(function(w){var s=$("svg.graph",w);if(!s)return;
var b0=s.getAttribute("viewBox").split(" ").map(Number),BW=b0[2],BH=b0[3],v=b0.slice(),KZ="teach-kg:"+b0.join(","),p=null,moved=false;
function set(n,save){var z=Math.min(1,Math.max(1/8,n[2]/BW)),vw=BW*z,vh=BH*z;
v=[Math.min(BW-vw,Math.max(0,n[0])),Math.min(BH-vh,Math.max(0,n[1])),vw,vh];
s.setAttribute("viewBox",v.map(function(x){return Math.round(x*10)/10;}).join(" "));s.style.setProperty("--ks",Math.pow(v[2]/BW,.6).toFixed(3));
if(save){try{sessionStorage.setItem(KZ,JSON.stringify(v));}catch(e){}}}
function at(e){var m=s.getScreenCTM();if(!m)return null;var q=s.createSVGPoint();q.x=e.clientX;q.y=e.clientY;return q.matrixTransform(m.inverse());}
function zoom(f,c){var r=Math.min(BW,Math.max(BW/8,v[2]*f))/v[2];set([c.x-(c.x-v[0])*r,c.y-(c.y-v[1])*r,v[2]*r,v[3]*r],1);}
try{var sv=JSON.parse(sessionStorage.getItem(KZ)||"null");if(sv&&sv.length===4)set(sv);}catch(e){}
s.addEventListener("wheel",function(e){e.preventDefault();var c=at(e);if(c)zoom(Math.pow(1.0015,e.deltaY*(e.deltaMode===1?33:1)),c);},{passive:false});
s.addEventListener("pointerdown",function(e){if(e.button!==0)return;p={x:e.clientX,y:e.clientY,v:v.slice(),id:e.pointerId};moved=false;});
s.addEventListener("pointermove",function(e){if(!p||e.pointerId!==p.id)return;var dx=e.clientX-p.x,dy=e.clientY-p.y;
if(!moved){if(dx*dx+dy*dy<25)return;moved=true;w.classList.add("drag");try{s.setPointerCapture(e.pointerId);}catch(_){}}
var m=s.getScreenCTM();if(m)set([p.v[0]-dx/m.a,p.v[1]-dy/m.d,p.v[2],p.v[3]]);});
function end(){if(!p)return;p=null;w.classList.remove("drag");if(moved)set(v,1);}
s.addEventListener("pointerup",end);s.addEventListener("pointercancel",end);
w.addEventListener("click",function(e){if(moved){moved=false;e.preventDefault();e.stopPropagation();}},true);
$$(".kg-zoom button",w).forEach(function(bt){bt.addEventListener("click",function(){var z=bt.getAttribute("data-z");
if(z==="fit")set(b0,1);else zoom(z==="in"?1/1.5:1.5,{x:v[0]+v[2]/2,y:v[1]+v[3]/2});});});});
try{var q=new URLSearchParams(location.search).get("panel");if(q)openDoc(q);}catch(e){}
var away=false,last=Date.now(),dirty=[];
function back(){if(!away||(d.visibilityState&&d.visibilityState!=="visible"))return;away=false;
if(Date.now()-last<2000||sheet.classList.contains("on")||dirty.length)return;last=Date.now();try{location.reload();}catch(e){}}
d.addEventListener("visibilitychange",function(){if(d.visibilityState==="hidden")away=true;else back();});
window.addEventListener("blur",function(){setTimeout(function(){var a=d.activeElement;if(!a||a.tagName!=="IFRAME")away=true;},0);});
window.addEventListener("focus",back);
window.addEventListener("message",function(e){var m=e.data;if(!m||m.type!=="teach-dirty")return;
var f=$$("iframe[src]").filter(function(x){return x.contentWindow===e.source;})[0];if(!f)return;
dirty=dirty.filter(function(x){return x!==f;});if(m.dirty)dirty.push(f);});})();"""


def tab_key(track_id: str) -> str:
    """Tab / URL-hash key of a track: its id ("genel" is the overview tab, so a track by that name is renamed)."""
    return track_id if track_id != "genel" else "konu-genel"


def level_counts(tracks: list[dict]) -> dict:
    counts = dict.fromkeys(LEVEL_KEYS, 0)
    for t in tracks:
        for n in t["map"]["nodes"]:
            counts[LEVEL_TR.get(n["level"], "yeni")] += 1
    return counts


def lesson_number(les: dict, lessons: list[dict]) -> int:
    """Lesson number from the file name's leading digits (0002-x.html → 2), else its position."""
    m = re.match(r"(\d+)", Path(les["path"]).name)
    return int(m.group(1)) if m else lessons.index(les) + 1


def lesson_slug(les: dict) -> str:
    """URL-hash / id part of a lesson: its file stem, reduced to [A-Za-z0-9_-] (the export carries it as "slug")."""
    if les.get("slug"):
        return les["slug"]
    return re.sub(r"[^\w-]", "-", Path(les["path"]).stem, flags=re.A) or "ders"


def current_lesson(t: dict) -> tuple[dict, int] | None:
    """The lesson the learner is on: the latest lesson whose quiz result is not recorded yet, else the latest one.
    Returns (lesson, number)."""
    ls = t["lessons"]
    if not ls:
        return None
    open_ = [x for x in ls if x["result_recorded"] is False]
    cur = open_[-1] if open_ else ls[-1]
    return cur, lesson_number(cur, ls)


TR_UNITS = {1: "i", 2: "si", 3: "ü", 4: "ü", 5: "i", 6: "sı", 7: "si", 8: "i", 9: "u"}
TR_TENS = {1: "u", 2: "si", 3: "u", 4: "ı", 5: "si", 6: "ı", 7: "i", 8: "i", 9: "ı"}


def tr_poss(n: int) -> str:
    """A numeral with its 3rd-person possessive suffix, as in "15 konudan 3'ü": 1'i 2'si 3'ü 6'sı 10'u 20'si
    40'ı 100'ü 1000'i 1000000'u. Follows the last spoken word of the number."""
    n = abs(int(n))
    if n % 10:
        suf = TR_UNITS[n % 10]
    elif n % 100:
        suf = TR_TENS[n % 100 // 10]
    elif n % 1000:
        suf = "ü"  # yüz
    elif n % 1_000_000:
        suf = "i"  # bin
    elif n % 1_000_000_000:
        suf = "u"  # milyon
    else:
        suf = "ı"  # milyar
    return f"{n}'{suf}"


def kpi_parts(scope: list[dict], days: int) -> dict:
    """{days, prog, due}: the three vital numbers as html blocks: studied days, one plain progress bar ("N konudan
    X'i öğrenildi · Y'si işlendi": öğrenildi = retained and above in ink, işlendi = learning/checked in grey; ""
    when there are no nodes) and memory freshness ("%73 güncel · 3 konu tekrar bekliyor"; "" before any study)."""
    done = sum(1 for t in scope for tk in t["tasks"] if tk["last_status"] in ("passed", "explained"))
    due = sum(t["due"]["today"] for t in scope)
    lc = level_counts(scope)
    total = sum(lc.values())
    learned, worked = lc["oturdu"] + lc["senin"], lc["öğreniliyor"]
    tip = f' title="{done} tamamlanan görev"' if done else ""
    kpis = [f'<div class="kpi days"{tip}><b class="num">{days}</b><span class="lbl">çalışılan gün</span></div>']
    if total:
        say = f"{total} konudan {tr_poss(learned)} öğrenildi" if learned else f"{total} konu"
        more = f'<span class="pm"> · {tr_poss(worked)} işlendi</span>' if worked else ""
        pct = lambda v: fmt(round(100 * v / total, 1))
        bar = (f'<div class="pbar" role="img" title="öğrenildi {learned} · işlendi {worked} · henüz değil {total - learned - worked}" '
               f'aria-label="{esc(say)}{f", {tr_poss(worked)} işlendi" if worked else ""}">'
               + (f'<i class="pl" style="width:{pct(learned)}%"></i>' if learned else "")
               + (f'<i class="pw" style="width:{pct(worked)}%"></i>' if worked else "") + "</div>")
        full = say + (f" · {tr_poss(worked)} işlendi" if worked else "")
        kpis.append(f'<div class="kpi prog"><p class="psay" title="{esc(full)}"><b>{esc(say)}</b>{more}</p>{bar}</div>')
    else:
        kpis.append("")
    studied = sum(t["due"].get("studied", 0) for t in scope)
    fresh = sum(t["due"].get("fresh", 0) for t in scope)
    if studied:  # memory freshness: the share of studied nodes whose review isn't due and that aren't slipping
        stale = studied - fresh
        tip = f"Çalıştığın {studied} konunun {tr_poss(fresh)} güncel" + (f"; {stale} konunun tekrarı geldi" if stale else "")
        sub = f"{stale} konu tekrar bekliyor" if stale else "tekrar bekleyen konu yok"
        kpis.append(f'<div class="kpi due" title="{esc(tip)}"><b class="num">%{round(100 * fresh / studied)}</b>'
                    f'<span class="dl"><b>güncel</b><small>{sub}</small></span></div>')
    else:
        kpis.append("")
    return dict(zip(("days", "prog", "due"), kpis))


def tr_ago(day: str | None) -> str:
    """A past day in plain Turkish, relative to today(): bugün, dün, 2–6 gün önce, 1 hafta önce, N hafta önce."""
    if not day:
        return ""
    n = (today() - dt.date.fromisoformat(day)).days
    if n <= 0:
        return "bugün"
    if n == 1:
        return "dün"
    if n < 7:
        return f"{n} gün önce"
    return f"{n // 7} hafta önce"


def track_stats(t: dict, last_day: str | None) -> str:
    """A track's stats at the right end of its tab row: the progress sentence + bar, and when it was last studied."""
    k = kpi_parts([t], 0)
    last = (f'<div class="kpi last"><span class="lbl">son çalışma</span><b class="ago">{tr_ago(last_day)}</b></div>'
            if last_day else "")
    parts = [x for x in (k["prog"], last) if x]
    return ('<div class="kpis">' + '<i class="div"></i>'.join(parts) + "</div>") if parts else ""


TR_MONTHS = ("Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara")
MILESTONE_TR = {"first-correct-answer": "İlk doğru cevap",
                "first-remembered-after-a-delay": "Aradan sonra ilk kez hatırladın",
                "first-task-passed": "İlk görev tamam",
                "first-node-owned": "İlk konu uygulamada da oturdu"}


def tr_date(day: str) -> str:
    d = dt.date.fromisoformat(day)
    return f"{d.day} {TR_MONTHS[d.month - 1]}"


def milestone_label(note: str, titles: dict) -> str:
    """Plain Turkish for a milestone id; unknown ids are humanized."""
    if note in MILESTONE_TR:
        return MILESTONE_TR[note]
    m = re.fullmatch(r"(\d+)-nodes-learned", note)
    if m:
        return f"{m.group(1)} konu öğrenildi"
    m = re.fullmatch(r"(\d+)-day-streak", note)
    if m:
        return f"{m.group(1)} gün üst üste"
    m = re.fullmatch(r"track-(.+)-retained", note)
    if m:
        return f"{titles.get(m.group(1), m.group(1))}: bütün konular öğrenildi"
    s = note.replace("-", " ").replace("_", " ").strip()
    return s[:1].upper() + s[1:]


def recent_rows(data: dict, tracks: list[dict], hue: dict) -> list[str]:
    """"Son çalışmalar": one row per (day, track) from learner.recent: what changed that day, in plain words.
    No change → the number of answers. Node titles only, never card text."""
    label = {(t["id"], n["id"]): node_label(n) for t in tracks for n in t["map"]["nodes"]}
    titles = {t["id"]: t["title"] for t in tracks}
    def names(t, ids, cap=3):
        xs = [f'<b>{esc(label.get((t, n)) or n.replace("-", " "))}</b>' for n in ids]
        return ", ".join(xs[:cap]) + (f" +{len(xs) - cap}" if len(xs) > cap else "")
    out = []
    for r in data["learner"].get("recent") or []:
        t, bits = r["track"], []
        for lvl, mark in MARK.items():
            ids = [x["node"] for x in r["done"] if x["level"] == lvl]
            if ids:
                bits.append(f'{names(t, ids)} <span class="rc-ok">{mark} {STATE_TR[lvl]}</span>')
        if r["started"]:
            bits.append(f'{names(t, r["started"])} başladı')
        if r["remembered"]:
            bits.append(f'{names(t, r["remembered"])}: günler sonra hatırladın')
        if r["slipping"]:
            bits.append(f'{names(t, r["slipping"])}: tekrar lazım')
        if not bits:
            bits.append(f'{r["answers"]} soru' if r["answers"] else "çalışıldı")
        tags = "".join(f'<span class="rc-tag">{esc(milestone_label(m, titles))}</span>' for m in r["milestones"])
        out.append(f'<li><div class="rc-h"><span class="rc-d">{tr_date(r["day"])}</span>'
                   f'<span class="rc-t"><i class="hue" style="background:{hue.get(t, "var(--muted)")}"></i>'
                   f'{esc(short_title(titles.get(t, t)))}</span></div>'
                   f'<div class="rc-x">{" · ".join(bits)}{tags}</div></li>')
    return out


def render_overview(data: dict, tracks: list[dict], tab: dict) -> str:
    """The "Genel" panel body: Kavram ağı (the hero, top left) and one side column: action card (all reviews due),
    progress (all tracks), studied days, the 8-week calendar with one gentle line, and "Son çalışmalar" (what each
    recent study day changed). Empty parts are left out."""
    days = set(data["learner"]["study_days"])
    td = today()
    start = td - dt.timedelta(days=td.weekday()) - dt.timedelta(weeks=7)  # at most 8 weeks, Monday first
    active = [w for w in range(8) if any((start + dt.timedelta(days=7 * w + k)).isoformat() in days for k in range(7))]
    start += dt.timedelta(weeks=active[0] if active else 7)  # begin at the first week with any study
    cells = []
    for k in range((td - start).days // 7 * 7 + 7):  # one row per week, one column per weekday
        d = start + dt.timedelta(days=k)
        cls = "fut" if d > td else ("on" if d.isoformat() in days else "")
        if d == td:
            cls += " today"
        cells.append(f'<i class="{cls.strip()}" title="{d.isoformat()}"></i>')
    week = sum(1 for k in range(td.weekday() + 1) if (td - dt.timedelta(days=k)).isoformat() in days)
    kp = kpi_parts(tracks, len(days))
    side = [f'<div class="blk">{kp["due"]}</div>'] if kp["due"] else []
    if kp["prog"]:
        side.append(f'<div class="blk">{kp["prog"]}</div>')
    side.append(f'<div class="blk" id="takvim"><h2 class="cal-h">{len(days)} gün çalıştın'
                + (f'<span class="wk"> · bu hafta {week}</span>' if week else "") + "</h2>"
                '<div class="cal-days" aria-hidden="true">' + "".join(f"<span>{x}</span>" for x in "PSÇPCCP") + "</div>"
                f'<div class="cal" aria-label="her satır bir hafta, her dolu kare çalıştığın bir gün">{"".join(cells)}</div>'
                + "</div>")
    if not days:
        side.pop()
    rows = recent_rows(data, tracks, track_hues(tracks))
    if rows:
        side.append(f'<div class="blk" id="son"><h2 class="bh">Son çalışmalar</h2><ol class="recent">{"".join(rows)}</ol></div>')
    if data["data_warnings"]:
        side.append('<div class="blk"><p class="warn">Bazı kayıt satırları okunamadı. Claude\'a söyle; o düzeltir.</p></div>')
    if any(t["map"]["nodes"] for t in tracks):
        svg, kg_legend = render_graph_svg([t for t in tracks if t["map"]["nodes"]], tab, track_hues(tracks))
        zoom = ('<div class="kg-zoom"><button type="button" data-z="in" aria-label="Yakınlaştır" title="Yakınlaştır">+</button>'
                '<button type="button" data-z="out" aria-label="Uzaklaştır" title="Uzaklaştır">−</button>'
                '<button type="button" data-z="fit" aria-label="Tümünü göster" title="Tümünü göster">⤢</button></div>')
        # the legend sits in the header line, outside the canvas, so it never covers nodes while panning / zooming
        main = (f'<div class="blk" id="ag"><h2 class="bh kg-h">Kavram ağı'
                + (f'<span class="kg-legend">{kg_legend}</span>' if kg_legend else "")
                + f'</h2><div class="kg-wrap">{svg}{zoom}</div></div>')
    else:
        main = ""
    return f'<div class="gen-grid"><div class="main">{main}</div><div class="side">{"".join(side)}</div></div>'


DOC_KIND = {"cheatsheet": "Özet", "glossary": "Sözlük", "resources": "Kaynaklar", "map": "Harita",
            "reference": "Referans", "task": "Görev"}


def _doc_id(*parts: str) -> str:
    return re.sub(r"[^\w-]", "-", "--".join(parts), flags=re.A)


def render_docs(t: dict, k: str, out_dir: Path) -> list[dict]:
    """The track's documents from the export, ready for the page: Markdown bodies embedded now (escaped), HTML pages
    framed by their relative link."""
    out = []
    for d in t.get("docs") or []:
        row = {"id": _doc_id(k, d["id"]), "key": d["id"], "kind": DOC_KIND.get(d["type"], d["type"]), "title": d["title"]}
        f = ROOT / d["path"]
        if d["type"] == "reference":
            row["src"] = link(d["path"], out_dir)
        elif f.is_file():
            row["html"] = md_body(f)
        else:
            continue
        out.append(row)
    return out


def doc_template(doc: dict) -> str:
    head = f'<template id="doc-{esc(doc["id"])}" data-kind="{esc(doc["kind"])}" data-title="{esc(doc["title"])}"'
    if "src" in doc:
        return (head + f' data-src="{doc["src"]}"><iframe class="doc-frame" data-src="{doc["src"]}" '
                f'title="{esc(doc["title"])}"></iframe></template>')
    return head + f'><div class="md">{doc["html"]}</div></template>'


def lesson_context(les: dict, docs: list[dict]) -> list[dict]:
    """A lesson's own material from the export: the track documents that belong to it, then its sources."""
    by_key = {d["key"]: d for d in docs}
    return [by_key[x] for x in les.get("docs") or [] if x in by_key] + \
        [{"kind": "Kaynak", "title": s["title"], "href": s["href"]} for s in les.get("sources") or []]


GROUP_TR = {"Görev": "Görevler", "Referans": "Referans sayfaları", "Kaynak": "Kaynaklar"}

# One line icon per document kind (24×24, stroke = currentColor), so a kind is recognisable before its tag is read.
_LINK_ICON = ('<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/>'
              '<path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>')
DOC_ICON = {
    "Özet": '<rect x="5" y="3.5" width="14" height="17" rx="2"/><path d="M9 8.5h6M9 12h6M9 15.5h3.5"/>',
    "Sözlük": '<path d="M5 18.5V5a2 2 0 0 1 2-2h12v14H7a2 2 0 0 0-2 2 2 2 0 0 0 2 2h12"/><path d="M9.5 11l2-5 2 5M10.2 9.4h2.6"/>',
    "Kaynaklar": _LINK_ICON,
    "Kaynak": _LINK_ICON,
    "Harita": '<circle cx="6" cy="6" r="2.2"/><circle cx="18" cy="9" r="2.2"/><circle cx="9" cy="18" r="2.2"/>'
              '<path d="M8.1 6.6l7.8 1.8M6.8 8.1l1.5 7.8M16.5 10.8l-6 5.6"/>',
    "Referans": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 16.5h6"/>',
    "Görev": '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8.5 12.5l2.5 2.5 4.5-5"/>',
}


def doc_icon(kind: str) -> str:
    """The kind's line icon (decorative: the kind tag carries the meaning); unknown kind → nothing."""
    paths = DOC_ICON.get(kind)
    return (f'<svg class="di" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{paths}</svg>') if paths else ""


def doc_list(items: list[dict], ctx: str, on: bool) -> str:
    """One context's list in the notes column: one line per item, title + type tag. Two or more items of the same
    kind fold into one collapsible group (<details>: the kind, plural, and the count), in first-seen order."""
    if not items:
        return ""
    def row(d):
        body = f'{doc_icon(d["kind"])}<span class="t">{esc(d["title"])}</span><span class="k">{esc(d["kind"])}</span>'
        if "href" in d:
            return (f'<li><a class="doc ext-doc" href="{esc(d["href"])}" target="_blank" rel="noopener" '
                    f'title="{esc(d["title"])} (yeni sekmede)">{body}</a></li>')
        return (f'<li><button type="button" class="doc" data-doc="{esc(d["id"])}" aria-haspopup="dialog" '
                f'aria-current="false" title="{esc(d["title"])}">{body}</button></li>')
    kinds = list(dict.fromkeys(d["kind"] for d in items))
    li = []
    for kd in kinds:
        same = [d for d in items if d["kind"] == kd]
        if len(same) == 1:
            li.append(row(same[0]))
        else:
            li.append(f'<li class="dgrp"><details><summary class="doc">{doc_icon(kd)}<span class="t">{esc(GROUP_TR.get(kd, kd))}</span>'
                      f'<span class="k">{len(same)}</span></summary><ul>{"".join(row(d) for d in same)}</ul></details></li>')
    return f'<ul class="dlist{" on" if on else ""}" data-for="{esc(ctx)}">' + "".join(li) + "</ul>"


def render_track_panel(t: dict, i: int, out_dir: Path, tab: dict) -> tuple[str, list[str]]:
    """One course: its performance strip, lesson tabs (Harita first and the first-open default, then Ders N…), the
    selected view (map, or the lesson in an iframe), and a notes column that follows the view: on Harita every
    note of the track, on a lesson only that lesson's material; no material → no column. Returns (panel body,
    doc templates)."""
    k = tab[t["id"]]
    S = []
    docs = render_docs(t, k, out_dir)
    resume = t.get("resume") or ""
    cl = current_lesson(t)
    vid = f"view-{k}-harita"
    tabs = [f'<button type="button" role="tab" class="ltab" id="lt-{esc(k)}-harita" data-view="harita" '
            f'aria-controls="{esc(vid)}" aria-selected="true" tabindex="0" '
            f'title="{esc(t["title"])}: konu haritası"><span class="ln">Harita</span></button>']
    probs = ""
    if t["map"]["nodes"] and t["map"]["problems"]:
        probs = '<p class="problems">' + " · ".join(esc(p) for p in t["map"]["problems"]) + "</p>"
    views = [f'<div class="view map on" id="{esc(vid)}" role="tabpanel" aria-labelledby="lt-{esc(k)}-harita">'
             + (map_box(t, i, k, out_dir) + probs if t["map"]["nodes"] else "") + "</div>"]
    lists = [doc_list(docs, "harita", True)]
    for les in t["lessons"]:
        slug, num = lesson_slug(les), lesson_number(les, t["lessons"])
        here = cl is not None and les is cl[0]
        vid = f"view-{k}-{slug}"
        tip = f"Ders {num} · {les['title']}" + (f" · sıradaki{' — ' + resume if resume else ''}" if here else "") + \
              (" · sonuç kaydedildi" if les["result_recorded"] else "")
        tabs.append(f'<button type="button" role="tab" class="ltab{" is-next" if here else ""}" id="lt-{esc(k)}-{esc(slug)}" '
                    f'data-view="{esc(slug)}" aria-controls="{esc(vid)}" aria-selected="false" tabindex="-1" title="{esc(tip)}">'
                    f'<span class="ln">{num}</span><span class="lt">{esc(les["title"])}</span>'
                    + ('<span class="okm" aria-label="sonuç kaydedildi">✓</span>' if les["result_recorded"] else "")
                    + "</button>")
        href = link(les["path"], out_dir)
        views.append(f'<div class="view lesson" id="{esc(vid)}" role="tabpanel" '
                     f'aria-labelledby="lt-{esc(k)}-{esc(slug)}"><iframe class="lesson-frame" data-src="{href}" '
                     f'title="Ders {num} · {esc(les["title"])}"></iframe>'
                     f'<a class="nojs" href="{href}">Ders {num} — {esc(les["title"])}</a></div>')
        lists.append(doc_list(lesson_context(les, docs), slug, False))
    lists = [x for x in lists if x]
    S.append(f'<div class="lrow"><div class="lt-wrap"><div class="ltabs" role="tablist" aria-label="{esc(t["title"])}: dersler" '
             f'data-track="{esc(k)}" data-default="harita">' + "".join(tabs) + "</div></div>"
             '<div class="lt-tools"><a class="ext" href="#" target="_blank" rel="noopener" hidden '
             'title="Dersi ayrı sekmede aç">↗ yeni sekmede aç</a>'
             + (f'<button type="button" class="notes-btn" data-track="{esc(k)}" aria-controls="docs-{esc(k)}" '
                f'aria-expanded="false"{"" if docs else " hidden"}>Notlar</button>' if lists else "") + '</div>'
             + track_stats(t, t.get("last_studied")) + '</div>')
    side = (f'<aside class="docs" id="docs-{esc(k)}" aria-label="Notlar ve dokümanlar"><h2 class="bh">Notlar &amp; dokümanlar</h2>'
            + "".join(lists) + "</aside>") if lists else ""
    S.append(f'<div class="work{"" if docs else " solo"}"><div class="views">' + "\n".join(views) + "</div>" + side + "</div>")
    return "\n".join(S), [doc_template(d) for d in docs] + node_templates(t, k)


def lesson_chips(t: dict, k: str) -> tuple[dict, dict]:
    """(node -> "D<n>" chip, node -> lesson route) from each lesson's nodes; the first lesson that teaches a node wins."""
    chips, go = {}, {}
    for les in t["lessons"]:
        for nid in les.get("nodes") or []:
            if nid not in chips:
                chips[nid] = f"D{lesson_number(les, t['lessons'])}"
                go[nid] = f"{k}/{lesson_slug(les)}"
    return chips, go


def map_box(t: dict, i: int, k: str, out_dir: Path) -> str:
    """The Harita view: the plan with TEMEL (top) / HEDEF (bottom), a tiny legend in the top-right corner (only the
    states present: bitti, sıradaki, henüz değil), lesson chips on taught nodes; a node with a lesson opens it,
    every node opens its card in the side panel (the card links the node's lesson)."""
    chips, go = lesson_chips(t, k)
    ids = {n["id"] for n in t["map"]["nodes"]}
    attrs = {nid: f' data-doc="{esc(_doc_id(k, "node-" + nid))}"' for nid in ids}
    lv = {n["level"] for n in t["map"]["nodes"]}
    leg = ([f'<span><b class="lg-done">✓</b>öğrenildi</span>'] if lv & set(DONE) else []) + \
          (['<span><i class="nx"></i>sıradaki</span>'] if t["next"] in ids else []) + \
          (['<span><b class="lg-new"></b>henüz değil</span>'] if "new" in lv else [])
    return ('<div class="mapbox">' + (f'<div class="mlegend">{"".join(leg)}</div>' if leg else "")
            + '<div class="dir">Temel</div>' + render_plan_svg(t, f"p{i}", chips=chips, attrs=attrs)
            + '<div class="dir">Hedef</div></div>')


def node_templates(t: dict, k: str) -> list[str]:
    """The node card (side panel), one fixed layout for every node of every track, from the export only:
    state + what it rests on, Tanım (the map's learner-facing definition, else its statement), Özetin (the
    learner's cheatsheet section for the node, else a note) and the lessons that teach it. No cards, no answers."""
    title = {n["id"]: node_label(n) for n in t["map"]["nodes"]}
    teach = {}
    for les in t["lessons"]:
        for nid in les.get("nodes") or []:
            teach.setdefault(nid, []).append(les)
    out = []
    for n in t["map"]["nodes"]:
        lv = n["level"]
        cls = "next" if n["id"] == t["next"] else LEVEL_CLASS.get(lv, "new")
        mark = MARK[lv] + " " if lv in DONE else ""
        state = "sıradaki" if cls == "next" else STATE_TR.get(lv, lv)
        deps = "".join(f'<span class="nc-chip">{esc(title.get(d, d))}</span>' for d in n.get("depends_on") or [])
        stale = '<span class="nc-st stale">tazelenmeli</span>' if n.get("slipping") else ""
        top = (f'<div class="nc-top"><span class="nc-st {cls}">{mark}{esc(state)}</span>{stale}'
               + (f'<span class="nc-deps"><span class="lbl">Dayandığı</span>{deps}</span>' if deps else "") + "</div>")
        definition = n.get("definition") or n.get("statement")
        sec_def = ('<div class="nc-sec"><h3 class="lbl">Tanım</h3>'
                   + (f'<p class="nc-def">{md_inline(definition)}</p>' if definition else
                      '<p class="nc-empty">Tanım henüz yazılmadı.</p>') + "</div>")
        if n.get("summary"):
            # each "**Temel gerçek:** …" line of a cheatsheet entry is its own paragraph
            body = f'<div class="md nc-sum">{md_to_html(re.sub(r"\n(?=\*\*)", "\n\n", n["summary"]))}</div>'
        elif lv in DONE:
            body = '<p class="nc-empty">Özeti henüz yazılmadı. Bir sonraki derste birlikte ekleyeceğiz.</p>'
        else:
            body = '<p class="nc-empty">Bu konu bitince özetini birlikte yazacağız.</p>'
        sec_sum = f'<div class="nc-sec"><h3 class="lbl">Özetin</h3>{body}</div>'
        les = teach.get(n["id"]) or []
        sec_les = (f'<div class="nc-sec"><h3 class="lbl">{"Dersler" if len(les) > 1 else "Ders"}</h3>' + "".join(
            f'<button type="button" class="nc-go" data-go="{esc(k)}/{esc(lesson_slug(x))}">'
            f'<span class="nc-num">D{lesson_number(x, t["lessons"])}</span>{esc(x["title"])}<span aria-hidden="true">→</span></button>'
            for x in les) + "</div>") if les else ""
        out.append(f'<template id="doc-{esc(_doc_id(k, "node-" + n["id"]))}" data-kind="Konu" data-title="{esc(title[n["id"]])}">'
                   f'<div class="nc">{top}{sec_def}{sec_sum}{sec_les}</div></template>')
    return out


SHEET = ('<div class="scrim" aria-hidden="true"></div>\n<aside class="sheet" id="sheet" role="dialog" aria-modal="true" '
         'aria-labelledby="sheet-title" aria-hidden="true"><div class="sheet-h"><div class="ttl"><div class="lbl" id="sheet-kind"></div>'
         '<h2 id="sheet-title"></h2></div><button type="button" class="sheet-x" aria-label="Kapat (Esc)">✕</button></div>'
         '<div class="sheet-b" tabindex="0"></div></aside>')


# The mark: Δ with a node at each corner, a wide base narrowing to one goal (foundations first, one step at a
# time), drawn like the map's nodes. LOGO = inline, follows the theme; FAVICON = the app icon (assets/logo.svg).
LOGO = ('<svg class="logo" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 6 L18.4 17.6 H5.6 Z" fill="none" '
        'stroke="currentColor" stroke-width="2.4" stroke-linejoin="round"/>' + "".join(
            f'<circle cx="{x}" cy="{y}" r="2" fill="currentColor"/>' for x, y in ((12, 6), (5.6, 17.6), (18.4, 17.6)))
        + "</svg>")
FAVICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' role='img' aria-label='teach'%3E %3Crect width='24' height='24' rx='5' fill='%231a1a1a'/%3E %3Cpath d='M12 6 L18.4 17.6 H5.6 Z' fill='none' stroke='%23fafafa' stroke-width='2.2' stroke-linejoin='round'/%3E %3Ccircle cx='12' cy='6' r='1.6' fill='%23fafafa'/%3E %3Ccircle cx='5.6' cy='17.6' r='1.6' fill='%23fafafa'/%3E %3Ccircle cx='18.4' cy='17.6' r='1.6' fill='%23fafafa'/%3E %3C/svg%3E"


def short_title(title: str, limit: int = 22) -> str:
    """A course tab's name: the part before ":" or " — " if there is one, cut to `limit` characters ("…")."""
    s = re.split(r":| — | – ", title, maxsplit=1)[0].strip() or title
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def render_dashboard(data: dict, out_dir: Path) -> str:
    """App shell: a slim bar (TEACH · course tabs · theme), then the selected course. "Genel": performance strip,
    Bugün + calendar, Kavram ağı. A track: its strip, lesson tabs, the lesson in an iframe, notes on the right
    (they open in a side panel). The server marks the active track and its current lesson as selected (first
    open); SHELL_JS then prefers the URL hash, then the learner's last choice (localStorage). Without JS every
    panel shows, stacked, with plain links to the lessons."""
    tracks = data["tracks"]
    by_id = {t["id"]: t for t in tracks}
    active = by_id.get(data["learner"]["active_track"]) or (tracks[0] if tracks else None)
    tab = {t["id"]: tab_key(t["id"]) for t in tracks}
    first = tab[active["id"]] if active else "genel"
    hue = track_hues(tracks)
    entries = [("genel", "Genel", "Genel", False, None)] + [(tab[t["id"]], t["title"], t["title"], t is active, hue[t["id"]])
                                                          for t in tracks]
    buttons, panels, templates = [], [], []
    for key, label, full, is_active, h in entries:
        on = key == first
        dot = f'<i class="hue" style="background:{h}" aria-hidden="true"></i>' if h else ""
        buttons.append(f'<button type="button" role="tab" class="tab" id="tab-{esc(key)}" '
                       f'data-tab="{esc(key)}" aria-controls="panel-{esc(key)}" aria-selected="{"true" if on else "false"}" '
                       f'tabindex="{"0" if on else "-1"}" title="{esc(full + (" · şu anki konu" if is_active else ""))}">'
                       f'{dot}<span class="tl">{esc(short_title(label))}</span></button>')
    gen = data["generated_at"][:16].replace("T", " ")
    days = len(data["learner"]["study_days"])
    panels.append(f'<section class="panel{" on" if first == "genel" else ""}" id="panel-genel" role="tabpanel" '
                  f'aria-labelledby="tab-genel" tabindex="-1">\n'
                  f'<div class="gen"><div class="gen-in">\n{render_overview(data, tracks, tab)}\n'
                  f'<footer><span>güncellendi: {esc(gen)}</span></footer>'
                  "\n</div></div>\n</section>")
    for i, t in enumerate(tracks):
        key = tab[t["id"]]
        body, tpl = render_track_panel(t, i, out_dir, tab)
        templates += tpl
        panels.append(f'<section class="panel{" on" if key == first else ""}" id="panel-{esc(key)}" role="tabpanel" '
                      f'aria-labelledby="tab-{esc(key)}" tabindex="-1">\n{body}\n</section>')
    nav = (f'<header class="bar"><span class="mark">{LOGO}TEACH</span><nav class="tabs" role="tablist" aria-label="Konular" '
           f'data-default="{esc(first)}">' + "".join(buttons) + "</nav>"
           '<button class="theme-btn" type="button" onclick="teachToggleTheme()" title="Açık / koyu tema" aria-label="Açık / koyu tema">◐<span class="tt"> Tema</span></button></header>')
    return ("<!doctype html>\n<html lang=\"tr\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n<title>Pano</title>\n"
            f"<link rel=\"icon\" href=\"{FAVICON}\">\n"
            f"<style>\n{style_tokens()}\n{DASH_CSS}</style>\n<script>{THEME_JS}</script>\n</head>\n<body>\n"
            + nav + "\n" + "\n".join(panels) + "\n" + SHEET + "\n" + "\n".join(templates) +
            f"\n<script>{SHELL_JS}</script>\n</body>\n</html>\n")


def cmd_dashboard(a):
    target = Path(a.out).expanduser().resolve() if a.out else LEARNER / "dashboard.html"
    page = render_dashboard(build_export(), target.parent)
    atomic_write_bytes(target, page.encode("utf-8"))
    print(rel(target))
    if a.open:
        try:
            if sys.platform == "darwin":
                r = subprocess.run(["open", str(target)], capture_output=True).returncode
            elif sys.platform.startswith("win"):
                os.startfile(str(target))  # type: ignore[attr-defined]
                r = 0
            else:
                r = subprocess.run(["xdg-open", str(target)], capture_output=True).returncode
            if r:
                raise OSError(f"exit {r}")
        except (OSError, AttributeError) as e:
            print(f"(couldn't open it automatically: {e}; open the file above in a browser)", file=sys.stderr)


# ── lesson-map: the track's map as one inline <svg class="lmap">, the lesson's nodes in focus ─────────────────
# Styled only through the assets/style.css tokens (with light fallbacks), so it reads the same in a lesson page
# (which links style.css) and on the dashboard. Deterministic; shows titles/statements only, never card text.

LMAP_CSS = (
    ".lmap{display:block;max-width:100%;height:auto;margin:0 auto;font-family:var(--font-prose,system-ui,sans-serif)}"
    ".lmap .box{stroke-width:1}"
    ".lmap .node text{font-size:12px;text-anchor:middle;dominant-baseline:central}"
    ".lmap .lv-new .box{fill:var(--bg,#fafafa);stroke:var(--muted,#6b6b6b);stroke-dasharray:4 3}"
    ".lmap .lv-new text{fill:var(--muted,#6b6b6b)}"
    ".lmap .lv-learn .box{fill:var(--bg,#fafafa);stroke:var(--ink,#1a1a1a)}"
    ".lmap .lv-learn text{fill:var(--ink,#1a1a1a)}"
    ".lmap .lv-kept .box,.lmap .lv-own .box{fill:var(--done-fill,#fff);stroke:var(--border,#cfcfcf);filter:drop-shadow(0 0 4px var(--done-glow,rgba(0,0,0,.12)))}"
    ".lmap .lv-kept text,.lmap .lv-own text{fill:var(--done-ink,#1a1a1a)}"
    ".lmap .pip{fill:none;stroke:var(--muted,#6b6b6b);stroke-width:1}"
    ".lmap .pip.on{fill:var(--ink,#1a1a1a);stroke:var(--ink,#1a1a1a)}"
    ".lmap .badge rect{fill:var(--done-ink,#1a1a1a);stroke:var(--done-fill,#fff);stroke-width:1}"
    ".lmap .node .badge text{font-family:var(--font-ui,monospace);font-size:10px;font-weight:700;fill:var(--done-fill,#fff)}"
    ".lmap .node text.mk{font-family:var(--font-ui,monospace);font-size:10px;text-anchor:end;fill:var(--muted,#6b6b6b)}"
    ".lmap .node text.mk.warn{fill:var(--ink,#1a1a1a);font-weight:700}"
    ".lmap .node.focus .box{stroke:var(--ink,#1a1a1a);stroke-width:1.6;stroke-dasharray:none}"
    ".lmap .node.focus text{font-weight:600}"
    ".lmap .node.dim{opacity:.4}"
    ".lmap .node.next .box{stroke:var(--current,#b88600);stroke-width:2;stroke-dasharray:none;fill:var(--current-soft,rgba(234,179,8,.16))}"
    ".lmap .node.next text{fill:var(--ink,#1a1a1a)}"
    ".lmap rect.glow{fill:var(--current-glow,rgba(234,179,8,.55));opacity:.55;stroke:none;pointer-events:none}"
    ".lmap .edge{fill:none;stroke:var(--ink,#1a1a1a);stroke-width:1.2}"
    ".lmap .edge.path{stroke:var(--muted,#6b6b6b);stroke-width:1}"
    ".lmap .edge.dim{stroke:var(--border,#cfcfcf);stroke-width:1}"
    ".lmap .ah{fill:var(--ink,#1a1a1a)}.lmap .ah.path{fill:var(--muted,#6b6b6b)}.lmap .ah.dim{fill:var(--border,#cfcfcf)}")


def lesson_map_svg(track: str, nodes: list[str], current: str | None = None, t: dict | None = None) -> str:
    """The track map with the lesson's `nodes` in focus (solid ink); the only yellow node is the track's real next
    node, wherever it is. `current` is accepted for old <!-- lesson-map --> comments and ignored. `t` = this
    track's export (refresh passes it so the export is built once)."""
    if t is None:
        track_dir(track)
        if track_map(track) is None:
            die(f"tracks/{track}/map.md not found")
        t = track_export(track)
    known = [n["id"] for n in t["map"]["nodes"]]
    want = list(dict.fromkeys(x.strip() for x in nodes if x.strip()))
    if not want:
        die("--nodes needs at least one node id")
    unknown = [x for x in want if x not in known]
    if unknown:
        die(f"unknown node(s) in {track}: {', '.join(dict.fromkeys(unknown))} (known: {', '.join(known)})")
    nxt = t["next"] if t["next"] in known else ""
    uid = "lm-" + hashlib.sha1(f"{track}|{','.join(want)}|{nxt}".encode()).hexdigest()[:8]
    return render_plan_svg(t, uid, focus=set(want), current=nxt, root_cls="lmap",
                           extra=f"<style>{LMAP_CSS}</style>")


def cmd_lesson_map(a):
    print(lesson_map_svg(a.track, a.nodes.split(","), a.current))


# ── data safety: backup, doctor-data, migrate ────────────────────────────

def data_source_files() -> list[Path]:
    """All files under learner/ and tracks/ (what a backup copies), minus the transient lock."""
    files = []
    for d in (LEARNER, TRACKS):
        if d.is_dir():
            files += [f for f in d.rglob("*") if f.is_file() and f != LOCK]
    return sorted(files)


def do_backup(dest: str | None = None) -> dict:
    """Copy learner/ and tracks/ verbatim to a directory outside the repo; verify file count and bytes."""
    if dest:
        target = Path(dest).expanduser().resolve()
    else:
        stamp = now().strftime("%Y%m%d-%H%M%S")
        target = ROOT.parent / "teach-backups" / f"{ROOT.name}-{stamp}"
        k = 2
        while target.exists():
            target = ROOT.parent / "teach-backups" / f"{ROOT.name}-{stamp}-{k}"
            k += 1
    for src_dir in (LEARNER, TRACKS):
        if target == src_dir.resolve() or src_dir.resolve() in target.parents:
            die(f"backup destination {target} is inside {rel(src_dir)}/; choose a directory outside it")
    if target.exists() and any(target.iterdir()):
        die(f"backup destination {target} already exists and is not empty")
    files = data_source_files()
    for f in files:
        dst = target / f.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
    copied = [f for f in target.rglob("*") if f.is_file()]
    src_bytes = sum(f.stat().st_size for f in files)
    dst_bytes = sum(f.stat().st_size for f in copied)
    if len(copied) != len(files) or src_bytes != dst_bytes:
        die(f"backup verification failed: {len(files)} files / {src_bytes} bytes in source, "
            f"{len(copied)} files / {dst_bytes} bytes in {target}")
    return {"backup": str(target), "files": len(files), "bytes": src_bytes, "verified": True}


def cmd_backup(a):
    out(do_backup(a.dest))


def cmd_doctor_data(a):
    """List unreadable lines; with --fix, back up, then move them verbatim to <file>.quarantine."""
    problems = scan_data()
    res = {"files_scanned": len(data_files()), "unreadable": problems, "contract": scan_contract()}
    for p in problems:
        if p["line"]:
            raw = split_lines((ROOT / p["file"]).read_bytes())[p["line"] - 1]
            p["preview"] = raw.decode("utf-8", errors="replace").rstrip("\r\n")[:120]
    if not problems:
        res["status"] = "all data files read cleanly" + (
            "; some rows break the data contract (schemas/): report to the maintainer, never edit by hand"
            if res["contract"] else ", every row matches the data contract (schemas/)")
        out(res)
        return
    if not a.fix:
        res["next"] = "tools/learn doctor-data --fix  (backs up first, then moves these lines verbatim to <file>.quarantine)"
        out(res)
        return
    if any(p["file"] == rel(FORMAT_FILE) for p in problems):
        die("learner/format.json is unreadable; fix it by hand first (it should be {\"version\": N})")
    res["backup"] = do_backup()["backup"]
    fixed = {}
    for f in data_files():
        lines = split_lines(f.read_bytes())
        bad = [ln for ln in lines if parse_line(ln) is BAD]
        if not bad:
            continue
        # quarantine first (a crash after this leaves a duplicate, never a loss), then rewrite without them
        append_bytes(Path(f"{f}.quarantine"), b"".join(ln if ln.endswith(b"\n") else ln + b"\n" for ln in bad))
        atomic_write_bytes(f, b"".join(ln for ln in lines if parse_line(ln) is not BAD))
        fixed[rel(f)] = {"quarantined_lines": len(bad), "to": rel(Path(f"{f}.quarantine"))}
    if not read_state()[1]:
        append_bytes(Path(f"{STATE}.quarantine"), STATE.read_bytes())
        STATE.unlink()
        fixed[rel(STATE)] = {"quarantined_lines": "whole file", "to": rel(Path(f"{STATE}.quarantine")),
                             "note": "state reset; set the active track again with: tools/learn use <track>"}
    res["fixed"] = fixed
    res["remaining"] = scan_data()
    out(res)


# Migrations: ordered, pure functions over the whole JSONL dataset.
#   data = {"tracks/<t>/cards.jsonl": [row, ...], "learner/moments.jsonl": [...], ...}
# Each entry is (version it migrates TO, name, fn(data) -> data). A function must be idempotent
# (applying it to already-migrated data changes nothing): a crash before the stamp is written re-runs it.
# To add one: append (FORMAT_VERSION + 1, "what-it-does", fn) here and bump FORMAT_VERSION.
MIGRATIONS: list[tuple[int, str, object]] = []


def load_dataset() -> dict[str, list[dict]]:
    return {rel(f): read_jsonl(f, strict=True) for f in data_files()}


def cmd_migrate(a):
    current = format_version()
    if current is None:
        die("learner/format.json is unreadable; fix it by hand first (it should be {\"version\": N})")
    if current > FORMAT_VERSION:
        die(f"learner data is format version {current}, newer than this engine ({FORMAT_VERSION}); "
            "update tools/ instead of migrating")
    pending = [(v, name, fn) for v, name, fn in MIGRATIONS if v > current]
    res = {"format_version": current, "engine_version": FORMAT_VERSION, "pending": [f"{v}: {n}" for v, n, _ in pending]}
    if not pending:
        res["status"] = "up to date"
        out(res)
        return
    bad = [p for p in scan_data() if p["line"]]
    if bad:
        die(f"{len(bad)} unreadable line(s) in the data (first: {bad[0]['file']} line {bad[0]['line']}); "
            "run tools/learn doctor-data --fix before migrating")
    before = load_dataset()
    data = copy.deepcopy(before)
    for v, name, fn in pending:
        data = fn(data)
    if a.dry_run:
        res.update({"dry_run": True, "would_change": sorted(k for k in data if data[k] != before.get(k)),
                    "rows": {k: {"before": len(before.get(k, [])), "after": len(v)} for k, v in data.items()}})
        out(res)
        return
    res["backup"] = do_backup()["backup"]
    changed = sorted(k for k in data if data[k] != before.get(k))
    for k in changed:
        write_jsonl(ROOT / k, data[k])
    target = pending[-1][0]
    atomic_write_bytes(FORMAT_FILE, (json.dumps({"version": target}) + "\n").encode("utf-8"))  # stamp last
    rows, ok = {}, True
    for k, v in data.items():
        n = len(read_jsonl(ROOT / k, strict=True))
        rows[k] = {"before": len(before.get(k, [])), "after": n, "check": "ok" if n == len(v) else f"expected {len(v)}"}
        ok &= n == len(v)
    validation = {t: validate_track(t)[0] for t in all_tracks()}
    res.update({"applied": res.pop("pending"), "format_version": target, "changed_files": changed, "rows": rows,
                "validate_errors": {t: e for t, e in validation.items() if e}, "ok": ok})
    out(res)
    if not ok:
        sys.exit(1)


WRITE_COMMANDS = {"new-track", "use", "add-card", "record", "retire", "task", "moment"}


def writes(a) -> bool:
    """Commands that change learner/ or tracks/: they run under the lock and refuse a newer format stamp."""
    return a.cmd in WRITE_COMMANDS or (a.cmd == "doctor-data" and a.fix) or (a.cmd == "migrate" and not a.dry_run)


EXPORT_FILE = "export.json"
LMAP_BLOCK = re.compile(r'<svg class="lmap"[^>]*>.*?</svg>', re.S)


def write_if_changed(path: Path, data: bytes) -> bool:
    if path.exists() and path.read_bytes() == data:
        return False
    atomic_write_bytes(path, data)
    return True


def refresh() -> dict:
    """Bring every generated view up to date, in order: learner/export.json (the data source) → learner/dashboard.html
    (rendered from it) → each lesson's <svg class="lmap"> (from its <!-- lesson-map: … --> comment; only that block
    is replaced; lessons without the comment are skipped). Unchanged files are not rewritten."""
    data = build_export()
    LEARNER.mkdir(exist_ok=True)
    atomic_write_bytes(LEARNER / EXPORT_FILE, (json.dumps(data, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    write_if_changed(LEARNER / "dashboard.html", render_dashboard(data, LEARNER).encode("utf-8"))
    by_id = {t["id"]: t for t in data["tracks"]}
    updated, problems = [], []
    for t in data["tracks"]:
        for les in t["lessons"]:
            f = ROOT / les["path"]
            text = f.read_text(encoding="utf-8")
            args = lesson_map_args(text)
            if not args or len(LMAP_BLOCK.findall(text)) != 1:
                continue
            try:
                svg = lesson_map_svg(args["track"], args["nodes"].split(","), None, by_id.get(args["track"]))
            except SystemExit as e:  # unknown node / missing map: leave the page as it is, say why
                problems.append(f"{les['path']}: {e}")
                continue
            new = LMAP_BLOCK.sub(lambda _: svg, text, count=1)
            if write_if_changed(f, new.encode("utf-8")):
                updated.append(les["path"])
    return {"export": rel(LEARNER / EXPORT_FILE), "dashboard": rel(LEARNER / "dashboard.html"),
            "lessons_updated": updated, "problems": problems}


def cmd_refresh(a):
    r = refresh()
    if not a.quiet:
        out(r)


def auto_refresh():
    """After a successful write: refresh, silently. Never fails the write: any error is one stderr line. Off with
    TEACH_NO_DASHBOARD=1, or when learner/ doesn't exist."""
    if os.environ.get("TEACH_NO_DASHBOARD") == "1" or not LEARNER.is_dir():
        return
    saved = dict(UNREADABLE)
    try:
        refresh()
    except BaseException as e:  # noqa: BLE001 — the write already succeeded; these are only views
        print(f"(dashboard not refreshed: {type(e).__name__}: {e})", file=sys.stderr)
    finally:
        UNREADABLE.clear()
        UNREADABLE.update(saved)


def main(argv: list[str] | None = None):
    # Windows consoles default to a legacy code page; Turkish text and symbols need UTF-8.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="learn", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="summary for session start")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("new-track", help="scaffold tracks/<track> from the template")
    s.add_argument("track")
    s.add_argument("--title")
    s.set_defaults(fn=cmd_new_track)

    s = sub.add_parser("use", help="set the active track")
    s.add_argument("track")
    s.set_defaults(fn=cmd_use)

    s = sub.add_parser("add-card", help="validate + shuffle + store card(s) from stdin JSON")
    s.add_argument("--track", required=True)
    s.set_defaults(fn=cmd_add_card)

    s = sub.add_parser("due", help="cards due for review (interleaved)")
    s.add_argument("--track")
    s.add_argument("--limit", type=int, default=8)
    s.add_argument("--ahead", type=int, default=0, help="look N days ahead (e.g. 1 = what tomorrow brings)")
    s.add_argument("--today-misses", action="store_true",
                   help="cards answered wrong / 'don't know' today and tasks with 2+ hints today (wrap-up retest)")
    s.set_defaults(fn=cmd_due)

    s = sub.add_parser("record", help="record an answer; grades option cards itself")
    s.add_argument("--card", required=True)
    s.add_argument("--choice", help="A-D, or X for 'I don't know'")
    s.add_argument("--correct", choices=["yes", "partial", "no"], help="for open-answer cards")
    s.add_argument("--confidence", type=int, choices=[1, 2, 3], help="1 guess, 2 unsure, 3 sure; omit if not asked")
    s.add_argument("--dont-know", action="store_true",
                   help="learner chose 'Bilmiyorum': recorded wrong, confidence 1, scheduled like a miss")
    s.add_argument("--misconception", help="m-… id you diagnosed (open answers)")
    s.add_argument("--answer-text", help="learner's own words, for open answers")
    s.add_argument("--session", help="free label, e.g. 2026-10-08-a")
    s.add_argument("--source", choices=["chat", "lesson", "predict"], default="chat",
                   help="lesson = answer pasted from an HTML lesson's quiz; predict = a guess before teaching "
                        "(both diagnostic only: no scheduling, no mastery)")
    s.set_defaults(fn=cmd_record)

    s = sub.add_parser("cards", help="cards of a track (optionally per node) with answers, for building a lesson")
    s.add_argument("--track", required=True)
    s.add_argument("--node", action="append", help="repeatable")
    s.add_argument("--html", action="store_true", help="emit quiz skeletons for assets/components.js")
    s.set_defaults(fn=cmd_cards)

    s = sub.add_parser("retire", help="stop reviewing a card (memorized wording, replaced by a transfer card, flawed)")
    s.add_argument("--card", required=True)
    s.add_argument("--reason", required=True)
    s.set_defaults(fn=cmd_retire)

    s = sub.add_parser("verify-task", help="check a task's tests against a reference solution from stdin (temp copy)")
    s.add_argument("--dir", required=True, help="tracks/<t>/tasks/NN-slug")
    s.add_argument("--solution", default="solution.py")
    s.set_defaults(fn=cmd_verify_task)

    s = sub.add_parser("task", help="record a task event")
    s.add_argument("--track", required=True)
    s.add_argument("--task", required=True)
    s.add_argument("--node", required=True)
    s.add_argument("--status", required=True)
    s.add_argument("--hints", type=int, default=0)
    s.add_argument("--note", default="")
    s.set_defaults(fn=cmd_task)

    s = sub.add_parser("progress", help="per-node mastery levels + recurring misconceptions")
    s.add_argument("--track")
    s.set_defaults(fn=cmd_progress)

    s = sub.add_parser("map", help="parse a track's map.md: node table + mermaid graph (+ problems)")
    s.add_argument("--track", required=True)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_map)

    s = sub.add_parser("moment", help="log an engagement moment so pacing knows about it")
    s.add_argument("--kind", required=True, help="recap|cheatsheet|teaser|value|milestone")
    s.add_argument("--note", default="")
    s.set_defaults(fn=cmd_moment)

    s = sub.add_parser("journey", help="then-vs-now evidence for recaps and milestones")
    s.set_defaults(fn=cmd_journey)

    s = sub.add_parser("signals", help="how this learner learns: calibration, question types, trend, hints")
    s.set_defaults(fn=cmd_signals)

    s = sub.add_parser("validate", help="check tracks against the standard")
    s.add_argument("--track")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("export", help="read-only JSON of everything a UI may show (no answers, no card text)")
    s.add_argument("--json", action="store_true", help="JSON output (the only format)")
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("dashboard", help="write a self-contained read-only HTML page (default learner/dashboard.html)")
    s.add_argument("--out", help="write here instead of learner/dashboard.html")
    s.add_argument("--open", action="store_true", help="open it in the default browser")
    s.set_defaults(fn=cmd_dashboard)

    s = sub.add_parser("refresh", help="regenerate learner/export.json, learner/dashboard.html and every lesson's mini map")
    s.add_argument("--quiet", action="store_true", help="print nothing")
    s.set_defaults(fn=cmd_refresh)

    s = sub.add_parser("lesson-map", help="print an inline <svg class=\"lmap\"> of the track map, a lesson's nodes in focus")
    s.add_argument("--track", required=True)
    s.add_argument("--nodes", required=True, help="comma-separated node ids the lesson covers")
    s.add_argument("--current", help="ignored (kept so old lesson-map comments still work); the glow is the track's next node")
    s.set_defaults(fn=cmd_lesson_map)

    s = sub.add_parser("doctor-data", help="list unreadable lines in learner/ and tracks/ data; --fix quarantines them")
    s.add_argument("--fix", action="store_true", help="back up, then move bad lines verbatim to <file>.quarantine")
    s.set_defaults(fn=cmd_doctor_data)

    s = sub.add_parser("backup", help="copy learner/ and tracks/ to ../teach-backups/<repo>-<timestamp>/")
    s.add_argument("--dest", help="exact destination directory (must not exist or be empty)")
    s.set_defaults(fn=cmd_backup)

    s = sub.add_parser("migrate", help="bring learner data up to this engine's format (backs up first)")
    s.add_argument("--dry-run", action="store_true", help="show what would change; write nothing")
    s.set_defaults(fn=cmd_migrate)

    a = p.parse_args(argv)
    if writes(a):
        with write_lock():
            if a.cmd != "migrate":
                ensure_format_writable()
            a.fn(a)
        auto_refresh()
    else:
        a.fn(a)
    if UNREADABLE and a.cmd not in ("status", "doctor-data"):
        for f, ns in sorted(UNREADABLE.items()):
            print(f"DATA WARNING: {f} line(s) {ns[:10]} unreadable and skipped → run: tools/learn doctor-data",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
