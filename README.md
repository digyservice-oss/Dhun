# Dhun
## Audio → Video tool

Open `/audio-to-video` in the running app. Upload an audio file (MP3/WAV/M4A…), pick a background
(photo or gradient), visualizer (bars, mirror, waveform, circle, pulse), title/artist text and size
(16:9, 9:16 Reels/Shorts, 1:1, 4:5), then click **Video banao**. The video is rendered in the browser in
real time; if the browser can't record H.264 directly, the clip is converted to MP4 (H.264 + AAC) by
`/api/to-mp4` using ffmpeg and deleted from the server right away.
