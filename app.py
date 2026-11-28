"""Dhun - a free, Suno-style AI music web app.

Run:  python app.py        (ENGINE=hf|modal|ace for real AI, default demo)
"""
import os
import queue
import sqlite3
import threading
import time
import traceback
import uuid

from flask import Flask, jsonify, request, send_file, send_from_directory, abort, make_response

import engines
import media
import voiceover
from auth import init_auth

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DATA_DIR", os.path.join(BASE, "data"))
SONGS = os.path.join(DATA, "songs")
os.makedirs(SONGS, exist_ok=True)
DB = os.path.join(DATA, "dhun.db")

ENGINE = os.environ.get("ENGINE", "demo")           # demo | ace
MAX_DURATION = int(os.environ.get("MAX_DURATION", "600"))   # seconds (10 min)
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "0"))      # generations per user per day (0 = unlimited)
MAX_QUEUE = int(os.environ.get("MAX_QUEUE", "100"))

LANGS = {"hi": "Hindi", "en": "English", "bn": "Bengali", "pa": "Punjabi", "mr": "Marathi"}
# Voice presets (our own, not copies of any real person or other app's voices).
VOICES = {
    "auto": {"name": "Auto", "gender": "", "caption": ""},
    "adil": {"name": "Adil", "gender": "male", "caption": "warm male baritone lead vocal, smooth, emotional"},
    "rohan": {"name": "Rohan", "gender": "male", "caption": "young male tenor lead vocal, bright and energetic"},
    "meera": {"name": "Meera", "gender": "female", "caption": "soft female lead vocal, sweet and airy"},
    "sana": {"name": "Sana", "gender": "female", "caption": "powerful female lead vocal, rich and expressive"},
    "kabir": {"name": "Kabir", "gender": "male", "caption": "deep husky male lead vocal, raw and soulful"},
    "arjun": {"name": "Arjun", "gender": "male", "caption": "classically trained male lead vocal, clear, strong high notes"},
    "riya": {"name": "Riya", "gender": "female", "caption": "young female pop lead vocal, playful and bright"},
    "gauri": {"name": "Gauri", "gender": "female", "caption": "classically trained female lead vocal, pure tone, graceful ornaments"},
}
# Emotion presets: added to the voice description so the same singer can sound sad, happy, devotional...
EMOTIONS = {
    "auto": {"name": "Auto", "caption": ""},
    "romantic": {"name": "💕 Romantic", "caption": "tender romantic delivery, warm and intimate"},
    "sad": {"name": "💧 Sad / Dard", "caption": "sad heartbroken delivery, emotional, breathy, slow"},
    "happy": {"name": "😊 Happy", "caption": "happy cheerful delivery, smiling tone, light"},
    "devotional": {"name": "🙏 Bhakti", "caption": "devotional bhajan delivery, peaceful, spiritual, heartfelt"},
    "sufi": {"name": "✨ Sufi", "caption": "soulful sufi delivery, passionate, long sustained notes"},
    "party": {"name": "🔥 Party / Josh", "caption": "high energy party delivery, powerful, punchy"},
    "motivational": {"name": "💪 Motivational", "caption": "inspiring anthemic delivery, confident, rising intensity"},
    "lori": {"name": "🌙 Lori / Shaant", "caption": "calm soothing lullaby delivery, gentle and soft"},
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "300")) * 1024 * 1024
init_auth(app, DATA)
Q = queue.Queue()
db_lock = threading.Lock()


