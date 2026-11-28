"""Music engines for Dhun.

ace  : real AI engine (ACE-Step 1.5 REST API, up to 10 min, vocals + lyrics).
demo : built-in procedural instrumental synth (no GPU needed) so the whole app
       works end-to-end anywhere. It is NOT AI and has no vocals.
"""
import hashlib
import json
import os
import random
import subprocess
import time
import urllib.parse
import urllib.request
import wave

import numpy as np
from scipy.signal import oaconvolve

SR = 32000


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def to_mp3(src, dst, title="", artist="Dhun AI"):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn",
           "-codec:a", "libmp3lame", "-b:a", "192k",
           "-metadata", f"title={title}", "-metadata", f"artist={artist}", dst]
    subprocess.run(cmd, check=True)


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


# --------------------------------------------------------------------------
# ACE-Step engine (real AI)
# --------------------------------------------------------------------------
def _http_json(url, payload=None, headers=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {})
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _caption(job):
    caption = job["styles"] or job["prompt"]
    if job["prompt"] and job["styles"]:
        caption = f'{job["styles"]}. {job["prompt"]}'
    if job.get("voice_caption") and not job["instrumental"]:
        caption += f'. {job["voice_caption"]}'
    if job.get("language_name") and not job["instrumental"]:
        caption += f'. Sung in {job["language_name"]}'
    # "exclude" is deliberately not added: the model has no negation, so naming a sound
    # in the caption (e.g. "Avoid: autotune") can make it appear.
    return caption


def generate_ace(job, out_dir, variants=2):
    """Returns list of dicts {path, seed}. Needs `uv run acestep-api` running."""
    base = os.environ.get("ACESTEP_URL", "http://localhost:8001").rstrip("/")
    key = os.environ.get("ACESTEP_API_KEY", "")
    hdr = {"Authorization": f"Bearer {key}"} if key else {}

    caption = _caption(job)
    lyrics = "[Instrumental]" if job["instrumental"] else job["lyrics"]

    payload = {
        "prompt": caption,
        "lyrics": lyrics,
        "audio_duration": float(job["duration"]),
        "audio_format": "mp3",
        "batch_size": variants,
        "use_random_seed": True,
        "inference_steps": 8,
        "thinking": job.get("quality") == "high",
        "vocal_language": job.get("language") or "unknown",
    }
    res = _http_json(base + "/release_task", payload, hdr)
    task_id = res["data"]["task_id"]

    deadline = time.time() + 60 * 40
    while time.time() < deadline:
        time.sleep(4)
        q = _http_json(base + "/query_result", {"task_id_list": [task_id]}, hdr)
        item = q["data"][0]
        if item["status"] == 2:
            raise RuntimeError("ACE-Step generation failed")
        if item["status"] == 1:
            files = json.loads(item["result"])
            outs = []
            for i, f in enumerate(files[:variants]):
                url = f["file"]
                if url.startswith("/"):
                    url = base + url
                raw = os.path.join(out_dir, f"raw{i}.mp3")
                req = urllib.request.Request(url, headers=hdr)
                with urllib.request.urlopen(req, timeout=300) as r, open(raw, "wb") as fh:
                    fh.write(r.read())
                outs.append({"path": raw, "seed": f.get("seed_value")})
            return outs
    raise TimeoutError("ACE-Step timed out")


