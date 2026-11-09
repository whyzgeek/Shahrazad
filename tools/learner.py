"""The learner's record: sessions, what was said, and errors grouped by grammar concept. Stored locally in data/learner.db."""
import json, os, re, sqlite3, time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("SHAHRAZAD_LEARNER_DB", ROOT / "data/learner.db"))

CARDS = yaml.safe_load((ROOT / "cards.yaml").read_text())
CONCEPTS = {k: v["title"] for k, v in CARDS.items()}
# Speech recognition mishears words but rarely invents a grammar pattern, so word-level errors in speech don't get cards.
NOT_IN_SPEECH = {"word_choice", "other"}
NOT_ARABIC = re.compile(r"[A-Za-z0-9٠-٩]")

SCHEMA = {"type": "object", "properties": {"errors": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {
    "wrong": {"type": "string"}, "right": {"type": "string"}, "concept": {"type": "string", "enum": [*CONCEPTS, "misheard"]}},
    "required": ["wrong", "right", "concept"]}},
    "correct_uses": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {"concept": {"type": "string", "enum": [*CONCEPTS]}, "quote": {"type": "string"}}, "required": ["concept", "quote"]}}}, "required": ["errors", "correct_uses"]}
INTERVAL_DAYS = [1, 3, 7, 21]   # gaps between follow-ups, growing as the learner succeeds
LEARNED_AFTER_DAYS = 2          # used correctly in free speech on this many different days

CHECKLIST = "\n".join(f"- {k}: {v['rule']}" for k, v in CARDS.items() if k not in ("word_choice", "other"))
PROMPT = f"""You review what an Arabic learner just said. The text may come from speech recognition.
Go through it carefully and list every genuine Modern Standard Arabic grammar error in the learner's own words. Check each noun with its adjective, each possessive phrase, each number and the noun after it, each verb, and each preposition. Report separate errors separately: one phrase can have several. If there are none, return an empty list.
Report only Arabic language errors. Never report facts about the world, names of people or places, numbers being wrong, disagreement with the material, or foreign words the learner mixed in.
Do not correct style or suggest alternatives to correct language. Do not rewrite a correct sentence. Vowel marks are normally missing, so don't report them unless a visible letter is wrong.
A short phrase answering the tutor is a fragment: judge it as a fragment, and don't require a full sentence, but still check the words it has.
"wrong" must be copied exactly from the learner's text and be as short as possible. "right" is the corrected form of just those words.
Use the concept "misheard" when a word makes no sense here and looks like a speech recognition mistake, not the learner's own error. Use "word_choice" for a real word used wrongly.

Concepts:
{CHECKLIST}"""

DIAC = re.compile(r"[ً-ْٰـ]")


def normal(s):
    s = re.sub("[إأآٱ]", "ا", DIAC.sub("", s)).replace("ى", "ي").replace("ة", "ه")
    return " ".join(re.sub(r"[^\w\s]", " ", s).split())


def clean_errors(text, found, source):
    """Keep only errors that really quote the learner, and mark which are trusted enough to track."""
    said = f" {normal(text)} "
    out, seen = [], set()
    for e in found:
        wrong, right, concept = normal(e.get("wrong", "")), normal(e.get("right", "")), e.get("concept", "other")
        if concept == "misheard" or concept not in CONCEPTS or not wrong or not right or wrong == right or NOT_ARABIC.search(e["wrong"] + e["right"]):
            continue
        if source == "voice" and concept in NOT_IN_SPEECH:
            continue
        if f" {wrong} " not in said or set(wrong.split()) & seen:  # overlapping reports of one mistake make one card
            continue
        seen.update(wrong.split())
        out.append({"wrong": e["wrong"].strip(), "right": e["right"].strip(), "concept": concept, "tracked": True})
    return out


async def find_errors(text, last_tutor, http, llm_url, source, practising=()):
    """Returns (errors, concepts from `practising` the learner used correctly)."""
    user = (f"The tutor had just said: {last_tutor}\n\n" if last_tutor else "") + f"The learner said: {text}"
    if practising:
        user += "\n\nIn correct_uses, list any of these concepts that the learner clearly used correctly, quoting the exact words that show it. Include one only if those words are a real example of that structure, and leave the list empty otherwise: " + ", ".join(practising)
    else:
        user += "\n\nReturn an empty correct_uses list."
    body = {"messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": user}], "max_tokens": 500, "temperature": 0, "id_slot": 1,
            "chat_template_kwargs": {"enable_thinking": False}, "response_format": {"type": "json_schema", "json_schema": {"schema": SCHEMA}}}
    r = await http.post(llm_url, json=body, timeout=90)
    r.raise_for_status()
    data = json.loads(r.json()["choices"][0]["message"]["content"])
    errors = clean_errors(text, data["errors"], source)
    wrong_concepts = {e["concept"] for e in errors}
    said = f" {normal(text)} "
    uses = [u["concept"] for u in data.get("correct_uses", []) if len(normal(u.get("quote", "")).split()) >= 2 and f" {normal(u['quote'])} " in said]
    return errors, [c for c in dict.fromkeys(uses) if c in practising and c not in wrong_concepts]


