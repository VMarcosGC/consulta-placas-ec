# Imagen oficial de Microsoft Playwright con Python + Chromium + libs del sistema
# ya preinstalados. Es la única opción confiable para hostings que no permiten
# sudo apt-get (caso Render free tier native runtime).
# https://playwright.dev/python/docs/docker
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

# Cache de capas: deps primero, código después.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Los browsers ya vienen instalados en la imagen base, este step es defensivo
# (no descarga nada si ya está) y asegura que la versión coincida con playwright pip.
RUN playwright install chromium

COPY . .

# Render asigna PORT en runtime; HOST se sobreescribe por env var del servicio.
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

# Migraciones + start. Render usa este CMD si no se especifica startCommand.
CMD alembic upgrade head && python run.py
