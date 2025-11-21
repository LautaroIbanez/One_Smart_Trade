#!/bin/bash
# Script para iniciar el servidor de desarrollo del backend
# Uso: ./start-dev.sh

cd "$(dirname "$0")"

echo "Iniciando servidor de desarrollo del backend..."
echo "El servidor estará disponible en http://localhost:8000"
echo "Presiona Ctrl+C para detener el servidor"
echo ""

# Verificar si Poetry está instalado
if ! command -v poetry &> /dev/null; then
    echo "ERROR: Poetry no está instalado o no está en PATH."
    echo "Por favor instala Poetry desde: https://python-poetry.org/docs/#installation"
    exit 1
fi

# Verificar si el puerto 8000 está en uso
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 || nc -z localhost 8000 2>/dev/null; then
    echo "ADVERTENCIA: El puerto 8000 ya está en uso."
    echo "Por favor detén el proceso que está usando el puerto 8000 o cambia el puerto en vite.config.ts"
    echo ""
fi

# Iniciar el servidor
poetry run uvicorn app.main:app --reload --port 8000

