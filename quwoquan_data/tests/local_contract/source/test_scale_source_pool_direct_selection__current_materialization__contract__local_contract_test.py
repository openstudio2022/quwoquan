# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-034
"Current direct source materialization stays detached from legacy families."
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from content.execution.source_pool.binding import bind_scale_source_pool
from content.source.research.scale_source_pool import build_scale_source_pool_plan
from support.scale_source_pool_catalog_fixture import IDENTITY, _article_candidate, _write_json
from support.scale_source_pool_projection_fixture import _project
from core.source_digest import (
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)


_FORBIDDEN = (
    "content.execution.agent",
    "content.execution.queue",
    "content.execution.controller",
    "content.execution.recovery",
    "content.execution.campaign",
)


def test_fresh_process_direct_article_materialization_writes_layout_without_legacy_imports(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    evidence_root = output_root / "data/local/direct-source-evidence"
    projection = _project(
        evidence_root,
        article_candidates=[_article_candidate(0)],
        per_member_roots=True,
    )
    article_row = next(
        dict(row) for row in projection["rows"] if row["carrier"] == "article"
    )
    article_row["objectRef"] = "posts/article/攻略/杭州-0/1"
    plan = build_scale_source_pool_plan(
        pool_id="direct-current-article",
        target_scale="WORKLOAD",
        created_at="2026-09-02T00:00:00Z",
        candidates=[article_row],
        workload_targets={"article": 1},
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )
    plan_path = output_root / "data/local/direct-source-pool/plan.json"
    _write_json(plan_path, plan)
    binding, evidence_ref, selection = bind_scale_source_pool(
        plan_path,
        evidence_root=evidence_root,
        output_root=output_root,
        target_scale="WORKLOAD",
        carrier="article",
        count=1,
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )
    execution_id = "20260902--travel-article-direct-current--china--pilot-001"
    task_root = output_root / "data/tasks" / execution_id
    target_set = {
        "executionId": execution_id,
        "selectionPolicy": "frozen",
        "sourceRef": binding["planRef"],
        "candidateBinding": {
            "ref": "inputs/candidate-bindings.json",
            "digest": "sha256:" + "1" * 64,
            "candidateCount": 1,
        },
        "entityCatalogDigest": IDENTITY["entityCatalogDigest"],
        "targetCount": 1,
        "targetRefs": ["posts/article/攻略/杭州-0/1"],
        "targets": [
            {
                "entityType": "地点/景区",
                "name": "杭州-0",
                "publishAngle": "攻略",
                "publishTitle": "杭州-0",
                "publishSeq": 1,
            }
        ],
    }
    _write_json(task_root / "0.plan/target_set.json", target_set)
    manifest = {
        "executionId": execution_id,
        "familyRef": {"ref": "content/travel/article/article", "sha256": "2" * 64},
        "sourceDigest": current_source_definition_snapshot().to_document(),
        "executionBundle": current_execution_bundle_identity().to_document(),
        "operationalFingerprint": "sha256:" + "4" * 64,
        "hostRuntime": "external_host_agent",
        "carrierDemand": {
            "ref": "inputs/carrier-demand.json",
            "digest": "sha256:" + "5" * 64,
            "workRequestRef": "inputs/work-request.json",
            "workRequestDigest": "sha256:" + "6" * 64,
        },
        "requestRef": "0.plan/request.json",
        "targetSetRef": "0.plan/target_set.json",
        "targetSetDigest": hashlib.sha256(
            json.dumps(
                target_set,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "retryOf": None,
    }
    _write_json(task_root / "execution_manifest.json", manifest)
    direct_selection = {
        "scaleSourcePool": binding,
        "sourcePoolEvidenceRootRef": evidence_ref,
        "sourcePoolSelection": selection,
    }
    selection_path = tmp_path / "direct-selection.json"
    _write_json(selection_path, direct_selection)
    probe = r'''
import json
import sys
from pathlib import Path

from content.source.research.scale_source_pool_runtime import (
    frozen_scale_source_pool_candidates,
    materialize_frozen_scale_source_pool_entity,
)

selection = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
rows = frozen_scale_source_pool_candidates(
    sys.argv[2], "article", direct_selection=selection
)
manifest = materialize_frozen_scale_source_pool_entity(
    sys.argv[2],
    "article",
    "杭州-0",
    "地点/景区",
    direct_selection=selection,
)
forbidden = tuple(json.loads(sys.argv[3]))
hits = sorted(
    name for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
)
print(json.dumps({
    "candidateIds": [row["candidateId"] for row in rows],
    "layoutExists": (
        Path(sys.argv[4]) / "sources" / manifest["sourceUnitId"] / "source.layout.json"
    ).is_file(),
    "forbiddenLoadedModules": hits,
}, ensure_ascii=False))
'''
    repo_root = Path(__file__).resolve().parents[4]
    environment = dict(os.environ)
    environment["QWQ_OUTPUT_ROOT"] = str(output_root)
    environment["QWQ_LIBRARY_ROOT"] = str(tmp_path / "content-library")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(repo_root / "quwoquan_data/scripts"),
            str(repo_root / "quwoquan_data/tests"),
            str(repo_root),
        )
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            probe,
            str(selection_path),
            execution_id,
            json.dumps(_FORBIDDEN),
            str(task_root),
        ],
        cwd=repo_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["candidateIds"] == ["article-hangzhou-0"]
    assert result["layoutExists"] is True
    assert result["forbiddenLoadedModules"] == []
