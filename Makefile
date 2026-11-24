.PHONY: test verify dev-backend dev-world dev-operations dev-jarvis build-frontend

PYTHON ?= python3

test:
	cd backend && $(PYTHON) -m unittest discover -s tests -p "test_*.py" -v

build-frontend:
	cd frontend && npm run build && npm run build:operations && npm run build:jarvis

verify: test build-frontend

dev-backend:
	cd backend && $(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-world:
	cd frontend && npm run dev:world

dev-operations:
	cd frontend && npm run dev:operations

dev-jarvis:
	cd frontend && npm run dev:jarvis
