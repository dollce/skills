PYTHON ?= python3

.PHONY: check check-cli dev-link dev-link-global dev-status dev-unlink

check:
	$(PYTHON) spl/scripts/check_release.py
	$(PYTHON) -m unittest discover -s tests

check-cli:
	$(PYTHON) -m scripts.check_cli

dev-link:
	$(PYTHON) scripts/dev_links.py link

dev-link-global:
	$(PYTHON) scripts/dev_links.py link --global

dev-status:
	$(PYTHON) scripts/dev_links.py status

dev-unlink:
	$(PYTHON) scripts/dev_links.py unlink
