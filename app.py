"""Dhun - a free, Suno-style AI music web app.

Run:  python app.py        (set ENGINE=ace for real AI, default demo)
"""
import os
import queue
import sqlite3
import threading
import time
import traceback
import uuid

from flask import Flask, jsonify, request, send_file, send_from_directory, abort, make_response

import sys, types
def _mod(name, src):
    m = types.ModuleType(name); exec(compile(src, name + ".py", "exec"), m.__dict__); sys.modules[name] = m
_mod("engines", '"""Music engines for Dhun.\n\nace  : real AI engine (ACE-Step 1.5 REST API, up to 10 min, vocals + lyrics).\ndemo : built-in procedural instrumental synth (no GPU needed) so the whole app\n       works end-to-end anywhere. It is NOT AI and has no vocals.\n"""\nimport hashlib\nimport json\nimport os\nimport random\nimport subprocess\nimport time\nimport urllib.parse\nimport urllib.request\nimport wave\n\nimport numpy as np\nfrom scipy.signal import oaconvolve\n\nSR = 32000\n\n\n# --------------------------------------------------------------------------\n# helpers\n# --------------------------------------------------------------------------\ndef to_mp3(src, dst, title="", artist="Dhun AI"):\n    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn",\n           "-codec:a", "libmp3lame", "-b:a", "192k",\n           "-metadata", f"title={title}", "-metadata", f"artist={artist}", dst]\n    subprocess.run(cmd, check=True)\n\n\ndef probe_duration(path):\n    out = subprocess.run(\n        ["ffprobe", "-v", "error", "-show_entries", "format=duration",\n         "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)\n    try:\n        return float(out.stdout.strip())\n    except ValueError:\n        return 0.0\n\n\n# --------------------------------------------------------------------------\n# ACE-Step engine (real AI)\n# --------------------------------------------------------------------------\ndef _http_json(url, payload=None, headers=None, timeout=60):\n    data = json.dumps(payload).encode() if payload is not None else None\n    req = urllib.request.Request(url, data=data, headers=headers or {})\n    if data:\n        req.add_header("Content-Type", "application/json")\n    with urllib.request.urlopen(req, timeout=timeout) as r:\n        return json.loads(r.read().decode())\n\n\ndef generate_ace(job, out_dir, variants=2):\n    """Returns list of dicts {path, seed}. Needs `uv run acestep-api` running."""\n    base = os.environ.get("ACESTEP_URL", "http://localhost:8001").rstrip("/")\n    key = os.environ.get("ACESTEP_API_KEY", "")\n    hdr = {"Authorization": f"Bearer {key}"} if key else {}\n\n    caption = job["styles"] or job["prompt"]\n    if job["prompt"] and job["styles"]:\n        caption = f\'{job["styles"]}. {job["prompt"]}\'\n    if job.get("exclude"):\n        caption += f\'. Avoid: {job["exclude"]}\'\n    lyrics = "[Instrumental]" if job["instrumental"] else job["lyrics"]\n\n    payload = {\n        "prompt": caption,\n        "lyrics": lyrics,\n        "audio_duration": float(job["duration"]),\n        "audio_format": "mp3",\n        "batch_size": variants,\n        "use_random_seed": True,\n        "inference_steps": 8,\n        "thinking": job.get("quality") == "high",\n    }\n    res = _http_json(base + "/release_task", payload, hdr)\n    task_id = res["data"]["task_id"]\n\n    deadline = time.time() + 60 * 40\n    while time.time() < deadline:\n        time.sleep(4)\n        q = _http_json(base + "/query_result", {"task_id_list": [task_id]}, hdr)\n        item = q["data"][0]\n        if item["status"] == 2:\n            raise RuntimeError("ACE-Step generation failed")\n        if item["status"] == 1:\n            files = json.loads(item["result"])\n            outs = []\n            for i, f in enumerate(files[:variants]):\n                url = f["file"]\n                if url.startswith("/"):\n                    url = base + url\n                raw = os.path.join(out_dir, f"raw{i}.mp3")\n                req = urllib.request.Request(url, headers=hdr)\n                with urllib.request.urlopen(req, timeout=300) as r, open(raw, "wb") as fh:\n                    fh.write(r.read())\n                outs.append({"path": raw, "seed": f.get("seed_value")})\n            return outs\n    raise TimeoutError("ACE-Step timed out")\n\n\n# --------------------------------------------------------------------------\n# Demo engine: procedural instrumental synth\n# --------------------------------------------------------------------------\nMAJOR = [0, 2, 4, 5, 7, 9, 11]\nMINOR = [0, 2, 3, 5, 7, 8, 10]\nPHRYG_DOM = [0, 1, 4, 5, 7, 8, 10]   # raga-ish / Bollywood flavour\nPENTA_MIN = [0, 3, 5, 7, 10]\n\nPROFILES = {\n    "lofi":    dict(bpm=(68, 84),  scale=MINOR, swing=0.14, drums="lofi",  lead="soft",  drone=False),\n    "pop":     dict(bpm=(100, 122), scale=MAJOR, swing=0.0,  drums="four", lead="pluck", drone=False),\n    "rock":    dict(bpm=(110, 140), scale=MINOR, swing=0.0,  drums="rock", lead="saw",   drone=False),\n    "edm":     dict(bpm=(122, 130), scale=MINOR, swing=0.0,  drums="four", lead="saw",   drone=False),\n    "hiphop":  dict(bpm=(78, 96),  scale=MINOR, swing=0.08, drums="trap", lead="soft",  drone=False),\n    "classic": dict(bpm=(64, 90),  scale=MAJOR, swing=0.0,  drums=None,   lead="soft",  drone=False),\n    "ambient": dict(bpm=(60, 76),  scale=PENTA_MIN, swing=0.0, drums=None, lead="soft", drone=True),\n    "indian":  dict(bpm=(84, 108), scale=PHRYG_DOM, swing=0.0, drums="dhol", lead="pluck", drone=True),\n    "acoustic": dict(bpm=(84, 108), scale=MAJOR, swing=0.0, drums="soft", lead="pluck", drone=False),\n}\nKEYWORDS = {\n    "lofi": ["lofi", "lo-fi", "chill", "study", "jazz"],\n    "rock": ["rock", "metal", "punk", "guitar"],\n    "edm": ["edm", "electronic", "house", "techno", "dance", "synth", "club"],\n    "hiphop": ["hip hop", "hip-hop", "hiphop", "rap", "trap", "drill"],\n    "classic": ["classical", "piano", "orchestra", "cinematic", "violin"],\n    "ambient": ["ambient", "meditation", "sleep", "calm", "relax", "drone"],\n    "indian": ["indian", "bollywood", "hindi", "raga", "desi", "punjabi", "bhangra", "tabla", "sitar", "qawwali", "ghazal"],\n    "acoustic": ["acoustic", "folk", "country", "ballad", "unplugged"],\n    "pop": ["pop", "upbeat", "happy", "romantic"],\n}\nPROGS_MAJOR = [[0, 4, 5, 3], [0, 5, 3, 4], [5, 3, 0, 4], [0, 3, 4, 3]]\nPROGS_MINOR = [[0, 5, 2, 6], [0, 3, 6, 5], [0, 6, 5, 6], [0, 2, 5, 6]]\n\nLAYOUT = [("intro", 4), ("verse", 8), ("chorus", 8), ("verse", 8), ("chorus", 8),\n          ("bridge", 8), ("chorus", 8), ("outro", 4)]\nINTENSITY = {"intro": 0.45, "verse": 0.7, "chorus": 1.0, "bridge": 0.6, "outro": 0.4}\n\n\ndef pick_profile(text):\n    t = text.lower()\n    for name, words in KEYWORDS.items():\n        if any(w in t for w in words):\n            return name\n    return "pop"\n\n\ndef _env(n, a, d, s, r):\n    e = np.ones(n, dtype=np.float32)\n    na, nd, nr = int(a * SR), int(d * SR), int(r * SR)\n    na = max(1, min(na, n))\n    e[:na] = np.linspace(0, 1, na, dtype=np.float32)\n    nd = min(nd, max(0, n - na))\n    if nd:\n        e[na:na + nd] = np.linspace(1, s, nd, dtype=np.float32)\n    e[na + nd:] = s\n    nr = min(nr, n)\n    if nr:\n        e[n - nr:] *= np.linspace(1, 0, nr, dtype=np.float32)\n    return e\n\n\n_cache = {}\n\n\ndef tone(freq, dur, kind, detune=1.0):\n    key = (round(freq, 2), round(dur, 3), kind, detune)\n    if key in _cache:\n        return _cache[key]\n    n = max(8, int(dur * SR))\n    t = np.arange(n, dtype=np.float32) / SR\n    f = freq * detune\n    if kind == "pad":\n        w = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * 2 * f * t)\n             + 0.25 * np.sin(2 * np.pi * 3 * f * t))\n        y = w * _env(n, 0.25, 0.3, 0.8, 0.35)\n    elif kind == "bass":\n        w = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t)\n        y = w * _env(n, 0.005, 0.12, 0.6, 0.05)\n    elif kind == "pluck":\n        w = sum((1.0 / h) * np.sin(2 * np.pi * f * h * t) for h in range(1, 6))\n        y = w * np.exp(-t * 5.0).astype(np.float32) * _env(n, 0.003, 0.0, 1.0, 0.03)\n    elif kind == "saw":\n        w = sum((1.0 / h) * np.sin(2 * np.pi * f * h * t) for h in range(1, 9))\n        y = w * _env(n, 0.01, 0.1, 0.7, 0.06)\n    elif kind == "drone":\n        w = np.sin(2 * np.pi * f * t) + 0.6 * np.sin(2 * np.pi * 1.5 * f * t)\n        y = w * _env(n, 1.0, 0.0, 1.0, 1.0)\n    else:  # soft\n        w = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)\n        y = w * _env(n, 0.02, 0.15, 0.7, 0.12)\n    y = (y / 2.2).astype(np.float32)\n    _cache[key] = y\n    return y\n\n\ndef _drum_samples():\n    rng = np.random.default_rng(1)\n    def kick():\n        n = int(0.28 * SR); t = np.arange(n) / SR\n        f = 120 * np.exp(-t * 22) + 42\n        return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 11)).astype(np.float32)\n    def snare():\n        n = int(0.2 * SR); t = np.arange(n) / SR\n        noise = rng.standard_normal(n) * np.exp(-t * 24)\n        tone_ = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 28)\n        return (0.7 * noise + 0.5 * tone_).astype(np.float32)\n    def hat():\n        n = int(0.05 * SR); t = np.arange(n) / SR\n        noise = np.diff(rng.standard_normal(n + 1)) * np.exp(-t * 90)\n        return (noise * 0.6).astype(np.float32)\n    def tom():\n        n = int(0.3 * SR); t = np.arange(n) / SR\n        f = 160 * np.exp(-t * 9) + 90\n        return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)).astype(np.float32)\n    return dict(kick=kick(), snare=snare(), hat=hat(), tom=tom())\n\n\nDRUMS = None\n\n# 16-step patterns: (kick, snare, hat) step lists\nPATTERNS = {\n    "lofi": ([0, 7, 10], [4, 12], list(range(0, 16, 2))),\n    "four": ([0, 4, 8, 12], [4, 12], list(range(2, 16, 4))),\n    "rock": ([0, 6, 8, 11], [4, 12], list(range(0, 16, 2))),\n    "trap": ([0, 3, 10], [8], list(range(0, 16, 1))),\n    "dhol": ([0, 3, 6, 8, 11], [4, 12], list(range(0, 16, 2))),\n    "soft": ([0, 8], [4, 12], list(range(0, 16, 4))),\n}\n\n\ndef _add(buf, smp, start, gain, pan=0.0):\n    if start < 0 or start >= buf.shape[1]:\n        return\n    end = min(buf.shape[1], start + len(smp))\n    seg = smp[: end - start] * gain\n    buf[0, start:end] += seg * (1 - max(0, pan))\n    buf[1, start:end] += seg * (1 + min(0, pan))\n\n\ndef render_demo(prompt_text, duration, seed_key, out_wav, progress=None):\n    global DRUMS\n    if DRUMS is None:\n        DRUMS = _drum_samples()\n    prof_name = pick_profile(prompt_text)\n    P = PROFILES[prof_name]\n    rng = random.Random(int(hashlib.sha1(seed_key.encode()).hexdigest()[:12], 16))\n    bpm = rng.randint(*P["bpm"])\n    beat = 60.0 / bpm\n    bar = 4 * beat\n    scale = P["scale"]\n    minorish = scale in (MINOR, PHRYG_DOM, PENTA_MIN)\n    prog = rng.choice(PROGS_MINOR if minorish else PROGS_MAJOR)\n    if len(scale) < 7:  # pentatonic: use natural minor for chords\n        chord_scale = MINOR\n    else:\n        chord_scale = scale\n    root_midi = rng.randint(45, 52)\n\n    total_bars = max(4, int(round(duration / bar)))\n    N = int((total_bars * bar + 4) * SR)\n    buf = np.zeros((2, N), dtype=np.float32)\n\n    def mtof(m):\n        return 440.0 * 2 ** ((m - 69) / 12.0)\n\n    def scale_note(deg, base=0):\n        octv, idx = divmod(deg, len(scale))\n        return root_midi + base + scale[idx] + 12 * octv\n\n    def chord_notes(deg):\n        out = []\n        for k in (0, 2, 4):\n            d = deg + k\n            octv, idx = divmod(d, 7)\n            out.append(root_midi + chord_scale[idx] + 12 * octv)\n        return out\n\n    # build section sequence\n    seq, bars_left, i = [], total_bars, 0\n    if total_bars < 16:\n        plan = [("intro", 2), ("verse", 4), ("chorus", 4), ("outro", 2)]\n    else:\n        plan = LAYOUT\n    while bars_left > 0:\n        name, n = plan[i % len(plan)]\n        if bars_left <= 6 and total_bars >= 16:\n            name, n = "outro", bars_left\n        n = min(n, bars_left)\n        seq.append((name, n)); bars_left -= n; i += 1\n    # melodies per section type (motifs)\n    motifs = {}\n    def motif(name):\n        if name not in motifs:\n            r = random.Random(rng.random())\n            deg, m = r.randint(0, 4), []\n            for _ in range(8):\n                deg = max(-2, min(9, deg + r.choice([-2, -1, -1, 0, 1, 1, 2])))\n                m.append(deg)\n            motifs[name] = m\n        return motifs[name]\n\n    kick_p, snare_p, hat_p = PATTERNS.get(P["drums"], ([], [], []))\n    step = beat / 4\n    bar_idx = 0\n    for sname, nbars in seq:\n        inten = INTENSITY[sname]\n        mot = motif("chorus" if sname == "chorus" else "verse")\n        for b in range(nbars):\n            t0 = bar_idx * bar\n            s0 = int(t0 * SR)\n            chord_deg = prog[bar_idx % len(prog)]\n            notes = chord_notes(chord_deg)\n            # pad\n            for k, m in enumerate(notes):\n                for det, pan in ((0.997, -0.5), (1.003, 0.5)):\n                    _add(buf, tone(mtof(m), bar * 0.98, "pad", det), s0, 0.16 * inten, pan)\n            # drone\n            if P["drone"] and b % 4 == 0:\n                _add(buf, tone(mtof(root_midi - 12), bar * 4, "drone"), s0, 0.12 * inten)\n            # bass\n            if sname != "intro" or b >= nbars // 2:\n                bn = mtof(notes[0] - 24)\n                pat = [0, 2, 3] if sname == "chorus" else [0, 2]\n                for q in pat:\n                    d = beat * (1.0 if q != 3 else 0.5)\n                    _add(buf, tone(bn * (1.5 if q == 3 else 1), d, "bass"), s0 + int(q * beat * SR), 0.34 * inten)\n            # drums\n            if P["drums"] and not (sname == "intro" and b < nbars // 2):\n                for st in range(16):\n                    off = step * st + (P["swing"] * step if st % 2 else 0)\n                    pos = s0 + int(off * SR)\n                    if st in kick_p and sname != "outro":\n                        _add(buf, DRUMS["kick"], pos, 0.55 * inten)\n                    if st in snare_p and sname not in ("intro",):\n                        _add(buf, DRUMS["snare"], pos, 0.32 * inten)\n                    if st in hat_p:\n                        _add(buf, DRUMS["hat"], pos, 0.16 * inten * (1.0 if st % 4 == 0 else 0.6), 0.3)\n                if P["drums"] == "dhol" and sname == "chorus":\n                    for st in (2, 5, 9, 14):\n                        _add(buf, DRUMS["tom"], s0 + int(step * st * SR), 0.25)\n            # lead\n            if sname in ("verse", "chorus", "bridge") or (sname == "intro" and b >= nbars // 2):\n                base = 12 if sname == "chorus" else 0\n                for q in range(8):\n                    pos_in = (bar_idx * 8 + q)\n                    mdeg = mot[(b * 2 + q // 4 * 3 + q) % len(mot)]\n                    rest = (q % 4 == 3 and sname != "chorus") or ((q + b) % 5 == 4)\n                    if rest:\n                        continue\n                    # snap strong beats toward chord tone\n                    if q % 4 == 0:\n                        mdeg = chord_deg + [0, 2, 4][(q // 4 + b) % 3]\n                    m = scale_note(mdeg, base)\n                    _add(buf, tone(mtof(m), beat * 0.9, P["lead"]), s0 + int(q * beat / 2 * SR),\n                         0.22 * inten, 0.15 if q % 2 else -0.15)\n            bar_idx += 1\n        if progress:\n            progress(bar_idx / total_bars * 0.9)\n\n    # trim, fade, reverb, normalise\n    n_out = int(duration * SR)\n    buf = buf[:, :n_out].copy()\n    ir_n = int(1.4 * SR)\n    ir = (np.random.default_rng(3).standard_normal(ir_n) * np.exp(-np.arange(ir_n) / SR * 3.2)).astype(np.float32)\n    ir /= np.sqrt((ir ** 2).sum()) + 1e-9\n    for c in (0, 1):\n        wet = oaconvolve(buf[c], ir * (1.0 if c == 0 else -1.0), mode="full")[:n_out]\n        buf[c] = buf[c] * 0.82 + wet.astype(np.float32) * 0.28\n    fo = min(int(4 * SR), n_out)\n    fi = min(int(0.05 * SR), n_out)\n    buf[:, n_out - fo:] *= np.linspace(1, 0, fo, dtype=np.float32)\n    buf[:, :fi] *= np.linspace(0, 1, fi, dtype=np.float32)\n    peak = float(np.abs(buf).max()) or 1.0\n    buf *= 0.9 / peak\n    pcm = (buf.T * 32767).astype(np.int16)\n    with wave.open(out_wav, "wb") as w:\n        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)\n        w.writeframes(pcm.tobytes())\n    if progress:\n        progress(1.0)\n    return dict(bpm=bpm, style=prof_name)\n\n\ndef generate_demo(job, out_dir, variants=2):\n    outs = []\n    text = f\'{job["styles"]} {job["prompt"]}\'\n    for v in range(variants):\n        wav = os.path.join(out_dir, f"raw{v}.wav")\n        info = render_demo(text, job["duration"], f\'{job["id"]}-{v}\', wav)\n        outs.append({"path": wav, "seed": None, "info": info})\n    return outs\n\n\nENGINES = {"ace": generate_ace, "demo": generate_demo}\n')
_mod("media", '"""Cover art (PIL) and MP4 visualizer video (ffmpeg)."""\nimport colorsys\nimport hashlib\nimport os\nimport random\nimport subprocess\n\nfrom PIL import Image, ImageDraw, ImageFilter, ImageFont\n\nFONT_CANDIDATES = [\n    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",\n    "/usr/share/fonts/truetype/google-fonts/ofl/notosansdevanagari/NotoSansDevanagari[wdth,wght].ttf",\n    "/usr/share/fonts/opentype/inter/Inter-Bold.otf",\n    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",\n    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",\n]\n\n\ndef _font(size, text=""):\n    # Prefer a Devanagari-capable font when the text contains Hindi.\n    cands = FONT_CANDIDATES if any("ऀ" <= c <= "ॿ" for c in text) else FONT_CANDIDATES[2:] + FONT_CANDIDATES[:2]\n    for p in cands:\n        if os.path.exists(p):\n            try:\n                return ImageFont.truetype(p, size)\n            except Exception:\n                continue\n    return ImageFont.load_default()\n\n\ndef _palette(seed):\n    h = int(hashlib.md5(seed.encode()).hexdigest()[:6], 16)\n    base = (h % 360) / 360.0\n    def c(hh, s, v):\n        r, g, b = colorsys.hsv_to_rgb(hh % 1.0, s, v)\n        return int(r * 255), int(g * 255), int(b * 255)\n    return c(base, 0.75, 0.95), c(base + 0.12, 0.8, 0.55), c(base + 0.55, 0.7, 0.25)\n\n\ndef make_cover(seed, path, size=640):\n    a, b, c = _palette(seed)\n    rnd = random.Random(seed)\n    img = Image.new("RGB", (size, size), c)\n    px = img.load()\n    for y in range(size):\n        for x in range(size):\n            t = (x * 0.4 + y * 0.9) / (size * 1.3)\n            px[x, y] = tuple(int(b[i] * (1 - t) + c[i] * t) for i in range(3))\n    layer = Image.new("RGB", (size, size), (0, 0, 0))\n    d = ImageDraw.Draw(layer)\n    for _ in range(6):\n        r = rnd.randint(size // 6, size // 2)\n        x, y = rnd.randint(0, size), rnd.randint(0, size)\n        d.ellipse([x - r, y - r, x + r, y + r], fill=a if rnd.random() > .4 else b)\n    layer = layer.filter(ImageFilter.GaussianBlur(size // 10))\n    img = Image.blend(img, layer, 0.55)\n    img.save(path, "JPEG", quality=88)\n\n\ndef make_video_bg(cover_path, title, styles, out_png, w=1280, h=720):\n    bg = Image.open(cover_path).convert("RGB").resize((w, w)).crop((0, (w - h) // 2, w, (w - h) // 2 + h))\n    bg = bg.filter(ImageFilter.GaussianBlur(40))\n    dark = Image.new("RGB", (w, h), (0, 0, 0))\n    bg = Image.blend(bg, dark, 0.55)\n    art = Image.open(cover_path).convert("RGB").resize((300, 300))\n    bg.paste(art, (90, 150))\n    d = ImageDraw.Draw(bg)\n    d.text((440, 190), title[:42], font=_font(58, title), fill=(255, 255, 255))\n    d.text((440, 275), (styles or "")[:70], font=_font(28, styles or ""), fill=(220, 220, 230))\n    d.text((440, 330), "Made with Dhun AI", font=_font(24), fill=(255, 140, 120))\n    bg.save(out_png)\n\n\ndef make_video(audio_path, cover_path, title, styles, out_mp4, workdir):\n    bg = os.path.join(workdir, "vbg.png")\n    make_video_bg(cover_path, title, styles, bg)\n    fc = ("[1:a]showwaves=s=1280x170:mode=cline:rate=24:colors=white@0.9,format=yuva420p[w];"\n          "[0:v][w]overlay=0:H-h-60,format=yuv420p[v]")\n    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "24", "-i", bg,\n           "-i", audio_path, "-filter_complex", fc, "-map", "[v]", "-map", "1:a",\n           "-c:v", "libx264", "-preset", "veryfast", "-crf", "31", "-r", "24",\n           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out_mp4]\n    subprocess.run(cmd, check=True)\n    try:\n        os.remove(bg)\n    except OSError:\n        pass\n')
import engines
import media
STATIC = {'index.html': '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Dhun – Make any song you can imagine</title>\n<link rel="icon" href="data:,">\n<link rel="stylesheet" href="/static/style.css">\n</head>\n<body>\n<div class="app">\n  <aside class="side">\n    <div class="logo"><span class="dot"></span>Dhun</div>\n    <nav>\n      <a data-view="create" class="active">✦ <span>Create</span></a>\n      <a data-view="library">♪ <span>Library</span></a>\n      <a data-view="explore">◎ <span>Explore</span></a>\n    </nav>\n    <div class="credits"><div id="creditsTxt">–</div><div class="bar"><i id="creditsBar"></i></div><small>creates left today (1 song each)</small></div>\n  </aside>\n\n  <main>\n    <!-- CREATE -->\n    <section id="v-create" class="view active">\n      <div class="create-grid">\n        <div class="panel form">\n          <div class="tabs" id="modeTabs"><button class="on" data-mode="simple">Simple</button><button data-mode="custom">Custom</button></div>\n\n          <div id="simpleBox">\n            <label>Song description</label>\n            <textarea id="prompt" rows="5" maxlength="500" placeholder="A dreamy lo-fi song about a rainy night in Mumbai, soft piano and slow beats…"></textarea>\n          </div>\n\n          <div id="customBox" hidden>\n            <div class="row between"><label>Lyrics</label><button class="ghost sm" id="btnLyrics">✎ Starter lyrics</button></div>\n            <textarea id="lyrics" rows="8" maxlength="5000" placeholder="[Verse 1]&#10;Write your own lyrics, or leave empty and tick Instrumental…&#10;&#10;[Chorus]&#10;…"></textarea>\n            <label>Styles</label>\n            <input id="styles" maxlength="200" placeholder="e.g. bollywood, romantic, female vocals, 90 bpm">\n            <div class="chips" id="styleChips"></div>\n            <label>Exclude styles <small>(optional)</small></label>\n            <input id="exclude" maxlength="200" placeholder="e.g. heavy metal, autotune">\n            <label>Song title <small>(optional)</small></label>\n            <input id="title" maxlength="80" placeholder="Give your song a name">\n          </div>\n\n          <div class="row between toggle"><span>Instrumental</span><label class="sw"><input type="checkbox" id="instrumental"><i></i></label></div>\n\n          <div class="adv">\n            <div class="row between"><label>Song length</label><b id="durLbl">2:00</b></div>\n            <input type="range" id="duration" min="30" max="600" step="15" value="120">\n            <div class="row between small"><span>0:30</span><span>10:00</span></div>\n            <div class="row between" style="margin-top:12px">\n              <label>Quality</label>\n              <select id="quality"><option value="fast">Fast</option><option value="high">High (slower)</option></select>\n            </div>\n            <div class="row between toggle"><span>Share on Explore</span><label class="sw"><input type="checkbox" id="public" checked><i></i></label></div>\n          </div>\n\n          <button class="primary" id="btnCreate">✦ Create</button>\n          <div class="err" id="err"></div>\n          <div class="note" id="engineNote"></div>\n        </div>\n\n        <div class="results">\n          <h2>Your latest songs</h2>\n          <div id="latest" class="songlist"></div>\n        </div>\n      </div>\n    </section>\n\n    <!-- LIBRARY -->\n    <section id="v-library" class="view">\n      <div class="row between head"><h2>Library</h2><input id="search" class="search" placeholder="Search songs…"></div>\n      <div id="library" class="songlist"></div>\n    </section>\n\n    <!-- EXPLORE -->\n    <section id="v-explore" class="view">\n      <div class="row between head"><h2>Explore</h2></div>\n      <div id="explore" class="songlist"></div>\n    </section>\n  </main>\n</div>\n\n<div class="player" id="player" hidden>\n  <img id="pCover" alt="">\n  <div class="pinfo"><b id="pTitle">–</b><small id="pStyles"></small></div>\n  <div class="pctl">\n    <button id="pPrev">⏮</button><button id="pPlay" class="pp">▶</button><button id="pNext">⏭</button>\n  </div>\n  <div class="pseek"><span id="pCur">0:00</span><input type="range" id="pSeek" min="0" max="1000" value="0"><span id="pDur">0:00</span></div>\n  <div class="pvol">🔈<input type="range" id="pVol" min="0" max="100" value="80"></div>\n</div>\n<audio id="audio" preload="metadata"></audio>\n\n<div class="modal" id="lyricModal" hidden>\n  <div class="mbox"><b id="lyTitle"></b><pre id="lyBody"></pre><button class="ghost" onclick="document.getElementById(\'lyricModal\').hidden=true">Close</button></div>\n</div>\n<div class="modal" id="vidModal" hidden>\n  <div class="mbox wide"><video id="vidEl" controls playsinline></video><button class="ghost" id="vidClose">Close</button></div>\n</div>\n<div class="toast" id="toast" hidden></div>\n<script src="/static/app.js"></script>\n</body>\n</html>\n', 'style.css': ':root{--bg:#0c0c0f;--panel:#16161b;--panel2:#1d1d24;--line:#2a2a33;--txt:#f2f2f5;--mut:#9a9aa8;--a:#ff5a36;--b:#ff2d8b;--g:linear-gradient(135deg,#ff5a36,#ff2d8b)}\n*{box-sizing:border-box}html,body{margin:0;height:100%}\nbody{background:var(--bg);color:var(--txt);font:15px/1.45 Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}\nbutton,input,select,textarea{font:inherit;color:inherit}\n.app{display:flex;min-height:100vh;padding-bottom:84px}\n.side{width:210px;flex:none;border-right:1px solid var(--line);padding:20px 14px;position:sticky;top:0;height:calc(100vh - 78px);display:flex;flex-direction:column;gap:18px}\n.logo{font-weight:800;font-size:24px;letter-spacing:.5px;display:flex;align-items:center;gap:10px;padding:0 8px}\n.dot{width:16px;height:16px;border-radius:50%;background:var(--g)}\nnav{display:flex;flex-direction:column;gap:4px}\nnav a{padding:10px 12px;border-radius:10px;cursor:pointer;color:var(--mut);display:flex;gap:10px}\nnav a:hover{background:var(--panel)}nav a.active{background:var(--panel2);color:var(--txt)}\n.credits{margin-top:auto;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;font-size:13px}\n.credits .bar{height:6px;border-radius:6px;background:var(--line);margin:8px 0}.credits .bar i{display:block;height:100%;border-radius:6px;background:var(--g);width:0}\n.credits small{color:var(--mut)}\nmain{flex:1;min-width:0;padding:22px 26px}\n.view{display:none}.view.active{display:block}\nh2{margin:0 0 14px;font-size:20px}\n.create-grid{display:grid;grid-template-columns:minmax(320px,430px) 1fr;gap:22px;align-items:start}\n.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px}\n.tabs{display:flex;background:var(--bg);border-radius:10px;padding:3px;margin-bottom:14px}\n.tabs button{flex:1;border:0;background:none;padding:8px;border-radius:8px;cursor:pointer;color:var(--mut)}\n.tabs button.on{background:var(--panel2);color:var(--txt)}\nlabel{display:block;margin:12px 0 6px;font-size:13px;color:var(--mut)}label small{opacity:.7}\ntextarea,input[type=text],input:not([type]),select{width:100%;background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px 12px;outline:none}\ntextarea:focus,input:focus,select:focus{border-color:#555}\ntextarea{resize:vertical}\nselect{width:auto}\n.row{display:flex;align-items:center;gap:10px}.between{justify-content:space-between}\n.small{font-size:12px;color:var(--mut)}\n.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}\n.chips span{background:var(--panel2);border:1px solid var(--line);border-radius:20px;padding:3px 10px;font-size:12px;cursor:pointer;color:var(--mut)}\n.chips span:hover{color:var(--txt);border-color:#666}\n.toggle{padding:12px 0;border-top:1px solid var(--line);margin-top:12px}\n.sw{position:relative;width:42px;height:24px;margin:0}.sw input{display:none}\n.sw i{position:absolute;inset:0;background:var(--line);border-radius:24px;transition:.2s;cursor:pointer}\n.sw i:before{content:"";position:absolute;left:3px;top:3px;width:18px;height:18px;border-radius:50%;background:#fff;transition:.2s}\n.sw input:checked+i{background:var(--a)}.sw input:checked+i:before{left:21px}\ninput[type=range]{width:100%;accent-color:var(--a)}\n.adv{border-top:1px solid var(--line);padding-top:12px;margin-top:6px}\n.primary{width:100%;margin-top:14px;border:0;border-radius:12px;padding:13px;font-weight:700;font-size:16px;background:var(--g);cursor:pointer}\n.primary:disabled{opacity:.5;cursor:wait}\n.ghost{background:none;border:1px solid var(--line);border-radius:10px;padding:8px 14px;cursor:pointer;color:var(--txt)}.ghost:hover{background:var(--panel2)}\n.ghost.sm{padding:3px 10px;font-size:12px}\n.err{color:#ff7a7a;margin-top:10px;font-size:13px}.note{color:var(--mut);font-size:12px;margin-top:10px}\n.head{margin-bottom:6px}.search{max-width:260px}\n.songlist{display:flex;flex-direction:column;gap:8px}\n.song{display:flex;gap:12px;align-items:center;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:10px;position:relative}\n.song:hover{background:var(--panel2)}.song.playing{border-color:var(--a)}\n.cv{position:relative;width:64px;height:64px;border-radius:10px;overflow:hidden;flex:none;background:var(--panel2);cursor:pointer}\n.cv img{width:100%;height:100%;object-fit:cover}\n.cv .pl{position:absolute;inset:0;display:grid;place-items:center;background:#0006;opacity:0;transition:.15s;font-size:22px}\n.cv:hover .pl{opacity:1}\n.meta{flex:1;min-width:0}.meta b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}\n.meta small{color:var(--mut);display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}\n.tag{display:inline-block;font-size:11px;padding:1px 8px;border-radius:10px;background:var(--panel2);border:1px solid var(--line);margin-left:6px;color:var(--mut)}\n.spin{width:18px;height:18px;border:3px solid var(--line);border-top-color:var(--a);border-radius:50%;animation:s 1s linear infinite;display:inline-block;vertical-align:-3px;margin-right:6px}\n@keyframes s{to{transform:rotate(360deg)}}\n.acts{display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end}\n.acts button,.acts a{background:none;border:1px solid transparent;border-radius:8px;padding:6px 9px;cursor:pointer;color:var(--mut);text-decoration:none;font-size:13px}\n.acts button:hover,.acts a:hover{background:var(--bg);border-color:var(--line);color:var(--txt)}\n.acts .liked{color:var(--b)}\n.player{position:fixed;left:0;right:0;bottom:0;height:78px;background:#101015f2;backdrop-filter:blur(12px);border-top:1px solid var(--line);display:flex;align-items:center;gap:18px;padding:0 18px;z-index:5}\n.player[hidden]{display:none}\n.player img{width:52px;height:52px;border-radius:8px;object-fit:cover}\n.pinfo{width:220px;min-width:0}.pinfo b,.pinfo small{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pinfo small{color:var(--mut);font-size:12px}\n.pctl{display:flex;gap:6px}.pctl button{background:none;border:0;font-size:18px;cursor:pointer;width:38px;height:38px;border-radius:50%}\n.pctl .pp{background:#fff;color:#000}\n.pseek{flex:1;display:flex;align-items:center;gap:10px;font-size:12px;color:var(--mut)}\n.pvol{display:flex;align-items:center;gap:6px;width:130px}\n.modal{position:fixed;inset:0;background:#000b;display:grid;place-items:center;z-index:10;padding:16px}.modal[hidden]{display:none}\n.mbox{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;max-width:560px;width:100%;max-height:85vh;overflow:auto;display:flex;flex-direction:column;gap:12px}\n.mbox.wide{max-width:960px}.mbox video{width:100%;border-radius:10px;background:#000}\n.mbox pre{white-space:pre-wrap;font:inherit;margin:0;color:#ddd}\n.toast{position:fixed;left:50%;bottom:96px;transform:translateX(-50%);background:#fff;color:#000;padding:10px 16px;border-radius:10px;z-index:20;font-weight:600}\n.toast[hidden]{display:none}.empty{color:var(--mut);padding:30px 0;text-align:center}\n@media(max-width:900px){\n .app{flex-direction:column;padding-bottom:150px}\n .side{width:100%;height:auto;position:static;flex-direction:row;align-items:center;border-right:0;border-bottom:1px solid var(--line);padding:10px 12px}\n .credits{display:none}nav{flex-direction:row;margin-left:auto}nav a span{display:none}\n main{padding:14px}.create-grid{grid-template-columns:1fr}\n .player{height:auto;flex-wrap:wrap;padding:8px 12px;gap:8px}.pinfo{width:auto;flex:1}.pseek{order:5;flex-basis:100%}.pvol{display:none}\n .song{flex-wrap:wrap}.acts{justify-content:flex-start;width:100%}\n}\n', 'app.js': 'const $ = (s, r = document) => r.querySelector(s);\nconst $$ = (s, r = document) => [...r.querySelectorAll(s)];\nlet cfg = {}, mode = "simple", queue = [], idx = -1, view = "create", cache = {};\nconst audio = $("#audio");\n\nconst fmt = s => { s = Math.floor(s || 0); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };\nconst esc = s => (s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", \'"\': "&quot;" }[c]));\nconst api = async (u, o = {}) => {\n  const r = await fetch(u, { headers: { "Content-Type": "application/json" }, ...o });\n  const j = await r.json().catch(() => ({}));\n  if (!r.ok) throw new Error(j.error || "Something went wrong");\n  return j;\n};\nfunction toast(t) { const e = $("#toast"); e.textContent = t; e.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => e.hidden = true, 2500); }\n\n/* ---------- nav ---------- */\n$$("nav a").forEach(a => a.onclick = () => show(a.dataset.view));\nfunction show(v) {\n  view = v;\n  $$("nav a").forEach(a => a.classList.toggle("active", a.dataset.view === v));\n  $$(".view").forEach(s => s.classList.toggle("active", s.id === "v-" + v));\n  refresh();\n}\n\n/* ---------- form ---------- */\n$$("#modeTabs button").forEach(b => b.onclick = () => {\n  mode = b.dataset.mode;\n  $$("#modeTabs button").forEach(x => x.classList.toggle("on", x === b));\n  $("#simpleBox").hidden = mode !== "simple";\n  $("#customBox").hidden = mode !== "custom";\n});\nconst STYLES = ["pop", "lo-fi", "bollywood", "indian classical", "rock", "edm", "hip hop", "acoustic", "ambient", "cinematic", "romantic", "punjabi", "ghazal", "sad", "upbeat", "female vocals", "male vocals"];\n$("#styleChips").innerHTML = STYLES.map(s => `<span>${s}</span>`).join("");\n$("#styleChips").onclick = e => {\n  if (e.target.tagName !== "SPAN") return;\n  const el = $("#styles"), cur = el.value.split(",").map(x => x.trim()).filter(Boolean);\n  if (!cur.includes(e.target.textContent)) cur.push(e.target.textContent);\n  el.value = cur.join(", ");\n};\n$("#duration").oninput = e => $("#durLbl").textContent = fmt(e.target.value);\n$("#instrumental").onchange = e => { $("#lyrics").disabled = e.target.checked; $("#lyrics").style.opacity = e.target.checked ? .4 : 1; };\n\n$("#btnLyrics").onclick = () => {\n  const idea = ($("#prompt").value || $("#title").value || $("#styles").value || "zindagi").trim().split(/\\s+/).slice(0, 4).join(" ");\n  $("#lyrics").value =\n`[Verse 1]\nRaat ke andhere mein, ${idea}\nDil ki dhadkan keh rahi hai, ek nayi kahani\nKhamosh si hawa mein, teri yaad aati hai\nHar pal bas tujhe hi, ye zindagi bulati hai\n\n[Chorus]\nOh ${idea}, tu hi meri dhun hai\nHar saans mein basa hai, tera hi toh sun hai\nChal chalein door kahin, jahan ho sirf hum tum\n${idea}, ${idea}, gunj uthe ye gagan\n\n[Verse 2]\nSubah ki pehli kiran, jab chhoo le ye zameen\nLagta hai sapne mere, ho gaye hain haseen\nKadam kadam par tera, saath hai bas yahi\nMushkilein jo aayein, ab koi darr nahi\n\n[Chorus]\nOh ${idea}, tu hi meri dhun hai\nHar saans mein basa hai, tera hi toh sun hai\n\n[Outro]\n${idea}…`;\n  toast("Starter lyrics added – edit freely");\n};\n\n$("#btnCreate").onclick = async () => {\n  const btn = $("#btnCreate"); $("#err").textContent = "";\n  const body = {\n    prompt: mode === "simple" ? $("#prompt").value : $("#prompt").value,\n    lyrics: mode === "custom" ? $("#lyrics").value : "",\n    styles: mode === "custom" ? $("#styles").value : "",\n    exclude: mode === "custom" ? $("#exclude").value : "",\n    title: mode === "custom" ? $("#title").value : "",\n    instrumental: $("#instrumental").checked,\n    duration: +$("#duration").value, quality: $("#quality").value, public: $("#public").checked,\n  };\n  btn.disabled = true;\n  try { const r = await api("/api/generate", { method: "POST", body: JSON.stringify(body) }); cfg.daily_left = r.daily_left; credits(); await refresh(); }\n  catch (e) { $("#err").textContent = e.message; }\n  btn.disabled = false;\n};\n\nfunction credits() {\n  $(".credits").hidden = !cfg.daily_limit;\n  if (!cfg.daily_limit) return;\n  $("#creditsTxt").textContent = `${cfg.daily_left} / ${cfg.daily_limit}`;\n  $("#creditsBar").style.width = (cfg.daily_left / cfg.daily_limit * 100) + "%";\n}\n\n/* ---------- lists ---------- */\nfunction card(s) {\n  const ready = s.status === "ready";\n  const st = s.status === "failed" ? `<small style="color:#ff7a7a">Failed: ${esc(s.error)}</small>`\n    : !ready ? `<small><span class="spin"></span>${s.status === "running" ? "Creating your song…" : "In queue…"}</small>`\n    : `<small>${esc(s.styles || s.prompt)}</small>`;\n  let vid = "";\n  if (ready && s.mine) {\n    vid = s.video === "ready" ? `<button data-a="watch">▶ Video</button><a href="/download/${s.id}.mp4">⬇ MP4</a>`\n      : s.video === "pending" ? `<button disabled><span class="spin"></span>Video…</button>`\n      : `<button data-a="video">🎬 Make video</button>`;\n  }\n  return `<div class="song ${queue[idx] && queue[idx].id === s.id ? "playing" : ""}" data-id="${s.id}">\n    <div class="cv" data-a="play">${ready ? `<img src="/media/${s.id}/cover.jpg" loading="lazy">` : ""}${ready ? \'<div class="pl">▶</div>\' : ""}</div>\n    <div class="meta"><b>${esc(s.title)}${ready ? `<span class="tag">${fmt(s.duration)}</span>` : ""}${s.instrumental ? \'<span class="tag">instrumental</span>\' : ""}${s.mine ? "" : \'<span class="tag">community</span>\'}</b>${st}</div>\n    ${ready ? `<div class="acts">\n      <button data-a="like" class="${s.liked ? "liked" : ""}">${s.liked ? "♥" : "♡"} ${s.likes || ""}</button>\n      ${s.lyrics ? \'<button data-a="lyrics">Lyrics</button>\' : ""}\n      <a href="/download/${s.id}.mp3">⬇ MP3</a>${vid}\n      ${s.mine ? `<button data-a="vis">${s.public ? "Public" : "Private"}</button><button data-a="del">🗑</button>` : ""}\n    </div>` : ""}\n  </div>`;\n}\nconst draw = (el, list, empty) => { cache[el] = list; $(el).innerHTML = list.length ? list.map(card).join("") : `<div class="empty">${empty}</div>`; };\n\nasync function refresh() {\n  try {\n    if (view === "create") draw("#latest", (await api("/api/songs")).slice(0, 12), "Your songs will appear here. Describe an idea and press Create ✦");\n    if (view === "library") draw("#library", await api("/api/songs?q=" + encodeURIComponent($("#search").value)), "No songs yet.");\n    if (view === "explore") draw("#explore", await api("/api/explore"), "Nothing shared yet – be the first!");\n  } catch (e) { }\n}\nsetInterval(() => {\n  const busy = Object.values(cache).flat().some(s => s.status === "pending" || s.status === "running" || s.video === "pending");\n  if (busy) refresh();\n}, 3000);\n$("#search").oninput = () => refresh();\n\ndocument.addEventListener("click", async e => {\n  const t = e.target.closest("[data-a]"); if (!t) return;\n  const row = t.closest(".song"); if (!row) return;\n  const id = row.dataset.id, list = Object.values(cache).flat().find(s => s.id === id), a = t.dataset.a;\n  if (a === "play") { const l = cache["#" + row.parentElement.id] || [list]; play(l.filter(x => x.status === "ready"), id); }\n  if (a === "like") { await api(`/api/songs/${id}/like`, { method: "POST" }); refresh(); }\n  if (a === "del") { if (confirm("Delete this song?")) { await api(`/api/songs/${id}`, { method: "DELETE" }); refresh(); } }\n  if (a === "vis") { await api(`/api/songs/${id}`, { method: "PATCH", body: JSON.stringify({ public: !list.public }) }); refresh(); }\n  if (a === "lyrics") { $("#lyTitle").textContent = list.title; $("#lyBody").textContent = list.lyrics; $("#lyricModal").hidden = false; }\n  if (a === "video") { try { await api(`/api/songs/${id}/video`, { method: "POST" }); toast("Video bana raha hai… ho jaye to MP4 button aa jayega"); refresh(); } catch (er) { toast(er.message); } }\n  if (a === "watch") { $("#vidEl").src = `/media/${id}/video.mp4`; $("#vidModal").hidden = false; $("#vidEl").play(); audio.pause(); }\n});\n$("#vidClose").onclick = () => { $("#vidEl").pause(); $("#vidModal").hidden = true; };\n\n/* ---------- player ---------- */\nfunction play(list, id) {\n  queue = list; idx = Math.max(0, list.findIndex(s => s.id === id)); load();\n}\nfunction load() {\n  const s = queue[idx]; if (!s) return;\n  audio.src = `/media/${s.id}/audio.mp3`; audio.play();\n  $("#player").hidden = false; $("#pCover").src = `/media/${s.id}/cover.jpg`;\n  $("#pTitle").textContent = s.title; $("#pStyles").textContent = s.styles || s.prompt || "";\n  $$(".song").forEach(r => r.classList.toggle("playing", r.dataset.id === s.id));\n}\n$("#pPlay").onclick = () => audio.paused ? audio.play() : audio.pause();\n$("#pNext").onclick = () => { if (queue.length) { idx = (idx + 1) % queue.length; load(); } };\n$("#pPrev").onclick = () => { if (queue.length) { idx = (idx - 1 + queue.length) % queue.length; load(); } };\naudio.onplay = () => $("#pPlay").textContent = "❚❚";\naudio.onpause = () => $("#pPlay").textContent = "▶";\naudio.onended = () => $("#pNext").click();\naudio.ontimeupdate = () => { if (audio.duration) { $("#pSeek").value = audio.currentTime / audio.duration * 1000; $("#pCur").textContent = fmt(audio.currentTime); $("#pDur").textContent = fmt(audio.duration); } };\n$("#pSeek").oninput = e => { if (audio.duration) audio.currentTime = e.target.value / 1000 * audio.duration; };\n$("#pVol").oninput = e => audio.volume = e.target.value / 100; audio.volume = .8;\n\n/* ---------- boot ---------- */\n(async () => {\n  cfg = await api("/api/config"); credits();\n  $("#duration").max = cfg.max_duration;\n  $("#engineNote").textContent = cfg.engine === "ace"\n    ? "Engine: ACE-Step 1.5 (AI music with vocals). Each Create makes 1 song."\n    : "Demo engine: instrumental-only procedural music (no AI vocals). Connect ACE-Step to get real AI songs with vocals – see README.";\n  refresh();\n})();\n'}

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DATA_DIR", os.path.join(BASE, "data"))
SONGS = os.path.join(DATA, "songs")
os.makedirs(SONGS, exist_ok=True)
DB = os.path.join(DATA, "dhun.db")

