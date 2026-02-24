"""
ModelRegistry: resolve production model path per scenario (local or OSS).
Placeholder: returns None so content_feed uses rule-based scorer; later load from env/OSS.
"""
from __future__ import annotations

import os
from typing import Optional


def get_model_path(scenario: str) -> Optional[str]:
    """
    Return path to production model for scenario, or None to use rule-based fallback.
    Env: REC_MODEL_CONTENT_FEED_PATH, REC_MODEL_CIRCLE_DISCOVERY_PATH, etc.
    """
    key = f"REC_MODEL_{scenario.upper()}_PATH"
    return os.environ.get(key)
