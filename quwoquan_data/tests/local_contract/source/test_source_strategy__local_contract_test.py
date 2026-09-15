# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-059
"""隔离的来源/评分指导文档契约，只读版本化文本，不访问生产根。

不执行 AI 真实语义测试，不证明正文无残留、在线可达、合法授权、真实媒体审核或 Bot 已更新。
"""
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[4]
SKILL = ROOT / ".agents/skills/content-production"


def document(relative_path):
    return (SKILL / relative_path).read_text(encoding="utf-8")


def test_homepage_priority_is_distinct_from_implemented_acquisition():
    sources = document("carriers/homepage/sources.md")
    carrier = document("carriers/homepage/CARRIER.md")
    assert "Wikipedia（第一）→百度百科（第二）→头条百科（第三）" in sources
    assert "baidu_baike · 宿主工具，未实现专用采集模块" in sources
    assert "缺条目、消歧不符、内容不足或无法合法取得" in sources
    assert "wikipedia|baidu_baike|toutiao_baike" in carrier
    assert "主页主源顺序只由" in carrier
    assert "不能宣称自动可抓" in sources


@pytest.mark.parametrize("carrier", ["article", "image", "video"])
def test_non_homepage_sources_share_priority_without_list_order(carrier):
    sources = document(f"carriers/{carrier}/sources.md")
    assert "专业类与综合类同等首选" in sources
    assert "不按名单顺序排名" in sources
    assert "百科/Commons 只作补充" in sources
    assert "有界检索" in sources


def test_shared_sourcing_owns_bounded_search_and_honest_capability():
    sourcing = document("references/sourcing.md")
    for phrase in (
        "实体/区域/中英文别名", "季节/主题/活动/视角", "站点轮换",
        "不让每件作品遍历全清单", "发现、详情读取、原件取得",
        "未验证", "无结果", "工具不支持", "不增加空客户端",
        "来源名单不是在线能力证明", "版权授权是不同事实",
    ):
        assert phrase in sourcing
    assert "1 为 Commons QI/FP/VI" not in sourcing
    assert "sourceTier" in sourcing and "不以平台、开放许可或取得便利性" in sourcing


def test_image_discovery_separates_original_and_licensed_asset():
    sources = document("carriers/image/sources.md")
    for platform in (
        "Pinterest", "图虫", "500px", "Flickr", "1x", "Unsplash", "Pexels", "Pixabay",
        "Getty Images", "iStock", "Shutterstock", "Adobe Stock", "Alamy", "视觉中国",
    ):
        assert platform in sources
    for phrase in ("发现入口", "原作者", "适用授权", "带水印预览", "未实现专用模块"):
        assert phrase in sources
    assert "imageProviderPriority" in sources
    assert "活跃外部 claim" in sources
    assert "旧线性排序冲突待 owner 处理" in sources


def test_video_discovery_records_aggregator_and_each_capability_boundary():
    sources = document("carriers/video/sources.md")
    for platform in (
        "抖音", "快手", "TikTok", "Facebook", "腾讯视频", "百度视频",
        "YouTube", "Bilibili", "Vimeo", "Dailymotion", "西瓜视频",
    ):
        assert platform in sources
    assert "实际播放页与供稿网站" in sources
    assert "抖音与 TikTok 分列" in sources
    assert "同原作重传先去重" in sources
    assert "不开放自动采集" in sources
    assert "电视剧/影视片段" in sources


@pytest.mark.parametrize("carrier", ["homepage", "article", "image", "video"])
def test_review_requires_current_draft_and_preserves_score_advisory(carrier):
    text = document(f"carriers/{carrier}/CARRIER.md")
    assert "当前草稿" in text
    assert "blocked" in text and "approved" in text
    assert "生产术语" in text
    assert "分数只记录" in text or "只记录" in text


