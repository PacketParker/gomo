FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SCHEDULE_FILE=/data/schedule.json \
    CYCLE_FILE=/data/cycle.json

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# uid/gid 1000 is the usual first user on the host, so that user owns the files in /data.
RUN groupadd --gid 1000 garden \
    && useradd --uid 1000 --gid 1000 --no-create-home garden \
    && mkdir /data && chown garden:garden /data
COPY . .

USER garden
VOLUME /data
EXPOSE 8080

# The Flask server stops cleanly on Ctrl-C; plain SIGTERM would leave PID 1 hanging.
STOPSIGNAL SIGINT
# One process only: the scheduler and live updates are in-process threads.
CMD ["python", "app.py"]
