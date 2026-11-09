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
    "required": ["wrong", "right", "concept"]}}}, "required": ["errors"]}

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


async def find_errors(text, last_tutor, http, llm_url, source):
    user = (f"The tutor had just said: {last_tutor}\n\n" if last_tutor else "") + f"The learner said: {text}"
    body = {"messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": user}], "max_tokens": 500, "temperature": 0, "id_slot": 1,
            "chat_template_kwargs": {"enable_thinking": False}, "response_format": {"type": "json_schema", "json_schema": {"schema": SCHEMA}}}
    r = await http.post(llm_url, json=body, timeout=90)
    r.raise_for_status()
    return clean_errors(text, json.loads(r.json()["choices"][0]["message"]["content"])["errors"], source)


class Learner:
    def __init__(self, path=DB_PATH):
        Path(path).parent.mkdir(exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, started REAL, ended REAL);
            CREATE TABLE IF NOT EXISTS turns(id INTEGER PRIMARY KEY, session INTEGER, at REAL, source TEXT, said TEXT, reply TEXT, subject TEXT);
            CREATE TABLE IF NOT EXISTS errors(id INTEGER PRIMARY KEY, turn INTEGER, at REAL, wrong TEXT, correct TEXT, concept TEXT, tracked INTEGER, dismissed INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS concepts(concept TEXT PRIMARY KEY, status TEXT DEFAULT 'new', first_seen REAL, last_seen REAL, times INTEGER DEFAULT 0);
        """)

    def start_session(self):
        cur = self.db.execute("INSERT INTO sessions(started) VALUES(?)", (time.time(),))
        self.db.commit()
        return cur.lastrowid

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
                self.db.execute("INSERT INTO concepts(concept,first_seen,last_seen,times) VALUES(?,?,?,1) ON CONFLICT(concept) DO UPDATE SET last_seen=excluded.last_seen, times=times+1", (e["concept"], now, now))
            rows.append({"id": cur.lastrowid, "wrong": e["wrong"], "right": e["right"], "key": e["concept"], "concept": CONCEPTS[e["concept"]], "reminder": CARDS[e["concept"]]["reminder"], "tracked": e["tracked"]})
        self.db.commit()
        return rows

    def seen_rules(self, limit=8):
        """Rules the learner has already met, most recent first, as one-line reminders."""
        rows = self.db.execute("SELECT concept FROM concepts WHERE times>=1 ORDER BY last_seen DESC LIMIT ?", (limit,)).fetchall()
        return [CARDS[r["concept"]]["reminder"] for r in rows if r["concept"] in CARDS]

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
