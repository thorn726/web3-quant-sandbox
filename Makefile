.PHONY: setup check verify courseware-check teaching-plots \
        deploy deploy-service deploy-timer service-status service-logs service-restart \
        snapshot-refresh snapshot-status snapshot-logs

PYTHON ?= python3
VENV_PYTHON := .venv/bin/python
SANDBOX_HOST ?= 0.0.0.0
SANDBOX_PORT ?= 8765
ON_CALENDAR ?= *-*-* 06:30:00
SERVICE_NAME := web3-sandbox
SNAPSHOT_TIMER_NAME := web3-sandbox-snapshot.timer
SNAPSHOT_SERVICE_NAME := web3-sandbox-snapshot.service

setup:
	$(PYTHON) scripts/course.py setup

verify:
	$(PYTHON) scripts/course.py verify

courseware-check:
	$(PYTHON) scripts/course.py courseware-check

teaching-plots:
	$(PYTHON) scripts/course.py teaching-plots

check:
	$(PYTHON) scripts/course.py check

# --- Production deployment (Linux server, systemd) ---

deploy: setup
	$(VENV_PYTHON) scripts/deploy_service.py install-service --host $(SANDBOX_HOST) --port $(SANDBOX_PORT)
	$(VENV_PYTHON) scripts/deploy_service.py install-timer --on-calendar "$(ON_CALENDAR)"

deploy-service:
	$(VENV_PYTHON) scripts/deploy_service.py install-service --host $(SANDBOX_HOST) --port $(SANDBOX_PORT)

deploy-timer:
	$(VENV_PYTHON) scripts/deploy_service.py install-timer --on-calendar "$(ON_CALENDAR)"

service-status:
	systemctl status $(SERVICE_NAME)

service-logs:
	journalctl -u $(SERVICE_NAME) -n 200 -f

snapshot-logs:
	journalctl -u $(SNAPSHOT_SERVICE_NAME) -n 200

service-restart:
	sudo systemctl restart $(SERVICE_NAME)

snapshot-refresh:
	$(VENV_PYTHON) dashboard_snapshot.py --mode auto

snapshot-status:
	systemctl list-timers $(SNAPSHOT_TIMER_NAME) --all
