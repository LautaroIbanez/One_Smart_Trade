.PHONY: help setup-backend setup-frontend setup install-backend install-frontend test-backend test-frontend lint-backend lint-frontend format-backend format-frontend run-backend run-frontend clean

help:
	@echo "One Smart Trade - Makefile Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup              - Setup both backend and frontend"
	@echo "  make setup-backend      - Setup backend only"
	@echo "  make setup-frontend     - Setup frontend only"
	@echo ""
	@echo "Install:"
	@echo "  make install-backend    - Install backend dependencies"
	@echo "  make install-frontend   - Install frontend dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make run-backend        - Run backend server"
	@echo "  make run-frontend       - Run frontend dev server"
	@echo ""
	@echo "Testing:"
	@echo "  make test-backend       - Run backend tests"
	@echo "  make test-frontend      - Run frontend tests"
	@echo ""
	@echo "Linting:"
	@echo "  make lint-backend       - Lint backend code"
	@echo "  make lint-frontend      - Lint frontend code"
	@echo ""
	@echo "Formatting:"
	@echo "  make format-backend     - Format backend code"
	@echo "  make format-frontend    - Format frontend code"
	@echo ""
	@echo "Clean:"
	@echo "  make clean              - Clean build artifacts"

setup: setup-backend setup-frontend

setup-backend:
	@echo "Setting up backend..."
	@cd backend && poetry install

setup-frontend:
	@echo "Setting up frontend..."
	@cd frontend && pnpm install

install-backend:
	@cd backend && poetry install

install-frontend:
	@cd frontend && pnpm install

run-backend:
	@cd backend && poetry run uvicorn app.main:app --reload --port 8000

run-frontend:
	@cd frontend && pnpm run dev

test-backend:
	@cd backend && poetry run pytest

test-frontend:
	@cd frontend && pnpm run test

lint-backend:
	@cd backend && poetry run ruff check . && poetry run mypy app

lint-frontend:
	@cd frontend && pnpm run lint

format-backend:
	@cd backend && poetry run ruff format .

format-frontend:
	@cd frontend && pnpm run format

clean:
	@echo "Cleaning build artifacts..."
	@rm -rf backend/.pytest_cache backend/htmlcov backend/.coverage
	@rm -rf frontend/dist frontend/node_modules/.vite frontend/coverage
	@find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete

