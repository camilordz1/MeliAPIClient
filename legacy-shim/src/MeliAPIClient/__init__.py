"""Deprecated name of meli-python-sdk.

This package only exists so that ``pip install MeliAPIClient`` points users to the new
distribution. Install ``meli-python-sdk`` and import ``meli_sdk`` instead.
"""

import importlib
import sys
import warnings

from meli_sdk import *  # noqa: F401,F403
from meli_sdk import __all__, __version__  # noqa: F401

_SUBMODULES = (
    "actions",
    "bills",
    "client",
    "exceptions",
    "items",
    "metrics",
    "orders",
    "session",
    "shipments",
    "storage",
)

for _name in _SUBMODULES:
    _module = importlib.import_module(f"meli_sdk.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _module
    globals()[_name] = _module

warnings.warn(
    "MeliAPIClient was renamed to meli-python-sdk. "
    "Run 'pip install meli-python-sdk' and import 'meli_sdk' instead. "
    "This package will not receive further updates.",
    FutureWarning,
    stacklevel=2,
)
