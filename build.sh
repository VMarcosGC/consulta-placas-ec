#!/usr/bin/env bash
# Build script para Render (o cualquier plataforma que ejecute un comando de build).
# - Instala dependencias Python.
# - Descarga Chromium para Playwright (necesario para los scrapers).
#
# En el dashboard de Render → Build Command:  ./build.sh

set -o errexit

pip install --upgrade pip
pip install -r requirements.txt
playwright install --with-deps chromium
