SHELL := /bin/bash
COMPOSE := docker compose
.PHONY: up down build reset logs psql smoke clean

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down -v
	$(COMPOSE) up -d --build
	@echo "Waiting for the app to boot..."
	@for i in $$(seq 1 60); do \
		curl -sf http://localhost:9080/api/v1/core/health >/dev/null 2>&1 && break; sleep 2; \
	done
	@curl -sf http://localhost:9080/api/v1/core/health && echo " -> OnlineBank is up: http://localhost:9080"

logs:
	$(COMPOSE) logs -f backend

psql:
	$(COMPOSE) exec db psql -U bank -d onlinebank

smoke:
	bash scripts/smoke.sh

clean:
	$(COMPOSE) down -v
