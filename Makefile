.PHONY: help up down logs migrate seed clean ps health test

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help:
	@echo "$(BLUE)GeM Tender SaaS — Development Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Docker & Infrastructure:$(NC)"
	@echo "  make up              Start all Docker services (postgres, redis)"
	@echo "  make down            Stop all Docker services"
	@echo "  make ps              Show running containers"
	@echo "  make logs            Tail logs from all services"
	@echo "  make clean           Remove containers and volumes (WARNING: deletes data)"
	@echo "  make health          Check health of services"
	@echo ""
	@echo "$(GREEN)Database:$(NC)"
	@echo "  make migrate         Run Alembic migrations (Phase 2)"
	@echo "  make seed            Create test user (Phase 2)"
	@echo ""
	@echo "$(GREEN)Development:$(NC)"
	@echo "  make test            Run all tests (Phase 15)"
	@echo ""

# === Docker Management ===

up:
	@echo "$(BLUE)Starting Docker services...$(NC)"
	docker compose up -d
	@echo "$(GREEN)✓ Docker services started$(NC)"
	@echo "  - PostgreSQL: localhost:5432"
	@echo "  - Redis: localhost:6379"

down:
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	docker compose down
	@echo "$(GREEN)✓ Docker services stopped$(NC)"

ps:
	@echo "$(BLUE)Running containers:$(NC)"
	docker compose ps

logs:
	@echo "$(BLUE)Tailing Docker logs (Ctrl+C to stop)...$(NC)"
	docker compose logs -f

health:
	@echo "$(BLUE)Checking service health...$(NC)"
	@docker compose ps --format "table {{.Service}}\t{{.State}}"
	@echo ""
	@echo "$(BLUE)Testing connections:$(NC)"
	@echo "  PostgreSQL..."
	@docker compose exec postgres pg_isready -U gem -d gem_tender 2>/dev/null && echo "    $(GREEN)✓ OK$(NC)" || echo "    $(RED)✗ FAILED$(NC)"
	@echo "  Redis..."
	@docker compose exec redis redis-cli ping 2>/dev/null | grep -q "PONG" && echo "    $(GREEN)✓ OK$(NC)" || echo "    $(RED)✗ FAILED$(NC)"

clean:
	@echo "$(RED)WARNING: This will delete all Docker containers and volumes!$(NC)"
	@read -p "Are you sure? (yes/no) " confirm && \
	[ "$$confirm" = "yes" ] && \
	(docker compose down -v && echo "$(GREEN)✓ Cleaned$(NC)") || \
	echo "$(YELLOW)Cancelled$(NC)"

# === Database ===

migrate:
	@echo "$(BLUE)Running Alembic migrations...$(NC)"
	@if [ ! -d "apps/api/alembic" ]; then \
		echo "$(RED)Error: apps/api/alembic not found. Run Phase 2 setup first.$(NC)"; \
		exit 1; \
	fi
	@cd apps/api && alembic upgrade head
	@echo "$(GREEN)✓ Migrations complete$(NC)"

seed:
	@echo "$(BLUE)Seeding test data...$(NC)"
	@if [ ! -f "scripts/seed.py" ]; then \
		echo "$(RED)Error: scripts/seed.py not found. Run Phase 2 setup first.$(NC)"; \
		exit 1; \
	fi
	@python scripts/seed.py
	@echo "$(GREEN)✓ Seed complete$(NC)"

# === Testing ===

test:
	@echo "$(BLUE)Running tests...$(NC)"
	pytest tests/ -v --cov=apps --cov-report=html
	@echo "$(GREEN)✓ Tests complete. Report: htmlcov/index.html$(NC)"

# === Development helpers ===

install-deps:
	@echo "$(BLUE)Installing local dependencies...$(NC)"
	@echo "  Installing db-models..."
	pip install -e packages/db-models
	@echo "  Installing API dependencies..."
	cd apps/api && pip install -e .
	@echo "  Installing Worker dependencies..."
	cd apps/worker && pip install -e .
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

psql:
	@echo "$(BLUE)Connecting to PostgreSQL...$(NC)"
	docker compose exec postgres psql -U gem -d gem_tender

redis-cli:
	@echo "$(BLUE)Connecting to Redis...$(NC)"
	docker compose exec redis redis-cli

# === CI/CD ===

verify-setup:
	@echo "$(BLUE)Verifying Phase 1 setup...$(NC)"
	@which docker > /dev/null || (echo "$(RED)✗ Docker not installed$(NC)" && exit 1)
	@which docker-compose > /dev/null || (echo "$(RED)✗ Docker Compose not installed$(NC)" && exit 1)
	@[ -f "docker-compose.yml" ] || (echo "$(RED)✗ docker-compose.yml missing$(NC)" && exit 1)
	@[ -f ".env.example" ] || (echo "$(RED)✗ .env.example missing$(NC)" && exit 1)
	@[ -f ".gitignore" ] || (echo "$(RED)✗ .gitignore missing$(NC)" && exit 1)
	@echo "$(GREEN)✓ Phase 1 setup verified$(NC)"