def test_sample_feedback_does_not_turn_into_a_new_score_gate():
    article = document("carriers/article/CARRIER.md")
    image = document("carriers/image/CARRIER.md")
    video = document("carriers/video/CARRIER.md")
    homepage = document("carriers/homepage/CARRIER.md")
    assert "年代/地址/面积" in article
    assert "摄影标签只能用于确有摄影观察" in article
    assert "practical_density=2" in article and "不把低分当新拒绝门" in article
    assert "像素不可读" in image
    assert "不标未核树种" in image
    assert "未听音轨" in video and "ffprobe" in video
    assert "镜像" in video and "poster" in video
    assert "不能只因身份清楚" in homepage


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-059
@pytest.mark.parametrize(
    ("carrier", "dimension", "expected"),
    [
        ("video", "unique_perspective", ("没有可辨的观察收益", "明确的观察收益", "揭示主体特征")),
        ("article", "practical_density", ("未回答读者问题", "具体事实或解释", "有效信息密度")),
        ("homepage", "information_completeness", ("关键事实缺失", "关键问题", "适用条件")),
        ("homepage", "practical_value", ("空泛百科转述", "具体决策问题", "适用条件")),
        ("homepage", "source_quality", ("关键事实无支持", "相关、可追溯", "交叉核实")),
    ],
)
def test_rubric_rows_reward_reader_value_not_production_form(carrier, dimension, expected):
    text = document(f"carriers/{carrier}/CARRIER.md")
    rows = [line for line in text.splitlines() if line.startswith(f"| `{dimension}` |")]
    assert len(rows) == 1
    anchors = [cell.strip() for cell in rows[0].split("|")[2:-1]]
    assert len(anchors) == 3
    for anchor, phrase in zip(anchors, expected):
        assert phrase in anchor
    for obsolete in ("有航拍或延时", "路线/时间/费用/贴士全无", "有两项具体信息", "有信息框", "到达/门票/时长中有两项"):
        assert obsolete not in rows[0]


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-038
@pytest.mark.parametrize("carrier", ["homepage", "article", "image", "video"])
def test_s_grade_needs_cross_team_evidence_without_changing_sealed_review(carrier):
    text = document(f"carriers/{carrier}/CARRIER.md")
    for phrase in (
        "单队场景", "缺少跨队复核证明时不标 S", "不以同队独立 QA 冒充跨队复核",
        "不新增发布审批", "不改变 admission", "不改 sealed review",
    ):
        assert phrase in text


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-059
@pytest.mark.parametrize("carrier", ["homepage", "article", "image", "video"])
def test_internal_language_guidance_requires_honest_current_text_review(carrier):
    text = document(f"carriers/{carrier}/CARRIER.md")
    assert "当前草稿" in text
    assert "未逐段核读不能宣称“无残留”" in text
    assert "发现残留须引用 exact 原句" in text
    assert "关键词未命中不证明语义无残留" in text


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-059
def test_tongli_r86_counterexample_stays_internal_and_does_not_certify_qa():
    text = document("carriers/article/CARRIER.md")
    for phrase in (
        "r86 同里", "仓侧地域：江苏省", "本篇冻结镇内命名节点", "模块看完即可折返",
        "不进入消费者正文", "不能据旧 approved 宣称“无残留”",
        "不把示例清单当自动判词器",
    ):
        assert phrase in text
    assert "人文、赏析" in text and "路线费用" in text


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-059
@pytest.mark.parametrize(
    ("relative_path", "counterexample", "required"),
    [
        ("carriers/homepage/CARRIER.md", "以现场为准掩盖已确认地址冲突",
         ("已确认的地理/到达矛盾", "不能用“现场为准”代偿")),
        ("carriers/article/CARRIER.md", "批量换角度而不回源核实路线",
         ("按读者问题回源", "不批量换角度", "已确认的地理/路线矛盾", "不能用“现场为准”代偿")),
        ("carriers/image/CARRIER.md", "以文件名或地点代替画面主体",
         ("seal 前", "画面主体", "文件名或地点不能代替", "原图、大单图预览与派生图")),
        ("carriers/video/CARRIER.md", "转码前听过便推定交付声音不变",
         ("seal 前", "exact 交付段", "转码后实际声音", "无音轨、有轨静音与不可听", "不可听不等于静音或无音轨")),
        ("references/sourcing.md", "按来源数量门逐站穷举或另建决策台账",
         ("每批复用已有 selection/report 留一条来源选择理由", "不新增表", "不新增站点数量门")),
    ],
)
def test_domain_counterexamples_have_explicit_document_guards(relative_path, counterexample, required):
    """只验反例约束仍在指导文本，不执行内容实看或 AI 语义验收。"""
    text = document(relative_path)
    for phrase in required:
        assert phrase in text, f"{counterexample}: 缺少 {phrase}"


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-038
@pytest.mark.parametrize("carrier", ["homepage", "article", "image", "video"])
def test_author_checks_existing_taxonomy_before_seal_and_links_shared_qa(carrier):
    text = document(f"carriers/{carrier}/CARRIER.md")
    assert "seal 前" in text and "解析到既有 taxonomy" in text
    assert "[共享 QA 决策](../../references/dispatch.md#qa-整批交总监)" in text


