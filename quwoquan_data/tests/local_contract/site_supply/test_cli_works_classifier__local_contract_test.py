from __future__ import annotations



from support.site_supply_fixtures import *  # noqa: F401,F403



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
        env=_cli_env(),
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
        env=_cli_env(),
    )
    assert candidate.returncode == 0, candidate.stderr

def test_site_score_works_classifier_passes_professional_article():
    """站点线：专业旅行攻略 → worksDecision=work（全站分类入库放行），works 门不阻断。"""
    score = ss.build_site_score_packet(
        _site_works_candidate(ref="works_pro", text=ARTICLE_TEXT, validation_only=False)
    )
    assert score["worksDecision"] == "work"
    assert "works classifier" not in "\n".join(score["gate"]["blockers"])

def test_site_score_works_classifier_blocks_casual_real_candidate():
    """站点线：真实抓取的碎片随记候选 → works 门阻断、不进全站分类入库。"""
    score = ss.build_site_score_packet(
        _site_works_candidate(ref="works_casual", text=_CASUAL_SITE_TEXT, validation_only=False)
    )
    assert score["worksDecision"] != "work"
    assert "works classifier" in "\n".join(score["gate"]["blockers"])
    assert not score["productionEligible"]

def test_site_score_validation_only_candidate_audited_not_blocked_by_works():
    """站点线：受控试跑候选只落审计 worksDecision、works 门不二次阻断（结构试跑合成候选）。"""
    score = ss.build_site_score_packet(
        _site_works_candidate(ref="works_trial", text=_CASUAL_SITE_TEXT, validation_only=True)
    )
    assert score["worksDecision"]
    assert "works classifier" not in "\n".join(score["gate"]["blockers"])

