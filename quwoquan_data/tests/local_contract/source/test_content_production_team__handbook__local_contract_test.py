# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-049.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-049.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-049.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-053
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-054
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-055
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-056
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-057
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-058
"""只核对文档契约与隔离负例；不证明原子写围栏、活跃 Bot 或 native 检查能力。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[4]
SKILL = ROOT / ".agents/skills/content-production"
TEAM = SKILL / "references/team.md"
REBUILD = SKILL / "references/grok-team-rebuild.md"
SKILL_MD = SKILL / "SKILL.md"
SESSION = SKILL / "references/session.md"
DISPATCH = SKILL / "references/dispatch.md"
PIPELINE = SKILL / "references/pipeline.md"
DATA_AGENTS = ROOT / "quwoquan_data/AGENTS.md"
HOMEPAGE = SKILL / "carriers/homepage/CARRIER.md"
ARTICLE = SKILL / "carriers/article/CARRIER.md"
IMAGE = SKILL / "carriers/image/CARRIER.md"
VIDEO = SKILL / "carriers/video/CARRIER.md"
SHARD_SCHEMA = SKILL / "schemas/shard.schema.json"
UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
ROUTINE_ID_RE = re.compile(r"automation-\d+")
COMMON = "你按本岗位行业顶级专业人员的标准工作"


def test_isolated_roots_do_not_point_at_canonical_publish():
    publish = Path(os.environ["QWQ_PUBLISH_ROOT"]).resolve()
    assert publish != Path("/Users/zhaoyuxi/Projects/quwoquan/publish").resolve()
    assert "qwq_pytest_isolated_" in str(publish)
    assert "独立临时根" in PIPELINE.read_text(encoding="utf-8")
    assert "独立临时根" in DATA_AGENTS.read_text(encoding="utf-8")
    assert "独立临时根" in SESSION.read_text(encoding="utf-8")
    isolated = Path(os.environ["QWQ_DATA_ROOT"]).resolve()
    for key in ("QWQ_OUTPUT_ROOT", "QWQ_PUBLISH_ROOT", "QWQ_LIBRARY_ROOT", "QWQ_CARRIED_MEDIA_ROOT"):
        assert Path(os.environ[key]).resolve().is_relative_to(isolated)


def test_template_has_no_bot_uuid_credential_or_run_id():
    combined = TEAM.read_text(encoding="utf-8") + "\n" + REBUILD.read_text(encoding="utf-8")
    assert UUID_RE.search(combined) is None
    assert ROUTINE_ID_RE.search(combined) is None
    assert "grok-bot-image-" not in combined
    assert "不得宣称已切换更强模型" in combined
    assert "不能宣称已切换更强模型" in REBUILD.read_text(encoding="utf-8")


def test_init_speech_does_not_start_production_or_routines():
    rebuild = REBUILD.read_text(encoding="utf-8")
    assert "不启动生产" in rebuild
    assert "不启用 Routine" in rebuild
    assert "等待我给出任务范围与启动授权" in rebuild
    assert "不擅自隐藏或删除" in rebuild
    skill = SKILL_MD.read_text(encoding="utf-8")
    assert "references/team.md" in skill
    assert "grok-team-rebuild" in skill


def test_repeat_rebuild_is_idempotent_with_four_role_types_and_variable_slots():
    rebuild = REBUILD.read_text(encoding="utf-8")
    team = TEAM.read_text(encoding="utf-8")
    assert "重建必须幂等" in rebuild
    assert "四类岗位" in rebuild
    assert "2–4" in team and "1–2" in team
    assert "按授权槽位核对成员" in rebuild
    for name in (
        "创作总监",
        "实体主页创作Bot",
        "文章创作Bot",
        "图片创作Bot",
        "视频创作Bot",
        "电脑管家",
        "独立 QA",
    ):
        assert name in team
        assert name in rebuild
    assert HOMEPAGE.is_file() and ARTICLE.is_file() and IMAGE.is_file() and VIDEO.is_file()
    assert "carriers/homepage/CARRIER.md" in team
    assert "carriers/article/CARRIER.md" in team
    assert "carriers/image/CARRIER.md" in team
    assert "carriers/video/CARRIER.md" in team
    assert COMMON in rebuild  # 资质共同前言；模板数量不是团队人数或 native 能力证据。
    assert "稳定 Bot ID" in rebuild
    assert "不得宣称已自动创建" in rebuild


def test_review_without_draft_or_media_access_fails_closed_in_handbook():
    dispatch = DISPATCH.read_text(encoding="utf-8")
    session = SESSION.read_text(encoding="utf-8")
    team = TEAM.read_text(encoding="utf-8")
    rebuild = REBUILD.read_text(encoding="utf-8")
    assert "无法读取当前草稿或实际媒体时停在 review" in dispatch
    assert "文件存在不是完成" in session
    assert "晚到文件不替换正式 review" in session
    assert "无法读取当前草稿、来源或实际媒体即 blocked" in team
    assert "无法访问当前草稿或实际媒体时提交 blocked" in rebuild
    assert "不写或修改正文、caption、script" in rebuild


def test_author_and_qa_own_whole_execution_seals_without_director_relay():
    skill = SKILL_MD.read_text(encoding="utf-8")
    dispatch = DISPATCH.read_text(encoding="utf-8")
    pipeline = PIPELINE.read_text(encoding="utf-8")
    assert "创作者就是本人 execution 的主会话" in skill
    assert "init/acquire/author seal" in dispatch
    assert "QA 自行运行 review seal" in pipeline
    assert "整批" in dispatch and "resultRefs" in dispatch
    assert "总监" in pipeline and "唯一" in pipeline and "原授权" in pipeline
    for obsolete in (
        "全部 Data CLI 机械命令", "reviewer 不 seal", "不自行 seal/publish",
        "默认主页与文章、图片与视频互审", "同时最多两个不重叠 author",
        "固定七人", "群成员恰为七", "独立 QA 是固定第七岗",
    ):
        assert obsolete not in "\n".join(path.read_text(encoding="utf-8") for path in (
            SKILL_MD, TEAM, REBUILD, SESSION, DISPATCH, PIPELINE,
            SKILL / "references/grok-team-bootstrap.md",
        )), obsolete


def test_single_ownership_and_end_to_end_wip_do_not_release_unknown():
    session = SESSION.read_text(encoding="utf-8")
    assert "每作者最多两个未闭合小批，其中最多一个正在创作" in session
    assert "送审、审核中、待发布都计入未闭合" in session
    assert "unknown 不释放" in session
    assert "同一短事务" in session
    assert "不另建语义状态机" in session
    assert "成功发布" in session and "明确终止" in session
    assert "其他健康" in session
    assert "不证明" in session and "claim" in session


def test_ratios_are_advisory_and_do_not_replace_milestone_or_unique_identity():
    session = SESSION.read_text(encoding="utf-8")
    for required in ("1:2:3:4", "50倍", "同一实体", "一个稳定主页身份", "热门", "冷门", "unknown", "M100000", "100000"):
        assert required in session
    assert "建议比例本身不停止" in session
    assert "不增加唯一计数" in session
    assert "content_distribution.policy.yaml" in session


def test_shared_facts_and_director_checks_are_requirements_not_native_evidence():
    session = SESSION.read_text(encoding="utf-8")
    team = TEAM.read_text(encoding="utf-8")
    for required in ("当前有效任务", "预算", "占用", "receipts", "QA", "publish proof", "同一", "凭证", "下一次认领/提交", "撤权", "写围栏"):
        assert required in session
    for required in ("仅@需要行动的人", "不以私聊保存唯一决定", "约每10分钟", "非重入", "人工唤醒", "下一动作", "下次检查", "用户"):
        assert required in team
    assert "不签发无人值守运行通过" in team
    assert "不以文档测试通过证明原生能力" in team


def test_bootstrap_modes_protect_inflight_and_require_shared_readback():
    bootstrap = (SKILL / "references/grok-team-bootstrap.md").read_text(encoding="utf-8")
    for required in ("模式 A", "模式 B", "模式 C", "安全交接点", "unknown", "不等待全队", "不改旧 receipt", "人工清单", "当前有效任务", "非重入", "不宣称活跃 Bot 已生效"):
        assert required in bootstrap
    assert "无在飞/待接管任务" in bootstrap
    assert "旧scope/actor/receipts/版本" in bootstrap


def test_existing_qa_requires_real_activation_not_cached_roster_mutation():
    bootstrap = (SKILL / "references/grok-team-bootstrap.md").read_text(encoding="utf-8")
    for requirement in (
        "QA 对象存在不等于", "NEEDS_MANUAL_CONFIGURATION", "不改本地 roster/cache",
        "停止创作者临时互审", "不虚构 QA 占位身份", "真实终态", "隔离输入",
    ):
        assert requirement in bootstrap


def test_capacity_and_approval_rules_do_not_offer_a_bypass():
    session = SESSION.read_text(encoding="utf-8")
    pipeline = PIPELINE.read_text(encoding="utf-8")
    assert "改变端到端容量须交工程 owner" in session
    assert "不新增第三批正式草稿" in session
    assert "不把备份 receipt 回填为当前通过" in session
    assert "新 execution 也不自动终止旧调用" in session
    assert "宿主工具审批和总监运营确认" in pipeline
    assert "不将总监逐批生成 env 文件" in pipeline
    assert "仅会话自述标为未验证" in pipeline


def test_handoff_freezes_review_input_and_spec_open_anchors_match_titles():
    dispatch = DISPATCH.read_text(encoding="utf-8")
    assert "QA 已领取后不以“改封 pilot”通知替换其输入" in dispatch
    assert "不覆盖已封存 review" in dispatch
    spec = (ROOT / "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md").read_text(encoding="utf-8")
    for number in ("035", "036"):
        assert f'<a id="open-{number}"></a>\n### OPEN-{number}' in spec
    assert "不要求与 author 同一会话" not in spec
    assert "包括 Cursor/Codex IDE/CLI 与 Grok Bot" in spec
    assert "不能继续将 SQLite 长事务当作现役停滞根因" in spec


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-059
def test_known_facts_and_required_observation_are_not_optional_scores():
    dispatch = DISPATCH.read_text(encoding="utf-8")
    assert "有声媒体未核听不能靠省略 audio_fit 后 approved" in dispatch
    assert "已确认矛盾不能降为一般 advisory" in dispatch
    assert "不代写修订" in dispatch
    assert "不新建分数门或最终质量审批" in dispatch


def test_direct_help_preserves_ownership_without_extra_management():
    team = TEAM.read_text(encoding="utf-8")
    session = SESSION.read_text(encoding="utf-8")
    for phrase in ("不代写他人已认领稿件", "不新增技术协调岗", "不增加预审", "不变成每批考试", "不另建日报或看板"):
        assert phrase in team
    for phrase in ("原任务负责人保留跟进责任", "接收方承担解阻责任", "由受影响角色确认一次", "不只扩作者", "不放宽名额堆稿"):
        assert phrase in session


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-056
def test_single_native_check_owns_hourly_zero_increment_reporting_contract():
    team = TEAM.read_text(encoding="utf-8")
    session = SESSION.read_text(encoding="utf-8")
    spec = (ROOT / "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md").read_text(encoding="utf-8")
    for required in (
        "同一个检查机制", "上个完整小时", "Asia/Shanghai", "首次入池",
        "eligible 池净变化", "连续两个完整小时", "完整小时键", "迟到事件",
        "unknown", "Mac 不可达", "群发送失败",
    ):
        assert required in team or required in session or required in spec, required
    assert "不另建第二套小时调度器" in team
    assert "读取失败、Mac不可达或范围不完整报 unknown，不伪造零" in session
    assert "修订、恢复资格、身份归并和退出不冒充新增" in spec
    assert "重复 tick 不重发" in spec


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-002
def test_duplicate_real_entity_is_not_presented_as_a_version_branch():
    identity = (ROOT / "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md").read_text(encoding="utf-8")
    for required in (
        "跨 ref 身份冲突", "不得再调用普通 publish", "revise-homepage",
        "唯一保留身份", "依赖迁移", "当前 reader/consumer 只返回唯一生效身份",
        "旧身份/旧版本仅离线审计", "不建立别名双读、版本选择或兼容分支",
    ):
        assert required in identity, required


def test_shard_requires_nonblank_bounded_name_without_changing_stable_id():
    schema = json.loads(SHARD_SCHEMA.read_text(encoding="utf-8"))
    base = {
        "shardId": "north-image-001",
        "name": "华北图片首轮",
        "regionScope": ["华北"],
        "carriers": ["image"],
        "targets": {"image": 3},
        "sourceBudget": {"example.com": 10},
    }
    jsonschema.Draft202012Validator(schema).validate(base)
    for invalid_name in ("", "   ", "x" * 81):
        candidate = {**base, "name": invalid_name}
        errors = list(jsonschema.Draft202012Validator(schema).iter_errors(candidate))
        assert errors, invalid_name
    assert "name" in schema["required"]
    assert "展示" in schema["properties"]["name"]["description"]
    assert "稳定身份" in schema["properties"]["name"]["description"]


def test_core_paths_subprocess_inherits_only_isolated_roots_by_default():
    code = """
import json
from pathlib import Path
from core import paths
print(json.dumps({
    'data': str(paths.DATA_ROOT.resolve()),
    'output': str(paths.OUTPUT_ROOT.resolve()),
    'publish': str(paths.PUBLISH_ROOT.resolve()),
    'library': str(paths.LIBRARY_ROOT.resolve()),
    'golden_default': str(paths.default_carried_media_root().resolve()),
    'carried': str(paths.carried_media_root().resolve()),
}, sort_keys=True))
"""
    # 不给 subprocess 传 env；它只能继承 conftest 在 collection 前建立的隔离契约。
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT / "quwoquan_data/scripts",
        check=True,
        capture_output=True,
        text=True,
    )
    values = json.loads(completed.stdout)
    isolated = Path(os.environ["QWQ_DATA_ROOT"]).resolve()
    assert set(values) == {"data", "output", "publish", "library", "golden_default", "carried"}
    assert all(Path(value).is_relative_to(isolated) for value in values.values())
