"""Quwoquan Ops Python package bootstrap.

Operational commands must never write interpreter caches into the source tree;
all disposable runtime state belongs under ``.qwq_output``.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True
