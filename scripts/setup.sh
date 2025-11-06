#!/bin/bash
set -e

echo "🚀 Setting up One Smart Trade..."

# Backend setup
echo "📦 Setting up backend..."
cd backend
if ! command -v poetry &> /dev/null; then
    echo "Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
fi
poetry install
cd ..

# Frontend setup
echo "📦 Setting up frontend..."
cd frontend
if ! command -v pnpm &> /dev/null; then
    echo "Installing pnpm..."
    npm install -g pnpm
fi
pnpm install
cd ..

echo "✅ Setup complete!"
echo ""
echo "To run backend: cd backend && poetry run uvicorn app.main:app --reload"
echo "To run frontend: cd frontend && pnpm run dev"

