PYTHON ?= python3

.PHONY: install test lint demo serve doctor web

install:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	ruff check src tests
	ruff format --check src tests

test:
	pytest

demo:
	shorts-pipeline run --topic "How to explain a hard idea in 30 seconds" --script-provider offline --voice-provider offline --publish --out docs/demo-reel.mp4

serve:
	shorts-pipeline serve --host 127.0.0.1 --port 8080

doctor:
	shorts-pipeline doctor

web:
	cd web && npm install && npm run build