def _download_example():
    text = document("carriers/video/sources.md")
    section = text.split("### 宿主批量下载的退出状态", 1)[1]
    return section.split("```bash\n", 1)[1].split("```", 1)[0]


@pytest.mark.parametrize("failures", [[], ["e"], ["c"], ["a", "b", "c", "d", "e"]])
def test_documented_download_command_preserves_each_exit_status(tmp_path, failures):
    """执行指导中的同一段命令；假下载器无网络，不证明真实下载或授权。"""
    fake = tmp_path / "fake downloader"
    fake.write_text(
        '#!/bin/sh\nfor arg do url="$arg"; done\nid=${url##*/}\n'
        'printf "%s\\n" "$id" >> "$FAKE_CALLS"\n'
        'case ",${FAKE_FAILURES}," in\n'
        '  *,"$id",*) printf "fixture HTTP 403: %s\\n" "$id" >&2; exit 22;;\n'
        'esac\nprintf "fixture media" > "$HOST/$id.mp4"\n',
        encoding="utf-8",
    )
    fake.chmod(0o700)
    host = tmp_path / "media"
    host.mkdir()
    calls = tmp_path / "calls.txt"
    env = {**os.environ, "YTDLP": str(fake), "HOST": str(host),
           "FAKE_CALLS": str(calls), "FAKE_FAILURES": ",".join(failures)}
    ids = ["a", "b", "c", "d", "e"]
    result = subprocess.run(
        ["/bin/bash", "-c", _download_example(), "batch", *[f"https://example.invalid/{i}" for i in ids]],
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == (1 if failures else 0), result.stderr
    success_count = ids.index(failures[0]) if failures else len(ids)
    attempted = success_count + bool(failures)
    assert calls.read_text().splitlines() == ids[:attempted]
    for position, identity in enumerate(ids):
        if position >= attempted:
            assert f"candidate\thttps://example.invalid/{identity}\tnot_attempted" in result.stdout
        else:
            code = 22 if identity in failures else 0
            assert f"candidate\thttps://example.invalid/{identity}\texit={code}" in result.stdout
        assert (host / f"{identity}.mp4").exists() == (position < success_count)
    assert f"summary\tok={success_count}\tfailed={int(bool(failures))}\tnot_attempted={5-attempted}" in result.stdout
    if failures:
        assert "fixture HTTP 403" in result.stderr


@pytest.mark.parametrize("missing_tool", [False, True])
def test_download_example_fails_explicitly_before_invalid_invocation(tmp_path, missing_tool):
    env = {**os.environ, "HOST": str(tmp_path), "YTDLP": "/bin/false"}
    if missing_tool:
        env["YTDLP"] = str(tmp_path / "missing-tool")
    urls = ["https://example.invalid/a"] if missing_tool else []
    result = subprocess.run(
        ["/bin/bash", "-c", _download_example(), "batch", *urls],
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 64
    assert "candidate\t" not in result.stdout


def test_host_invocation_guidance_avoids_false_success_and_hidden_work():
    pipeline = document("references/pipeline.md")
    session = document("references/session.md")
    video = document("carriers/video/sources.md")
    for phrase in ("子命令退出码", "空匹配", "现有准确路径", "unknown 不等于 timeout"):
        assert phrase in pipeline
    assert "观察调用不捎带下载" in session
    assert "固定 sleep" in session
    assert "已登记且摘要校验通过的资产" in video
    assert "不是审批、评分或自动重试器" in video
