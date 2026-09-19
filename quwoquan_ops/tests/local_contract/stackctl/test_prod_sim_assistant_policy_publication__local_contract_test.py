# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""prod-sim Assistant policy publication chain and launch hook contracts."""
from __future__ import annotations

import pytest

from quwoquan_ops.cli.lib.prod_sim_assistant_policy_publication import (
    ProdSimAssistantPolicyPublicationError,
    linux_goarch,
    publication_chain,
)


def test_linux_goarch_maps_container_inspect_values() -> None:
    assert linux_goarch("arm64") == "arm64"
    assert linux_goarch("aarch64") == "arm64"
    assert linux_goarch("amd64") == "amd64"
    assert linux_goarch("x86_64") == "amd64"
    with pytest.raises(ProdSimAssistantPolicyPublicationError):
        linux_goarch("ppc64le")


def test_publication_chain_walks_expected_revision_oldest_first() -> None:
    artifacts = {
        "assistant/assistant-default/rollouts/revision-4.json": {
            "expectedRevision": 3,
            "assignments": [{"releaseDigest": "d" * 64}],
        },
        "assistant/assistant-default/rollouts/revision-3.json": {
            "expectedRevision": 2,
            "assignments": [{"releaseDigest": "c" * 64}],
        },
        "assistant/assistant-default/rollouts/revision-2.json": {
            "expectedRevision": 1,
            "assignments": [{"releaseDigest": "b" * 64}],
        },
        "assistant/assistant-default/rollouts/revision-1.json": {
            "expectedRevision": 0,
            "assignments": [{"releaseDigest": "a" * 64}],
        },
    }
    chain = publication_chain(
        current_rollout_ref="assistant/assistant-default/rollouts/revision-4.json",
        load_rollout=artifacts.__getitem__,
    )
    assert chain == [
        (
            f"assistant/assistant-default/releases/{'a' * 64}.json",
            "assistant/assistant-default/rollouts/revision-1.json",
        ),
        (
            f"assistant/assistant-default/releases/{'b' * 64}.json",
            "assistant/assistant-default/rollouts/revision-2.json",
        ),
        (
            f"assistant/assistant-default/releases/{'c' * 64}.json",
            "assistant/assistant-default/rollouts/revision-3.json",
        ),
        (
            f"assistant/assistant-default/releases/{'d' * 64}.json",
            "assistant/assistant-default/rollouts/revision-4.json",
        ),
    ]


def test_publication_chain_rejects_cyclic_rollout_refs() -> None:
    artifacts = {
        "assistant/assistant-default/rollouts/revision-2.json": {
            "expectedRevision": 2,
            "assignments": [{"releaseDigest": "a" * 64}],
        }
    }
    with pytest.raises(ProdSimAssistantPolicyPublicationError):
        publication_chain(
            current_rollout_ref="assistant/assistant-default/rollouts/revision-2.json",
            load_rollout=artifacts.__getitem__,
        )
