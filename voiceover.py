"""Script -> spoken voice-over over background music. Runs fully offline.

Speech: Piper (set PIPER_VOICES_DIR, files named <lang>*.onnx, e.g. hi_IN-....onnx),
otherwise espeak-ng (robotic, but needs no download).
"""
import glob
import os
import shutil
import subprocess
import sys
import wave

RATE = 44100


def parse(d):
    if not isinstance(d, dict):
        raise ValueError("JSON object chahiye")
    segs = d.get("segments")
    if not segs:
        segs = [{"text": t} for t in str(d.get("script") or "").splitlines()]
    if not isinstance(segs, list):
        raise ValueError("segments ek list honi chahiye")
    out = []
    try:
        for s in segs:
            text = str(s.get("text") or "").strip()
            if text:
                out.append({"text": text, "pause": max(0.0, min(10.0, float(s.get("pause", 0.4))))})
        music = d.get("music") or {}
        volume = max(0.0, min(1.0, float(music.get("volume", 0.25))))
        style = str(music.get("style", "soft cinematic"))[:200]
    except (AttributeError, TypeError, ValueError):
        raise ValueError("segments / music ka format galat hai")
    if not out:
        raise ValueError("Script khali hai")
    if sum(len(s["text"]) for s in out) > 9000:
        raise ValueError("Script bahut lambi hai (max 9000 akshar, lagbhag 10 min)")
    lang = str(d.get("language") or "hi")
    if lang not in ("hi", "en", "bn", "pa", "mr"):
        raise ValueError("language: hi, en, bn, pa ya mr")
    return {"title": str(d.get("title") or out[0]["text"][:40])[:80], "language": lang,
            "segments": out, "music_style": style, "music_volume": volume}


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def speak(text, lang, out_wav):
    voices = os.environ.get("PIPER_VOICES_DIR")
    models = sorted(glob.glob(os.path.join(voices, f"{lang}*.onnx"))) if voices else []
    if models:
        subprocess.run([sys.executable, "-m", "piper", "-m", models[0], "-f", out_wav],
                       input=text.encode(), check=True)
    elif shutil.which("espeak-ng"):
        subprocess.run(["espeak-ng", "-v", lang, "-s", "150", "-w", out_wav, "--stdin"],
                       input=text.encode(), check=True)
    else:
        raise RuntimeError("Voice engine nahi mila: Piper voice ya espeak-ng install karein")


def render(spec, music_engine, sid, work, out_mp3, max_seconds):
    speech = os.path.join(work, "speech.wav")
    with wave.open(speech, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        total = 0
        for i, seg in enumerate(spec["segments"]):
            raw, fixed = os.path.join(work, f"s{i}.wav"), os.path.join(work, f"f{i}.wav")
            speak(seg["text"], spec["language"], raw)
            _ffmpeg("-i", raw, "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", fixed)
            with wave.open(fixed) as r:
                frames = r.readframes(r.getnframes())
            frames += b"\0\0" * int(seg["pause"] * RATE)
            total += len(frames) // 2
            if total > max_seconds * RATE:
                raise RuntimeError("Voice-over 10 minute se lamba ho gaya")
            w.writeframes(frames)
    seconds = total / RATE
    if not spec["music_volume"] or not spec["music_style"]:
        _ffmpeg("-i", speech, "-b:a", "192k", out_mp3)
        return
    job = {"id": sid, "prompt": "", "styles": spec["music_style"], "lyrics": "", "instrumental": True,
           "exclude": "", "duration": max(30.0, min(float(max_seconds), seconds + 2)),
           "language": "", "quality": "fast"}
    music = music_engine(job, work, variants=1)[0]["path"]
    # loop the music if short, duck it under the voice, stop with the voice
    graph = (f"[0:a]aformat=channel_layouts=stereo,apad=pad_dur=1.5,asplit=2[v][key];"
             f"[1:a]aformat=channel_layouts=stereo,volume={spec['music_volume']}[m];"
             "[m][key]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[duck];"
             "[v][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[out]")
    _ffmpeg("-i", speech, "-stream_loop", "-1", "-i", music, "-filter_complex", graph,
            "-map", "[out]", "-b:a", "192k", out_mp3)
