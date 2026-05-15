"""Deduplication tracking via task_manifest.json."""
from __future__ import annotations

from pathlib import Path

from .paths import task_manifest
from .io import read_json, write_json


def load_manifest(task_id: str) -> dict:
    path = task_manifest(task_id)
    if path.exists():
        return read_json(path)
    return {"taskId": task_id, "completedEntities": [], "completedTopics": [], "downloadedSources": []}


def save_manifest(task_id: str, manifest: dict) -> None:
    write_json(task_manifest(task_id), manifest)


def is_entity_done(task_id: str, entity_id: str) -> bool:
    m = load_manifest(task_id)
    return entity_id in m.get("completedEntities", [])


def mark_entity_done(task_id: str, entity_id: str) -> None:
    m = load_manifest(task_id)
    if entity_id not in m["completedEntities"]:
        m["completedEntities"].append(entity_id)
    save_manifest(task_id, m)


def is_topic_done(task_id: str, topic_id: str) -> bool:
    m = load_manifest(task_id)
    return topic_id in m.get("completedTopics", [])


def mark_topic_done(task_id: str, topic_id: str) -> None:
    m = load_manifest(task_id)
    if topic_id not in m["completedTopics"]:
        m["completedTopics"].append(topic_id)
    save_manifest(task_id, m)


def is_source_downloaded(task_id: str, source_key: str) -> bool:
    m = load_manifest(task_id)
    return source_key in m.get("downloadedSources", [])


def mark_source_downloaded(task_id: str, source_key: str) -> None:
    m = load_manifest(task_id)
    if source_key not in m["downloadedSources"]:
        m["downloadedSources"].append(source_key)
    save_manifest(task_id, m)
