# Ingress Prime Leaderboard Bot Makefile

.PHONY: install dev run test clean lint format

# Installation
install:
	pip install -r requirements.txt

dev:
	pip install -r requirements.txt
	pip install -e ".[dev]"

# Running
run:
	python main.py

run-termux:
	python scripts/run_termux.py

# Testing
test:
	python -m pytest tests/ -v

test-cov:
	python -m pytest tests/ -v --cov=bot --cov-report=html

# Code Quality
lint:
	flake8 bot/ tests/
	mypy bot/

format:
	black bot/ tests/
	isort bot/ tests/

# Cleanup
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/ dist/

# Database
db-backup:
	@echo "Run /backup command in bot for manual backup"

db-reset:
	rm -f bot.db
	@echo "Database reset. Bot will create new database on next run."

# Docker
docker-build:
	docker build -t ingress-bot .

docker-run:
	docker run -d --name ingress-bot --env-file .env ingress-bot

docker-stop:
	docker stop ingress-bot
	docker rm ingress-bot

# Development
dev-setup:
	@echo "Setting up development environment..."
	python -m venv venv
	source venv/bin/activate && pip install --upgrade pip
	source venv/bin/activate && pip install -r requirements.txt
	source venv/bin/activate && pip install -e ".[dev]"
	@echo "Development environment ready!"
	@echo "Activate with: source venv/bin/activate"

# Help
help:
	@echo "Available commands:"
	@echo "  install     - Install dependencies"
	@echo "  dev         - Install with development dependencies"
	@echo "  run         - Run the bot"
	@echo "  test        - Run tests"
	@echo "  lint        - Run linting"
	@echo "  format      - Format code"
	@echo "  clean       - Clean up temporary files"
	@echo "  db-reset    - Reset database"
	@echo "  docker-build - Build Docker image"
	@echo "  dev-setup   - Setup development environment"