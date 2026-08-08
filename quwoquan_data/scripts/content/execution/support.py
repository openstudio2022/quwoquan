"""Shared external dependencies for decomposed execution services."""
from __future__ import annotations
import argparse
import copy
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from core.control_types import ExecutionStage, ExecutionStateStatus, StageKind, StageStatus
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueError,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
    data_issues,
    issue_messages,
)
from core.cursor_credentials import cursor_api_key_file, is_cursor_auth_error, resolve_cursor_api_key
from core.article_commercial_policy import article_commercial_closure_enabled
from core.execution_branch import execution_branch_issues, execution_branch_payload
from governance.coverage.entity_extract import require_domain_etype
from core.image_asset_strategy import (
    REFERENCE_ONLY_NO_IMAGE_RELEASE,
    image_count_is_hard_quota,
    image_asset_strategy_scale_issues,
    image_asset_strategy,
    image_strategy_allows_ai_generated,
    image_strategy_requires_publishable_images,
    minimum_publishable_images_per_target,
    validate_image_asset_strategy,
)
from core.io import read_json, write_json
from core.python_environment import (
    DEFAULT_SEMANTIC_AGENT_STARTUP_TIMEOUT_SECONDS,
    resolve_semantic_agent_startup_timeout_seconds,
)
from core.source_plan_contract import source_plan_rule_signature
from core.paths import release_root
from content.execution.workspace import (
    execution_command_root,
    execution_content_plan_packet_path,
    execution_root,
    execution_baseline_freeze_packet_path,
    ensure_execution_command_layout,
    relative_execution_ref,
)
from content.execution import store
from content.execution.recovery.download_hints import (
    _download_diagnostic_image_repair_hints,
    _download_issue_repair_hints,
    _download_repair_lanes,
    _planned_pixel_issue,
    _research_image_repair_hints,
)
from content.execution.context import (
    AUTO,
    CHECKPOINT,
    DEFAULT_SEMANTIC_AGENT_MODEL,
    DEFAULT_MANAGED_AGENT_PROVIDER,
    DOWNLOAD_FETCH_ONLY_RETRY_LIMIT,
    MANAGED_AGENT_FUTURE_GRACE_SECONDS,
    MANAGED_AGENT_PROVIDERS,
    _MANAGED_AGENT_SUBPROCESS_LOCK,
    _MANAGED_AGENT_SUBPROCESS_PIDS,
    MANAGED_AGENT_TIMEOUT_SECONDS,
    MANAGED_LANE_LIMITS,
    MANAGED_LOCAL_CURSOR_MAX_WORKERS,
    MANAGED_SCHEDULER_STALE_SECONDS,
    MAX_MANAGED_INFRA_RETRIES,
    MAX_REACT_REWINDS,
    ExecutionContext,
    StageResult,
    stage_issues,
    EXECUTION_STATE_CONTRACT,
    _CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS,
    _CURSOR_BRIDGE_READY_DELAY_SECONDS,
    _managed_local_cursor_worker_cap as _context_managed_local_cursor_worker_cap,
    _normalize_managed_agent_provider,
    _resolve_managed_model,
    _state_path,
    _write_execution_packet,
    load_execution_state,
    execution_state_status,
    save_execution_state,
)
from content.execution.contracts import ExecutionState, ExecutionStateTransition
from content.execution.planning.active_spec import (
    active_spec as _active_spec,
    active_target as _active_target,
    entity_homepages_per_target as _entity_homepages_per_target,
    is_homepage_only_execution as _is_homepage_only_execution,
)
from content.execution.target_integrity import (
    frozen_target_names,
    prune_non_target_homepage_artifacts as _prune_inactive_entity_homepage_artifacts,
)

_IMAGE_SOURCE_TEXT_NOISE_PATTERNS = (
    r"https?://\S+",
    r"\b(?:pinterest|etsy|youtube|wallpapersafari|hdpicorner(?:\.com)?)\b",
    r"^pin\s+by\s+.+?\s+on\s+.+$",
    r"\bthis\s+pin\s+was\s+discovered\s+by\s+.+?(?:[.!]|$)",
    r"\bthis\s+item\s+is\s+unavailable\b",
    r"\bis\s+for\s+sale\b",
    r"\bpins?\s+by\s+you\b",
    r"\bdiscover\s+your\s+own\s+pins?\b",
    r"\binstant\s+download\b",
    r"\bhello,\s*welcome\s+to\s+my\s+youtube\s+channel.*$",
    r"\bthis\s+channel\s+contains.*$",
    r"\bentdecke\b.*\bdeine\s+eigenen\s+pins?\b.*\bpinterest\b",
    r"\bkendi\s+pinlerinizi\b",
    r"\bpinlerinizi\b",
    r"\bkeşfedin\b",
    r"\bkaydedin\b",
    r"\bscopri\b.*\bsalva\b.*\btuoi\s+pin\b.*\bpinterest\b",
    r"\bscopri\b",
    r"\bsalva\b",
)

_IMAGE_SOURCE_TEXT_NOISE_TOKENS = {
    "a",
    "an",
    "and",
    "apr",
    "aug",
    "by",
    "channel",
    "com",
    "dec",
    "de",
    "discover",
    "download",
    "e",
    "feb",
    "for",
    "fr",
    "fondos",
    "hd",
    "hello",
    "in",
    "is",
    "item",
    "it",
    "its",
    "jan",
    "jul",
    "jun",
    "kas",
    "mar",
    "may",
    "my",
    "nov",
    "oct",
    "of",
    "on",
    "own",
    "pinlerinizi",
    "pin",
    "pins",
    "sale",
    "sammle",
    "save",
    "saved",
    "scopri",
    "sep",
    "sept",
    "su",
    "the",
    "this",
    "to",
    "tuoi",
    "unavailable",
    "wallpaper",
    "welcome",
    "ve",
    "you",
    "your",
}

_MANAGED_LOCAL_DATA_CLI_MARKERS = (
    "task execute",
    "data research-plan",
    "task scaled-e2e",
)

_MANAGED_LOCAL_DESTRUCTIVE_MARKERS = (
    "pkill -KILL -f",
    "pkill -TERM -f",
    "killall",
)
