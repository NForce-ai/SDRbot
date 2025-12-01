.PHONY: all lint format test help run test_integration test_watch

# Default target executed when no arguments are given to make.
all: help

######################
# TESTING AND COVERAGE
######################

# Define a variable for the test file path.
TEST_FILE ?= tests/
INTEGRATION_FILES ?= tests/integration_tests

test:
	uv run pytest --disable-socket --allow-unix-socket $(TEST_FILE)

test_integration:
	uv run pytest $(INTEGRATION_FILES)

test_watch:
	uv run ptw . -- $(TEST_FILE)

run:
	uvx --no-cache --reinstall .

build_executable:
	uv run pyinstaller --onefile sdrbot_entry.py --name sdrbot --paths . --collect-all sdrbot_cli


######################
# LINTING AND FORMATTING
######################

# Define a variable for Python and notebook files.
lint format: PYTHON_FILES=sdrbot_cli/ tests/
lint_diff format_diff: PYTHON_FILES=$(shell git diff --relative=. --name-only --diff-filter=d master | grep -E '\.py$$|\.ipynb$$')

lint lint_diff:
	[ "$(PYTHON_FILES)" = "" ] ||	uv run ruff format $(PYTHON_FILES) --diff
	@if [ "$(LINT)" != "minimal" ]; then \
		if [ "$(PYTHON_FILES)" != "" ]; then \
			uv run ruff check $(PYTHON_FILES) --diff; \
		fi; \
	fi
	# [ "$(PYTHON_FILES)" = "" ] || uv run mypy $(PYTHON_FILES)

format format_diff:
	[ "$(PYTHON_FILES)" = "" ] || uv run ruff format $(PYTHON_FILES)
	[ "$(PYTHON_FILES)" = "" ] || uv run ruff check --fix $(PYTHON_FILES)

format_unsafe:
	[ "$(PYTHON_FILES)" = "" ] || uv run ruff format --unsafe-fixes $(PYTHON_FILES)


######################
# UPSTREAM TRACKING
######################

# Fetch latest upstream tags
upstream_fetch:
	git fetch upstream --tags

# Show diff between our baseline (0.0.9) and latest upstream
upstream_diff:
	./scripts/upstream-diff.sh

# Show diff between specific versions (e.g., make upstream_diff_version V=0.0.10)
upstream_diff_version:
	./scripts/upstream-diff.sh $(V)

# List available upstream versions
upstream_versions:
	@echo "Available deepagents-cli versions:"
	@git tag -l 'deepagents-cli==*' | sort -V

######################
# HELP
######################

help:
	@echo '===================='
	@echo '-- LINTING --'
	@echo 'format                       - run code formatters'
	@echo 'lint                         - run linters'
	@echo '-- TESTS --'
	@echo 'test                         - run unit tests'
	@echo 'test TEST_FILE=<test_file>   - run all tests in file'
	@echo '-- UPSTREAM TRACKING --'
	@echo 'upstream_fetch               - fetch latest upstream tags'
	@echo 'upstream_diff                - show changes since our baseline (0.0.9)'
	@echo 'upstream_diff_version V=X    - show changes for specific version'
	@echo 'upstream_versions            - list available upstream versions'
