PYTHON ?= python3
export PYTHONPATH := $(CURDIR)/src
export PYTHONDONTWRITEBYTECODE := 1

.PHONY: run test media app

run:
	$(PYTHON) -B -m audio_forge

test:
	$(PYTHON) -B -m unittest discover -s tests -t . -v

media:
	$(PYTHON) -B scripts/build_media.py

app:
	$(PYTHON) -B scripts/build_app.py
