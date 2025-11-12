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
	python server.py


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
	rm -f data/bot.db
	@echo "Database reset. Bot will create new database on next run."

# Docker
docker-build:
	docker build -t ingress-bot .

docker-run:
	docker run -d --name ingress-bot --env-file .env ingress-bot

docker-stop:
	docker stop ingress-bot
	docker rm ingress-bot

# Ubuntu 24.04 LTS Deployment
deploy-ubuntu:
	@echo "Deploying to Ubuntu 24.04 LTS Linode server..."
	./deploy-linode.sh

deploy-ubuntu-interactive:
	@echo "Interactive Ubuntu 24.04 LTS deployment with prompts..."
	./deploy-linode.sh

# Ubuntu Commands
ubuntu-check-deps:
	@echo "Checking Ubuntu 24.04 LTS dependencies..."
	apt list --installed | grep -E "python3|git|redis-server|nginx|nodejs|npm" || echo "Some packages missing"

ubuntu-update:
	@echo "Updating Ubuntu 24.04 LTS packages..."
	sudo apt update && sudo apt upgrade -y

ubuntu-services:
	@echo "Checking Ubuntu services status..."
	sudo systemctl status redis-server || echo "Redis service status: not running"
	sudo systemctl status nginx || echo "Nginx service status: not running"
	sudo systemctl status ufw || echo "UFW firewall status: not running"

ubuntu-firewall:
	@echo "Showing UFW firewall rules..."
	sudo ufw status verbose

ubuntu-security:
	@echo "Ubuntu security status:"
	sudo ufw status
	echo "Fail2ban status:"
	sudo systemctl status fail2ban 2>/dev/null || echo "Fail2ban not installed"

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
	@echo "  install              - Install dependencies"
	@echo "  dev                 - Install with development dependencies"
	@echo "  run                 - Run the bot"
	@echo "  test                - Run tests"
	@echo "  lint                - Run linting"
	@echo "  format              - Format code"
	@echo "  clean               - Clean up temporary files"
	@echo "  db-reset            - Reset database"
	@echo "  docker-build        - Build Docker image"
	@echo "  docker-stop         - Stop Docker container"
	@echo "  deploy-ubuntu       - Deploy to Ubuntu 24.04 LTS Linode"
	@echo "  ubuntu-check-deps   - Check Ubuntu dependencies"
	@echo "  ubuntu-update       - Update Ubuntu packages"
	@echo "  ubuntu-services     - Check service status"
	@echo "  ubuntu-firewall     - Show firewall rules"
	@echo "  ubuntu-security      - Check security status"
	@echo "  dev-setup           - Setup development environment"