FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core fonts-noto-core espeak-ng && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask numpy scipy pillow gunicorn piper-tts
RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app
COPY --chown=user *.py audio_to_video.html ./
COPY --chown=user static ./static
ENV DATA_DIR=/home/user/data
CMD ["sh", "-c", "gunicorn -w 1 --threads 8 --timeout 0 -b 0.0.0.0:${PORT:-7860} app:app"]