async def check_target(text, concept, http, llm_url):
    """After a follow-up question: did the learner attempt this one structure, and get it right? Returns True, False, or None if not attempted."""
    card = CARDS[concept]
    ask = f"An Arabic learner is practising this rule: {card['rule']}\nThe learner said: {text}\nDid they use this structure at all, and if so was it correct? Ignore missing vowel marks, and ignore mistakes unrelated to this rule."
    schema = {"type": "object", "properties": {"used": {"type": "boolean"}, "correct": {"type": "boolean"}}, "required": ["used", "correct"]}
    body = {"messages": [{"role": "user", "content": ask}], "max_tokens": 40, "temperature": 0, "id_slot": 1, "chat_template_kwargs": {"enable_thinking": False}, "response_format": {"type": "json_schema", "json_schema": {"schema": schema}}}
    r = await http.post(llm_url, json=body, timeout=60)
    r.raise_for_status()
    d = json.loads(r.json()["choices"][0]["message"]["content"])
    return bool(d["correct"]) if d["used"] else None


class Learner:
    def __init__(self, path=DB_PATH):
        Path(path).parent.mkdir(exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, started REAL, ended REAL, title TEXT, state TEXT, updated REAL);
            CREATE TABLE IF NOT EXISTS turns(id INTEGER PRIMARY KEY, session INTEGER, at REAL, source TEXT, said TEXT, reply TEXT, subject TEXT);
            CREATE TABLE IF NOT EXISTS errors(id INTEGER PRIMARY KEY, turn INTEGER, at REAL, wrong TEXT, correct TEXT, concept TEXT, tracked INTEGER, dismissed INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS concepts(concept TEXT PRIMARY KEY, status TEXT DEFAULT 'new', first_seen REAL, last_seen REAL, times INTEGER DEFAULT 0, step INTEGER DEFAULT 0, due_at REAL, free_days TEXT DEFAULT '[]');
        """)
        for table, columns in (("sessions", ("title TEXT", "state TEXT", "updated REAL")), ("concepts", ("step INTEGER DEFAULT 0", "due_at REAL", "free_days TEXT DEFAULT '[]'"))):
            have = {r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")}
            for col in columns:
                if col.split()[0] not in have:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
        self.db.execute("UPDATE concepts SET status='practising', due_at=COALESCE(due_at, ?) WHERE status='new'", (time.time(),))
        self.db.execute("UPDATE sessions SET title='Earlier conversation' WHERE title IS NULL")
        self.db.commit()

    def start_session(self, title="New conversation"):
        now = time.time()
        cur = self.db.execute("INSERT INTO sessions(started,updated,title) VALUES(?,?,?)", (now, now, title))
        self.db.commit()
        return cur.lastrowid

    def save_session(self, sid, title, state):
        self.db.execute("UPDATE sessions SET title=?, state=?, updated=? WHERE id=?", (title, state, time.time(), sid))
        self.db.commit()

    def load_session(self, sid):
        row = self.db.execute("SELECT id, title, state FROM sessions WHERE id=?", (sid,)).fetchone()
        return dict(row) if row else None

    def latest_session(self):
        row = self.db.execute("SELECT id FROM sessions ORDER BY updated DESC, id DESC LIMIT 1").fetchone()
        return row["id"] if row else None

    def list_sessions(self, current, limit=40):
        """Sessions with something in them, plus the current one, most recent first."""
        rows = self.db.execute("SELECT s.id, s.title, s.updated, COUNT(t.id) AS turns FROM sessions s LEFT JOIN turns t ON t.session=s.id GROUP BY s.id HAVING turns>0 OR s.id=? ORDER BY s.updated DESC, s.id DESC LIMIT ?", (current, limit)).fetchall()
        return [dict(r) for r in rows]

    def session_turns(self, sid):
        return [dict(r) for r in self.db.execute("SELECT said, reply FROM turns WHERE session=? ORDER BY id", (sid,))]

    def session_errors(self, sid):
        rows = self.db.execute("SELECT e.id, e.wrong, e.correct, e.concept FROM errors e JOIN turns t ON t.id=e.turn WHERE t.session=? AND e.dismissed=0 ORDER BY e.id", (sid,)).fetchall()
        return [{"id": r["id"], "wrong": r["wrong"], "right": r["correct"], "key": r["concept"], "concept": CONCEPTS.get(r["concept"], r["concept"]), "reminder": CARDS.get(r["concept"], {}).get("reminder", ""), "tracked": True} for r in rows]

    def end_session(self, sid):
        self.db.execute("UPDATE sessions SET ended=? WHERE id=?", (time.time(), sid))
        self.db.commit()

    def add_turn(self, sid, source, said, reply, subject):
        cur = self.db.execute("INSERT INTO turns(session,at,source,said,reply,subject) VALUES(?,?,?,?,?,?)", (sid, time.time(), source, said, reply, subject))
        self.db.commit()
        return cur.lastrowid

    def add_errors(self, turn_id, errors):
        now, rows = time.time(), []
        for e in errors:
            cur = self.db.execute("INSERT INTO errors(turn,at,wrong,correct,concept,tracked) VALUES(?,?,?,?,?,?)", (turn_id, now, e["wrong"], e["right"], e["concept"], int(e["tracked"])))
            if e["tracked"]:
                # A new mistake makes the concept due again and sets its progress back a step.
                self.db.execute("INSERT INTO concepts(concept,status,first_seen,last_seen,times,step,due_at,free_days) VALUES(?,'practising',?,?,1,0,?,'[]') ON CONFLICT(concept) DO UPDATE SET status='practising', last_seen=excluded.last_seen, times=times+1, step=MAX(step-1,0), due_at=excluded.due_at, free_days='[]'", (e["concept"], now, now, now))
            rows.append({"id": cur.lastrowid, "wrong": e["wrong"], "right": e["right"], "key": e["concept"], "concept": CONCEPTS[e["concept"]], "reminder": CARDS[e["concept"]]["reminder"], "tracked": e["tracked"]})
        self.db.commit()
        return rows

    def seen_rules(self, limit=8):
        """Rules the learner has already met, most recent first, as one-line reminders."""
        rows = self.db.execute("SELECT concept FROM concepts WHERE times>=1 ORDER BY last_seen DESC LIMIT ?", (limit,)).fetchall()
        return [CARDS[r["concept"]]["reminder"] for r in rows if r["concept"] in CARDS]

    def practising(self):
        return [r["concept"] for r in self.db.execute("SELECT concept FROM concepts WHERE status='practising'")]

    def due_concepts(self, limit=5):
        rows = self.db.execute("SELECT concept FROM concepts WHERE status='practising' AND due_at IS NOT NULL AND due_at<=? ORDER BY due_at LIMIT ?", (time.time(), limit)).fetchall()
        return [r["concept"] for r in rows]

    def last_mistake(self, concept):
        row = self.db.execute("SELECT wrong, correct FROM errors WHERE concept=? AND dismissed=0 ORDER BY id DESC LIMIT 1", (concept,)).fetchone()
        return dict(row) if row else None

    def review_result(self, concept, success):
        """Move a concept along the follow-up schedule: further out after a success, back to tomorrow after a failure."""
        row = self.db.execute("SELECT step FROM concepts WHERE concept=?", (concept,)).fetchone()
        if not row:
            return
        days = INTERVAL_DAYS[row["step"]] if success else 1
        step = min(row["step"] + 1, len(INTERVAL_DAYS) - 1) if success else max(row["step"] - 1, 0)
        self.db.execute("UPDATE concepts SET step=?, due_at=? WHERE concept=?", (step, time.time() + days * 86400, concept))
        self.db.commit()

    def record_free_use(self, concepts):
        """Unprompted correct use. A concept counts as learned after this happens on two different days."""
        today = time.strftime("%Y-%m-%d")
        for c in concepts:
            row = self.db.execute("SELECT free_days FROM concepts WHERE concept=? AND status='practising'", (c,)).fetchone()
            if not row:
                continue
            days = json.loads(row["free_days"] or "[]")
            if today not in days:
                days.append(today)
            learned = len(days) >= LEARNED_AFTER_DAYS
            self.db.execute("UPDATE concepts SET free_days=?, status=?, due_at=? WHERE concept=?", (json.dumps(days), "learned" if learned else "practising", None if learned else time.time(), c)) if learned else self.db.execute("UPDATE concepts SET free_days=? WHERE concept=?", (json.dumps(days), c))
        self.db.commit()

    def weak_rules(self, limit=3):
        """The rules this learner trips on most, for steering the discussion toward them."""
        rows = self.db.execute("SELECT concept FROM concepts WHERE times>=1 ORDER BY times DESC, last_seen DESC LIMIT ?", (limit,)).fetchall()
        return [CARDS[r["concept"]]["title"] for r in rows if r["concept"] in CARDS]

    def dismiss(self, error_id):
        """The learner says this isn't what they said, so it stops counting."""
        row = self.db.execute("SELECT concept, tracked, dismissed FROM errors WHERE id=?", (error_id,)).fetchone()
        if not row or row["dismissed"]:
            return
        self.db.execute("UPDATE errors SET dismissed=1 WHERE id=?", (error_id,))
        if row["tracked"]:
            self.db.execute("UPDATE concepts SET times=times-1 WHERE concept=?", (row["concept"],))
            self.db.execute("DELETE FROM concepts WHERE concept=? AND times<=0", (row["concept"],))
        self.db.commit()
