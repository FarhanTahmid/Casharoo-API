FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Runs as an unprivileged user; logs and uploads are the only writable paths
RUN useradd --create-home app \
    && mkdir -p logs Media_Files staticfiles \
    && chown -R app:app logs Media_Files staticfiles
USER app

EXPOSE 8000

# The web process. The worker uses the same image with:
#   python manage.py procrastinate worker
CMD ["sh", "-c", "python manage.py collectstatic --noinput && python manage.py migrate --noinput && gunicorn casharoo.wsgi:application --bind 0.0.0.0:8000 --workers 3"]
