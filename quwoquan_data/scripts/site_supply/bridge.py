"""Dynamic calls back to the site_supply.handler facade for legacy tests."""
from __future__ import annotations

import sys
from typing import Any


def call(name: str, fallback: Any, *args: Any, **kwargs: Any) -> Any:
    facade = sys.modules.get("site_supply.handler")
    fn = getattr(facade, name, None) if facade is not None else None
    if callable(fn) and fn is not fallback:
        return fn(*args, **kwargs)
    return fallback(*args, **kwargs)