def generate_modal(job, out_dir, variants=1):
    """Serverless GPU on Modal (see modal_app.py). Env: MODAL_URL, MODAL_KEY."""
    base = os.environ.get("MODAL_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("MODAL_URL is not set")
    hdr = {"X-Api-Key": os.environ.get("MODAL_KEY", "")}
    payload = {
        "prompt": _caption(job),
        "lyrics": "[Instrumental]" if job["instrumental"] else job["lyrics"],
        "duration": float(job["duration"]),
        "language": job.get("language") or "unknown",
        "thinking": job.get("quality") == "high",
    }
    call_id = _http_json(base + "/submit", payload, hdr, timeout=120)["call_id"]
    deadline = time.time() + 60 * 40
    while time.time() < deadline:
        time.sleep(4)
        req = urllib.request.Request(base + "/result/" + call_id, headers=hdr)
        with urllib.request.urlopen(req, timeout=300) as r:
            if r.status == 202:
                continue
            raw = os.path.join(out_dir, "raw0.mp3")
            with open(raw, "wb") as fh:
                fh.write(r.read())
            return [{"path": raw, "seed": None}]
    raise TimeoutError("GPU job timed out")


def generate_hf(job, out_dir, variants=1):
    """Free: official ACE-Step Hugging Face Space (ZeroGPU). Env: HF_TOKEN, HF_SPACE (optional)."""
    host = os.environ.get("HF_SPACE", "https://ace-step-ace-step-v1-5.hf.space").rstrip("/")
    tok = os.environ.get("HF_TOKEN", "")
    hdr = {"Authorization": "Bearer " + tok} if tok else {}
    lang = job.get("language") or "unknown"
    # positional order of /generation_wrapper (49 inputs), defaults from the Space's API info
    data = [
        os.environ.get("HF_MODEL", "acestep-v15-turbo"), "custom", "", "unknown",
        _caption(job), "[Instrumental]" if job["instrumental"] else job["lyrics"],
        0, "", "", lang,
        8, 7.0, True, "-1", None,
        float(job["duration"]), 1, None, "",
        0.0, -1, "Fill the audio semantic mask based on the given conditions:", 1.0, "text2music",
        False, 0.0, 1.0, 3.0, "ode", "",
        "mp3", 0.85, job.get("quality") == "high", 2.0, 0, 0.9, "NO USER INPUT",
        True, True, True, False, True, False, False, 0.5, 8, None, [], False,
    ]
    assert len(data) == 49, len(data)
    ev = _http_json(host + "/gradio_api/call/generation_wrapper", {"data": data}, hdr, timeout=120)["event_id"]
    req = urllib.request.Request(host + "/gradio_api/call/generation_wrapper/" + ev, headers=hdr)
    event, payload = None, None
    with urllib.request.urlopen(req, timeout=60 * 25) as r:
        for raw in r:
            line = raw.decode("utf-8", "ignore").strip()
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:") and event in ("complete", "error"):
                payload = line[5:].strip()
                break
    if event != "complete" or payload is None:
        raise RuntimeError("HF Space error (quota/queue?): " + str(payload)[:300])
    outs = json.loads(payload)
    url = None
    for o in outs:
        if isinstance(o, dict) and (o.get("url") or o.get("path")):
            url = o.get("url") or (host + "/gradio_api/file=" + o["path"])
            break
    if not url:
        raise RuntimeError("HF Space returned no audio: " + str(payload)[:300])
    raw = os.path.join(out_dir, "raw0.mp3")
    with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=300) as r, open(raw, "wb") as fh:
        fh.write(r.read())
    return [{"path": raw, "seed": None}]


# --------------------------------------------------------------------------
# Demo engine: procedural instrumental synth
# --------------------------------------------------------------------------
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]
PHRYG_DOM = [0, 1, 4, 5, 7, 8, 10]   # raga-ish / Bollywood flavour
PENTA_MIN = [0, 3, 5, 7, 10]

PROFILES = {
    "lofi":    dict(bpm=(68, 84),  scale=MINOR, swing=0.14, drums="lofi",  lead="soft",  drone=False),
    "pop":     dict(bpm=(100, 122), scale=MAJOR, swing=0.0,  drums="four", lead="pluck", drone=False),
    "rock":    dict(bpm=(110, 140), scale=MINOR, swing=0.0,  drums="rock", lead="saw",   drone=False),
    "edm":     dict(bpm=(122, 130), scale=MINOR, swing=0.0,  drums="four", lead="saw",   drone=False),
    "hiphop":  dict(bpm=(78, 96),  scale=MINOR, swing=0.08, drums="trap", lead="soft",  drone=False),
    "classic": dict(bpm=(64, 90),  scale=MAJOR, swing=0.0,  drums=None,   lead="soft",  drone=False),
    "ambient": dict(bpm=(60, 76),  scale=PENTA_MIN, swing=0.0, drums=None, lead="soft", drone=True),
    "indian":  dict(bpm=(84, 108), scale=PHRYG_DOM, swing=0.0, drums="dhol", lead="pluck", drone=True),
    "acoustic": dict(bpm=(84, 108), scale=MAJOR, swing=0.0, drums="soft", lead="pluck", drone=False),
}
KEYWORDS = {
    "lofi": ["lofi", "lo-fi", "chill", "study", "jazz"],
    "rock": ["rock", "metal", "punk", "guitar"],
    "edm": ["edm", "electronic", "house", "techno", "dance", "synth", "club"],
    "hiphop": ["hip hop", "hip-hop", "hiphop", "rap", "trap", "drill"],
    "classic": ["classical", "piano", "orchestra", "cinematic", "violin"],
    "ambient": ["ambient", "meditation", "sleep", "calm", "relax", "drone"],
    "indian": ["indian", "bollywood", "hindi", "raga", "desi", "punjabi", "bhangra", "tabla", "sitar", "qawwali", "ghazal"],
    "acoustic": ["acoustic", "folk", "country", "ballad", "unplugged"],
    "pop": ["pop", "upbeat", "happy", "romantic"],
}
PROGS_MAJOR = [[0, 4, 5, 3], [0, 5, 3, 4], [5, 3, 0, 4], [0, 3, 4, 3]]
PROGS_MINOR = [[0, 5, 2, 6], [0, 3, 6, 5], [0, 6, 5, 6], [0, 2, 5, 6]]

