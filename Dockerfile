FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system django \
    && adduser --system --ingroup django django

COPY requirements/ ./requirements/
RUN pip install --upgrade pip \
    && pip install -r requirements/production.txt

COPY . .
COPY docker/entrypoint.sh /entrypoint.sh

RUN mkdir -p /app/staticfiles /app/media /app/logs \
    && chmod +x /entrypoint.sh \
    && chown -R django:django /app/staticfiles /app/media /app/logs /entrypoint.sh

USER django

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--no-control-socket"]
