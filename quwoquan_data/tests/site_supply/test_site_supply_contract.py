"""Site-dimensional content supply packet/gate contract tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
_TMP = Path(tempfile.mkdtemp(prefix="site_supply_"))
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from site_supply import handler as ss  # noqa: E402


ARTICLE_TEXT = (
    "这是一篇用于测试的网站候选正文，包含目的地路线、开放时间、交通方式和体验判断。"
    "内容长度需要超过抽取门槛，确保候选可以进入评分与后续 content_plan handoff。"
)


def _write_frontier(batch: str = "b1") -> dict:
    packet = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        daily_target=100_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert packet["gate"]["passed"], packet["gate"]
    ss.write_site_frontier_packet(packet)
    return packet


def _write_candidate(batch: str = "b1") -> dict:
    _write_frontier(batch)
    packet = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        url="https://touch.travel.qunar.com/travelbook/note/123456",
        lane="article",
        title="九寨沟两日玩法",
        text=ARTICLE_TEXT,
        published_at="2026-06-01",
        entity_mentions=["地点/景区/九寨沟"],
        tag_mentions=["Topic/旅行/玩法/自然风光"],
    )
    assert packet["gate"]["passed"], packet["gate"]
    ss.write_site_candidate_packet(packet)
    return packet


def test_qunar_frontier_passes_and_ctrip_is_blocked():
    qunar = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="frontier_ok",
        daily_target=100_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert qunar["gate"]["passed"], qunar["gate"]
    assert qunar["profile"]["crawlAllowed"] is True
    assert qunar["queuePolicy"]["backend"] == "reliabletask"

    ctrip = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="ctrip_travelogue",
        batch_id="frontier_block",
        daily_target=100_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert not ctrip["gate"]["passed"]
    assert ctrip["profile"]["maxDepth"] == 0
    text = "\n".join(ctrip["gate"]["blockers"])
    warning_text = "\n".join(ctrip["gate"]["warnings"])
    assert "fetchable=false" in text
    assert "crawlAllowed" in text
    assert "maxPagesPerDay=0" in warning_text

    mafengwo = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="mafengwo_travelogue",
        batch_id="frontier_block_mafengwo",
        daily_target=100_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert not mafengwo["gate"]["passed"]
    assert mafengwo["profile"]["rawProfilePresent"] is True
    assert mafengwo["profile"]["maxDepth"] == 0
    mafengwo_text = "\n".join(mafengwo["gate"]["blockers"])
    mafengwo_warning_text = "\n".join(mafengwo["gate"]["warnings"])
    assert "fetchable=false" in mafengwo_text
    assert "crawlAllowed" in mafengwo_text
    assert "maxPagesPerDay=0" in mafengwo_warning_text


def test_ctrip_mafengwo_controlled_trial_frontier_passes_without_batch_crawl():
    for site_id in ("ctrip_travelogue", "mafengwo_travelogue"):
        packet = ss.build_site_frontier_packet(
            vertical="travel",
            site_id=site_id,
            batch_id=f"{site_id}_controlled",
            daily_target=10_000,
            queue_backend="reliabletask",
            end_date="2026-06-19",
            admission_mode="controlled_trial",
        )
        assert packet["gate"]["passed"], packet["gate"]
        assert packet["admissionMode"] == "controlled_trial"
        assert packet["profile"]["fetchable"] is False
        assert packet["profile"]["crawlAllowed"] is False
        assert packet["profile"]["controlledTrial"]["validationOnly"] is True
        warning_text = "\n".join(packet["gate"]["warnings"])
        assert "does not grant raw batch crawl" in warning_text


def test_trial_command_materializes_multi_lane_controlled_batch_for_ctrip():
    cli = SCRIPTS_ROOT / "cli.py"
    trial = subprocess.run(
        [
            sys.executable,
            str(cli),
            "site-supply",
            "trial",
            "--site-id",
            "ctrip_travelogue",
            "--batch",
            "ctrip_multi_lane",
            "--target-count",
            "8",
            "--article-count",
            "5",
            "--image-count",
            "2",
            "--video-count",
            "1",
            "--daily-target",
            "1000",
            "--objects-per-hour",
            "120",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert trial.returncode == 0, trial.stderr
    payload = json.loads(trial.stdout)
    assert payload["frontier"]["admissionMode"] == "controlled_trial"
    assert payload["siteFunnel"]["candidateCount"] == 8
    assert payload["siteFunnel"]["laneCounts"] == {"article": 5, "image": 2, "video": 1}
    assert payload["siteFunnel"]["contentPlanHandoffLaneCounts"] == {"article": 5, "image": 2, "video": 1}


def test_candidate_score_map_rollup_handoff_isolated_from_entity_runtime():
    candidate = _write_candidate("pipeline_ok")
    score = ss.build_site_score_packet(candidate)
    assert score["productionEligible"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["contentPlanHandoff"]["eligible"], mapped
    assert mapped["semanticMentions"]["state"] == "mention_only"
    assert mapped["contentPlanHandoff"]["oneSourceOneWork"] is True
    ss.write_site_map_packet(mapped)

    rollup = ss.build_site_rollup_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="pipeline_ok",
        objects_per_hour=5000,
        first_pass_rate=0.82,
        token_ledger_count=1,
        release_verified=True,
        import_verified=True,
        search_visible=True,
        recommendation_feedback_ready=True,
    )
    assert rollup["passed"], rollup
    assert rollup["siteFunnel"]["contentPlanHandoffCount"] == 1
    path = ss.write_site_rollup_report(rollup)
    assert "/site_supply/travel/qunar_guide/pipeline_ok/" in str(path)
    assert "/runtime/tasks/" not in str(path)
    for name in ("stage_result.json", "gate_report.json", "repair_report.json"):
        assert (path.parents[1] / "candidates" / candidate["candidateRef"] / name).is_file()
        assert (path.parents[1] / "scores" / candidate["candidateRef"] / name).is_file()
        assert (path.parents[1] / "map" / candidate["candidateRef"] / name).is_file()


def test_rollup_blocks_missing_score_before_downstream_handoff():
    candidate = _write_candidate("missing_score")
    rollup = ss.build_site_rollup_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="missing_score",
        objects_per_hour=500,
        first_pass_rate=0.82,
        token_ledger_count=1,
    )
    text = "\n".join(rollup["blockers"])
    assert not rollup["passed"]
    assert f"{candidate['candidateRef']}: missing site_score_packet" in text
    assert rollup["siteFunnel"]["stageFailures"]["missing_score"] == 1


def test_rollup_blocks_missing_map_for_production_eligible_score():
    candidate = _write_candidate("missing_map")
    score = ss.build_site_score_packet(candidate)
    assert score["productionEligible"], score
    ss.write_site_score_packet(score)
    rollup = ss.build_site_rollup_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="missing_map",
        objects_per_hour=500,
        first_pass_rate=0.82,
        token_ledger_count=1,
    )
    text = "\n".join(rollup["blockers"])
    assert not rollup["passed"]
    assert f"{candidate['candidateRef']}: missing site_map_packet" in text
    assert rollup["siteFunnel"]["stageFailures"]["missing_map"] == 1


def test_candidate_outside_frontier_domain_is_blocked():
    _write_frontier("bad_domain")
    packet = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="bad_domain",
        url="https://example.com/travelbook/note/123456",
        lane="article",
        title="越界候选",
        text=ARTICLE_TEXT,
        published_at="2026-06-01",
    )
    assert not packet["gate"]["passed"]
    assert "outside site frontier" in "\n".join(packet["gate"]["blockers"])
    score = ss.build_site_score_packet(packet)
    assert not score["productionEligible"]
    assert "candidate gate did not pass" in "\n".join(score["gate"]["blockers"])


def test_trial_command_materializes_hundred_level_structural_batch():
    cli = SCRIPTS_ROOT / "cli.py"
    trial = subprocess.run(
        [
            sys.executable,
            str(cli),
            "site-supply",
            "trial",
            "--site-id",
            "qunar_guide",
            "--batch",
            "trial_100",
            "--target-count",
            "100",
            "--daily-target",
            "1000",
            "--objects-per-hour",
            "120",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert trial.returncode == 0, trial.stderr
    payload = json.loads(trial.stdout)
    assert payload["siteFunnel"]["candidateCount"] == 100
    assert payload["siteFunnel"]["contentPlanHandoffCount"] == 100
    assert payload["siteFunnel"]["stageFailures"]["missing_score"] == 0


def test_cli_site_supply_roundtrip():
    cli = SCRIPTS_ROOT / "cli.py"
    plan = subprocess.run(
        [
            sys.executable,
            str(cli),
            "site-supply",
            "plan",
            "--site-id",
            "qunar_guide",
            "--batch",
            "cli_roundtrip",
            "--daily-target",
            "100000",
            "--end-date",
            "2026-06-19",
            "--write",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert plan.returncode == 0, plan.stderr
    payload = json.loads(plan.stdout)
    assert payload["schemaVersion"] == "quwoquan.site_supply.site_frontier_packet/1"

    candidate = subprocess.run(
        [
            sys.executable,
            str(cli),
            "site-supply",
            "candidate",
            "--site-id",
            "qunar_guide",
            "--batch",
            "cli_roundtrip",
            "--url",
            "https://touch.travel.qunar.com/travelbook/note/654321",
            "--lane",
            "article",
            "--title",
            "CLI 候选",
            "--text",
            ARTICLE_TEXT,
            "--published-at",
            "2026-06-01",
            "--write",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert candidate.returncode == 0, candidate.stderr


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")


if __name__ == "__main__":
    _run_all()