def conn():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS songs(
            id TEXT PRIMARY KEY, uid TEXT, grp TEXT, variant INTEGER,
            title TEXT, prompt TEXT, lyrics TEXT, styles TEXT, exclude TEXT,
            instrumental INTEGER, duration REAL, actual REAL, quality TEXT,
            status TEXT, error TEXT, public INTEGER, created REAL,
            video TEXT DEFAULT 'none', engine TEXT,
            creator TEXT DEFAULT '', language TEXT DEFAULT '', voice TEXT DEFAULT '', plays INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT, text TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS likes(uid TEXT, song TEXT, PRIMARY KEY(uid, song));
        CREATE TABLE IF NOT EXISTS usage(uid TEXT, day TEXT, n INTEGER, PRIMARY KEY(uid, day));
        """)
        for col, typ in (("creator", "TEXT DEFAULT ''"), ("language", "TEXT DEFAULT ''"),
                         ("voice", "TEXT DEFAULT ''"), ("plays", "INTEGER DEFAULT 0")):
            try:
                c.execute(f"ALTER TABLE songs ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass
        # anything left running from a previous process is dead
        c.execute("UPDATE songs SET status='failed', error='Server restarted' WHERE status IN ('pending','running')")
        c.execute("UPDATE songs SET video='failed' WHERE video='pending'")


init_db()


# ------------------------------------------------------------------ identity
def uid():
    return "owner"   # single-user app: every request is already behind the login


def song_dir(sid):
    return os.path.join(SONGS, sid)


def row_to_json(r, me, likes):
    return {
        "id": r["id"], "title": r["title"], "styles": r["styles"], "prompt": r["prompt"],
        "lyrics": r["lyrics"], "instrumental": bool(r["instrumental"]),
        "duration": r["actual"] or r["duration"], "status": r["status"], "error": r["error"],
        "public": bool(r["public"]), "mine": r["uid"] == me, "video": r["video"],
        "created": r["created"], "liked": r["id"] in likes, "engine": r["engine"],
        "likes": r["nlikes"] if "nlikes" in r.keys() else 0,
        "creator": r["creator"] or "Guest", "language": r["language"] or "", "voice": r["voice"] or "",
        "plays": r["plays"] or 0,
    }


def left_today(u):
    if not DAILY_LIMIT:
        return None
    day = time.strftime("%Y-%m-%d")
    with conn() as c:
        row = c.execute("SELECT n FROM usage WHERE uid=? AND day=?", (u, day)).fetchone()
    return max(0, DAILY_LIMIT - (row["n"] if row else 0))


# ------------------------------------------------------------------ pages / api
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/audio-to-video")
def audio_to_video():
    """Standalone in-browser Audio -> Video maker (no upload; renders client-side)."""
    return send_from_directory(BASE, "audio_to_video.html")


@app.route("/api/to-mp4", methods=["POST"])
def to_mp4():
    """Convert a browser-recorded clip (WebM / VP9 MP4) to a universal H.264+AAC MP4."""
    import io, shutil, subprocess, tempfile
    f = request.files.get("file")
    if not f:
        abort(400)
    tmp = tempfile.mkdtemp(prefix="a2v_")
    try:
        src, dst = os.path.join(tmp, "in"), os.path.join(tmp, "out.mp4")
        f.save(src)
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", dst],
                           capture_output=True, timeout=1800)
        if r.returncode != 0 or not os.path.exists(dst):
            return jsonify(error="convert failed"), 500
        with open(dst, "rb") as fh:
            data = io.BytesIO(fh.read())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return send_file(data, mimetype="video/mp4", as_attachment=True, download_name="video.mp4")


@app.route("/api/config")
def config():
    u = uid()
    return jsonify(engine=ENGINE, max_duration=MAX_DURATION, daily_left=left_today(u),
                   daily_limit=DAILY_LIMIT)


@app.route("/api/generate", methods=["POST"])
def generate():
    u = uid()
    d = request.get_json(force=True, silent=True) or {}
    prompt = (d.get("prompt") or "").strip()[:500]
    lyrics = (d.get("lyrics") or "").strip()[:5000]
    styles = (d.get("styles") or "").strip()[:200]
    exclude = (d.get("exclude") or "").strip()[:200]
    instrumental = bool(d.get("instrumental"))
    language = d.get("language") if d.get("language") in LANGS else ""
    voice = d.get("voice") if d.get("voice") in VOICES else "auto"
    emotion = d.get("emotion") if d.get("emotion") in EMOTIONS else "auto"
    if emotion != "auto":
        voice = f"{voice}:{emotion}"   # stored together, e.g. "meera:sad"
    creator = "".join(ch for ch in (d.get("creator") or "").strip()[:30] if ch.isalnum() or ch in " ._-") or ("Guest-" + u[:4])
    title = (d.get("title") or "").strip()[:80]
    quality = d.get("quality") if d.get("quality") in ("fast", "high") else "fast"
    try:
        duration = float(d.get("duration", 120))
    except (TypeError, ValueError):
        duration = 120
    duration = max(30.0, min(float(MAX_DURATION), duration))
    if not (prompt or lyrics or styles):
        return jsonify(error="Describe your song, add lyrics or pick a style."), 400
    if DAILY_LIMIT and left_today(u) <= 0:
        return jsonify(error=f"Daily limit of {DAILY_LIMIT} generations reached. Come back tomorrow!"), 429
    if Q.qsize() >= MAX_QUEUE:
        return jsonify(error="Server is busy, try again in a minute."), 429

    grp = uuid.uuid4().hex
    ids = []
    now = time.time()
    day = time.strftime("%Y-%m-%d")
    with db_lock, conn() as c:
        for v in (0, 1):
            sid = uuid.uuid4().hex
            t = title or (prompt[:40] or styles[:40] or "Untitled")
            c.execute("INSERT INTO songs(id,uid,grp,variant,title,prompt,lyrics,styles,exclude,"
                      "instrumental,duration,quality,status,public,created,engine,creator,language,voice) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (sid, u, grp, v, t if v == 0 else f"{t} (v2)", prompt, lyrics, styles, exclude,
                       int(instrumental), duration, quality, "pending", int(d.get("public", True)), now, ENGINE,
                       creator, language, voice))
            ids.append(sid)
        c.execute("INSERT INTO usage(uid,day,n) VALUES(?,?,1) ON CONFLICT(uid,day) DO UPDATE SET n=n+1", (u, day))
    Q.put(("gen", ids))
    return jsonify(ids=ids, daily_left=left_today(u))


def _list(where, args, u, limit=100, order="created DESC, variant ASC"):
    with conn() as c:
        likes = {r["song"] for r in c.execute("SELECT song FROM likes WHERE uid=?", (u,))}
        rows = c.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM likes l WHERE l.song=s.id) AS nlikes FROM songs s "
            f"WHERE {where} ORDER BY {order} LIMIT {int(limit)}", args).fetchall()
    return [row_to_json(r, u, likes) for r in rows]


@app.route("/api/songs")
def my_songs():
    u = uid()
    q = (request.args.get("q") or "").strip()
    if q:
        return jsonify(_list("uid=? AND (title LIKE ? OR styles LIKE ?)", (u, f"%{q}%", f"%{q}%"), u, 300))
    return jsonify(_list("uid=?", (u,), u, 300))


@app.route("/api/explore")
def explore():
    u = uid()
    if request.args.get("sort") == "top":
        return jsonify(_list("public=1 AND status='ready'", (), u, 30, "plays DESC, created DESC"))
    return jsonify(_list("public=1 AND status='ready'", (), u, 30))


@app.route("/api/songs/<sid>")
def one_song(sid):
    u = uid()
    rows = _list("id=? AND (public=1 OR uid=?)", (sid, u), u, 1)
    if not rows:
        abort(404)
    return jsonify(rows[0])


def _owned(sid):
    u = uid()
    with conn() as c:
        r = c.execute("SELECT * FROM songs WHERE id=? AND uid=?", (sid, u)).fetchone()
    if not r:
        abort(404)
    return r


@app.route("/api/songs/<sid>", methods=["PATCH"])
def patch_song(sid):
    _owned(sid)
    d = request.get_json(force=True, silent=True) or {}
    with conn() as c:
        if "title" in d:
            c.execute("UPDATE songs SET title=? WHERE id=?", (str(d["title"])[:80], sid))
        if "public" in d:
            c.execute("UPDATE songs SET public=? WHERE id=?", (int(bool(d["public"])), sid))
    return jsonify(ok=True)


@app.route("/api/songs/<sid>", methods=["DELETE"])
def delete_song(sid):
    _owned(sid)
    with conn() as c:
        c.execute("DELETE FROM songs WHERE id=?", (sid,))
        c.execute("DELETE FROM likes WHERE song=?", (sid,))
    import shutil
    shutil.rmtree(song_dir(sid), ignore_errors=True)
    return jsonify(ok=True)


@app.route("/api/voices")
def voices():
    return jsonify(voices=[{"id": k, "name": v["name"], "gender": v["gender"]} for k, v in VOICES.items()],
                   emotions=[{"id": k, "name": v["name"]} for k, v in EMOTIONS.items()],
                   languages=[{"id": k, "name": v} for k, v in LANGS.items()])


@app.route("/api/songs/<sid>/play", methods=["POST"])
def played(sid):
    with conn() as c:
        c.execute("UPDATE songs SET plays=plays+1 WHERE id=? AND status='ready'", (sid,))
    return jsonify(ok=True)


@app.route("/api/feedback", methods=["POST"])
def feedback():
    u = uid()
    text = ((request.get_json(force=True, silent=True) or {}).get("text") or "").strip()[:1000]
    if not text:
        return jsonify(error="Empty"), 400
    with conn() as c:
        c.execute("INSERT INTO feedback(uid,text,created) VALUES(?,?,?)", (u, text, time.time()))
    print("FEEDBACK:", text, flush=True)
    return jsonify(ok=True)


@app.route("/api/songs/<sid>/like", methods=["POST"])
def like(sid):
    u = uid()
    with conn() as c:
        if c.execute("SELECT 1 FROM likes WHERE uid=? AND song=?", (u, sid)).fetchone():
            c.execute("DELETE FROM likes WHERE uid=? AND song=?", (u, sid)); liked = False
        else:
            c.execute("INSERT INTO likes VALUES(?,?)", (u, sid)); liked = True
    return jsonify(liked=liked)


@app.route("/api/songs/<sid>/video", methods=["POST"])
def make_video(sid):
    r = _owned(sid)
    if r["status"] != "ready":
        return jsonify(error="Song is not ready yet."), 400
    if r["video"] in ("pending", "ready"):
        return jsonify(video=r["video"])
    with conn() as c:
        c.execute("UPDATE songs SET video='pending' WHERE id=?", (sid,))
    Q.put(("video", sid))
    return jsonify(video="pending")


def _file(sid, name, mime, dl_name=None):
    u = uid()
    with conn() as c:
        r = c.execute("SELECT * FROM songs WHERE id=? AND (public=1 OR uid=?)", (sid, u)).fetchone()
    p = os.path.join(song_dir(sid), name)
    if not r or not os.path.exists(p):
        abort(404)
    safe = "".join(ch for ch in (r["title"] or "song") if ch.isalnum() or ch in " -_") .strip() or "song"
    if dl_name:
        return send_file(p, mimetype=mime, as_attachment=True, download_name=f"{safe}.{dl_name}")
    return send_file(p, mimetype=mime, conditional=True)


@app.route("/media/<sid>/audio.mp3")
def audio(sid):
    return _file(sid, "audio.mp3", "audio/mpeg")


@app.route("/media/<sid>/cover.jpg")
def cover(sid):
    return _file(sid, "cover.jpg", "image/jpeg")


@app.route("/download/<sid>.mp3")
def dl_mp3(sid):
    return _file(sid, "audio.mp3", "audio/mpeg", "mp3")


@app.route("/download/<sid>.mp4")
def dl_mp4(sid):
    return _file(sid, "video.mp4", "video/mp4", "mp4")


@app.route("/media/<sid>/video.mp4")
def stream_mp4(sid):
    return _file(sid, "video.mp4", "video/mp4")


@app.route("/api/voiceover", methods=["POST"])
def create_voiceover():
    try:
        spec = voiceover.parse(request.get_json(force=True, silent=True))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if Q.qsize() >= MAX_QUEUE:
        return jsonify(error="Server is busy, try again in a minute."), 429
    sid = uuid.uuid4().hex
    script = "\n".join(s["text"] for s in spec["segments"])
    with db_lock, conn() as c:
        c.execute("INSERT INTO songs(id,uid,grp,variant,title,prompt,lyrics,styles,exclude,instrumental,duration,"
                  "quality,status,public,created,engine,creator,language,voice) "
                  "VALUES(?,?,?,0,?,?,?,?,'',0,0,'fast','pending',0,?,?,?,?,'auto')",
                  (sid, uid(), sid, spec["title"], "voice-over", script, spec["music_style"],
                   time.time(), ENGINE, "Owner", spec["language"]))
    Q.put(("voice", (sid, spec)))
    return jsonify(ids=[sid])


def do_voiceover(arg):
    sid, spec = arg
    d = song_dir(sid)
    work = os.path.join(d, "_tmp")
    os.makedirs(work, exist_ok=True)
    set_status([sid], status="running")
    try:
        out = os.path.join(d, "audio.mp3")
        voiceover.render(spec, engines.ENGINES[ENGINE], sid, work, out, MAX_DURATION)
        media.make_cover(sid, os.path.join(d, "cover.jpg"))
        set_status([sid], status="ready", actual=engines.probe_duration(out))
    except Exception as e:  # noqa
        traceback.print_exc()
        set_status([sid], status="failed", error=str(e)[:300])
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


# ------------------------------------------------------------------ worker
def set_status(ids, **kw):
    sets = ",".join(f"{k}=?" for k in kw)
    with conn() as c:
        for i in ids:
            c.execute(f"UPDATE songs SET {sets} WHERE id=?", (*kw.values(), i))


def do_generate(ids):
    with conn() as c:
        rows = [dict(c.execute("SELECT * FROM songs WHERE id=?", (i,)).fetchone()) for i in ids]
    if not rows or any(r is None for r in rows):
        return
    job = dict(rows[0]); job["id"] = rows[0]["grp"]
    job["exclude"] = rows[0]["exclude"]
    _v, _, _e = (rows[0]["voice"] or "auto").partition(":")
    job["voice_caption"] = ", ".join(x for x in (VOICES.get(_v, VOICES["auto"])["caption"],
                                                 EMOTIONS.get(_e, EMOTIONS["auto"])["caption"]) if x)
    job["language_name"] = LANGS.get(rows[0]["language"] or "", "")
    set_status(ids, status="running")
    work = os.path.join(song_dir(ids[0]), "_tmp")
    os.makedirs(work, exist_ok=True)
    try:
        gen = engines.ENGINES[rows[0]["engine"]]
        outs = []
        while len(outs) < len(ids):   # some engines return only one song per call
            part = os.path.join(work, str(len(outs)))
            os.makedirs(part, exist_ok=True)
            job["id"] = f'{rows[0]["grp"]}-{len(outs)}'
            got = gen(job, part, variants=len(ids) - len(outs))
            if not got:
                raise RuntimeError("Engine returned no audio")
            outs.extend(got)
        for sid, o, row in zip(ids, outs, rows):
            d = song_dir(sid)
            os.makedirs(d, exist_ok=True)
            engines.to_mp3(o["path"], os.path.join(d, "audio.mp3"), title=row["title"])
            media.make_cover(sid, os.path.join(d, "cover.jpg"))
            set_status([sid], status="ready", actual=engines.probe_duration(os.path.join(d, "audio.mp3")))
    except Exception as e:  # noqa
        traceback.print_exc()
        set_status(ids, status="failed", error=str(e)[:300])
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


def do_video(sid):
    with conn() as c:
        r = c.execute("SELECT * FROM songs WHERE id=?", (sid,)).fetchone()
    if not r:
        return
    d = song_dir(sid)
    try:
        media.make_video(os.path.join(d, "audio.mp3"), os.path.join(d, "cover.jpg"),
                         r["title"], r["styles"], os.path.join(d, "video.mp4"), d)
        set_status([sid], video="ready")
    except Exception:
        traceback.print_exc()
        set_status([sid], video="failed")


def worker():
    while True:
        kind, arg = Q.get()
        try:
            {"gen": do_generate, "video": do_video, "voice": do_voiceover}[kind](arg)
        finally:
            Q.task_done()


threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "7860"))
    print(f"Dhun running on http://0.0.0.0:{port}  engine={ENGINE}  max={MAX_DURATION}s")
    app.run(host="0.0.0.0", port=port, threaded=True)
