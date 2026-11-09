"""The current subject of the conversation, and the tools that find one."""
import json, re
from urllib.parse import unquote
from dataclasses import dataclass, field
from pathlib import Path

import httpx, yaml
from defusedxml import ElementTree

from .registry import META

ROOT = Path(__file__).resolve().parent.parent
SOURCES = yaml.safe_load((ROOT / "sources.yaml").read_text())["sources"]
SECTION_CHARS = 14000   # about 5K tokens, so a section, history and reply fit Gemma's 16K context
MAX_ITEMS = 6
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Shahrazad/1.0"}
TAGS = re.compile(r"<[^>]+>")


@dataclass
class Subject:
    kind: str                   # article or video
    title: str
    url: str
    sections: list = field(default_factory=list)
    index: int = 0
    questions: list = field(default_factory=list)   # prepared questions for the current section
    next_q: int = 0
    planned_for: int = -1                           # the section the questions were written for

    @property
    def text(self):
        return self.sections[self.index]


def split_sections(text):
    """Split long text at sentence or line ends so each section fits the model's context."""
    out, cur = [], ""
    for piece in re.split(r"(?<=[.؟!\n])\s+", text):
        if cur and len(cur) + len(piece) > SECTION_CHARS:
            out.append(cur.strip())
            cur = ""
        cur += piece + " "
    if cur.strip():
        out.append(cur.strip())
    return out or [""]


def numbered(items, heading):
    lines = [f"{i}. {x['title']}" + (f" - {x['summary']}" if x.get("summary") else "") for i, x in enumerate(items, 1)]
    return heading + "\n" + "\n".join(lines) + "\nOffer the learner two or three of these in simple Arabic and ask which one to discuss. When they choose, call open_item with its number."


def match_source(text):
    low = text.lower()
    for key, s in SOURCES.items():
        if any(a.lower() in low for a in s["aliases"]):
            return key
    return None


async def find_news(args, ctx):
    key = match_source(str(args.get("source", ""))) or match_source(ctx.user_text)
    if not key:
        return "That news source isn't configured. Known sources: " + ", ".join(s["name"] for s in SOURCES.values()) + ". Use web_search instead."
    r = await ctx.http.get(SOURCES[key]["feed"], headers=UA, timeout=20, follow_redirects=True)
    r.raise_for_status()
    items = []
    for it in ElementTree.fromstring(r.content).iter("item"):
        title, link = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
        if title and link.startswith("http"):
            items.append({"title": title, "summary": TAGS.sub("", it.findtext("description") or "").strip()[:220], "url": link})
    ctx.items = items[:MAX_ITEMS]
    ctx.skill = "news"
    return numbered(ctx.items, f"Latest headlines from {SOURCES[key]['name']}:") if ctx.items else "The feed had no headlines."


def real_url(url):
    """Search engines sometimes return a redirect; the real address is inside it."""
    m = re.search(r"/RU=([^/]+)/", url)
    return unquote(m.group(1)) if m else url


async def after_search(text, ctx):
    """Turn donsetch's search output into the session's numbered list."""
    urls = {}
    m = META.match(text)
    if m:
        meta = json.loads(m.group(1))
        for s in [meta] + meta.get("searches", []):
            urls.update({x["handle"]: real_url(x["url"]) for x in s.get("results", [])})
        text = text[m.end():]
    items, last = [], None
    for line in text.splitlines():
        h = re.match(r"\s*\d+\.\s+(\S+)\s+·\s+(.*?)\s+:\s+\S+(?:\s+·.*)?$", line)
        if h and h.group(1) in urls:
            last = {"title": h.group(2), "summary": "", "url": urls[h.group(1)]}
            items.append(last)
        elif last is not None and line.startswith("   ") and not last["summary"]:
            last["summary"] = line.strip()[:220]
    found = [x for x in items if x["url"].startswith("http")][:MAX_ITEMS]
    if not found:
        return "Nothing useful was found. Ask the learner for different words."
    ctx.items = found
    ctx.skill = "news"
    return numbered(ctx.items, "Search results:")


async def open_item(args, ctx):
    try:
        n = int(args.get("number"))
        item = ctx.items[n - 1] if n > 0 else None
    except (TypeError, ValueError, IndexError):
        item = None
    if not item:
        return "That number isn't in the list. Ask the learner which one they mean."
    text = await ctx.registry.mcp_call("donsetch", "web_fetch", {"url": item["url"], "max_chars": SECTION_CHARS})
    m = META.match(text)
    body = text[m.end():].strip() if m else text.strip()
    if len(body) < 200:
        return "That page couldn't be read. Offer the learner another item from the list."
    ctx.subject = Subject("article", item["title"], item["url"], [body[:SECTION_CHARS]])
    ctx.skill = "news"
    return f"Opened \"{item['title']}\". It is now the current subject."


async def next_section(args, ctx):
    s = ctx.subject
    if not s or len(s.sections) < 2:
        return "There are no more sections."
    if s.index + 1 >= len(s.sections):
        return "That was the last section of the video. Offer to wrap up or choose a new subject."
    s.index += 1
    return f"Moved to section {s.index + 1} of {len(s.sections)}."
