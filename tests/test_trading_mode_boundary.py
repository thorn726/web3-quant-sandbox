import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROBE = (
    "import sys; sys.path.insert(0, {src!r}); "
    "from config.trading_mode import execution_enabled, get_trading_mode; "
    "print(get_trading_mode(), int(execution_enabled()))"
).format(src=str(ROOT / "src"))


def _probe(env_extra: dict[str, str]) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-I", "-c", PROBE],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
        env={**os.environ, **env_extra},
    )
    return result.stdout.split()


def test_default_mode_is_research_only_without_execution():
    assert _probe({}) == ["research_only", "0"]


def test_explicit_opt_in_enables_execution():
    assert _probe({"TRADING_MODE": "live"}) == ["live", "1"]


def test_unknown_mode_is_rejected():
    proc = subprocess.run(
        [sys.executable, "-I", "-c", PROBE],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={**os.environ, "TRADING_MODE": "yolo"},
    )
    assert proc.returncode != 0
    assert "unsupported TRADING_MODE" in proc.stderr
