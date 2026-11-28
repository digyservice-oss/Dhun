"""Reference audio: validate an upload and turn it into a clean WAV the music model can use."""
import os
import re
import subprocess
import uuid

MIN_SECONDS, MAX_SECONDS = 10, 60


def path_for(ref_dir, ref_id):
    if not re.fullmatch(r"[0-9a-f]{32}", ref_id or ""):
        return None
    p = os.path.join(ref_dir, ref_id + ".wav")
    return p if os.path.exists(p) else None


def save(upload, ref_dir):
    """Returns (ref_id, warnings). Raises ValueError for unusable audio."""
    os.makedirs(ref_dir, exist_ok=True)
    ref_id = uuid.uuid4().hex
    src, dst = os.path.join(ref_dir, ref_id + ".upload"), os.path.join(ref_dir, ref_id + ".wav")
    try:
        upload.save(src)
        r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-nostats", "-protocol_whitelist", "file,pipe",
                            "-i", src, "-vn", "-t", str(MAX_SECONDS), "-af", "volumedetect",
                            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", dst],
                           capture_output=True, text=True, errors="replace", timeout=300)
        seconds = (os.path.getsize(dst) - 44) / (48000 * 4) if r.returncode == 0 and os.path.exists(dst) else 0
        mean = re.search(r"mean_volume: (-?[0-9.]+) dB", r.stderr)
        peak = re.search(r"max_volume: (-?[0-9.]+) dB", r.stderr)
        if not seconds or not mean:
            raise ValueError("Yeh audio file padhi nahi ja saki")
        if seconds < MIN_SECONDS:
            raise ValueError(f"Reference kam se kam {MIN_SECONDS} second ka hona chahiye")
        if float(mean.group(1)) < -45:
            raise ValueError("Recording bahut dheemi ya khaali hai")
        warnings = []
        if float(mean.group(1)) < -30:
            warnings.append("Awaaz dheemi hai")
        if peak and float(peak.group(1)) >= 0:
            warnings.append("Awaaz phat (clip) rahi ho sakti hai")
        return ref_id, warnings
    except (ValueError, subprocess.TimeoutExpired) as e:
        if os.path.exists(dst):
            os.remove(dst)
        raise ValueError(str(e) if isinstance(e, ValueError) else "File bahut badi hai")
    finally:
        if os.path.exists(src):
            os.remove(src)
