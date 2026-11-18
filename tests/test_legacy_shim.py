"""The MeliAPIClient shim warns and re-exports meli_sdk."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SHIM_SRC = ROOT / "legacy-shim" / "src"


def _run(code: str, *python_args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(SRC), str(SHIM_SRC)])
    return subprocess.run(
        [sys.executable, *python_args, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_shim_emits_future_warning():
    """Importing the shim warns that the package was renamed to meli-sdk."""
    result = _run("import MeliAPIClient", "-W", "error::FutureWarning")

    assert result.returncode != 0
    assert "meli-sdk" in result.stderr


def test_shim_reexports_public_api():
    """Zincro's exact import returns the same objects as meli_sdk."""
    code = (
        "import MeliAPIClient, meli_sdk;"
        "from MeliAPIClient import MeliClient, CallbackTokenStorage;"
        "assert MeliClient is meli_sdk.MeliClient;"
        "assert CallbackTokenStorage is meli_sdk.CallbackTokenStorage;"
        "assert set(MeliAPIClient.__all__) == set(meli_sdk.__all__)"
    )

    result = _run(code)

    assert result.returncode == 0, result.stderr


def test_shim_aliases_submodules():
    """Old submodule imports resolve to the same module objects as meli_sdk."""
    code = (
        "import MeliAPIClient.client as old_client, meli_sdk.client as new_client;"
        "assert old_client is new_client;"
        "from MeliAPIClient.storage import FileTokenStorage as OldStorage;"
        "from meli_sdk.storage import FileTokenStorage as NewStorage;"
        "assert OldStorage is NewStorage"
    )

    result = _run(code)

    assert result.returncode == 0, result.stderr


def test_shim_exposes_version():
    """The shim reports the same version as meli_sdk."""
    code = (
        "import MeliAPIClient, meli_sdk;"
        "assert MeliAPIClient.__version__ == meli_sdk.__version__"
    )

    result = _run(code)

    assert result.returncode == 0, result.stderr
