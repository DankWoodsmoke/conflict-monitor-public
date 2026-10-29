FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN python -m pip install --no-cache-dir pip==26.2.2 setuptools==84.2.1
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
RUN useradd --uid 10001 --create-home --home-dir /home/monitor monitor && mkdir -p /app/sessions /app/videos/briefing && chown -R monitor /app/sessions /app/videos
ENV HOME=/home/monitor
USER monitor
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-max-size", "4096"]
