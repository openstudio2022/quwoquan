from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest


def _parser():
    import content.source.research.handler_cli as handler

    parser = argparse.ArgumentParser()
    handler.register_parser(parser.add_subparsers(dest="command", required=True))
    return parser


def _arguments(*, batch: Path, evidence_root: Path, output_root: Path) -> list[str]:
    return [
        "source-pool",
        "freeze-homepage-article-catalogs",
        "--source-ready-manifest",
        str(batch),
        "--evidence-root",
        str(evidence_root),
        "--minimum-homepage-candidate-count",
        "180",
        "--minimum-article-candidate-count",
        "180",
        "--output-root",
        str(output_root),
    ]


def test_freeze_catalog_cli_uses_only_immutable_batch_builder(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    import content.source.research.handler_cli as handler

    batch = tmp_path / "batch.json"
    batch.write_text("{}\n", encoding="utf-8")
    evidence_root = tmp_path / "evidence"
    output_root = tmp_path / "output"
    captured: dict[str, object] = {}

    def freeze(source_ready_manifest: Path, **kwargs):
        captured["sourceReadyManifest"] = source_ready_manifest
        captured.update(kwargs)
        return {
            "schema": "quwoquan_data.homepage_article_source_ready_batch_write_result",
            "sourceSetDigest": "sha256:" + "a" * 64,
            "homepage": {"candidateCount": 180},
            "article": {"candidateCount": 180},
        }

    monkeypatch.setattr(handler, "freeze_homepage_article_source_ready_batch", freeze)
    parsed = _parser().parse_args(
        _arguments(batch=batch, evidence_root=evidence_root, output_root=output_root)
    )

    parsed.handler(parsed)

    result = json.loads(capsys.readouterr().out)
    assert captured == {
        "sourceReadyManifest": batch,
        "evidence_root": evidence_root,
        "output_root": output_root.resolve(),
        "minimum_homepage_candidate_count": 180,
        "minimum_article_candidate_count": 180,
    }
    assert result["homepage"]["candidateCount"] == 180
    assert result["article"]["candidateCount"] == 180


def test_freeze_catalog_cli_preserves_typed_batch_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import content.source.research.handler_cli as handler
    from content.source.research.homepage_article_source_ready_batch import (
        HomepageArticleSourceReadyBatchError,
    )

    def freeze(*args, **kwargs):
        raise HomepageArticleSourceReadyBatchError(
            "DATA.SOURCE.POOL_SHORTFALL", ["required=180/180 actual=1/1"]
        )

    monkeypatch.setattr(handler, "freeze_homepage_article_source_ready_batch", freeze)
    parsed = _parser().parse_args(
        _arguments(
            batch=tmp_path / "batch.json",
            evidence_root=tmp_path / "evidence",
            output_root=tmp_path / "output",
        )
    )

    with pytest.raises(SystemExit) as captured:
        parsed.handler(parsed)

    assert "[source-pool freeze-homepage-article-catalogs] GATE_BLOCK" in str(
        captured.value
    )
    assert "DATA.SOURCE.POOL_SHORTFALL" in str(captured.value)


def test_freeze_catalog_cli_has_no_free_form_candidate_bypass(capsys) -> None:
    parser = _parser()
    with pytest.raises(SystemExit) as captured:
        parser.parse_args(
            ["source-pool", "freeze-homepage-article-catalogs", "--help"]
        )
    assert captured.value.code == 0
    help_text = capsys.readouterr().out
    assert "--source-ready-manifest" in help_text
    assert "--evidence-root" in help_text
    assert "--candidates" not in help_text

    for retired in ("freeze-homepage-catalog", "freeze-article-catalog"):
        with pytest.raises(SystemExit):
            parser.parse_args(["source-pool", retired, "--help"])
