"""Template library CLI contract tests."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import json
import subprocess
import sys
from pathlib import Path


CLI_PATH = SCRIPTS_ROOT / "cli.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_template_lint_passes():
    result = _run("template", "lint")
    assert result.returncode == 0, result.stderr
    assert "PASSED" in result.stdout


def test_template_creator_lint_passes():
    result = _run("template", "creator-lint")
    assert result.returncode == 0, result.stderr
    assert "PASSED" in result.stdout


def test_template_rec_contract_passes():
    result = _run("template", "rec-contract")
    assert result.returncode == 0, result.stderr
    assert "PASSED" in result.stdout


def test_template_region_season_lint_passes():
    result = _run("template", "region-season-lint")
    assert result.returncode == 0, result.stderr
    assert "PASSED" in result.stdout


def test_plan_injects_region_season_conditions():
    result = _run("plan", "--instruction", "为川西做冬季自驾线路攻略")
    assert result.returncode == 0, result.stderr
    brief = json.loads(result.stdout)
    assert brief["templateId"] == "线路_自驾路书"
    ctx = brief["conditionContext"]
    assert ctx["region"]["name"] == "高原"
    assert ctx["season"]["name"] == "冬"
    assert "海拔与高反风险" in brief["mustIncludeFacts"]
    assert brief["recommendation"]["conditionContext"] == {"region": "高原", "season": "冬"}


def test_plan_food_columnist_resolves_for_foodie():
    result = _run("plan", "--subject", "topic", "--kind", "主题", "--intent", "深度报道", "--audience", "foodieReader")
    assert result.returncode == 0, result.stderr
    brief = json.loads(result.stdout)
    assert brief["templateId"] == "主题_风物美食"
    assert brief["creator"]["creatorArchetype"] == "food_columnist"


def test_plan_citywalk_resolves_for_photo_traveler():
    result = _run("plan", "--subject", "topic", "--kind", "主题", "--intent", "体验", "--audience", "photoTraveler")
    assert result.returncode == 0, result.stderr
    brief = json.loads(result.stdout)
    assert brief["templateId"] == "主题_城市漫步"


def test_plan_career_mentor_resolves_for_job_seeker():
    result = _run(
        "plan", "--subject", "entity", "--kind", "学校", "--vertical", "campus",
        "--intent", "校招就业", "--audience", "jobSeeker",
    )
    assert result.returncode == 0, result.stderr
    brief = json.loads(result.stdout)
    assert brief["templateId"] == "学校_校招就业"
    assert brief["creator"]["creatorArchetype"] == "career_mentor"


def test_routing_specific_audience_not_shadowed():
    result = _run("plan", "--subject", "topic", "--kind", "线路", "--intent", "攻略", "--audience", "budgetStudent")
    assert result.returncode == 0, result.stderr
    brief = json.loads(result.stdout)
    assert brief["templateId"] == "线路_省钱攻略"


def test_plan_instruction_resolves_self_drive_creator():
    result = _run("plan", "--instruction", "为川西做自驾线路攻略，面向休闲游客")
    assert result.returncode == 0, result.stderr
    brief = json.loads(result.stdout)
    assert brief["templateId"] == "线路_自驾路书"
    assert brief["creator"]["creatorArchetype"] == "self_drive_expert"
    assert brief["recommendation"]["authorId"] == "builtin_travel_self_drive_guide"
    assert "Topic/旅行/出行方式/自驾" in brief["tagRefs"]


def test_plan_campus_new_student_resolves_mentor():
    result = _run(
        "plan",
        "--subject",
        "entity",
        "--kind",
        "学校",
        "--vertical",
        "campus",
        "--intent",
        "新生攻略",
        "--audience",
        "freshmanStudent",
    )
    assert result.returncode == 0, result.stderr
    brief = json.loads(result.stdout)
    assert brief["templateId"] == "学校_新生攻略"
    assert brief["creator"]["creatorArchetype"] == "student_mentor"


if __name__ == "__main__":
    test_template_lint_passes()
    test_template_creator_lint_passes()
    test_template_rec_contract_passes()
    test_template_region_season_lint_passes()
    test_plan_instruction_resolves_self_drive_creator()
    test_plan_campus_new_student_resolves_mentor()
    test_plan_injects_region_season_conditions()
    test_plan_food_columnist_resolves_for_foodie()
    test_plan_citywalk_resolves_for_photo_traveler()
    test_plan_career_mentor_resolves_for_job_seeker()
    test_routing_specific_audience_not_shadowed()
    print("template cli tests passed")
