"""local gamma content-service 配置合约测试共享 compose 渲染 helpers
（自 test_local_gamma_content_service_config__local_contract_test 拆分）。
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from quwoquan_ops.cli.lib.compose_layout import gamma_compose_files
from quwoquan_ops.cli.alpha.content_release_runtime import _compose_build_environment
from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology


ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "quwoquan_ops" / "environments" / "compose" / "docker-compose.gamma-local.yaml"
CADDYFILE = ROOT / "quwoquan_ops" / "environments" / "gamma" / "local" / "Caddyfile"
CONTENT_SERVICE_ROOT = (
    ROOT / "quwoquan_service" / "services" / "content-service"
)


def content_environment_compose(environment: str) -> Path:
    return (
        CONTENT_SERVICE_ROOT
        / "environments"
        / environment
        / "deploy"
        / "compose.yaml"
    )


CONTENT_GAMMA_COMPOSE_FILE = content_environment_compose("gamma")
OBJECT_STORAGE_LIFECYCLE_FILE = (
    ROOT
    / "quwoquan_ops"
    / "environments"
    / "compose"
    / "object-storage-lifecycle.json"
)
START_SCRIPT = ROOT / "quwoquan_app" / "scripts" / "gamma" / "start_local_gamma_mirror.sh"
PRODUCT_OPS_LOCAL_ES_COMPOSE_FILE = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "product-ops-service"
    / "deploy"
    / "local-elasticsearch.compose.yaml"
)
RELEASE_CONSUMER_SCRIPT = ROOT / "quwoquan_app" / "scripts" / "gamma" / "run_local_gamma_release_consumer_api.py"


def service_compose(service: str) -> str:
    return (
        ROOT
        / "quwoquan_service"
        / "services"
        / service
        / "deploy"
        / "compose.yaml"
    ).read_text(encoding="utf-8")