LAYOUT = [("intro", 4), ("verse", 8), ("chorus", 8), ("verse", 8), ("chorus", 8),
          ("bridge", 8), ("chorus", 8), ("outro", 4)]
INTENSITY = {"intro": 0.45, "verse": 0.7, "chorus": 1.0, "bridge": 0.6, "outro": 0.4}


def pick_profile(text):
    t = text.lower()
    for name, words in KEYWORDS.items():
        if any(w in t for w in words):
            return name
    return "pop"


def _env(n, a, d, s, r):
    e = np.ones(n, dtype=np.float32)
    na, nd, nr = int(a * SR), int(d * SR), int(r * SR)
    na = max(1, min(na, n))
    e[:na] = np.linspace(0, 1, na, dtype=np.float32)
    nd = min(nd, max(0, n - na))
    if nd:
        e[na:na + nd] = np.linspace(1, s, nd, dtype=np.float32)
    e[na + nd:] = s
    nr = min(nr, n)
    if nr:
        e[n - nr:] *= np.linspace(1, 0, nr, dtype=np.float32)
    return e


_cache = {}


def tone(freq, dur, kind, detune=1.0):
    key = (round(freq, 2), round(dur, 3), kind, detune)
    if key in _cache:
        return _cache[key]
    n = max(8, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    f = freq * detune
    if kind == "pad":
        w = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * 2 * f * t)
             + 0.25 * np.sin(2 * np.pi * 3 * f * t))
        y = w * _env(n, 0.25, 0.3, 0.8, 0.35)
    elif kind == "bass":
        w = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t)
        y = w * _env(n, 0.005, 0.12, 0.6, 0.05)
    elif kind == "pluck":
        w = sum((1.0 / h) * np.sin(2 * np.pi * f * h * t) for h in range(1, 6))
        y = w * np.exp(-t * 5.0).astype(np.float32) * _env(n, 0.003, 0.0, 1.0, 0.03)
    elif kind == "saw":
        w = sum((1.0 / h) * np.sin(2 * np.pi * f * h * t) for h in range(1, 9))
        y = w * _env(n, 0.01, 0.1, 0.7, 0.06)
    elif kind == "drone":
        w = np.sin(2 * np.pi * f * t) + 0.6 * np.sin(2 * np.pi * 1.5 * f * t)
        y = w * _env(n, 1.0, 0.0, 1.0, 1.0)
    else:  # soft
        w = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)
        y = w * _env(n, 0.02, 0.15, 0.7, 0.12)
    y = (y / 2.2).astype(np.float32)
    _cache[key] = y
    return y


def _drum_samples():
    rng = np.random.default_rng(1)
    def kick():
        n = int(0.28 * SR); t = np.arange(n) / SR
        f = 120 * np.exp(-t * 22) + 42
        return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 11)).astype(np.float32)
    def snare():
        n = int(0.2 * SR); t = np.arange(n) / SR
        noise = rng.standard_normal(n) * np.exp(-t * 24)
        tone_ = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 28)
        return (0.7 * noise + 0.5 * tone_).astype(np.float32)
    def hat():
        n = int(0.05 * SR); t = np.arange(n) / SR
        noise = np.diff(rng.standard_normal(n + 1)) * np.exp(-t * 90)
        return (noise * 0.6).astype(np.float32)
    def tom():
        n = int(0.3 * SR); t = np.arange(n) / SR
        f = 160 * np.exp(-t * 9) + 90
        return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)).astype(np.float32)
    return dict(kick=kick(), snare=snare(), hat=hat(), tom=tom())


