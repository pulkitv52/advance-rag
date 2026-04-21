# Advance-Rag Makefile

.PHONY: help up down nuke up-all down-all nuke-all install-uv backend-setup backend-start backend-stop logs-backend install-pnpm frontend-setup frontend-start frontend-stop frontend-preview logs-frontend start stop setup restart logs ps health build

# Variables
DOCKER_COMPOSE = -f docker-compose.yml
DOCKER = docker compose
BACKEND_PORT = 8081
FRONTEND_PORT = 5177
LOG_DIR_BACKEND = logs/backend
LOG_DIR_FRONTEND = logs/frontend
-include .env
export

UV = /home/pulkitv52/.local/bin/uv
PNPM = pnpm

help:
	@echo "Available commands:"
	@echo "  make up             - Ups infrastructure only (Postgres, Qdrant, Minio, Redis, Neo4j)"
	@echo "  make up-all         - Ups all services in Docker (infra + backend + frontend)"
	@echo "  make build          - Builds all Docker images"
	@echo "  make start          - Starts hybrid environment (infra in Docker + local app)"
	@echo "  make setup          - Setups backend and frontend dependencies"

# Infra Management
up:
	$(DOCKER) $(DOCKER_COMPOSE) up -d db qdrant minio redis neo4j

down:
	$(DOCKER) $(DOCKER_COMPOSE) down

nuke:
	$(DOCKER) $(DOCKER_COMPOSE) down -v

up-all:
	$(DOCKER) $(DOCKER_COMPOSE) up -d --build

down-all:
	$(DOCKER) $(DOCKER_COMPOSE) down

nuke-all:
	$(DOCKER) $(DOCKER_COMPOSE) down -v

build:
	$(DOCKER) $(DOCKER_COMPOSE) build

# Backend Commands
install-uv:
	curl -LsSf https://astral.sh/uv/install.sh | sh

backend-setup:
	cd backend && $(UV) sync

backend-start:
	@mkdir -p $(LOG_DIR_BACKEND)
	@echo "Starting backend..."
	@cd backend && nohup sh -cl "uv run python -m uvicorn src.main:app --host 0.0.0.0 --port $(BACKEND_PORT) --reload" > ../$(LOG_DIR_BACKEND)/app.log 2>&1 &

backend-stop:
	@echo "Stopping backend..."
	@pkill -f "uvicorn src.main:app" || true

logs-backend:
	tail -f $(LOG_DIR_BACKEND)/app.log

graph-align:
	@echo "Aligning Neo4j schema with fraud flags..."
	@cd backend && $(UV) run python scripts/align_graph_schema.py

# Frontend Commands
install-pnpm:
	npm install -g pnpm

frontend-setup:
	cd frontend && pnpm install

frontend-start:
	@mkdir -p $(LOG_DIR_FRONTEND)
	@echo "Starting frontend..."
	@$(MAKE) frontend-stop >/dev/null 2>&1 || true
	@cd frontend && nohup pnpm dev --host 0.0.0.0 --port $(FRONTEND_PORT) --strictPort </dev/null > ../$(LOG_DIR_FRONTEND)/dev.log 2>&1 &

frontend-stop:
	@echo "Stopping frontend..."
	@bash -lc "ps -eo pid=,args= | grep '/home/pulkitv52/Advance-rag/frontend' | grep 'pnpm dev --host 0.0.0.0 --port $(FRONTEND_PORT) --strictPort' | grep -v grep | awk '{print \$$1}' | xargs -r kill" || true
	@bash -lc "ps -eo pid=,args= | grep '/home/pulkitv52/Advance-rag/frontend' | grep 'vite/bin/vite.js --port $(FRONTEND_PORT)' | grep -v grep | awk '{print \$$1}' | xargs -r kill" || true
	@bash -lc "ps -eo pid=,args= | grep '/home/pulkitv52/Advance-rag/frontend' | grep '@esbuild/.*/bin/esbuild --service' | grep -v grep | awk '{print \$$1}' | xargs -r kill" || true

frontend-preview:
	cd frontend && pnpm build && pnpm preview

logs-frontend:
	tail -f $(LOG_DIR_FRONTEND)/dev.log

# Combined Commands
start: up
	@echo "Waiting for infra to stabilize..."
	@sleep 2
	$(MAKE) backend-start
	$(MAKE) frontend-start
	@echo "All services starting. Check logs/ directory for output."

stop: backend-stop frontend-stop
	$(DOCKER) $(DOCKER_COMPOSE) stop

setup: install-uv install-pnpm
	$(MAKE) backend-setup
	$(MAKE) frontend-setup

restart: stop start

logs:
	@echo "Tailing all logs..."
	tail -f $(LOG_DIR_BACKEND)/app.log $(LOG_DIR_FRONTEND)/dev.log

ps:
	@echo "--- Docker Services ---"
	$(DOCKER) $(DOCKER_COMPOSE) ps
	@echo ""
	@echo "--- Local Services ---"
	@pgrep -af "uvicorn|vite" || echo "No local backend/frontend running."

health:
	@echo "Checking health of services..."
	@$(DOCKER) $(DOCKER_COMPOSE) ps | grep -E "Up|running"



