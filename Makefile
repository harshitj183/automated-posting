.PHONY: install run test lint check help

# ── Default target ────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Automated Multi-Platform Posting System"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────
install: ## Install all Python dependencies
	pip install -r requirements.txt

# ── Development ───────────────────────────────────────────────────────────────
run: ## Start the development server on port 4000 (with auto-reload)
	uvicorn app.main:app --host 0.0.0.0 --port 4000 --reload

# ── Quality ───────────────────────────────────────────────────────────────────
test: ## Run the full test suite (no credentials required)
	pytest tests/ -v

lint: ## Check Python syntax across all source files
	python -m py_compile \
	  app/main.py app/schemas.py app/config.py \
	  app/platforms/base.py \
	  app/platforms/pastebin.py \
	  app/platforms/telegram.py \
	  app/platforms/mastodon.py \
	  app/platforms/reddit.py \
	  app/platforms/wordpress.py \
	  app/services/posting_service.py \
	&& echo "Syntax OK — no errors found."

check: lint test ## Run lint then tests
