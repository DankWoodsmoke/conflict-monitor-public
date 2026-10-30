FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS media-build
# Compile only the local source-card media formats the worker actually uses.
# General-purpose FFmpeg pulls unused network parsers and a large codec stack.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential pkg-config nasm libx264-dev zlib1g-dev curl gnupg ca-certificates && rm -rf /var/lib/apt/lists/*
COPY container/build_ffmpeg.sh /build_ffmpeg.sh
RUN sh /build_ffmpeg.sh

FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
WORKDIR /app
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends fonts-dejavu-core libx264-164 libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=media-build /opt/ffmpeg/bin/ffmpeg /opt/ffmpeg/bin/ffprobe /usr/local/bin/
COPY --from=media-build /opt/ffmpeg/share /usr/local/share/ffmpeg
COPY requirements.txt .
RUN python -m pip install --no-cache-dir pip==26.2.2 setuptools==84.2.1
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
RUN useradd --uid 10001 --create-home --home-dir /home/monitor monitor && mkdir -p /app/sessions /app/videos/briefing && chown -R monitor /app/sessions /app/videos \
    && find /usr -xdev -type f -perm /6000 -exec chmod a-s '{}' +
ENV HOME=/home/monitor
USER monitor
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-max-size", "4096"]
