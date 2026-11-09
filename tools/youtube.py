"""Load a YouTube video's Arabic captions as the current subject. Videos without Arabic captions are declined."""
import asyncio, html, json, re, sys, tempfile
from pathlib import Path

from .subjects import Subject, split_sections

URL = re.compile(r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:[^\s]*&)?v=|shorts/|live/)|youtu\.be/)([\w-]{11})")
TIMESTAMP = re.compile(r"^\d{2}:\d{2}.*-->")
TAG = re.compile(r"<[^>]+>")


def find_video(text):
    m = URL.search(text)
    return f"https://www.youtube.com/watch?v={m.group(1)}" if m else None


async def run(args, timeout):
    p = await asyncio.create_subprocess_exec(sys.executable, "-m", "yt_dlp", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, _ = await asyncio.wait_for(p.communicate(), timeout)
    except BaseException:
        p.kill()
        await p.wait()
        raise
    return p.returncode, out


def choose_track(info):
    """Prefer human captions. Automatic 'ar' tracks on non-Arabic videos are machine translations, so they are skipped."""
    subs, auto = info.get("subtitles") or {}, info.get("automatic_captions") or {}
    for key in subs:
        if key == "ar" or key.startswith("ar-"):
            return key, False
    if "ar-orig" in auto:
        return "ar-orig", True
    if "ar" in auto and str(info.get("language") or "").startswith("ar"):
        return "ar", True
    return None, False


def vtt_to_text(vtt):
    """Plain text from WebVTT. Automatic captions repeat each line as it scrolls, so repeats are dropped."""
    lines, seen = [], set()
    for raw in vtt.splitlines():
        s = raw.strip()
        if not s or s == "WEBVTT" or s.startswith(("Kind:", "Language:", "NOTE")) or s.isdigit() or TIMESTAMP.match(s):
            continue
        s = " ".join(html.unescape(TAG.sub("", s)).split())
        if s and s not in seen:
            seen.add(s)
            lines.append(s)
    return "\n".join(lines)


async def load(url):
    """Returns (subject, None) on success or (None, a message in Arabic for the learner)."""
    code, out = await run(["-J", "--skip-download", "--no-warnings", "--no-playlist", url], 45)
    if code or not out:
        return None, "عذراً، لم أستطع فتح هذا الفيديو. تأكد من الرابط من فضلك."
    info = json.loads(out)
    track, is_auto = choose_track(info)
    if not track:
        return None, "عذراً، هذا الفيديو ليس فيه ترجمة مكتوبة باللغة العربية. أرسل لي رابط فيديو آخر من فضلك."
    with tempfile.TemporaryDirectory() as d:
        write = "--write-auto-subs" if is_auto else "--write-subs"
        await run(["--skip-download", "--no-warnings", "--no-playlist", write, "--sub-langs", track, "--sub-format", "vtt", "-o", f"{d}/v.%(ext)s", url], 60)
        files = list(Path(d).glob("*.vtt"))
        if not files:
            return None, "عذراً، لم أستطع تحميل الترجمة. جرب مرة أخرى أو أرسل فيديو آخر."
        text = vtt_to_text(files[0].read_text(errors="replace"))
    if len(text) < 100:
        return None, "عذراً، الترجمة العربية في هذا الفيديو قصيرة جداً. أرسل لي فيديو آخر من فضلك."
    return Subject("video", info.get("title") or "YouTube video", url, split_sections(text)), None
