.PHONY: help install test harness docker-up docker-down

PYTHON = .\.venv\Scripts\python.exe
PYTEST = .\.venv\Scripts\pytest.exe

help:
	@echo "Threat Defense Swarm Management Commands:"
	@echo "  make install       Install dependencies into virtual environment"
	@echo "  make test          Run entire Pytest test suite"
	@echo "  make harness       Run 100-run evaluation benchmark"
	@echo "  make docker-up     Build and run services via Docker Compose"
	@echo "  make docker-down   Stop Docker Compose containers"

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest

harness:
	$(PYTHON) harness/runner.py

docker-up:
	docker-compose up --build -d

docker-down:
	docker-compose down
