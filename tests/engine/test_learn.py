"""Golden tests for tools/learn.py (the deterministic engine).

Run from the repo root:  python3 -m unittest discover -s tests/engine -v

Every test builds a throwaway root in a temp dir (tracks scaffolded from tools/track-template, a fake
learner/) and points the engine at it with TEACH_ROOT. TEACH_TODAY pins "today" (test seam in today()).
The real learner/ and tracks/ are never touched: a fingerprint of them is checked before and after the run.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEARN = REPO / "tools" / "learn.py"
DAY0 = "2026-10-20"


def day(n: int) -> str:
    return (dt.date.fromisoformat(DAY0) + dt.timedelta(days=n)).isoformat()


def fingerprint() -> str:
    h = hashlib.sha256()
    for d in ("learner", "tracks"):
        base = REPO / d
        if base.is_dir():
            for f in sorted(base.rglob("*")):
                if f.is_file():
                    h.update(str(f.relative_to(REPO)).encode())
                    h.update(f.read_bytes())
    return h.hexdigest()


_REAL = None


def setUpModule():
    global _REAL
    _REAL = fingerprint()


def tearDownModule():
    assert fingerprint() == _REAL, "the real learner/ or tracks/ changed during the tests"


def load_engine(root: Path):
    """Import learn.py as a fresh module bound to `root` (for in-process tests)."""
    os.environ["TEACH_ROOT"] = str(root)
    try:
        spec = importlib.util.spec_from_file_location(f"learn_{id(root)}", LEARN)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        del os.environ["TEACH_ROOT"]
    assert mod.ROOT == root.resolve()
    return mod


MCQ = {"node": "n1", "type": "mcq", "prompt": "Which is right?", "explanation": "Because.",
       "options": [{"text": "right one", "correct": True},
                   {"text": "wrong one", "misconception": "m-wrong"},
                   {"text": "other wrong", "misconception": "m-other"}]}
RECALL = {"node": "n2", "type": "recall", "prompt": "Recall it.", "explanation": "x", "answer": "the answer"}


class EngineCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.root = self.base / "repo"
        (self.root / "learner").mkdir(parents=True)
        (self.root / "tracks").mkdir()
        (self.root / "learner" / "profile.md").write_text("# Profile\n", encoding="utf-8")
        self.assertNotEqual(self.root.resolve(), REPO.resolve())

    def tearDown(self):
        self._tmp.cleanup()

    def run_learn(self, *args, stdin: str | None = None, today: str = DAY0, check: bool = True, **env):
        e = dict(os.environ, TEACH_ROOT=str(self.root), TEACH_TODAY=today, PYTHONIOENCODING="utf-8", TEACH_NO_DASHBOARD="1")
        e.update({k: str(v) for k, v in env.items()})
        r = subprocess.run([sys.executable, str(LEARN), *args], input=stdin, capture_output=True, text=True,
                           encoding="utf-8", env=e)
        if check and r.returncode != 0:
            self.fail(f"learn {' '.join(args)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        return r

    def json_of(self, *args, **kw):
        return json.loads(self.run_learn(*args, **kw).stdout)

    def new_track(self, name="demo"):
        self.run_learn("new-track", name)
        return self.root / "tracks" / name

    def add(self, card, track="demo", **kw):
        return self.json_of("add-card", "--track", track, stdin=json.dumps(card), **kw)

    def correct_letter(self, card_id, track="demo"):
        for c in self.read_rows(self.root / "tracks" / track / "cards.jsonl"):
            if c["id"] == card_id:
                return "ABCD"[next(i for i, o in enumerate(c["options"]) if o.get("correct"))]

    @staticmethod
    def read_rows(path: Path) -> list[dict]:
        return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


# ── scheduling ────────────────────────────────────────────────────────────

class TestSchedule(EngineCase):
    # (reps, interval, quality) -> (new interval, new reps, new ease, lapses, due offset in days)
    # Captured from the engine before the Phase-0 changes: the behaviour must not drift.
    GOLDEN = [
        ((0, 0, 1), (1, 0, 1.96, 1, 1)), ((0, 0, 3), (1, 1, 2.36, 0, 1)),
        ((0, 0, 4), (1, 1, 2.5, 0, 1)), ((0, 0, 5), (1, 1, 2.6, 0, 1)),
        ((1, 1, 1), (1, 0, 1.96, 1, 1)), ((1, 1, 3), (2, 2, 2.36, 0, 2)),
        ((1, 1, 4), (3, 2, 2.5, 0, 3)), ((1, 1, 5), (3, 2, 2.6, 0, 3)),
        ((1, 10, 3), (3, 2, 2.36, 0, 3)),
        ((2, 3, 3), (4, 3, 2.36, 0, 4)), ((2, 3, 4), (8, 3, 2.5, 0, 8)), ((2, 3, 5), (8, 3, 2.6, 0, 8)),
        ((2, 10, 1), (1, 0, 1.96, 1, 1)), ((2, 10, 3), (11, 3, 2.36, 0, 11)),
        ((2, 10, 4), (25, 3, 2.5, 0, 25)), ((5, 10, 5), (25, 6, 2.6, 0, 25)),
        ((2, 0, 4), (0, 3, 2.5, 0, 0)),  # quirk kept as-is: unreachable in practice (reps>=2 implies interval>=1)
    ]

    def test_schedule_table(self):
        L = load_engine(self.root)
        os.environ["TEACH_TODAY"] = DAY0
        try:
            for (reps, interval, q), (n_int, n_reps, ease, lapses, due) in self.GOLDEN:
                s = L.schedule({"reps": reps, "interval": interval, "ease": 2.5, "lapses": 0}, q)
                self.assertEqual((s["interval"], s["reps"], s["ease"], s["lapses"], s["due"], s["last"]),
                                 (n_int, n_reps, ease, lapses, day(due), DAY0), (reps, interval, q))
            # ease floor
            self.assertEqual(L.schedule({"reps": 0, "interval": 1, "ease": 1.3}, 1)["ease"], 1.3)
        finally:
            del os.environ["TEACH_TODAY"]

    def test_quality(self):
        L = load_engine(self.root)
        self.assertEqual([L.quality("no", c) for c in (1, 2, 3)], [1, 1, 1])
        self.assertEqual([L.quality("partial", c) for c in (1, 2, 3)], [3, 3, 3])
        self.assertEqual([L.quality("yes", c) for c in (1, 2, 3)], [3, 4, 5])

    def test_today_seam(self):
        L = load_engine(self.root)
        os.environ["TEACH_TODAY"] = "2030-01-02"
        try:
            self.assertEqual(L.today(), dt.date(2030, 1, 2))
            self.assertTrue(L.now_iso().startswith("2030-01-02T"))
        finally:
            del os.environ["TEACH_TODAY"]


# ── record ────────────────────────────────────────────────────────────────

class TestRecord(EngineCase):
    def test_record_row_shape_and_srs(self):
        self.new_track()
        cid = self.add(MCQ)["added"][0]["id"]
        self.assertEqual(cid, "d-001")
        res = self.json_of("record", "--card", cid, "--choice", self.correct_letter(cid), "--confidence", "3")
        self.assertEqual(res["correct"], "yes")
        self.assertEqual(res["next_due"], day(1))
        rows = self.read_rows(self.root / "tracks/demo/attempts.jsonl")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(list(row), ["ts", "kind", "card", "node", "type", "correct", "confidence",
                                     "misconception", "delayed", "session", "choice"])
        self.assertEqual({k: row[k] for k in list(row)[1:]},
                         {"kind": "card", "card": cid, "node": "n1", "type": "mcq", "correct": "yes",
                          "confidence": 3, "misconception": None, "delayed": False, "session": None,
                          "choice": self.correct_letter(cid)})
        ts = dt.datetime.fromisoformat(row["ts"])
        self.assertIsNotNone(ts.tzinfo, "new rows carry a UTC offset")
        self.assertEqual(row["ts"][:10], DAY0)
        card = self.read_rows(self.root / "tracks/demo/cards.jsonl")[0]
        self.assertEqual(card["srs"], {"due": day(1), "interval": 1, "ease": 2.6, "reps": 1, "lapses": 0, "last": DAY0})

    def test_wrong_choice_logs_misconception(self):
        self.new_track()
        cid = self.add(MCQ)["added"][0]["id"]
        wrong = next(L for L in "ABC" if L != self.correct_letter(cid))
        res = self.json_of("record", "--card", cid, "--choice", wrong, "--confidence", "3")
        self.assertEqual(res["correct"], "no")
        self.assertIn(res["misconception"], {"m-wrong", "m-other"})
        self.assertIn("flag", res)

    def test_lesson_source_is_not_scheduled(self):
        self.new_track()
        cid = self.add(MCQ)["added"][0]["id"]
        before = (self.root / "tracks/demo/cards.jsonl").read_bytes()
        self.json_of("record", "--card", cid, "--choice", "A", "--source", "lesson")
        self.assertEqual((self.root / "tracks/demo/cards.jsonl").read_bytes(), before)
        self.assertEqual(self.read_rows(self.root / "tracks/demo/attempts.jsonl")[0]["source"], "lesson")

    def test_attempt_is_appended_before_card_rewrite(self):
        self.new_track()
        cid = self.add(RECALL)["added"][0]["id"]
        cards_before = (self.root / "tracks/demo/cards.jsonl").read_bytes()
        L = load_engine(self.root)

        def boom(path, rows):
            raise RuntimeError("crash while rewriting cards")
        L.write_jsonl = boom
        with self.assertRaises(RuntimeError), contextlib.redirect_stdout(io.StringIO()):
            L.main(["record", "--card", cid, "--correct", "yes"])
        # the evidence survived; the schedule did not move
        self.assertEqual(len(self.read_rows(self.root / "tracks/demo/attempts.jsonl")), 1)
        self.assertEqual((self.root / "tracks/demo/cards.jsonl").read_bytes(), cards_before)
        self.assertFalse((self.root / "learner/.lock").exists(), "lock released after a crash")


# ── progress ladder (as it currently behaves) ─────────────────────────────

class TestProgress(EngineCase):
    def level(self, node, today=DAY0):
        return self.json_of("progress", today=today)["demo"]["nodes"][node]["level"]

    def test_ladder(self):
        # old rules (attempts before MASTERY_RULES_SINCE = DAY0): an MCQ delayed correct is enough for retained
        self.new_track()
        cid = self.add(MCQ, today=day(-3))["added"][0]["id"]
        self.add(RECALL, today=day(-3))
        self.assertEqual(self.level("n1", day(-3)), "new")
        self.run_learn("record", "--card", cid, "--choice", self.correct_letter(cid), today=day(-3))
        self.assertEqual(self.level("n1", day(-3)), "checked")
        self.run_learn("record", "--card", cid, "--choice", self.correct_letter(cid), today=day(-2))
        self.assertEqual(self.level("n1", day(-2)), "retained")
        self.run_learn("task", "--track", "demo", "--task", "01-x", "--node", "n1", "--status", "passed", today=day(-2))
        self.assertEqual(self.level("n1", day(-2)), "owned")
        self.assertEqual(self.level("n2", day(-2)), "new")

    def test_learning_and_struggling(self):
        self.new_track()
        rid = self.add(RECALL)["added"][0]["id"]
        self.run_learn("record", "--card", rid, "--correct", "no")
        self.assertEqual(self.level("n2"), "struggling")
        self.run_learn("record", "--card", rid, "--correct", "partial")
        self.assertEqual(self.level("n2"), "learning")


# ── corrupt lines ─────────────────────────────────────────────────────────

class TestCorruptData(EngineCase):
    def corrupt(self):
        self.new_track()
        cid = self.add(MCQ)["added"][0]["id"]
        self.add(RECALL)
        cards = self.root / "tracks/demo/cards.jsonl"
        good = cards.read_bytes()
        bad = [b'{"id": "half-written", "node": \n', b"\xff\xfe not utf-8\n", b"[1, 2, 3]\n"]
        cards.write_bytes(good[: good.index(b"\n") + 1] + bad[0] + good[good.index(b"\n") + 1:] + bad[1] + bad[2])
        return cid, cards, good, bad

    def test_status_warns_and_still_prints(self):
        self.corrupt()
        r = self.run_learn("status")
        self.assertIn("DATA WARNING: tracks/demo/cards.jsonl line 2 unreadable → run: tools/learn doctor-data", r.stdout)
        self.assertIn("DATA WARNING: tracks/demo/cards.jsonl line 4 unreadable", r.stdout)
        self.assertIn("DATA WARNING: tracks/demo/cards.jsonl line 5 unreadable", r.stdout)
        self.assertIn("- track demo (ACTIVE): 2 cards", r.stdout)
        self.assertLess(r.stdout.index("DATA WARNING"), r.stdout.index("- track demo"))

    def test_read_commands_skip_and_warn(self):
        self.corrupt()
        for args in (["progress"], ["due"], ["cards", "--track", "demo"]):
            r = self.run_learn(*args)
            json.loads(r.stdout)
            self.assertIn("DATA WARNING: tracks/demo/cards.jsonl line(s) [2, 4, 5]", r.stderr, args)
        for args in (["signals"], ["journey"]):  # read attempts first; nothing recorded yet → unaffected
            json.loads(self.run_learn(*args).stdout)
        r = self.run_learn("validate", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("cards.jsonl line 2 unreadable", r.stdout)

    def test_rewrite_commands_refuse(self):
        cid, cards, _, _ = self.corrupt()
        before_cards, attempts = cards.read_bytes(), self.root / "tracks/demo/attempts.jsonl"
        before_att = attempts.read_bytes()
        for args, stdin in ((["add-card", "--track", "demo"], json.dumps(RECALL)),
                            (["record", "--card", cid, "--choice", "A"], None),
                            (["retire", "--card", cid, "--reason", "x"], None)):
            r = self.run_learn(*args, stdin=stdin, check=False)
            self.assertNotEqual(r.returncode, 0, args)
            self.assertIn("refusing to rewrite", r.stderr)
            self.assertIn("doctor-data", r.stderr)
        self.assertEqual(cards.read_bytes(), before_cards)
        self.assertEqual(attempts.read_bytes(), before_att, "record refused before appending anything")
        # append-only writes still work
        self.run_learn("task", "--track", "demo", "--task", "01", "--node", "n1", "--status", "started")
        self.assertEqual(len(self.read_rows(attempts)), 1)

    def test_doctor_data_fix_quarantines_without_losing_bytes(self):
        _, cards, _, bad = self.corrupt()
        original = cards.read_bytes()
        listed = self.json_of("doctor-data")
        self.assertEqual([(p["file"], p["line"]) for p in listed["unreadable"]],
                         [("tracks/demo/cards.jsonl", 2), ("tracks/demo/cards.jsonl", 4), ("tracks/demo/cards.jsonl", 5)])
        self.assertEqual(cards.read_bytes(), original, "doctor-data without --fix is read-only")
        fixed = self.json_of("doctor-data", "--fix")
        self.assertTrue(Path(fixed["backup"]).is_dir())
        self.assertFalse(Path(fixed["backup"]).is_relative_to(self.root))
        self.assertEqual((Path(fixed["backup"]) / "tracks/demo/cards.jsonl").read_bytes(), original)
        quarantine = Path(f"{cards}.quarantine").read_bytes()
        self.assertEqual(quarantine, b"".join(bad))
        kept = cards.read_bytes()
        self.assertEqual(sorted((kept + quarantine).splitlines(keepends=True)),
                         sorted(original.splitlines(keepends=True)), "every byte is either kept or quarantined")
        self.assertEqual(fixed["remaining"], [])
        self.assertNotIn("DATA WARNING", self.run_learn("status").stdout)
        self.add(RECALL)  # rewrites work again

    def test_unterminated_last_line_is_not_glued_onto(self):
        self.new_track()
        att = self.root / "tracks/demo/attempts.jsonl"
        att.write_bytes(b'{"ts": "2026-10-19T10:00:00", "kind": "task", "task": "t", "node": "n1", "status": "started"}')
        self.run_learn("task", "--track", "demo", "--task", "t", "--node", "n1", "--status", "passed")
        self.assertEqual(len(self.read_rows(att)), 2)


# ── atomic writes and the lock ────────────────────────────────────────────

class TestAtomicAndLock(EngineCase):
    def test_state_write_is_atomic(self):
        L = load_engine(self.root)
        L.save_state({"active_track": "a"})
        self.assertEqual(json.loads((self.root / "learner/state.json").read_text()), {"active_track": "a"})
        real_replace = os.replace

        def failing_replace(src, dst):
            raise OSError("disk full")
        L.os.replace = failing_replace
        try:
            with self.assertRaises(OSError):
                L.save_state({"active_track": "b"})
        finally:
            L.os.replace = real_replace
        self.assertEqual(json.loads((self.root / "learner/state.json").read_text()), {"active_track": "a"})
        self.assertEqual([p.name for p in (self.root / "learner").iterdir() if p.name.endswith(".tmp")], [])

    def test_write_jsonl_leaves_no_tmp(self):
        self.new_track()
        self.add(RECALL)
        self.assertEqual([p.name for p in (self.root / "tracks/demo").iterdir() if "tmp" in p.name], [])

    def test_live_lock_blocks_writes(self):
        self.new_track()
        cid = self.add(RECALL)["added"][0]["id"]
        lock = self.root / "learner/.lock"
        lock.write_text("someone else")
        r = self.run_learn("record", "--card", cid, "--correct", "yes", check=False, TEACH_LOCK_WAIT=0.3)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("learner/.lock", r.stderr)
        self.assertEqual(self.read_rows(self.root / "tracks/demo/attempts.jsonl"), [])
        self.assertEqual(lock.read_text(), "someone else", "a live lock is not stolen")
        self.run_learn("status")  # reads don't need the lock

    def test_stale_lock_is_taken_over_and_released(self):
        self.new_track()
        cid = self.add(RECALL)["added"][0]["id"]
        lock = self.root / "learner/.lock"
        lock.write_text("crashed")
        old = time.time() - 60
        os.utime(lock, (old, old))
        self.run_learn("record", "--card", cid, "--correct", "yes", TEACH_LOCK_WAIT=0.3)
        self.assertFalse(lock.exists())

    def test_concurrent_writers_lose_nothing(self):
        self.new_track()
        e = dict(os.environ, TEACH_ROOT=str(self.root), TEACH_TODAY=DAY0)
        procs = [subprocess.Popen([sys.executable, str(LEARN), "moment", "--kind", "value", "--note", str(i)],
                                  env=e, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) for i in range(6)]
        for p in procs:
            _, err = p.communicate()
            self.assertEqual(p.returncode, 0, err)
        rows = self.read_rows(self.root / "learner/moments.jsonl")
        self.assertEqual(sorted(r["note"] for r in rows), [str(i) for i in range(6)])


# ── backup ────────────────────────────────────────────────────────────────

class TestBackup(EngineCase):
    def test_backup_counts(self):
        self.new_track()
        self.add(MCQ)
        (self.root / "tracks/demo/lessons").mkdir()
        (self.root / "tracks/demo/lessons/0001.html").write_text("<p>x</p>")
        src = [f for d in ("learner", "tracks") for f in (self.root / d).rglob("*") if f.is_file()]
        res = self.json_of("backup")
        dest = Path(res["backup"])
        self.assertEqual(dest.parent, self.base / "teach-backups")
        self.assertTrue(dest.name.startswith("repo-"))
        self.assertEqual(res["files"], len(src))
        self.assertTrue(res["verified"])
        for f in src:
            self.assertEqual((dest / f.relative_to(self.root)).read_bytes(), f.read_bytes())

    def test_backup_dest_and_refusals(self):
        self.new_track()
        res = self.json_of("backup", "--dest", str(self.base / "mine"))
        self.assertEqual(Path(res["backup"]), self.base / "mine")
        r = self.run_learn("backup", "--dest", str(self.base / "mine"), check=False)
        self.assertIn("not empty", r.stderr)
        r = self.run_learn("backup", "--dest", str(self.root / "learner" / "bk"), check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.root / "learner" / "bk").exists())


# ── format stamp and migrate ──────────────────────────────────────────────

class TestMigrate(EngineCase):
    def test_up_to_date_writes_nothing(self):
        self.new_track()
        self.add(MCQ)
        for args in (["migrate", "--dry-run"], ["migrate"]):
            res = self.json_of(*args)
            self.assertEqual(res["status"], "up to date")
        for args in (["status"], ["progress"], ["validate"], ["due"]):
            self.run_learn(*args)
        self.assertFalse((self.root / "learner/format.json").exists(), "reads never create the stamp")
        self.assertFalse((self.base / "teach-backups").exists())

    def run_main(self, L, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            L.main(list(argv))
        return json.loads(buf.getvalue())

    def test_migration_framework_is_idempotent(self):
        self.new_track()
        self.add(MCQ)
        self.add(RECALL)
        L = load_engine(self.root)

        def add_flag(data):
            for k, rows in data.items():
                if k.endswith("cards.jsonl"):
                    for r in rows:
                        r.setdefault("flag", "v2")
            return data
        L.FORMAT_VERSION = 2
        L.MIGRATIONS = [(2, "add-flag", add_flag)]
        cards = self.root / "tracks/demo/cards.jsonl"
        before = cards.read_bytes()
        dry = self.run_main(L, "migrate", "--dry-run")
        self.assertEqual(dry["would_change"], ["tracks/demo/cards.jsonl"])
        self.assertEqual(cards.read_bytes(), before)
        self.assertFalse((self.root / "learner/format.json").exists())

        res = self.run_main(L, "migrate")
        self.assertTrue(res["ok"])
        self.assertEqual(res["format_version"], 2)
        self.assertEqual(res["rows"]["tracks/demo/cards.jsonl"], {"before": 2, "after": 2, "check": "ok"})
        self.assertTrue(Path(res["backup"]).is_dir())
        self.assertEqual(json.loads((self.root / "learner/format.json").read_text()), {"version": 2})
        self.assertTrue(all(c["flag"] == "v2" for c in self.read_rows(cards)))
        snapshot = {f: f.read_bytes() for f in self.root.rglob("*") if f.is_file()}

        again = self.run_main(L, "migrate")
        self.assertEqual(again["status"], "up to date")
        self.assertEqual({f: f.read_bytes() for f in self.root.rglob("*") if f.is_file()}, snapshot)
        # the function itself is idempotent too
        data = L.load_dataset()
        self.assertEqual(add_flag(json.loads(json.dumps(data))), data)

    def test_newer_stamp_refuses_writes(self):
        self.new_track()
        cid = self.add(RECALL)["added"][0]["id"]
        (self.root / "learner/format.json").write_text('{"version": 99}')
        cards = (self.root / "tracks/demo/cards.jsonl").read_bytes()
        for args in (["migrate"], ["migrate", "--dry-run"], ["record", "--card", cid, "--correct", "yes"],
                     ["use", "demo"], ["moment", "--kind", "recap"]):
            r = self.run_learn(*args, check=False)
            self.assertNotEqual(r.returncode, 0, args)
            self.assertIn("newer", r.stderr)
        self.assertEqual((self.root / "tracks/demo/cards.jsonl").read_bytes(), cards)
        self.assertEqual(self.read_rows(self.root / "tracks/demo/attempts.jsonl"), [])
        r = self.run_learn("status")
        self.assertIn("learner/format.json is version 99", r.stdout)
        self.run_learn("progress")


# ── timestamps ────────────────────────────────────────────────────────────

class TestTimestamps(EngineCase):
    def test_new_rows_are_tz_aware(self):
        self.new_track()
        self.run_learn("task", "--track", "demo", "--task", "t", "--node", "n1", "--status", "started")
        self.run_learn("moment", "--kind", "recap")
        for f in ("tracks/demo/attempts.jsonl", "learner/moments.jsonl"):
            ts = self.read_rows(self.root / f)[0]["ts"]
            self.assertIsNotNone(dt.datetime.fromisoformat(ts).tzinfo, f)

    def test_naive_and_aware_rows_mix(self):
        self.new_track()
        cid = self.add(RECALL)["added"][0]["id"]
        att = self.root / "tracks/demo/attempts.jsonl"
        old = {"ts": f"{day(-2)}T10:00:00", "kind": "card", "card": cid, "node": "n2", "type": "recall",
               "correct": "no", "confidence": 2, "misconception": None, "delayed": False, "session": None}
        att.write_text(json.dumps(old) + "\n", encoding="utf-8")
        self.run_learn("record", "--card", cid, "--correct", "yes", today=day(-1))
        self.run_learn("record", "--card", cid, "--correct", "yes")
        rows = self.read_rows(att)
        self.assertIsNone(dt.datetime.fromisoformat(rows[0]["ts"]).tzinfo)
        self.assertIsNotNone(dt.datetime.fromisoformat(rows[2]["ts"]).tzinfo)
        j = self.json_of("journey")
        self.assertEqual((j["started"], j["study_days"], j["current_streak"]), (day(-2), 3, 3))
        self.assertEqual((j["accuracy_first_10"], j["answers"]), (0.67, 3))
        self.assertEqual(self.json_of("signals")["answers"], 3)
        self.assertIn("- track demo", self.run_learn("status").stdout)
        L = load_engine(self.root)
        order = [r["ts"] for r in L.all_attempts()]
        self.assertEqual(order, [r["ts"] for r in rows])
        self.assertEqual(L.parse_ts(f"{DAY0}T10:00:00").tzinfo is not None, True)
        self.assertEqual(L.ts_day("2026-10-20T23:30:00"), "2026-10-20")


# ── card ids across tracks ────────────────────────────────────────────────

class TestCrossTrackIds(EngineCase):
    def test_auto_and_explicit_ids_are_unique_across_tracks(self):
        self.new_track("game-theory")
        self.new_track("graph-theory")  # same prefix "gt"
        a = self.add(RECALL, track="game-theory")["added"][0]["id"]
        b = self.add(RECALL, track="graph-theory")["added"][0]["id"]
        self.assertEqual(a, "gt-001")
        self.assertNotEqual(a, b)
        res = self.add(dict(RECALL, id="gt-001"), track="graph-theory")
        new = res["added"][0]["id"]
        self.assertNotIn(new, (a, b))
        self.assertEqual(res["renamed_ids"], {"gt-001": new})
        # same-track explicit duplicate still refuses (unchanged behaviour)
        r = self.run_learn("add-card", "--track", "game-theory", stdin=json.dumps(dict(RECALL, id="gt-001")), check=False)
        self.assertIn("already exists", r.stderr)
        self.assertEqual(self.json_of("validate")["game-theory"]["errors"], [])

    def test_validate_reports_existing_cross_track_duplicates(self):
        self.new_track("alpha")
        self.new_track("beta")
        self.add(dict(RECALL, id="x-001"), track="alpha")
        # an existing duplicate (from before this check) is reported, never renamed
        row = self.read_rows(self.root / "tracks/alpha/cards.jsonl")[0]
        row["track"] = "beta"
        (self.root / "tracks/beta/cards.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        r = self.run_learn("validate", check=False)
        self.assertEqual(r.returncode, 1)
        rep = json.loads(r.stdout)
        for t in ("alpha", "beta"):
            self.assertIn("x-001: duplicate id across tracks (alpha, beta)", rep[t]["errors"])
        self.assertEqual(self.run_learn("validate", "--track", "beta").returncode, 0)
        self.assertEqual(self.read_rows(self.root / "tracks/beta/cards.jsonl")[0]["id"], "x-001")


# ── Phase 1: record flags ─────────────────────────────────────────────────

MCQ4 = dict(MCQ, options=MCQ["options"] + [{"text": "fourth", "misconception": "m-fourth"}])
MCQ2 = dict(MCQ, options=MCQ["options"][:2])


class TestRecordFlags(EngineCase):
    def card(self, cid):
        return next(c for c in self.read_rows(self.root / "tracks/demo/cards.jsonl") if c["id"] == cid)

    def test_confidence_optional_is_null_and_schedules_like_unsure(self):
        self.new_track()
        a = self.add(RECALL)["added"][0]["id"]
        b = self.add(RECALL)["added"][0]["id"]
        self.assertIsNone(self.json_of("record", "--card", a, "--correct", "yes")["confidence"])
        self.json_of("record", "--card", b, "--correct", "yes", "--confidence", "2")
        rows = self.read_rows(self.root / "tracks/demo/attempts.jsonl")
        self.assertEqual([r["confidence"] for r in rows], [None, 2])
        self.assertEqual(self.card(a)["srs"], self.card(b)["srs"])
        cal = self.json_of("signals")["calibration"]
        self.assertEqual(cal["unsure"]["n"], 1, "null rows are not counted in calibration")
        self.assertEqual(cal["guessed"]["n"] + cal["sure"]["n"], 0)

    def test_dont_know(self):
        self.new_track()
        mcq = self.add(MCQ4)["added"][0]["id"]
        rec = self.add(RECALL)["added"][0]["id"]
        res = self.json_of("record", "--card", mcq, "--dont-know", "--confidence", "3")
        self.assertEqual((res["correct"], res["confidence"], res["chosen"]), ("no", 1, "dont-know"))
        self.assertIn("correct_option", res)
        self.json_of("record", "--card", rec, "--dont-know")
        for row in self.read_rows(self.root / "tracks/demo/attempts.jsonl"):
            self.assertEqual((row["correct"], row["confidence"], row["choice"], row["dont_know"]), ("no", 1, None, True))
        for cid in (mcq, rec):
            self.assertEqual(self.card(cid)["srs"]["lapses"], 1, "scheduled like a wrong answer")
        for extra in (["--choice", "A"], ["--correct", "no"]):
            r = self.run_learn("record", "--card", mcq, "--dont-know", *extra, check=False)
            self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.json_of("signals")["dont_know_rate"], 1.0)

    def test_option_counts(self):
        self.new_track()
        for card in (MCQ2, MCQ, MCQ4):
            cid = self.add(card)["added"][0]["id"]
            self.assertEqual(len(self.card(cid)["options"]), len(card["options"]))
        r = self.run_learn("add-card", "--track", "demo", stdin=json.dumps(dict(MCQ, options=MCQ["options"][:1])), check=False)
        self.assertIn("needs 2-4 options", r.stderr)
        self.assertEqual(self.json_of("validate")["demo"]["errors"], [])

    def test_never_asked_card_waits_for_its_node(self):
        self.new_track()
        a = self.add(MCQ, today=day(-3))["added"][0]["id"]
        probe = self.add(dict(MCQ, node="n2"), today=day(-3))["added"][0]["id"]
        self.run_learn("record", "--card", a, "--choice", self.correct_letter(a), today=day(-3))
        variant = self.add(dict(MCQ, prompt="Which variant?"), today=day(-2))["added"][0]["id"]
        same_day = self.add(dict(MCQ, prompt="Which today?"))["added"][0]["id"]
        ids = [c["id"] for c in load_engine(self.root).due_cards("demo")]
        self.assertIn(variant, ids, "a never-asked card on a node already worked on comes due from the next day")
        self.assertNotIn(probe, ids, "a probe for an untouched node stays out")
        self.assertNotIn(same_day, ids, "a card written today is asked in-session, not listed as due")

    def test_one_card_per_node_and_siblings_move_on(self):
        self.new_track()
        ids = [self.add(dict(MCQ, prompt=f"Q{k}?"), today=day(-5))["added"][0]["id"] for k in range(3)]
        for cid in ids:
            self.run_learn("record", "--card", cid, "--choice", self.correct_letter(cid), today=day(-5))
        due = self.json_of("due", "--limit", "10")
        self.assertEqual((due["due_total"], due["due_nodes"], len(due["cards"])), (3, 1, 1), "one card per node")
        first = due["cards"][0]["id"]
        self.run_learn("record", "--card", first, "--choice", self.correct_letter(first))
        self.assertEqual(self.json_of("due")["due_total"], 0, "a correct answer moves the node's other due cards on")
        others = [c for c in self.read_rows(self.root / "tracks/demo/cards.jsonl") if c["id"] != first]
        self.assertTrue(all(c["srs"]["due"] > DAY0 for c in others))
        self.assertTrue(all(c["srs"]["reps"] == 1 for c in others), "no evidence is invented for them")

    def test_predict_source_is_diagnostic_only(self):
        self.new_track()
        cid = self.add(MCQ)["added"][0]["id"]
        cards = self.root / "tracks/demo/cards.jsonl"
        before = cards.read_bytes()
        wrong = next(L for L in "ABC" if L != self.correct_letter(cid))
        res = self.json_of("record", "--card", cid, "--choice", wrong, "--source", "predict", "--confidence", "3")
        self.assertIn("prediction", res["note"])
        self.assertEqual(cards.read_bytes(), before, "a prediction never reschedules (card stays new)")
        row = self.read_rows(self.root / "tracks/demo/attempts.jsonl")[0]
        self.assertEqual((row["source"], row["choice"], row["confidence"]), ("predict", wrong, None))
        self.assertIn(row["misconception"], {"m-wrong", "m-other"})
        n1 = self.json_of("progress")["demo"]["nodes"]["n1"]
        self.assertEqual((n1["level"], n1["attempts"], n1["predict_answers"]), ("new", 0, 1))
        self.assertEqual(self.json_of("signals"), {"note": "no answers recorded yet"})
        self.assertEqual(self.json_of("due")["due_total"], 0, "still never asked")


class TestCueMode(EngineCase):
    def test_validated_and_shown(self):
        self.new_track()
        cid = self.add(dict(RECALL, cue="far", mode="compose"))["added"][0]["id"]
        self.add(RECALL)  # both optional
        for bad in ({"cue": "near"}, {"mode": "remember"}):
            r = self.run_learn("add-card", "--track", "demo", stdin=json.dumps(dict(RECALL, **bad)), check=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("not in", r.stderr)
        rows = self.json_of("cards", "--track", "demo")["cards"]
        self.assertEqual((rows[0]["id"], rows[0]["cue"], rows[0]["mode"]), (cid, "far", "compose"))
        self.assertNotIn("cue", rows[1])
        f = self.root / "tracks/demo/cards.jsonl"
        f.write_text(f.read_text().replace('"far"', '"farther"'), encoding="utf-8")
        r = self.run_learn("validate", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn(f"{cid}: cue 'farther' not in", r.stdout)


# ── Phase 1: honest mastery ───────────────────────────────────────────────

class TestHonestMastery(EngineCase):
    def setUp(self):
        super().setUp()
        self.new_track()

    def level(self, node, today=DAY0):
        return self.json_of("progress", today=today)["demo"]["nodes"][node]

    def answer(self, cid, today, ok=True, conf="2"):
        if "options" in next(c for c in self.read_rows(self.root / "tracks/demo/cards.jsonl") if c["id"] == cid):
            letter = self.correct_letter(cid) if ok else next(L for L in "ABC" if L != self.correct_letter(cid))
            return self.run_learn("record", "--card", cid, "--choice", letter, "--confidence", conf, today=today)
        return self.run_learn("record", "--card", cid, "--correct", "yes" if ok else "no", "--confidence", conf, today=today)

    def test_pre_date_mcq_retained_stays_retained(self):
        cid = self.add(MCQ, today=day(-5))["added"][0]["id"]
        self.answer(cid, day(-5))
        self.answer(cid, day(-2))
        self.assertEqual(self.level("n1", day(-2))["level"], "retained")
        self.answer(cid, day(3), ok=False)  # a later miss does not take it away …
        n = self.level("n1", day(3))
        self.assertEqual(n["level"], "retained")
        self.assertTrue(n["slipping"], "… but the node is flagged")
        self.answer(cid, day(4))  # the next delayed answer is right → slipping clears
        self.assertNotIn("slipping", self.level("n1", day(4)))

    def test_post_date_mcq_only_is_not_retained(self):
        cid = self.add(MCQ)["added"][0]["id"]
        self.answer(cid, DAY0)
        self.answer(cid, day(1), conf="3")
        self.answer(cid, day(4), conf="3")
        self.assertEqual(self.level("n1", day(4))["level"], "checked")
        # a passed task makes the MCQ delayed answers count (task shows production) → straight to owned
        self.run_learn("task", "--track", "demo", "--task", "01", "--node", "n1", "--status", "passed", today=day(4))
        self.assertEqual(self.level("n1", day(4))["level"], "owned")

    def test_post_date_generative_retained_unless_guessed(self):
        rid = self.add(RECALL)["added"][0]["id"]
        self.answer(rid, DAY0)
        self.answer(rid, day(1), conf="1")
        self.assertEqual(self.level("n2", day(1))["level"], "checked", "a guessed delayed answer is not retention")
        self.run_learn("record", "--card", rid, "--correct", "yes", today=day(2))  # confidence not asked: counts
        self.assertEqual(self.level("n2", day(2))["level"], "retained")
        self.run_learn("task", "--track", "demo", "--task", "01", "--node", "n2", "--status", "passed", today=day(2))
        self.assertEqual(self.level("n2", day(2))["level"], "owned")

    def test_far_cue_delayed_correct_is_owned(self):
        rid = self.add(dict(RECALL, cue="far"))["added"][0]["id"]
        self.answer(rid, DAY0)
        self.assertEqual(self.level("n2")["level"], "checked")
        self.answer(rid, day(1))
        self.assertEqual(self.level("n2", day(1))["level"], "owned")

    def test_durable_needs_spaced_retrieval_over_weeks(self):
        rid = self.add(dict(RECALL, cue="far"))["added"][0]["id"]
        self.answer(rid, DAY0)
        self.answer(rid, day(1))
        self.answer(rid, day(8))
        self.assertEqual(self.level("n2", day(8))["level"], "owned", "two delayed days, 7 days apart: not yet durable")
        self.answer(rid, day(22))
        self.assertEqual(self.level("n2", day(22))["level"], "durable", "3 delayed days spanning 21 days")

    def test_learning_struggling_unchanged(self):
        rid = self.add(RECALL)["added"][0]["id"]
        self.answer(rid, DAY0, ok=False)
        self.assertEqual(self.level("n2")["level"], "struggling")
        self.run_learn("record", "--card", rid, "--correct", "partial")
        self.assertEqual(self.level("n2")["level"], "learning")


# ── Phase 1: map ──────────────────────────────────────────────────────────

LEGACY_MAP = """# Dependency map — Demo