DRUMS = None

# 16-step patterns: (kick, snare, hat) step lists
PATTERNS = {
    "lofi": ([0, 7, 10], [4, 12], list(range(0, 16, 2))),
    "four": ([0, 4, 8, 12], [4, 12], list(range(2, 16, 4))),
    "rock": ([0, 6, 8, 11], [4, 12], list(range(0, 16, 2))),
    "trap": ([0, 3, 10], [8], list(range(0, 16, 1))),
    "dhol": ([0, 3, 6, 8, 11], [4, 12], list(range(0, 16, 2))),
    "soft": ([0, 8], [4, 12], list(range(0, 16, 4))),
}


def _add(buf, smp, start, gain, pan=0.0):
    if start < 0 or start >= buf.shape[1]:
        return
    end = min(buf.shape[1], start + len(smp))
    seg = smp[: end - start] * gain
    buf[0, start:end] += seg * (1 - max(0, pan))
    buf[1, start:end] += seg * (1 + min(0, pan))


def render_demo(prompt_text, duration, seed_key, out_wav, progress=None):
    global DRUMS
    if DRUMS is None:
        DRUMS = _drum_samples()
    prof_name = pick_profile(prompt_text)
    P = PROFILES[prof_name]
    rng = random.Random(int(hashlib.sha1(seed_key.encode()).hexdigest()[:12], 16))
    bpm = rng.randint(*P["bpm"])
    beat = 60.0 / bpm
    bar = 4 * beat
    scale = P["scale"]
    minorish = scale in (MINOR, PHRYG_DOM, PENTA_MIN)
    prog = rng.choice(PROGS_MINOR if minorish else PROGS_MAJOR)
    if len(scale) < 7:  # pentatonic: use natural minor for chords
        chord_scale = MINOR
    else:
        chord_scale = scale
    root_midi = rng.randint(45, 52)

    total_bars = max(4, int(round(duration / bar)))
    N = int((total_bars * bar + 4) * SR)
    buf = np.zeros((2, N), dtype=np.float32)

    def mtof(m):
        return 440.0 * 2 ** ((m - 69) / 12.0)

    def scale_note(deg, base=0):
        octv, idx = divmod(deg, len(scale))
        return root_midi + base + scale[idx] + 12 * octv

    def chord_notes(deg):
        out = []
        for k in (0, 2, 4):
            d = deg + k
            octv, idx = divmod(d, 7)
            out.append(root_midi + chord_scale[idx] + 12 * octv)
        return out

    # build section sequence
    seq, bars_left, i = [], total_bars, 0
    if total_bars < 16:
        plan = [("intro", 2), ("verse", 4), ("chorus", 4), ("outro", 2)]
    else:
        plan = LAYOUT
    while bars_left > 0:
        name, n = plan[i % len(plan)]
        if bars_left <= 6 and total_bars >= 16:
            name, n = "outro", bars_left
        n = min(n, bars_left)
        seq.append((name, n)); bars_left -= n; i += 1
    # melodies per section type (motifs)
    motifs = {}
    def motif(name):
        if name not in motifs:
            r = random.Random(rng.random())
            deg, m = r.randint(0, 4), []
            for _ in range(8):
                deg = max(-2, min(9, deg + r.choice([-2, -1, -1, 0, 1, 1, 2])))
                m.append(deg)
            motifs[name] = m
        return motifs[name]

    kick_p, snare_p, hat_p = PATTERNS.get(P["drums"], ([], [], []))
    step = beat / 4
    bar_idx = 0
    for sname, nbars in seq:
        inten = INTENSITY[sname]
        mot = motif("chorus" if sname == "chorus" else "verse")
        for b in range(nbars):
            t0 = bar_idx * bar
            s0 = int(t0 * SR)
            chord_deg = prog[bar_idx % len(prog)]
            notes = chord_notes(chord_deg)
            # pad
            for k, m in enumerate(notes):
                for det, pan in ((0.997, -0.5), (1.003, 0.5)):
                    _add(buf, tone(mtof(m), bar * 0.98, "pad", det), s0, 0.16 * inten, pan)
            # drone
            if P["drone"] and b % 4 == 0:
                _add(buf, tone(mtof(root_midi - 12), bar * 4, "drone"), s0, 0.12 * inten)
            # bass
            if sname != "intro" or b >= nbars // 2:
                bn = mtof(notes[0] - 24)
                pat = [0, 2, 3] if sname == "chorus" else [0, 2]
                for q in pat:
                    d = beat * (1.0 if q != 3 else 0.5)
                    _add(buf, tone(bn * (1.5 if q == 3 else 1), d, "bass"), s0 + int(q * beat * SR), 0.34 * inten)
            # drums
            if P["drums"] and not (sname == "intro" and b < nbars // 2):
                for st in range(16):
                    off = step * st + (P["swing"] * step if st % 2 else 0)
                    pos = s0 + int(off * SR)
                    if st in kick_p and sname != "outro":
                        _add(buf, DRUMS["kick"], pos, 0.55 * inten)
                    if st in snare_p and sname not in ("intro",):
                        _add(buf, DRUMS["snare"], pos, 0.32 * inten)
                    if st in hat_p:
                        _add(buf, DRUMS["hat"], pos, 0.16 * inten * (1.0 if st % 4 == 0 else 0.6), 0.3)
                if P["drums"] == "dhol" and sname == "chorus":
                    for st in (2, 5, 9, 14):
                        _add(buf, DRUMS["tom"], s0 + int(step * st * SR), 0.25)
            # lead
            if sname in ("verse", "chorus", "bridge") or (sname == "intro" and b >= nbars // 2):
                base = 12 if sname == "chorus" else 0
                for q in range(8):
                    pos_in = (bar_idx * 8 + q)
                    mdeg = mot[(b * 2 + q // 4 * 3 + q) % len(mot)]
                    rest = (q % 4 == 3 and sname != "chorus") or ((q + b) % 5 == 4)
                    if rest:
                        continue
                    # snap strong beats toward chord tone
                    if q % 4 == 0:
                        mdeg = chord_deg + [0, 2, 4][(q // 4 + b) % 3]
                    m = scale_note(mdeg, base)
                    _add(buf, tone(mtof(m), beat * 0.9, P["lead"]), s0 + int(q * beat / 2 * SR),
                         0.22 * inten, 0.15 if q % 2 else -0.15)
            bar_idx += 1
        if progress:
            progress(bar_idx / total_bars * 0.9)

    # trim, fade, reverb, normalise
    n_out = int(duration * SR)
    buf = buf[:, :n_out].copy()
    ir_n = int(1.4 * SR)
    ir = (np.random.default_rng(3).standard_normal(ir_n) * np.exp(-np.arange(ir_n) / SR * 3.2)).astype(np.float32)
    ir /= np.sqrt((ir ** 2).sum()) + 1e-9
    for c in (0, 1):
        wet = oaconvolve(buf[c], ir * (1.0 if c == 0 else -1.0), mode="full")[:n_out]
        buf[c] = buf[c] * 0.82 + wet.astype(np.float32) * 0.28
    fo = min(int(4 * SR), n_out)
    fi = min(int(0.05 * SR), n_out)
    buf[:, n_out - fo:] *= np.linspace(1, 0, fo, dtype=np.float32)
    buf[:, :fi] *= np.linspace(0, 1, fi, dtype=np.float32)
    peak = float(np.abs(buf).max()) or 1.0
    buf *= 0.9 / peak
    pcm = (buf.T * 32767).astype(np.int16)
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    if progress:
        progress(1.0)
    return dict(bpm=bpm, style=prof_name)


def generate_demo(job, out_dir, variants=2):
    outs = []
    text = f'{job["styles"]} {job["prompt"]}'
    for v in range(variants):
        wav = os.path.join(out_dir, f"raw{v}.wav")
        info = render_demo(text, job["duration"], f'{job["id"]}-{v}', wav)
        outs.append({"path": wav, "seed": None, "info": info})
    return outs


ENGINES = {"ace": generate_ace, "modal": generate_modal, "hf": generate_hf, "demo": generate_demo}
