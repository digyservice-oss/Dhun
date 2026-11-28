"""Cover art (PIL) and MP4 visualizer video (ffmpeg)."""
import colorsys
import hashlib
import os
import random
import subprocess

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/google-fonts/ofl/notosansdevanagari/NotoSansDevanagari[wdth,wght].ttf",
    "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _font(size, text=""):
    # Prefer a Devanagari-capable font when the text contains Hindi.
    cands = FONT_CANDIDATES if any("ऀ" <= c <= "ॿ" for c in text) else FONT_CANDIDATES[2:] + FONT_CANDIDATES[:2]
    for p in cands:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _palette(seed):
    h = int(hashlib.md5(seed.encode()).hexdigest()[:6], 16)
    base = (h % 360) / 360.0
    def c(hh, s, v):
        r, g, b = colorsys.hsv_to_rgb(hh % 1.0, s, v)
        return int(r * 255), int(g * 255), int(b * 255)
    return c(base, 0.75, 0.95), c(base + 0.12, 0.8, 0.55), c(base + 0.55, 0.7, 0.25)


def make_cover(seed, path, size=640):
    a, b, c = _palette(seed)
    rnd = random.Random(seed)
    img = Image.new("RGB", (size, size), c)
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x * 0.4 + y * 0.9) / (size * 1.3)
            px[x, y] = tuple(int(b[i] * (1 - t) + c[i] * t) for i in range(3))
    layer = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(6):
        r = rnd.randint(size // 6, size // 2)
        x, y = rnd.randint(0, size), rnd.randint(0, size)
        d.ellipse([x - r, y - r, x + r, y + r], fill=a if rnd.random() > .4 else b)
    layer = layer.filter(ImageFilter.GaussianBlur(size // 10))
    img = Image.blend(img, layer, 0.55)
    img.save(path, "JPEG", quality=88)


def make_video_bg(cover_path, title, styles, out_png, w=1280, h=720):
    bg = Image.open(cover_path).convert("RGB").resize((w, w)).crop((0, (w - h) // 2, w, (w - h) // 2 + h))
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    bg = Image.blend(bg, dark, 0.55)
    art = Image.open(cover_path).convert("RGB").resize((300, 300))
    bg.paste(art, (90, 150))
    d = ImageDraw.Draw(bg)
    d.text((440, 190), title[:42], font=_font(58, title), fill=(255, 255, 255))
    d.text((440, 275), (styles or "")[:70], font=_font(28, styles or ""), fill=(220, 220, 230))
    d.text((440, 330), "Made with Dhun AI", font=_font(24), fill=(255, 140, 120))
    bg.save(out_png)


def make_video(audio_path, cover_path, title, styles, out_mp4, workdir):
    bg = os.path.join(workdir, "vbg.png")
    make_video_bg(cover_path, title, styles, bg)
    fc = ("[1:a]showwaves=s=1280x170:mode=cline:rate=24:colors=white@0.9,format=yuva420p[w];"
          "[0:v][w]overlay=0:H-h-60,format=yuv420p[v]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "24", "-i", bg,
           "-i", audio_path, "-filter_complex", fc, "-map", "[v]", "-map", "1:a",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "31", "-r", "24",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out_mp4]
    subprocess.run(cmd, check=True)
    try:
        os.remove(bg)
    except OSError:
        pass