```mermaid
graph TD
  game-def["game-def: players, strategies"] --> best-response
  ordinal["payoffs only rank"] --> best-response
  best-response --> nash
  nash --> pd
  ordinal --> pd
```

## Nodes

| id | kind | statement (one line) | depends on | mastery evidence |
|---|---|---|---|---|
| game-def | truth | A game is players, strategies, payoffs. | – | MCQ |
| ordinal | truth | Ordinal payoffs only rank (4 > 3). | – | explain |
| best-response | derived | Highest own payoff given the others. | game-def, ordinal | recall |
| nash | derived | Everyone best-responds. | best-response | card |
| pd | goal | T > R > P > S. | nash, ordinal | task 01 |

## Coverage carried over

| node | evidence there | status to assume |
|---|---|---|
| game-def, ordinal | 5/5 | strong |
"""


class TestMap(EngineCase):
    def write_map(self, text, track="demo"):
        (self.root / "tracks" / track / "map.md").write_text(text, encoding="utf-8")

    def test_parse_legacy_map(self):
        self.new_track()
        self.write_map(LEGACY_MAP)
        m = self.json_of("map", "--track", "demo", "--json")
        self.assertEqual(m["problems"], [])
        self.assertEqual([n["id"] for n in m["nodes"]], ["game-def", "ordinal", "best-response", "nash", "pd"])
        self.assertEqual(m["nodes"][0], {"id": "game-def", "kind": "truth", "statement": "A game is players, strategies, payoffs.",
                                         "evidence": "MCQ", "depends_on": [], "title": "players, strategies"})
        self.assertEqual(m["nodes"][4]["depends_on"], ["nash", "ordinal"])
        self.assertIn({"from": "ordinal", "to": "pd"}, m["edges"])
        self.assertEqual(len(m["edges"]), 5)
        self.assertIn("5 nodes, 5 edges", self.run_learn("map", "--track", "demo").stdout)

    def test_definition_column(self):
        self.new_track()
        self.write_map(LEGACY_MAP.replace("| id | kind |", "| id | tanım (öğrenci) | kind |", 1)
                       .replace("|---|---|", "|---|---|---|", 1)
                       .replace("| game-def | truth |", "| game-def | Oyun: oyuncular, stratejiler, kazançlar. | truth |", 1))
        m = self.json_of("map", "--track", "demo", "--json")
        self.assertEqual(m["nodes"][0]["definition"], "Oyun: oyuncular, stratejiler, kazançlar.")

    def test_problems(self):
        L = load_engine(self.root)
        bad = LEGACY_MAP.replace("| nash | derived", "| Nash_X | derived").replace("  nash --> pd\n", "  nash --> pd\n  pd --> best-response\n")
        probs = L.parse_map(bad)["problems"]
        self.assertTrue(any("'Nash_X' is not a slug" in p for p in probs), probs)
        self.assertTrue(any("not in the mermaid graph: Nash_X" in p for p in probs), probs)
        self.assertTrue(any("not in the node table: nash" in p for p in probs), probs)
        self.assertTrue(any(p.startswith("the graph has a cycle") for p in probs), probs)
        self.assertTrue(all(p.startswith(("line ", "the graph")) for p in probs), probs)
        self.assertIn("no ```mermaid block", " ".join(L.parse_map("| id | kind |\n|---|---|\n| a | truth |\n")["problems"]))

    def test_template_parses_and_fresh_track_validates(self):
        self.new_track()
        m = self.json_of("map", "--track", "demo", "--json")
        self.assertEqual(m["problems"], [])
        self.assertEqual([n["id"] for n in m["nodes"]], ["truth-a", "derived-b", "goal-c"])
        self.add(RECALL)  # node n2 is not in the unfinished map → warning, not error
        rep = self.json_of("validate")["demo"]
        self.assertEqual(rep["errors"], [])
        self.assertTrue(any("node 'n2'" in w for w in rep["warnings"]))

    def test_validate_legacy_map_warns_marked_map_errors(self):
        self.new_track()
        self.add(RECALL)  # node n2
        self.run_learn("task", "--track", "demo", "--task", "01", "--node", "ghost", "--status", "started")
        cyclic = LEGACY_MAP.replace("  nash --> pd\n", "  nash --> pd\n  pd --> nash\n")
        self.write_map(cyclic)  # no format marker: pre-existing content → warnings only
        rep = self.json_of("validate")["demo"]
        self.assertTrue(rep["ok"])
        w = " | ".join(rep["warnings"])
        for needle in ("cycle", "node 'n2' (card", "node 'ghost' (task 01)"):
            self.assertIn(needle, w)
        self.write_map(cyclic.replace("## Nodes", "<!-- map-format: 1 -->\n## Nodes"))
        r = self.run_learn("validate", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("cycle", " ".join(json.loads(r.stdout)["demo"]["errors"]))

    def test_progress_lists_every_map_node(self):
        self.new_track()
        self.write_map(LEGACY_MAP)
        self.add(dict(RECALL, node="nash"))
        self.add(RECALL)  # n2: not in the map
        nodes = self.json_of("progress")["demo"]["nodes"]
        self.assertEqual(list(nodes), ["game-def", "ordinal", "best-response", "nash", "pd", "n2"])
        self.assertEqual(nodes["pd"]["level"], "new")
        self.assertEqual(nodes["nash"]["cards"], 1)
        self.assertTrue(nodes["n2"]["not_in_map"])
        self.assertNotIn("not_in_map", nodes["nash"])
        self.assertIn("nodes {'new': 2}", self.run_learn("status").stdout, "status counts evidence nodes only")


# ── Phase 1: due --today-misses, signals, lessons, engagement ────────────

class TestTodayMisses(EngineCase):
    def test_misses(self):
        self.new_track()
        a, b, c, d = (self.add(RECALL)["added"][0]["id"] for _ in range(4))
        self.run_learn("record", "--card", a, "--correct", "no", today=day(-1))   # yesterday: not today
        self.run_learn("record", "--card", b, "--correct", "no")
        self.run_learn("record", "--card", c, "--dont-know")
        self.run_learn("record", "--card", d, "--correct", "no", "--source", "lesson")  # lesson: excluded
        self.run_learn("record", "--card", a, "--correct", "yes")
        self.run_learn("task", "--track", "demo", "--task", "01", "--node", "n9", "--status", "passed", "--hints", "2")
        self.run_learn("task", "--track", "demo", "--task", "02", "--node", "n8", "--status", "passed", "--hints", "1")
        before = {f: f.read_bytes() for f in self.root.rglob("*") if f.is_file()}
        res = self.json_of("due", "--today-misses")
        self.assertEqual([x["id"] for x in res["cards"]], [b, c])
        self.assertEqual(res["due_total"], 2)
        self.assertEqual(res["nodes"], [{"track": "demo", "node": "n2", "why": [f"{b}: wrong", f"{c}: dont-know"]},
                                        {"track": "demo", "node": "n9", "why": ["task 01: 2 hints"]}])
        self.assertEqual({f: f.read_bytes() for f in self.root.rglob("*") if f.is_file()}, before, "read-only")
        self.assertEqual(self.json_of("due", "--today-misses", "--track", "demo", today=day(1))["cards"], [])


class TestGenerationGap(EngineCase):
    def test_gap(self):
        self.new_track()
        m = self.add(MCQ)["added"][0]["id"]
        r = self.add(RECALL)["added"][0]["id"]
        self.run_learn("record", "--card", m, "--choice", self.correct_letter(m))
        g = self.json_of("signals")["generation_gap"]
        self.assertEqual(g, {"mcq_accuracy": 1.0, "generative_accuracy": None, "gap": None, "n_mcq": 1,
                             "n_generative": 0, "flag": None})
        for _ in range(7):
            self.run_learn("record", "--card", m, "--choice", self.correct_letter(m))
        for ok in ["yes", "no", "no", "partial", "no", "no", "yes", "no"]:
            self.run_learn("record", "--card", r, "--correct", ok)
        g = self.json_of("signals")["generation_gap"]
        self.assertEqual(g, {"mcq_accuracy": 1.0, "generative_accuracy": 0.25, "gap": 0.75, "n_mcq": 8,
                             "n_generative": 8, "flag": True})


class TestLessons(EngineCase):
    def lesson(self, name, body):
        d = self.root / "tracks/demo/lessons"
        d.mkdir(exist_ok=True)
        (d / name).write_text(f"<html><body>{body}</body></html>", encoding="utf-8")

    def test_status_and_validate(self):
        self.new_track()
        cid = self.add(MCQ)["added"][0]["id"]
        self.lesson("0001-a.html", '<div class="quiz"><p>q</p></div>')
        self.lesson("0002-b.html", "<p>reading only</p>")
        self.lesson("0003-c.html", f'<div class="quiz" data-card="{cid}"></div>')
        out = self.run_learn("status").stdout
        self.assertIn("- demo: sonucu kaydedilmedi: 0003-c; quiz bağlı değil: 0001-a, 0002-b", out)
        rep = self.json_of("validate")["demo"]
        self.assertEqual(rep["errors"], [])
        self.assertTrue(any("0001-a.html: quiz without data-card" in w for w in rep["warnings"]))
        self.assertTrue(any("0002-b.html: no data-card quiz" in w for w in rep["warnings"]))
        self.run_learn("record", "--card", cid, "--choice", "A", "--source", "lesson")
        self.assertNotIn("sonucu kaydedilmedi", self.run_learn("status").stdout)
        self.lesson("0004-d.html", f'<div class="quiz" data-card="{cid}"></div><div class="quiz" data-card="zz-404"></div>')
        r = self.run_learn("validate", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("demo/lessons/0004-d.html: data-card 'zz-404' is not a card", json.loads(r.stdout)["demo"]["errors"])

    def test_no_lessons_no_section(self):
        self.new_track()
        self.assertNotIn("## Lessons", self.run_learn("status").stdout)


class TestEngagement(EngineCase):
    def test_cheatsheet_offered_once_a_node_is_owned(self):
        self.new_track()
        rid = self.add(RECALL)["added"][0]["id"]
        self.run_learn("record", "--card", rid, "--correct", "yes")
        self.run_learn("record", "--card", rid, "--correct", "yes", today=day(1))
        self.assertNotIn("cheatsheet:", self.run_learn("status", today=day(1)).stdout)
        self.run_learn("task", "--track", "demo", "--task", "01", "--node", "n2", "--status", "passed", today=day(1))
        out = self.run_learn("status", today=day(1)).stdout
        self.assertIn("cheatsheet: demo/n2 reached owned", out)
        self.run_learn("moment", "--kind", "cheatsheet", "--note", "demo/n2", today=day(1))
        self.assertNotIn("cheatsheet:", self.run_learn("status", today=day(1)).stdout)

    def test_recap_after_four_new_nodes(self):
        self.new_track()
        ids = [self.add(dict(RECALL, node=f"k{i}"))["added"][0]["id"] for i in range(4)]
        for cid in ids[:3]:
            self.run_learn("record", "--card", cid, "--correct", "yes")
        self.assertNotIn("recap due", self.run_learn("status").stdout)
        self.run_learn("record", "--card", ids[3], "--correct", "yes")
        self.assertIn("recap due: 4 nodes", self.run_learn("status").stdout)
        self.run_learn("moment", "--kind", "recap")
        self.assertNotIn("recap due", self.run_learn("status").stdout)


# ── Phase 2: lesson confidence, export, dashboard ─────────────────────────

class TestLessonConfidence(EngineCase):
    def test_lesson_keeps_confidence_and_answer_text_never_schedules(self):
        self.new_track()
        cid = self.add(MCQ)["added"][0]["id"]
        before = (self.root / "tracks/demo/cards.jsonl").read_bytes()
        res = self.json_of("record", "--card", cid, "--choice", "A", "--confidence", "3", "--source", "lesson",
                           "--answer-text", "çünkü öyle")
        self.assertEqual(res["confidence"], 3)
        self.json_of("record", "--card", cid, "--choice", "B", "--source", "lesson")  # not asked → null
        self.json_of("record", "--card", cid, "--choice", "B", "--confidence", "2", "--source", "predict")
        self.assertEqual((self.root / "tracks/demo/cards.jsonl").read_bytes(), before, "never scheduled")
        rows = self.read_rows(self.root / "tracks/demo/attempts.jsonl")
        self.assertEqual([(r["source"], r["confidence"]) for r in rows], [("lesson", 3), ("lesson", None), ("predict", None)])
        self.assertEqual(rows[0]["answer_text"], "çünkü öyle")
        self.assertEqual(self.json_of("progress")["demo"]["nodes"]["n1"]["attempts"], 0, "not mastery evidence")


SECRET_MCQ = {"node": "game-def", "type": "mcq", "prompt": "SECRET-PROMPT-1 which?", "explanation": "SECRET-EXPL-1",
              "options": [{"text": "SECRET-RIGHT-1", "correct": True},
                          {"text": "SECRET-WRONG-1", "misconception": "m-secret-belief"},
                          {"text": "SECRET-WRONG-2", "misconception": "m-secret-other"}]}
SECRET_RECALL = {"node": "nash", "type": "recall", "prompt": "SECRET-PROMPT-2", "explanation": "SECRET-EXPL-2",
                 "answer": "SECRET-ANSWER-2"}
SECRETS = ["SECRET-PROMPT", "SECRET-EXPL", "SECRET-RIGHT", "SECRET-WRONG", "SECRET-ANSWER", "m-secret",
           "SECRET-OBSERVED", "SECRET-WHY", "ease", "interval"]


class DashCase(EngineCase):
    """Two tracks: demo (legacy map, lessons, task, answers) and second (template map, untouched)."""

    def build(self):
        self.new_track()
        (self.root / "tracks/demo/map.md").write_text(LEGACY_MAP, encoding="utf-8")
        (self.root / "tracks/demo/README.md").write_text("# Demo Konusu\n\nStarted: x\n", encoding="utf-8")
        (self.root / "tracks/demo/handoff.md").write_text(
            "# Handoff\n\n## Next step\n\nTUTOR-ONLY warm-up gt-001.\n\n## Öğrenci için\n\nÖnce **nash** düğümüne bak.\n\n## Session log\n", encoding="utf-8")
        (self.root / "tracks/demo/cheatsheet.md").write_text(
            "# Özet\n\n- **Nash**: kimse tek başına sapmaz <b>x</b>\n\n| a | b |\n|---|---|\n| `x` | y |\n", encoding="utf-8")
        (self.root / "tracks/demo/glossary.md").write_text("# Sözlük\n\n1. oyun\n2. ödeme\n", encoding="utf-8")
        (self.root / "tracks/demo/RESOURCES.md").unlink(missing_ok=True)  # a missing file exports as null
        (self.root / "learner/profile.md").write_text("# Profile\n\n## Observed\n- SECRET-OBSERVED pattern\n", encoding="utf-8")
        self.mcq = self.add(SECRET_MCQ, today=day(-2))["added"][0]["id"]
        self.rec = self.add(SECRET_RECALL, today=day(-2))["added"][0]["id"]
        self.run_learn("record", "--card", self.mcq, "--choice", self.correct_letter(self.mcq), "--confidence", "3",
                       "--answer-text", "SECRET-WHY", today=day(-2))
        self.run_learn("record", "--card", self.rec, "--correct", "partial", today=day(-1))
        self.run_learn("task", "--track", "demo", "--task", "01-x", "--node", "nash", "--status", "started", today=day(-1))
        lessons = self.root / "tracks/demo/lessons"
        lessons.mkdir()
        (lessons / "0001-a.html").write_text(f'<title>Birinci &amp; Ders</title><div class="quiz" data-card="{self.mcq}"></div>',
                                             encoding="utf-8")
        (lessons / "0002-b.html").write_text("<p>okuma</p>", encoding="utf-8")
        self.new_track("second")
        self.run_learn("use", "demo")


class TestExport(DashCase):
    def test_shape_and_no_secrets(self):
        self.build()
        raw = self.run_learn("export", "--json").stdout
        for s in SECRETS:
            self.assertNotIn(s, raw, f"export leaks {s}")
        d = json.loads(raw)
        self.assertEqual(list(d), ["schema", "generated", "format_version", "generated_at", "data_warnings", "learner",
                                   "tracks"])
        self.assertIs(d["generated"], True)
        self.assertEqual(d["schema"], "teach.export/1")
        self.assertEqual(d["format_version"], 1)
        self.assertIsNotNone(dt.datetime.fromisoformat(d["generated_at"]).tzinfo)
        self.assertEqual(d["data_warnings"], [])
        recent = d["learner"].pop("recent")
        self.assertEqual(d["learner"], {"active_track": "demo", "study_days": [day(-2), day(-1)], "streak": 2,
                                        "started": day(-2), "gains": [], "milestones": []})
        row = lambda d, n, k: {"day": d, "track": "demo", "done": [], "started": [n], "slipping": [], "remembered": [],
                               "answers": k, "milestones": []}
        self.assertEqual(recent, [row(day(-1), "nash", 1), row(day(-2), "game-def", 1)], "newest first, node ids only")
        self.assertEqual([t["id"] for t in d["tracks"]], ["demo", "second"])
        t = d["tracks"][0]
        self.assertEqual(list(t), ["id", "title", "map", "next", "due", "lessons", "tasks", "files", "docs",
                                   "last_studied", "resume"])
        self.assertEqual(t["docs"], [{"id": "cheatsheet", "type": "cheatsheet", "title": "Özet", "path": "tracks/demo/cheatsheet.md"},
                                     {"id": "glossary", "type": "glossary", "title": "Sözlük", "path": "tracks/demo/glossary.md"},
                                     {"id": "map", "type": "map", "title": "Harita (metin)", "path": "tracks/demo/map.md"}])
        self.assertEqual((t["last_studied"], t["resume"]), (day(-1), "Önce nash düğümüne bak."))
        self.assertEqual(t["title"], "Demo Konusu")
        self.assertEqual(list(t["map"]), ["nodes", "edges", "problems"])
        node = t["map"]["nodes"][0]
        self.assertEqual(node, {"id": "game-def", "title": "players, strategies",
                                "statement": "A game is players, strategies, payoffs.", "kind": "truth",
                                "definition": None, "summary": None, "depends_on": [], "in_map": True, "level": "checked",
                                "slipping": False,
                                "evidence": {"attempts": 1, "correct": 1, "delayed_correct": 0, "tasks_passed": 0}})
        self.assertEqual([n["id"] for n in t["map"]["nodes"]], ["game-def", "ordinal", "best-response", "nash", "pd"])
        self.assertEqual(t["map"]["nodes"][3]["level"], "learning")
        self.assertEqual(t["next"], "nash", "a started (learning) node comes first")
        self.assertEqual(t["due"], {"today": 2, "tomorrow": 0, "nodes_today": 2, "studied": 2, "fresh": 0})
        self.assertEqual(self.json_of("export", "--json", today=day(-2))["tracks"][0]["due"],
                         {"today": 0, "tomorrow": 1, "nodes_today": 0, "studied": 2, "fresh": 2})
        self.assertEqual(t["lessons"], [
            {"path": "tracks/demo/lessons/0001-a.html", "title": "Birinci & Ders", "result_recorded": False,
             "slug": "0001-a", "nodes": ["game-def"], "docs": [], "sources": [], "number": 1},
            {"path": "tracks/demo/lessons/0002-b.html", "title": "0002-b", "result_recorded": None,
             "slug": "0002-b", "nodes": [], "docs": [], "sources": [], "number": 2}])
        self.assertEqual(t["tasks"], [{"id": "01-x", "node": "nash", "last_status": "started"}])
        self.assertEqual(t["files"], {"handoff": "tracks/demo/handoff.md", "cheatsheet": "tracks/demo/cheatsheet.md",
                                      "glossary": "tracks/demo/glossary.md", "map": "tracks/demo/map.md",
                                      "resources": None})
        s = d["tracks"][1]
        self.assertEqual((s["next"], s["due"], s["lessons"], s["tasks"]), ("truth-a", {"today": 0, "tomorrow": 0, "nodes_today": 0, "studied": 0, "fresh": 0}, [], []))
        self.run_learn("record", "--card", self.mcq, "--choice", "A", "--source", "lesson")
        self.assertTrue(self.json_of("export", "--json")["tracks"][0]["lessons"][0]["result_recorded"])

    def test_node_summary_from_cheatsheet(self):
        self.build()
        (self.root / "tracks/demo/cheatsheet.md").write_text(
            "# Özet\n\n## Players, **strategies**\n\nOyun = oyuncular + stratejiler.\n\n## nash\n\n- kimse tek başına sapmaz\n"
            "\n## unknown-node\n\nx\n", encoding="utf-8")
        nodes = {n["id"]: n for n in self.json_of("export", "--json")["tracks"][0]["map"]["nodes"]}
        self.assertEqual(nodes["game-def"]["summary"], "Oyun = oyuncular + stratejiler.", "matched by title")
        self.assertEqual(nodes["nash"]["summary"], "- kimse tek başına sapmaz", "matched by id")
        self.assertIsNone(nodes["pd"]["summary"])
        html = (self.base / "p.html")
        self.run_learn("dashboard", "--out", str(html))
        self.assertIn('<h3 class="lbl">Özetin</h3><div class="md nc-sum"><ul><li>kimse tek başına sapmaz</li></ul></div>',
                      html.read_text(encoding="utf-8"))

    def test_unlogged_days(self):
        self.build()
        L = load_engine(self.root)
        u = L.unlogged_days()
        self.assertTrue(any(f"demo: {day(-1)} has" in x for x in u), u)
        h = self.root / "tracks/demo/handoff.md"
        h.write_text(h.read_text(encoding="utf-8") + f"- {day(-2)} · x\n- {day(-1)} · y\n", encoding="utf-8")
        self.assertEqual([x for x in L.unlogged_days() if x.startswith("demo:")], [], "logged days are not listed")

    def test_data_contract(self):
        """Every row the engine writes and the export itself match schemas/ (the contract other agents rely on)."""
        self.build()
        self.run_learn("record", "--card", self.rec, "--dont-know")
        self.run_learn("moment", "--kind", "teaser", "--note", "x")
        L = load_engine(self.root)
        self.assertEqual(L.scan_contract(), [], "engine-written rows break the contract")
        export = self.json_of("export", "--json")
        self.assertEqual(L.schema_errors(export, L.load_schema("export")), [])
        bad = {"ts": "2026-10-20T10:00:00+03:00", "kind": "card", "card": "x", "node": "n", "type": "mcq",
               "correct": "maybe", "delayed": False}
        self.assertTrue(L.schema_errors(bad, L.load_schema("attempt")), "an invalid row is caught")
        with (self.root / "tracks/demo/attempts.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(bad) + "\n")
        self.assertEqual(len(L.scan_contract()), 1)
        self.assertIn("break the data contract", "\n".join(L.data_warning_lines()))

    def test_notes_gaps(self):
        self.build()
        L = load_engine(self.root)
        gaps = L.notes_gaps()
        self.assertTrue(any("demo: map nodes without `tanım (öğrenci)`: game-def, ordinal" in g for g in gaps), gaps)
        self.assertFalse(any("done without a cheatsheet" in g for g in gaps), "nothing is done yet")

    def test_empty_root_unknowns_are_null(self):
        d = self.json_of("export", "--json")
        self.assertEqual(d["learner"], {"active_track": None, "study_days": [], "streak": 0, "started": None,
                                        "gains": [], "milestones": [], "recent": []})
        self.assertEqual(d["tracks"], [])

    def test_next_rule(self):
        L = load_engine(self.root)
        mk = lambda i, lv: {"id": i, "level": lv, "in_map": True}
        edges = [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]
        self.assertEqual(L.next_node([mk("a", "checked"), mk("r", "new"), mk("b", "new"), mk("c", "new")], edges), "b")
        self.assertEqual(L.next_node([mk("a", "new"), mk("b", "new"), mk("c", "new")], edges), "a")
        self.assertEqual(L.next_node([mk("a", "owned"), mk("b", "retained"), mk("c", "struggling")], edges), "c")
        self.assertIsNone(L.next_node([mk("a", "owned"), mk("b", "checked"), mk("c", "retained")], edges))


class TestDashboard(DashCase):
    def strip_gen(self, html):
        return re.sub(r"güncellendi: [^<]*<", "<", html)

    def docs_fixture(self):
        """Extra notes for the side panel: a reference page, a task (TASK.md + a solution that must never show)."""
        d = self.root / "tracks/demo"
        (d / "reference").mkdir()
        (d / "reference/sozluk.html").write_text("<title>Glossary</title><h1>Sözlük <span>(ref)</span></h1>", encoding="utf-8")
        (d / "tasks/01-x").mkdir(parents=True)
        (d / "tasks/01-x/TASK.md").write_text("# Görev 01 — Demo Konusu\n\nYap <script>alert(1)</script> [s](solution.md)\n",
                                              encoding="utf-8")
        (d / "tasks/01-x/solution.md").write_text("SECRET-SOLUTION\n", encoding="utf-8")
        (d / "lessons/0002-b.html").write_text(
            '<!-- lesson-map: --track demo --nodes nash --current nash --><p><a href="../reference/sozluk.html">S</a> '
            '<a href="../cheatsheet.md">c</a> <a href="https://ex.org/x">not a source</a></p>'
            '<ol class="refs"><li id="r1"><a href="https://ex.org/a?x=1&amp;y=2">Kaynak <i>A</i></a></li></ol>',
            encoding="utf-8")

    def render(self, name="pano.html"):
        out = self.base / name
        self.run_learn("dashboard", "--out", str(out))
        return out.read_text(encoding="utf-8")

    def test_generates_deterministically(self):
        self.build()
        self.docs_fixture()
        out = self.base / "out" / "pano.html"
        r1 = self.run_learn("dashboard", "--out", str(out))
        self.assertEqual(r1.stdout.strip(), str(out.resolve()))
        first = out.read_text(encoding="utf-8")
        second_run = self.run_learn("dashboard", "--out", str(out))
        self.assertEqual(second_run.returncode, 0)
        self.assertEqual(self.strip_gen(out.read_text(encoding="utf-8")), self.strip_gen(first))
        self.assertTrue(first.startswith("<!doctype html>") and first.rstrip().endswith("</html>"))
        for needle in ('lang="tr"', '<svg class="logo" viewBox="0 0 24 24" aria-hidden="true">', "gün çalıştın", "son çalışma",
                       "konu tekrar bekliyor", '<h2 class="bh">Kavram ağı</h2>', '<h2 class="cal-h">2 gün çalıştın',
                       'class="plan"', 'class="graph"', "--current:", 'data-node="nash"',  "güncellendi:",
                       'sıradaki — Önce nash düğümüne bak."', "teach-theme", ">Temel<",
                       ">Hedef<"):
            self.assertIn(needle, first)
        for gone in ("<h2>Bugün</h2>", "Öğrenme panon", "henüz ders yok", "Henüz", "tamamlanan görev</span>",
                     "Sıradaki ders", "Kaldığın yer", "nx-tag", "tekrar yapalım", " dk<", "oturdu", "senin", 'class="perf"'):
            self.assertNotIn(gone, first, "no decorative text, no filler, no level words, no extra rows")
        self.assertEqual(first.count("<section"), 3, "Genel + one panel per track")
        genel = first[first.index('id="panel-genel"'):first.index('id="panel-demo"')]
        self.assertLess(genel.index('id="ag"'), genel.index('class="kpi due"'), "the graph first, the column beside it")
        order = [genel.index(x) for x in ('class="kpi due"', 'class="kpi prog"', 'id="takvim"')]
        self.assertEqual(order, sorted(order), "column: reviews, progress, calendar")
        self.assertNotIn('class="kpi days"', genel, "the day count lives in the calendar heading")
        self.assertNotIn("TUTOR-ONLY", first, "tutor-facing Next step never reaches the learner page")
        self.assertEqual(first.count('class="node lv-learn next"'), 1, "demo's next (nash, learning) glows")
        self.assertEqual(first.count('class="node lv-new next"'), 1, "second's next (truth-a) glows")
        self.assertNotRegex(first, r'src="https?://|<link (?!rel="icon" href="data:)|<script src|@import|url\(http', "offline: nothing external")
        for s in SECRETS[:-2] + ["SECRET-SOLUTION"]:
            self.assertNotIn(s, first, f"dashboard leaks {s}")

    def test_tabs_structure(self):
        self.build()
        h = self.render()
        self.assertEqual(h.count('role="tablist"'), 3, "course tabs + one lesson-tab row per track")
        self.assertEqual(re.findall(r'role="tab" class="tab" id="tab-([\w-]+)"', h), ["genel", "demo", "second"])
        self.assertEqual(re.findall(r'id="panel-([\w-]+)" role="tabpanel" aria-labelledby="tab-\1"', h),
                         ["genel", "demo", "second"])
        for k in ("genel", "demo", "second"):
            self.assertIn(f'data-tab="{k}" aria-controls="panel-{k}"', h)
        self.assertEqual(re.findall(r'id="tab-([\w-]+)" data-tab="[^"]*" aria-controls="[^"]*" aria-selected="true"', h),
                         ["demo"], "first open: the active track's tab")
        self.assertEqual(h.count('class="panel on"'), 1)
        self.assertIn('data-default="demo"', h)
        self.assertNotIn("tdot", h, "a course tab carries only its colour chip")
        self.assertIn('<i class="hue" style="background:#6f9f7f" aria-hidden="true"></i><span class="tl">Demo Konusu</span>', h)
        self.assertIn('title="Demo Konusu · şu anki konu"', h)
        for js in ('classList.add("js")', '"teach-tab"', '"teach-lesson:"', "location.hash", "history.replaceState",
                   '"ArrowRight"', '"ArrowLeft"', '"Home"', '"End"', "hashchange", "data-go", "flash",
                   "embed=1&theme=", 'teach:"theme"', '"ready"', '"nav"', '"Escape"', '"Tab"', '"panel"'):
            self.assertIn(js, h)
        self.assertIn(".js .panel { display: none; }", h, "panels hide only with JS; without it all stay stacked")
        # lesson tabs: Harita first (and the first-open default), then Ders N · title; iframes load lazily (data-src)
        self.assertEqual(re.findall(r'role="tab" class="ltab[^"]*" id="lt-demo-([\w-]+)" data-view="\1"', h),
                         ["harita", "0001-a", "0002-b"])
        self.assertIn('<span class="ln">1</span><span class="lt">Birinci &amp; Ders</span>', h)
        self.assertIn('title="Ders 1 · Birinci &amp; Ders · sıradaki — Önce nash düğümüne bak."', h, "full title on hover")
        self.assertRegex(h, r"\.ltab \{[^}]*height: 32px", "compact lesson tabs")
        self.assertRegex(h, r'\.ltab\[data-view="harita"\] \{ position: sticky; left: 0;', "Harita pinned")
        self.assertRegex(h, r'id="lt-demo-harita" [^>]*aria-selected="true"')
        self.assertRegex(h, r'class="ltab is-next" id="lt-demo-0001-a" [^>]*aria-selected="false"',
                         "the current lesson (latest unrecorded, 0001) is marked sıradaki")
        self.assertNotIn('class="okm"', h, "no result recorded yet → no ✓")
        self.assertIn('data-track="demo" data-default="harita"', h)
        self.assertEqual(re.findall(r'<iframe class="lesson-frame" data-src="([^"]+)"', h),
                         ["repo/tracks/demo/lessons/0001-a.html", "repo/tracks/demo/lessons/0002-b.html"])
        self.assertNotRegex(h, r'<iframe[^>]* src=', "no iframe loads before JS picks a tab")
        self.assertIn('data-track="second" data-default="harita"', h, "a track without lessons opens on its map")
        self.assertEqual(re.findall(r'role="tab" class="ltab" id="lt-second-([\w-]+)"', h), ["harita"])
        # one row per track: lesson tabs left; right only the progress sentence + bar and when it was last studied
        demo = h[h.index('id="panel-demo"'):h.index('id="panel-second"')]
        row = demo[demo.index('class="lrow"'):demo.index('class="work')]
        for x in ('class="ltabs"', 'class="kpi prog"', 'class="kpi last"'):
            self.assertIn(x, row)
        for x in ('class="kpi days"', 'class="kpi due"'):
            self.assertNotIn(x, row)
        self.assertIn("<b>5 konu</b><span class=\"pm\"> · 2'si işlendi</span>", row)
        self.assertIn('<span class="lbl">son çalışma</span><b class="ago">dün</b>', row)
        second = h[h.index('id="panel-second"'):]
        self.assertNotIn("son çalışma", second, "never studied → nothing")
        self.assertNotIn("tekrar yok", h, "no due → nothing, not a 'yok' line")
        genel = h[h.index('id="panel-genel"'):h.index('id="panel-demo"')]
        self.assertIn('<b class="num">%0</b><span class="dl"><b>güncel</b><small>2 konu tekrar bekliyor</small></span></div>', genel,
                      "memory freshness: share of studied nodes not due and not slipping")
        for gone in ("Şu an", "nw-", "ŞU AN", "Sıradaki"):
            self.assertNotIn(gone, h)
        # each track has its own calm hue: tab chip, cloud, legend chip (never the yellow of the next node)
        self.assertIn('id="tab-demo" data-tab="demo" aria-controls="panel-demo" aria-selected="true" tabindex="0" '
                      'title="Demo Konusu · şu anki konu"><i class="hue" style="background:#6f9f7f"', h)
        self.assertIn('<i class="hue" style="background:#6f8fb8"', h)
        self.assertIn('stop-color="#6f9f7f"', h)
        # concept network: clouds and labels open the course, nodes its map; the legend only adds "sıradaki"
        self.assertIn('<div class="kg-legend"><span class="kg-key"><i class="dot-next"></i>sıradaki</span></div>', h)
        self.assertNotIn('<button type="button" class="kg-key"', h, "track names are already on the canvas")
        self.assertIn('class="kg-label" data-go="second"', h)
        self.assertIn('data-doc="demo--node-nash" data-node="nash"', h, "a node opens its card")
        self.run_learn("record", "--card", self.mcq, "--choice", "A", "--source", "lesson")
        h2 = self.render()
        self.assertRegex(h2, r'class="ltab is-next" id="lt-demo-0002-b"', "all recorded → the latest")
        self.assertRegex(h2, r'id="lt-demo-0001-a" [^>]*>.*?<span class="okm" aria-label="sonuç kaydedildi">✓</span>')

    def test_notes_column_and_side_panel(self):
        self.build()
        self.docs_fixture()
        h = self.render()
        demo = h[h.index('id="panel-demo"'):h.index('id="panel-second"')]
        lists = dict(re.findall(r'<ul class="dlist[^"]*" data-for="([\w-]+)">(.*?)</ul>', demo))
        self.assertEqual(list(lists), ["harita", "0002-b"], "Harita: every note; a lesson: its own; nothing → no list")
        self.assertIn('<ul class="dlist on" data-for="harita">', demo)
        self.assertEqual(re.findall(r'data-doc="([\w-]+)"', lists["harita"]),
                         ["demo--cheatsheet", "demo--glossary", "demo--map", "demo--ref-sozluk", "demo--task-01-x"])
        self.assertIn('<span class="t">Harita (metin)</span><span class="k">Harita</span>', demo)
        self.assertIn('<span class="t">Sözlük (ref)</span><span class="k">Referans</span>', demo, "title from <h1>")
        self.assertIn('<span class="t">Görev 01</span><span class="k">Görev</span>', demo, "first heading minus the track")
        self.assertEqual(re.findall(r'data-doc="([\w-]+)"', lists["0002-b"]),
                         ["demo--cheatsheet", "demo--ref-sozluk", "demo--task-01-x"],
                         "linked documents + tasks on the lesson's nodes (nash)")
        self.assertIn('<a class="doc ext-doc" href="https://ex.org/a?x=1&amp;y=2" target="_blank" rel="noopener" '
                      'title="Kaynak A (yeni sekmede)"><span class="t">Kaynak A</span><span class="k">Kaynak</span></a>',
                      lists["0002-b"], "the lesson's sources open in a new tab")
        self.assertNotIn("not a source", demo)
        self.assertIn('class="notes-btn" data-track="demo"', demo)
        # embedded at generation time, escaped; HTML pages framed lazily
        self.assertRegex(h, r'<template id="doc-demo--cheatsheet" data-kind="Özet" data-title="Özet"><div class="md">')
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", h)
        self.assertIn("<code>x</code>", h)
        self.assertIn("<ol>", h)
        self.assertIn("<p>Yap &lt;script&gt;alert(1)&lt;/script&gt; s</p>", h, "escaped; relative links become plain text")
        self.assertNotIn("<script>alert(1)", h)
        self.assertIn('<template id="doc-demo--ref-sozluk" data-kind="Referans" data-title="Sözlük (ref)" '
                      'data-src="repo/tracks/demo/reference/sozluk.html"><iframe class="doc-frame" '
                      'data-src="repo/tracks/demo/reference/sozluk.html"', h)
        for f in ("handoff", "misconceptions", "cards.jsonl"):
            self.assertNotIn(f'data-doc="demo--{f}"', h)
        # one side panel: a modal dialog, labelled, with a close button
        self.assertEqual(h.count('role="dialog"'), 1)
        self.assertIn('<aside class="sheet" id="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title" '
                      'aria-hidden="true">', h)
        self.assertIn('class="sheet-x" aria-label="Kapat (Esc)"', h)
        # no notes → no column, no button
        second = h[h.index('id="panel-second"'):]
        self.assertIn('data-doc="second--map"', second, "the template track has a map.md")
        (self.root / "tracks/second/map.md").unlink()
        for f in ("cheatsheet.md", "glossary.md", "RESOURCES.md"):
            (self.root / "tracks/second" / f).unlink(missing_ok=True)
        h3 = self.render()
        second = h3[h3.index('id="panel-second"'):]
        self.assertNotIn('class="docs"', second)
        self.assertNotIn('class="notes-btn"', second)
        self.assertIn('class="work solo"', second)

    def test_turkish_relative_day(self):
        L = load_engine(self.root)
        os.environ["TEACH_TODAY"] = DAY0
        try:
            for n, want in {0: "bugün", 1: "dün", 2: "2 gün önce", 6: "6 gün önce", 7: "1 hafta önce",
                            13: "1 hafta önce", 14: "2 hafta önce", 30: "4 hafta önce"}.items():
                self.assertEqual(L.tr_ago(day(-n)), want, n)
            self.assertEqual(L.tr_ago(None), "")
        finally:
            del os.environ["TEACH_TODAY"]

    def test_short_tab_title(self):
        L = load_engine(self.root)
        self.assertEqual(L.short_title("Oyun Teorisi: Tarihsel Strateji"), "Oyun Teorisi")
        self.assertEqual(L.short_title("Proofs to Structures"), "Proofs to Structures")
        self.assertEqual(L.short_title("Kanıtlar — yapılar"), "Kanıtlar")
        self.assertEqual(L.short_title("Bir çok uzun konu başlığı burada"), "Bir çok uzun konu baş…")

    def test_turkish_numeral_suffix(self):
        L = load_engine(self.root)
        cases = {1: "1'i", 2: "2'si", 3: "3'ü", 4: "4'ü", 5: "5'i", 6: "6'sı", 7: "7'si", 8: "8'i", 9: "9'u", 10: "10'u",
                 15: "15'i", 20: "20'si", 30: "30'u", 40: "40'ı", 50: "50'si", 60: "60'ı", 70: "70'i", 80: "80'i",
                 90: "90'ı", 100: "100'ü", 300: "300'ü", 1000: "1000'i", 2000000: "2000000'u", 123: "123'ü"}
        for n, want in cases.items():
            self.assertEqual(L.tr_poss(n), want, n)

    def test_map_states_chips_and_clicks(self):
        self.build()
        self.docs_fixture()
        h = self.render()
        demo = h[h.index('id="panel-demo"'):h.index('id="panel-second"')]
        plan = demo[demo.index('<svg class="plan"'):demo.index("</svg>")]
        # demo: game-def checked (1 pip), nash learning + next (0 pips, yellow), the rest new (dashed)
        self.assertRegex(plan, r'(?s)class="node lv-learn"[^>]*data-node="game-def"[^>]*>.*?<circle class="pip on"')
        self.assertRegex(plan, r'class="node lv-learn next"[^>]*data-node="nash"')
        self.assertEqual(plan.count('class="glow"'), 1)
        self.assertRegex(plan, r'class="node lv-new"[^>]*data-node="pd"')
        self.assertIn("svg.plan .lv-new .box { fill: var(--bg); stroke: var(--muted); stroke-dasharray: 4 3; }", h)
        # path emphasis: into the next node solid, its prerequisite chain kept, the rest faint
        self.assertIn('class="edge"', plan)
        self.assertIn('class="edge path"', plan)
        self.assertIn('class="edge dim"', plan)
        # 0002-b teaches nash (lesson-map comment) → chip D2 and a click opens that lesson; others open their card
        self.assertRegex(plan, r'(?s)data-node="nash" data-doc="demo--node-nash">.*?<g class="chip"><rect[^>]*/><text[^>]*>D2</text>')
        self.assertRegex(plan, r'data-node="pd" data-doc="demo--node-pd"')
        self.assertIn('<template id="doc-demo--node-pd" data-kind="Konu" data-title="pd">', h)
        nash = h[h.index('<template id="doc-demo--node-nash"'):]
        nash = nash[:nash.index("</template>")]
        self.assertIn('<button type="button" class="nc-go" data-go="demo/0002-b"><span class="nc-num">D2</span>', nash,
                      "every node opens its card; the card links the node's lesson")
        for part in ('<h3 class="lbl">Tanım</h3>', '<h3 class="lbl">Özetin</h3>', '<span class="nc-st next">sıradaki</span>'):
            self.assertIn(part, nash)
        # one tiny legend, only the states present (no "bitti": nothing retained yet)
        self.assertIn('<div class="mlegend"><span><i class="nx"></i>sıradaki</span><span><b class="lg-new"></b>henüz değil</span></div>', demo)
        self.assertIn('<div class="dir">Temel</div>', demo)
        self.assertIn('<div class="dir">Hedef</div>', demo)
        for gone in ("öğreniliyor</span>", "tekrar lazım</span>", 'class="legend"'):
            self.assertNotIn(gone, demo)

    def test_recent_study_days(self):
        self.build()
        att = self.root / "tracks/demo/attempts.jsonl"
        ts = lambda d: f"{d}T10:00:00+00:00"
        rows = [{"ts": ts(day(-9)), "kind": "card", "card": "x1", "node": "pd", "correct": "no", "delayed": False},
                {"ts": ts(day(-1)), "kind": "card", "card": "x1", "node": "pd", "correct": "yes", "delayed": True,
                 "type": "recall", "confidence": 3}]
        with att.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        (self.root / "learner/moments.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [
            {"ts": ts(day(-1)), "kind": "milestone", "note": "5-nodes-learned"},
            {"ts": ts(day(-4)), "kind": "teaser", "note": "SECRET-TEASER"}]), encoding="utf-8")
        recent = self.json_of("export", "--json")["learner"]["recent"]
        self.assertEqual([(r["day"], r["track"]) for r in recent], [(day(-1), "demo"), (day(-2), "demo"), (day(-9), "demo")])
        self.assertEqual(recent[0]["done"], [{"node": "pd", "level": "retained"}], "missed first, right after a delay")
        self.assertEqual(recent[0]["remembered"], ["pd"])
        self.assertEqual(recent[0]["started"], ["nash"])
        self.assertEqual(recent[0]["milestones"], ["5-nodes-learned"])
        self.assertEqual(recent[2]["started"], ["pd"])
        h = self.render()
        k = h[h.index('id="son"'):]
        k = k[:k.index("</ol>")]
        self.assertIn('<h2 class="bh">Son çalışmalar</h2>', k)
        self.assertEqual(k.count("<li>"), 3)
        self.assertIn('<b>pd</b> <span class="rc-ok">✓ öğrenildi</span> · <b>nash</b> başladı · '
                      '<b>pd</b>: günler sonra hatırladın<span class="rc-tag">5 konu öğrenildi</span>', k)
        self.assertIn(load_engine(self.root).tr_date(day(-1)), k)
        self.assertNotIn("SECRET", h)
        self.assertNotIn('id="kazanim"', h, "the old then-vs-now block is gone")
        (self.root / "learner/moments.jsonl").unlink()
        att.write_text("", encoding="utf-8")
        self.assertNotIn('id="son"', self.render(), "nothing studied → no block")

    def test_ten_tracks_render(self):
        L = load_engine(self.root)
        def track(i):
            nodes = [{"id": f"n{j}", "title": f"Kavram {i}.{j}", "statement": f"Cümle {j}", "kind": "truth",
                      "depends_on": [f"n{j - 1}"] if j else [], "in_map": True,
                      "level": ["new", "learning", "retained", "owned"][(i + j) % 4], "slipping": False,
                      "evidence": {}} for j in range(5)]
            return {"id": f"konu-{i:02d}", "title": f"Çok uzun bir konu başlığı numara {i} " * (2 if i == 4 else 1),
                    "map": {"nodes": nodes, "edges": [{"from": f"n{j - 1}", "to": f"n{j}"} for j in range(1, 5)],
                            "problems": []},
                    "next": "n2", "due": {"today": i, "tomorrow": 0},
                    "lessons": [{"path": f"tracks/konu-{i:02d}/lessons/000{k}-x.html", "title": f"Ders {k}",
                                 "result_recorded": None} for k in range(1, 1 + i % 3)],
                    "tasks": [], "files": {"cheatsheet": None, "glossary": None}}
        data = {"schema": "teach.export/1", "format_version": 1, "generated_at": "2026-10-20T10:00:00+00:00",
                "data_warnings": [], "learner": {"active_track": "konu-07", "study_days": [DAY0], "streak": 1,
                                                 "started": DAY0},
                "tracks": [track(i) for i in range(10)] + [dict(track(10), id="genel", title="Genel diye bir konu")]}
        os.environ["TEACH_TODAY"] = DAY0
        try:
            h = L.render_dashboard(data, self.root / "learner")
            self.assertEqual(h, L.render_dashboard(data, self.root / "learner"), "deterministic")
        finally:
            del os.environ["TEACH_TODAY"]
        self.assertEqual(h.count('role="tab" class="tab"'), 12)
        self.assertEqual(len(re.findall(r'role="tab" class="ltab', h)), sum(1 + i % 3 for i in range(11)),
                         "one tab per lesson + Harita per track")
        self.assertEqual(h.count('" role="tabpanel" aria-labelledby="tab-'), 12)
        self.assertIn('id="tab-konu-genel"', h, "a track named genel does not clash with the overview tab")
        self.assertIn('data-track="konu-genel"', h)
        self.assertEqual(re.findall(r'id="tab-([\w-]+)" data-tab="[^"]*" aria-controls="[^"]*" aria-selected="true"', h),
                         ["konu-07"])
        self.assertIn('<span class="tl">Çok uzun bir konu baş…</span>', h, "short tab name, ≤ 22 characters")
        self.assertIn('title="Çok uzun bir konu başlığı numara 4 Çok uzun bir konu başlığı numara 4 "', h, "full title on hover")
        self.assertIn('data-track="konu-00" data-default="harita"', h, "no lessons → its map")
        self.assertIn('data-src="../tracks/konu-02/lessons/0002-x.html"', h)
        self.assertNotIn('class="docs"', h, "no notes anywhere → no notes column")
        self.assertNotRegex(h, r'src="https?://|<link (?!rel="icon" href="data:)|<script src|@import|url\(http')

    def test_writes_refresh_the_dashboard(self):
        self.build()
        page = self.root / "learner/dashboard.html"
        self.assertFalse(page.exists(), "the harness turns auto-refresh off (TEACH_NO_DASHBOARD=1)")
        r = self.run_learn("moment", "--kind", "recap", TEACH_NO_DASHBOARD="0")
        self.assertTrue(page.exists(), "a write regenerates learner/dashboard.html")
        self.assertEqual(r.stderr, "")
        self.assertIn("recorded", json.loads(r.stdout))
        before = page.read_text(encoding="utf-8")
        self.run_learn("record", "--card", self.mcq, "--choice", "A", "--source", "lesson", TEACH_NO_DASHBOARD="0")
        self.assertNotEqual(page.read_text(encoding="utf-8"), before, "updated after the next write")
        self.run_learn("status", TEACH_NO_DASHBOARD="0")
        # a dashboard failure never changes the write: same exit code, stdout still the command's JSON
        page.unlink()
        page.mkdir()
        r = self.run_learn("moment", "--kind", "recap", TEACH_NO_DASHBOARD="0", check=False)
        self.assertEqual(r.returncode, 0)
        self.assertIn("recorded", json.loads(r.stdout))
        self.assertIn("dashboard not refreshed", r.stderr)
        self.assertEqual(r.stderr.count("\n"), 1, "one stderr line")
        # no learner/ → nothing written
        page.rmdir()
        self.assertFalse(page.exists())

    def test_default_path_is_learner_dashboard(self):
        self.build()
        before = {f: f.read_bytes() for f in self.root.rglob("*") if f.is_file()}
        r = self.run_learn("dashboard")
        self.assertEqual(r.stdout.strip(), "learner/dashboard.html")
        after = {f: f.read_bytes() for f in self.root.rglob("*") if f.is_file()}
        self.assertEqual(set(after) - set(before), {self.root / "learner/dashboard.html"})
        self.assertEqual({f: b for f, b in after.items() if f in before}, before, "nothing else changes")


class TestRefresh(DashCase):
    def lesson(self, name, body):
        f = self.root / "tracks/demo/lessons" / name
        f.write_text(body, encoding="utf-8")
        return f

    def test_refresh_writes_export_dashboard_and_lesson_maps(self):
        self.build()
        with_map = self.lesson("0003-c.html", '<title>Üç</title><!-- lesson-map: --track demo --nodes pd,nash --current pd -->'
                               '<div class="lmap-slot"><svg class="lmap"></svg></div><p>metin</p>')
        without = self.lesson("0004-d.html", '<title>Dört</title><svg class="lmap"></svg>')
        broken = self.lesson("0005-e.html", '<!-- lesson-map: --track demo --nodes nope --><svg class="lmap"></svg>')
        before_without, before_broken = without.read_bytes(), broken.read_bytes()
        r = self.json_of("refresh")
        self.assertEqual(r["lessons_updated"], ["tracks/demo/lessons/0003-c.html"])
        self.assertEqual(len(r["problems"]), 1)
        self.assertIn("0005-e.html", r["problems"][0])
        exp = json.loads((self.root / "learner/export.json").read_text(encoding="utf-8"))
        self.assertIs(exp["generated"], True)
        self.assertEqual(exp["schema"], "teach.export/1")
        raw = (self.root / "learner/export.json").read_text(encoding="utf-8")
        for sec in SECRETS:
            self.assertNotIn(sec, raw, f"export.json leaks {sec}")
        self.assertTrue((self.root / "learner/dashboard.html").exists())
        text = with_map.read_text(encoding="utf-8")
        self.assertEqual(text.count('<svg class="lmap"'), 1)
        self.assertRegex(text, r'class="node [\w-]+ focus next"[^>]*data-node="nash"', "filled from the comment")
        self.assertTrue(text.endswith("</svg></div><p>metin</p>"), "only the svg block is replaced")
        self.assertEqual(without.read_bytes(), before_without, "no comment → untouched")
        self.assertEqual(broken.read_bytes(), before_broken, "bad comment → untouched, reported")
        mtime = with_map.stat().st_mtime_ns
        self.assertEqual(self.json_of("refresh")["lessons_updated"], [], "idempotent")
        self.assertEqual(with_map.stat().st_mtime_ns, mtime, "unchanged lesson is not rewritten")
        self.assertEqual(self.run_learn("refresh", "--quiet").stdout, "")

    def test_dashboard_renders_from_the_export_alone(self):
        self.build()
        self.run_learn("refresh")
        L = load_engine(self.root)
        exp = json.loads((self.root / "learner/export.json").read_text(encoding="utf-8"))
        os.environ["TEACH_TODAY"] = DAY0
        try:
            from_file = L.render_dashboard(exp, self.root / "learner")
            for f in ("attempts.jsonl", "cards.jsonl", "handoff.md"):  # gone: the page must not need them
                (self.root / "tracks/demo" / f).unlink()
            (self.root / "tracks/demo/lessons/0001-a.html").unlink()
            self.assertEqual(L.render_dashboard(exp, self.root / "learner"), from_file)
        finally:
            del os.environ["TEACH_TODAY"]

    def test_writes_run_refresh(self):
        self.build()
        self.run_learn("moment", "--kind", "recap", TEACH_NO_DASHBOARD="0")
        self.assertTrue((self.root / "learner/export.json").exists())
        self.assertTrue((self.root / "learner/dashboard.html").exists())


class TestRefreshHook(DashCase):
    HOOK = REPO / ".claude/hooks/refresh_after_edit.py"

    def hook(self, payload, **env):
        e = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root), TEACH_TODAY=DAY0)
        e.pop("TEACH_NO_DASHBOARD", None)
        e.update(env)
        return subprocess.run([sys.executable, str(self.HOOK)], input=payload, capture_output=True, text=True, env=e,
                              timeout=60)

    def test_refreshes_only_for_tracks_and_learner_edits(self):
        self.build()
        exp = self.root / "learner/export.json"
        for payload in ('{"tool_input": {"file_path": "%s"}}' % (self.root / "workspace/x.py"),
                        '{"tool_input": {"file_path": "%s"}}' % (self.root / "learner/export.json"),
                        '{"tool_input": {"file_path": "%s"}}' % (self.root / "learner/dashboard.html"),
                        '{"tool_input": {}}', "not json", ""):
            r = self.hook(payload)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), payload)
            self.assertFalse(exp.exists(), payload)
        r = self.hook('{"tool_input": {"file_path": "tracks/demo/map.md"}}')
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertTrue(exp.exists(), "a relative tracks/ path refreshes")
        exp.unlink()
        self.hook('{"tool_input": {"file_path": "%s"}}' % (self.root / "learner/profile.md"), TEACH_NO_DASHBOARD="1")
        self.assertFalse(exp.exists(), "TEACH_NO_DASHBOARD=1 turns it off")
        (self.root / "tracks/demo/map.md").write_text("broken", encoding="utf-8")
        r = self.hook('{"tool_input": {"file_path": "%s"}}' % (self.root / "tracks/demo/map.md"))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), "never errors the session")

    def test_settings_register_the_hooks(self):
        s = json.loads((REPO / ".claude/settings.json").read_text(encoding="utf-8"))
        post = s["hooks"]["PostToolUse"][0]
        self.assertEqual(post["matcher"], "Edit|Write|MultiEdit")
        self.assertIn("refresh_after_edit.py", post["hooks"][0]["command"])
        self.assertLessEqual(post["hooks"][0]["timeout"], 30)
        self.assertIn("tools/learn refresh --quiet", s["hooks"]["SessionStart"][0]["hooks"][0]["command"])


class TestLessonMap(DashCase):
    def test_lesson_map_svg(self):
        self.build()
        svg = self.run_learn("lesson-map", "--track", "demo", "--nodes", "best-response,nash").stdout
        self.assertTrue(svg.startswith('<svg class="lmap" '), svg[:80])
        self.assertTrue(svg.rstrip().endswith("</svg>"))
        self.assertEqual(svg, self.run_learn("lesson-map", "--track", "demo", "--nodes", "best-response,nash").stdout)
        self.assertEqual(svg.count("<style>"), 1)
        css = re.search(r"<style>(.*?)</style>", svg, re.S).group(1)
        self.assertTrue(all(rule.strip().startswith(".lmap") for rule in css.split("}") if rule.strip()),
                        "every rule is scoped to .lmap")
        tokens = (REPO / "assets" / "style.css").read_text(encoding="utf-8")
        for var in set(re.findall(r"var\((--[\w-]+)", css)):
            self.assertIn(var + ":", tokens, f"{var} is a style.css token")
        self.assertRegex(svg, r'class="node lv-new focus"[^>]*data-node="best-response"', "the lesson's nodes in focus")
        self.assertRegex(svg, r'class="node lv-learn focus next"[^>]*data-node="nash"', "yellow = the track's next node")
        self.assertRegex(svg, r'class="node [\w-]+ dim"[^>]*data-node="pd"')
        self.assertEqual(svg.count('class="glow"'), 1)
        self.assertIn("A game is players, strategies, payoffs.", svg, "node <title> carries the statement")
        for sec in SECRETS[:-2]:
            self.assertNotIn(sec, svg)
        self.assertNotRegex(svg, r'(src|href)="https?://|<link |<script|@import')
        cur = self.run_learn("lesson-map", "--track", "demo", "--nodes", "pd,game-def", "--current", "pd").stdout
        self.assertRegex(cur, r'class="node [\w-]+ dim next"[^>]*data-node="nash"', "--current is ignored; next stays nash")
        self.assertNotRegex(cur, r'class="node [\w-]+ focus next"[^>]*data-node="pd"')
        self.assertRegex(cur, r'class="node [\w-]+ focus"[^>]*data-node="pd"')
        r = self.run_learn("lesson-map", "--track", "demo", "--nodes", "nope", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown node", r.stderr)
        self.assertNotEqual(self.run_learn("lesson-map", "--track", "missing", "--nodes", "a", check=False).returncode, 0)

    def test_glow_is_only_the_next_node(self):
        self.build()
        svg = self.run_learn("lesson-map", "--track", "demo", "--nodes", "pd").stdout
        self.assertEqual(len(re.findall(r'class="node [^"]*next"', svg)), 1)
        self.assertRegex(svg, r'class="node [\w-]+ dim next"[^>]*data-node="nash"')
        self.assertRegex(svg, r'class="node lv-new focus"[^>]*data-node="pd"')
        self.assertIn(".lmap .node.focus .box{stroke:var(--ink,#1a1a1a);stroke-width:1.6;stroke-dasharray:none}", svg)


class TestLayouts(EngineCase):
    def dag(self, n=20, seed=3):
        import random as R
        rng = R.Random(seed)
        ids = [f"n{i}" for i in range(n)]
        edges = [(ids[a], ids[b]) for b in range(1, n) for a in rng.sample(range(b), min(b, rng.randint(1, 3)))]
        sizes = {i: (60 + 7 * (int(i[1:]) % 5), 31 + 15 * (int(i[1:]) % 2)) for i in ids}
        return ids, edges, sizes

    def test_dag_layout_layers_and_no_overlap(self):
        L = load_engine(self.root)
        ids, edges, sizes = self.dag()
        lay = L.dag_layout(ids, edges, sizes)
        self.assertEqual(lay, L.dag_layout(ids, edges, sizes), "deterministic")
        self.assertEqual(lay["back"], [])
        for a, b in edges:
            self.assertGreater(lay["layer"][b], lay["layer"][a], f"{a}->{b} goes forward")
        boxes = [(lay["pos"][i][0], lay["pos"][i][1], sizes[i][0], sizes[i][1]) for i in ids]
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                x1, y1, w1, h1 = boxes[i]
                x2, y2, w2, h2 = boxes[j]
                self.assertFalse(x1 < x2 + w2 and x2 < x1 + w1 and y1 < y2 + h2 and y2 < y1 + h1,
                                 f"{ids[i]} overlaps {ids[j]}")
        for i in ids:
            x, y = lay["pos"][i]
            self.assertTrue(0 <= x and x + sizes[i][0] <= lay["width"] and 0 <= y and y + sizes[i][1] <= lay["height"])
        self.assertEqual(len(lay["routes"]), len(set(edges)))
        for a, b, pts in lay["routes"]:
            ys = [p[1] for p in pts]
            self.assertEqual(ys, sorted(ys), "routes run downward")
        # a cycle never hangs or crashes: the closing edge is reported as a back edge
        cyc = L.dag_layout(["a", "b"], [("a", "b"), ("b", "a")], {"a": (60, 30), "b": (60, 30)})
        self.assertEqual(cyc["back"], [("b", "a")])

    def test_force_layout_deterministic(self):
        L = load_engine(self.root)
        keys = [("t1", f"a{i}") for i in range(8)] + [("t2", f"b{i}") for i in range(8)]
        groups = {k: k[0] for k in keys}
        edges = [(keys[i], keys[i + 1]) for i in range(7)] + [(keys[8 + i], keys[9 + i]) for i in range(7)]
        p1 = L.force_layout(keys, groups, edges, 760, 440)
        self.assertEqual(p1, L.force_layout(keys, groups, edges, 760, 440))
        self.assertTrue(all(0 <= x <= 760 and 0 <= y <= 440 for x, y in p1.values()))
        mean = lambda g: sum(p1[k][0] for k in keys if k[0] == g) / 8
        self.assertLess(mean("t1"), mean("t2"), "each track stays its own cluster")

    def test_markdown_escapes(self):
        L = load_engine(self.root)
        h = L.md_to_html("## T <x>\n\n- **a** `<b>`\n- [s](https://e.org) [r](x.md)\n\n```\n<raw>\n```\n")
        self.assertIn("<h4>T &lt;x&gt;</h4>", h)
        self.assertIn("<li><strong>a</strong> <code>&lt;b&gt;</code></li>", h)
        self.assertIn('<a href="https://e.org" target="_blank" rel="noopener">s</a> r', h)
        self.assertIn("<pre><code>&lt;raw&gt;</code></pre>", h)


if __name__ == "__main__":
    unittest.main()
