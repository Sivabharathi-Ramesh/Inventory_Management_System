SHELL := /bin/bash

# ── Config ────────────────────────────────────────────────────────────────────
APP       := InventoryManagement
VERSION   ?= 1.0.0
PYTHON    := python3
VENV      := venv
PIP       := $(VENV)/bin/pip
PY        := $(VENV)/bin/python
RELEASE   := release

# ── Default ───────────────────────────────────────────────────────────────────
.DEFAULT_GOAL := help

help:
	@echo ""
	@echo "  Inventory Management — Local Build Pipeline"
	@echo "  ─────────────────────────────────────────────"
	@echo "  make setup           Install all dependencies into venv"
	@echo "  make build-linux     Build portable Linux binary  → release/"
	@echo "  make build-windows   Build Windows .exe           → release/"
	@echo "  make build-all       Build both targets"
	@echo "  make build-onefile   Build both as single-file executables"
	@echo "  make release         Full pipeline: clean → setup → build-all"
	@echo "  make clean           Remove build artefacts (keep release/)"
	@echo "  make clean-all       Remove build artefacts + release/"
	@echo "  make ls-release      List contents of release/"
	@echo ""

# ── Environment ───────────────────────────────────────────────────────────────
setup:
	@echo "▶  Setting up virtual environment …"
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install pyinstaller
	@echo "✔  Environment ready"

# ── Build targets ─────────────────────────────────────────────────────────────
build-linux:
	@echo "▶  Building Linux binary …"
	$(PY) pipeline.py linux --version=$(VERSION)

build-windows:
	@echo "▶  Building Windows .exe …"
	$(PY) pipeline.py windows --version=$(VERSION)

build-all:
	@echo "▶  Building all targets …"
	$(PY) pipeline.py all --version=$(VERSION)

build-onefile:
	@echo "▶  Building single-file executables for all targets …"
	$(PY) pipeline.py all --onefile --version=$(VERSION)

# ── Full release pipeline ─────────────────────────────────────────────────────
release: clean setup build-all
	@echo ""
	@echo "══════════════════════════════════════"
	@echo "  RELEASE COMPLETE  →  $(RELEASE)/"
	@echo "══════════════════════════════════════"
	@$(MAKE) --no-print-directory ls-release

release-onefile: clean setup build-onefile
	@echo ""
	@echo "══════════════════════════════════════"
	@echo "  RELEASE (onefile) COMPLETE  →  $(RELEASE)/"
	@echo "══════════════════════════════════════"
	@$(MAKE) --no-print-directory ls-release

# ── Utilities ─────────────────────────────────────────────────────────────────
ls-release:
	@echo ""
	@find $(RELEASE) -maxdepth 3 | sort | sed 's|[^/]*/|  |g'
	@echo ""

clean:
	@echo "▶  Cleaning build artefacts …"
	$(PY) pipeline.py clean 2>/dev/null || true
	rm -rf build dist __pycache__ *.spec _build_tmp
	@echo "✔  Clean done"

clean-all: clean
	rm -rf $(RELEASE)
	@echo "✔  Release folder removed"

# ── Phony ─────────────────────────────────────────────────────────────────────
.PHONY: help setup build-linux build-windows build-all build-onefile \
        release release-onefile ls-release clean clean-all