ENGINE = os.environ.get("ENGINE", "demo")           # demo | ace
MAX_DURATION = int(os.environ.get("MAX_DURATION", "600"))   # seconds (10 min)
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "20"))      # generations per user per day (0 = unlimited)
MAX_QUEUE = int(os.environ.get("MAX_QUEUE", "20"))

_sd = os.path.join(DATA, "_static"); os.makedirs(_sd, exist_ok=True)
for _n, _c in STATIC.items():
    open(os.path.join(_sd, _n), "w", encoding="utf-8").write(_c)
app = Flask(__name__, static_folder=_sd, static_url_path="/static")
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
            video TEXT DEFAULT 'none', engine TEXT);
        CREATE TABLE IF NOT EXISTS likes(uid TEXT, song TEXT, PRIMARY KEY(uid, song));
        CREATE TABLE IF NOT EXISTS usage(uid TEXT, day TEXT, n INTEGER, PRIMARY KEY(uid, day));
        """)
        # anything left running from a previous process is dead
        c.execute("UPDATE songs SET status='failed', error='Server restarted' WHERE status IN ('pending','running')")
        c.execute("UPDATE songs SET video='failed' WHERE video='pending'")


init_db()


# ------------------------------------------------------------------ identity
def uid():
    u = request.cookies.get("uid")
    if not u or len(u) != 32:
        u = getattr(request, "new_uid", None) or uuid.uuid4().hex
        request.new_uid = u
    return u


@app.after_request
def set_cookie(resp):
    if getattr(request, "new_uid", None):
        resp.set_cookie("uid", request.new_uid, max_age=3600 * 24 * 365 * 3, samesite="Lax")
    return resp


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
        for v in (0,):
            sid = uuid.uuid4().hex
            t = title or (prompt[:40] or styles[:40] or "Untitled")
            c.execute("INSERT INTO songs(id,uid,grp,variant,title,prompt,lyrics,styles,exclude,"
                      "instrumental,duration,quality,status,public,created,engine) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (sid, u, grp, v, t if v == 0 else t, prompt, lyrics, styles, exclude,
                       int(instrumental), duration, quality, "pending", int(d.get("public", True)), now, ENGINE))
            ids.append(sid)
        c.execute("INSERT INTO usage(uid,day,n) VALUES(?,?,1) ON CONFLICT(uid,day) DO UPDATE SET n=n+1", (u, day))
    Q.put(("gen", ids))
    return jsonify(ids=ids, daily_left=left_today(u))


def _list(where, args, u, limit=100):
    with conn() as c:
        likes = {r["song"] for r in c.execute("SELECT song FROM likes WHERE uid=?", (u,))}
        rows = c.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM likes l WHERE l.song=s.id) AS nlikes FROM songs s "
            f"WHERE {where} ORDER BY created DESC, variant ASC LIMIT {int(limit)}", args).fetchall()
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
    return jsonify(_list("public=1 AND status='ready'", (), u, 100))


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
    set_status(ids, status="running")
    work = os.path.join(song_dir(ids[0]), "_tmp")
    os.makedirs(work, exist_ok=True)
    try:
        outs = engines.ENGINES[rows[0]["engine"]](job, work, variants=len(ids))
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
            do_generate(arg) if kind == "gen" else do_video(arg)
        finally:
            Q.task_done()


threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "7860"))
    print(f"Dhun running on http://0.0.0.0:{port}  engine={ENGINE}  max={MAX_DURATION}s")
    app.run(host="0.0.0.0", port=port, threaded=True)
