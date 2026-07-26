SERVICE_ROOT := $(abspath ../..)
REPO_ROOT := $(abspath ../../..)
QWQ_OUTPUT_ROOT := $(REPO_ROOT)/.qwq_output
QWQ_PYTHON_CACHE_ROOT ?= $(HOME)/.cache/quwoquan/python-envs
REC_PYTHON_ROOT := $(QWQ_PYTHON_CACHE_ROOT)/rec-model
REC_PYTHON := $(REC_PYTHON_ROOT)/bin/python
ML_PYTHON ?= $(REC_PYTHON)
RUNTIME_REQUIREMENTS := internal/recommendation/recommendation_model_release/infrastructure/model_runtime/requirements.txt
RUNTIME_REQUIREMENTS_MARKER := $(REC_PYTHON_ROOT)/requirements.sha256
PYTHON_SOURCES := cmd internal generated tests
PYTEST_FLAGS := -o cache_dir=$(QWQ_OUTPUT_ROOT)/env/repo/local/tests/cache/pytest/recommendation-service

.PHONY: prepare-test-python build test gate

prepare-test-python:
	@mkdir -p "$(dir $(REC_PYTHON_ROOT))"
	@if [ ! -x "$(ML_PYTHON)" ]; then python3 -m venv "$(REC_PYTHON_ROOT)"; fi
	@cd $(SERVICE_ROOT)/services/recommendation-service && \
		requirements_digest="$$("$(ML_PYTHON)" -B -c 'import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$(RUNTIME_REQUIREMENTS)")"; \
		if [ ! -f "$(RUNTIME_REQUIREMENTS_MARKER)" ] || [ "$$(tr -d '\n' < "$(RUNTIME_REQUIREMENTS_MARKER)")" != "$$requirements_digest" ]; then \
			"$(ML_PYTHON)" -B -m pip install --disable-pip-version-check -r "$(RUNTIME_REQUIREMENTS)"; \
			printf '%s\n' "$$requirements_digest" > "$(RUNTIME_REQUIREMENTS_MARKER)"; \
		fi
	@PYTHONDONTWRITEBYTECODE=1 "$(ML_PYTHON)" -B -c 'import fastapi, pymongo, pytest'

build: prepare-test-python
	cd $(SERVICE_ROOT)/services/recommendation-service && PYTHONDONTWRITEBYTECODE=1 $(ML_PYTHON) -B -c 'import ast,pathlib; [ast.parse(path.read_text(encoding="utf-8"), filename=str(path)) for root in "$(PYTHON_SOURCES)".split() for path in pathlib.Path(root).rglob("*.py")]'

test: prepare-test-python
	cd $(SERVICE_ROOT)/services/recommendation-service && PYTHONDONTWRITEBYTECODE=1 $(ML_PYTHON) -B -m pytest $(PYTEST_FLAGS) -q tests

gate: build test
