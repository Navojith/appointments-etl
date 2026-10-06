FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ETL_DB_PATH=/data/appointments.db \
    ETL_LOG_DIR=/data/logs

RUN useradd --uid 10001 --no-create-home etl && mkdir /data && chown etl /data

WORKDIR /app
COPY etl ./etl

USER etl
VOLUME /data
CMD ["python", "-m", "etl"]
