"""Install/uninstall systemd units for the web3 quant sandbox (Linux only).

Usage:
    python scripts/deploy_service.py install-service
    python scripts/deploy_service.py install-timer [--on-calendar daily]
    python scripts/deploy_service.py uninstall

Unit files are rendered from deploy/systemd/*.in with the repository path
substituted in, then copied to /etc/systemd/system (requires sudo).
"""

from __future__ import annotations

import argparse
import os
import pwd
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "deploy" / "systemd"
UNIT_DIR = Path("/etc/systemd/system")

SERVICE_UNIT = "web3-sandbox.service"
SNAPSHOT_SERVICE_UNIT = "web3-sandbox-snapshot.service"
SNAPSHOT_TIMER_UNIT = "web3-sandbox-snapshot.timer"


def _render(template: str, *, host: str, port: str, on_calendar: str) -> str:
    try:
        user = pwd.getpwuid(os.getuid()).pw_name
    except KeyError:  # pragma: no cover
        user = os.environ.get("USER", "root")
    return (
        template.replace("{{REPO_DIR}}", str(ROOT))
        .replace("{{HOST}}", host)
        .replace("{{PORT}}", port)
        .replace("{{ON_CALENDAR}}", on_calendar)
        .replace("{{USER}}", user)
    )


def _systemctl(*args: str) -> None:
    subprocess.run(["sudo", "systemctl", *args], check=True)


def _write_unit(name: str, content: str) -> None:
    target = UNIT_DIR / name
    tmp = Path("/tmp") / name
    tmp.write_text(content, encoding="utf-8")
    subprocess.run(["sudo", "cp", str(tmp), str(target)], check=True)
    tmp.unlink()


def install_service(host: str, port: str) -> None:
    if sys.platform == "darwin":
        raise SystemExit("systemd deployment targets Linux servers; run this on the server.")
    template = (TEMPLATE_DIR / f"{SERVICE_UNIT}.in").read_text(encoding="utf-8")
    _write_unit(SERVICE_UNIT, _render(template, host=host, port=port, on_calendar=""))
    _systemctl("daemon-reload")
    _systemctl("enable", "--now", SERVICE_UNIT)
    print(f"installed and started {SERVICE_UNIT}")


def install_timer(on_calendar: str) -> None:
    if sys.platform == "darwin":
        raise SystemExit("systemd deployment targets Linux servers; run this on the server.")
    service_tpl = (TEMPLATE_DIR / f"{SNAPSHOT_SERVICE_UNIT}.in").read_text(encoding="utf-8")
    timer_tpl = (TEMPLATE_DIR / f"{SNAPSHOT_TIMER_UNIT}.in").read_text(encoding="utf-8")
    _write_unit(SNAPSHOT_SERVICE_UNIT, _render(service_tpl, host="", port="", on_calendar=on_calendar))
    _write_unit(SNAPSHOT_TIMER_UNIT, _render(timer_tpl, host="", port="", on_calendar=on_calendar))
    _systemctl("daemon-reload")
    _systemctl("enable", "--now", SNAPSHOT_TIMER_UNIT)
    print(f"installed and started {SNAPSHOT_TIMER_UNIT}")


def uninstall() -> None:
    if sys.platform == "darwin":
        raise SystemExit("systemd deployment targets Linux servers; run this on the server.")
    for unit in (SNAPSHOT_TIMER_UNIT, SNAPSHOT_SERVICE_UNIT, SERVICE_UNIT):
        subprocess.run(
            ["sudo", "systemctl", "disable", "--now", unit],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        path = UNIT_DIR / unit
        if path.exists():
            subprocess.run(["sudo", "rm", str(path)], check=True)
    _systemctl("daemon-reload")
    _systemctl("reset-failed")
    print("units removed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["install-service", "install-timer", "uninstall"])
    parser.add_argument("--host", default=os.environ.get("SANDBOX_HOST", "0.0.0.0"))
    parser.add_argument("--port", default=os.environ.get("SANDBOX_PORT", "8765"))
    parser.add_argument(
        "--on-calendar",
        default=os.environ.get("SNAPSHOT_REFRESH_CALENDAR", "*-*-* 06:30:00"),
        help="systemd OnCalendar expression (default: daily at 06:30).",
    )
    args = parser.parse_args()
    if args.command == "install-service":
        install_service(args.host, args.port)
    elif args.command == "install-timer":
        install_timer(args.on_calendar)
    else:
        uninstall()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
