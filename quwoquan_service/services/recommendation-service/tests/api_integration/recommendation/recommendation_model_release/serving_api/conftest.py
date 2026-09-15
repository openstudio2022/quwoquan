from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI

from support.service_token import configure_test_auth_environment

configure_test_auth_environment()

from main import app


class _HealthyRuntimeDependency:
    def healthy(self) -> bool:
        return True


_RUNTIME_STATE_KEYS = (
    "runtime_workload",
    "ranked_window_facade",
    "model_release_command_facade",
    "model_release_outbox_relay",
    "model_release_runtime_consumer",
    "candidate_post_lifecycle_consumer",
    "feature_post_lifecycle_consumer",
    "candidate_gathering_lifecycle_consumer",
    "candidate_premium_pool_consumer",
    "experiment_policy_consumer",
    "user_account_closed_consumer",
    "content_behavior_consumer",
    "feed_page_delivered_consumer",
)
_MISSING = object()


@pytest.fixture
def app_factory() -> Iterator[Callable[..., FastAPI]]:
    previous: dict[str, Any] = {
        key: getattr(app.state, key, _MISSING) for key in _RUNTIME_STATE_KEYS
    }

    def build(*, workload: str = "full", scoring_ready: bool = True) -> FastAPI:
        healthy = _HealthyRuntimeDependency()
        app.state.runtime_workload = workload
        app.state.ranked_window_facade = object() if scoring_ready else None
        app.state.model_release_command_facade = object()
        app.state.model_release_outbox_relay = healthy
        app.state.model_release_runtime_consumer = healthy
        app.state.candidate_post_lifecycle_consumer = healthy
        app.state.feature_post_lifecycle_consumer = healthy
        app.state.candidate_gathering_lifecycle_consumer = healthy
        app.state.candidate_premium_pool_consumer = healthy
        app.state.experiment_policy_consumer = healthy if scoring_ready else None
        app.state.user_account_closed_consumer = healthy
        app.state.content_behavior_consumer = healthy
        app.state.feed_page_delivered_consumer = healthy
        return app

    yield build

    for key, value in previous.items():
        if value is _MISSING:
            try:
                delattr(app.state, key)
            except AttributeError:
                pass
        else:
            setattr(app.state, key, value)
