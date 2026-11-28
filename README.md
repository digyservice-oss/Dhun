# Dhun
## Audio → Video tool

Open `/audio-to-video` in the running app. Upload an audio file (MP3/WAV/M4A…), pick a background
(photo or gradient), visualizer (bars, mirror, waveform, circle, pulse), title/artist text and size
(16:9, 9:16 Reels/Shorts, 1:1, 4:5), then click **Video banao**. The video is rendered in the browser in
real time; if the browser can't record H.264 directly, the clip is converted to MP4 (H.264 + AAC) by
`/api/to-mp4` using ffmpeg and deleted from the server right away.

## Login
First visit: enter the setup code printed in the server log (or set `SETUP_CODE`) and choose a password.
Keep `DATA_DIR` on persistent storage, or the password and songs are lost on restart.

### Forgot password
`/reset` accepts the setup code of the current run. To receive a code by email instead, set `SMTP_USER`,
`SMTP_PASSWORD` (a Gmail app password) and `RESET_EMAIL` (in Colab: add them under Secrets).

## Engine
No paid API is needed. `ENGINE=ace` uses your own ACE-Step server (`ACESTEP_URL`, needs a GPU).
The default `demo` engine makes simple instrumental music only.

## JSON / voice-over
`POST /api/voiceover` with `{"title":"", "language":"hi", "script":"..." or "segments":[{"text":"","pause":0.5}],
"music":{"style":"soft cinematic","volume":0.25}}`. In the UI use the "JSON / Voice-over" tab.
Songs use `{"type":"song","styles":"","lyrics":"","duration":120}`.
Hindi and English use the free Kokoro-82M model when `requirements-voice.txt` is installed (the Colab notebook
does this); `"voice"` is `female` or `male`. For other languages set `PIPER_VOICES_DIR` to a folder with Piper models; otherwise espeak-ng is used.
