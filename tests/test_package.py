import os
import subprocess
import sys
from pathlib import Path

import meli_sdk

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


def run_in_subprocess(code: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    """Run Python code in a subprocess with ``src`` on the import path."""
    full_env = {**env, "PYTHONPATH": str(SRC_DIR)}
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=full_env,
        capture_output=True,
        text=True,
    )


def test_version_is_exposed():
    """The package exposes its distribution version."""
    assert meli_sdk.__version__ == "1.0.0a2"


def test_public_api_is_exported():
    """Every name listed in ``__all__`` is available on the package."""
    assert meli_sdk.__all__
    for name in meli_sdk.__all__:
        assert hasattr(meli_sdk, name), name


def test_import_does_not_load_dotenv(tmp_path):
    """Importing the package must not load the .env of the current directory."""
    (tmp_path / ".env").write_text("MELI_SDK_PROBE=1\n")
    env = {key: value for key, value in os.environ.items() if key != "MELI_SDK_PROBE"}

    result = run_in_subprocess(
        'import meli_sdk, os; print(os.getenv("MELI_SDK_PROBE"))', tmp_path, env
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "None"


def test_legacy_session_still_reads_dotenv(tmp_path):
    """The legacy Session still reads its credentials from .env."""
    (tmp_path / ".env").write_text("ML_CLIENT_ID=from-env\nML_CLIENT_SECRET=s\n")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"ML_CLIENT_ID", "ML_CLIENT_SECRET"}
    }

    code = """
import time

from meli_sdk import Session

token = {
    "access_token": "APP_USR-valid",
    "refresh_token": "TG-refresh-1",
    "expires_in": 21600,
    "created_at": time.time(),
    "expires_at": time.time() + 21600,
    "user_id": 12345,
}
print(Session(token=token).ml_keys["client_id"])
"""

    result = run_in_subprocess(code, tmp_path, env)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "from-env"
