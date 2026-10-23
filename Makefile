COMPOSE = docker compose

.PHONY: setup up seed test lint migrate eval

setup:
	test ! -e .env && python3 -c 'import base64, pathlib, secrets; template = pathlib.Path(".env.example").read_text(); key = base64.b64encode(secrets.token_bytes(32)).decode(); configured = template.replace("DATA_ENCRYPTION_KEY=\n", f"DATA_ENCRYPTION_KEY={key}\n").replace("DATA_ENCRYPTION_KEYS=\n", f"DATA_ENCRYPTION_KEYS={{\"demo\":\"{key}\"}}\n"); pathlib.Path(".env").write_text(configured)'

up:
	$(COMPOSE) up --build -d

seed:
	$(COMPOSE) exec backend python -m app.seed

test:
	$(COMPOSE) exec backend pytest -q

lint:
	$(COMPOSE) exec backend ruff check app tests
	cd frontend && npm run lint

migrate:
	$(COMPOSE) exec backend alembic upgrade head

eval:
	@echo "Evals completos fazem parte do marco M5."
