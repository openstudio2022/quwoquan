"""按 templateId + 小节标题生成差异化正文（消费 entity facts + sources）。"""
from __future__ import annotations

from dataclasses import dataclass, field

from cold_start.chuanxi_catalog_v2 import ArticleSpec, P0_SEASON
from cold_start.chuanxi_v2_entity_facts import INBOUND_TRANSPORT, get_entity_facts
from cold_start.chuanxi_v2_shared import entity_names_from_refs


@dataclass
class ComposeContext:
    spec: ArticleSpec
    brief: dict
    source_snippets: list[str] = field(default_factory=list)

    @property
    def creator_name(self) -> str:
        return (self.brief.get("creator") or {}).get("displayName") or "作者"

    @property
    def entities(self) -> list[str]:
        return entity_names_from_refs(self.spec.entity_refs)

    @property
    def primary_entity(self) -> str:
        return self.entities[0] if self.entities else self.spec.title

    @property
    def transport(self) -> str:
        return self.spec.transport or "自驾"

    @property
    def origin(self) -> str:
        return self.spec.origin_city or "成都"

    @property
    def season(self) -> str:
        return self.spec.season or P0_SEASON

    def condition_blurb(self) -> str:
        ctx = self.brief.get("conditionContext") or {}
        parts: list[str] = []
        region = ctx.get("region")
        if isinstance(region, dict):
            packing = "、".join(region.get("packing", [])[:3])
            if packing:
                parts.append(f"我一般会备：{packing}。")
            risks = "、".join(region.get("riskNotes", [])[:3])
            if risks:
                parts.append(f"区域风险：{risks}。")
            region_name = region.get("name") or region.get("label") or ""
            if "高原" in str(region_name) or "雪山" in str(region_name):
                parts.append(
                    "海拔与高反风险要留适应日；强紫外线防护与昼夜温差大，分层穿衣比单件厚外套更实用。"
                )
        season = ctx.get("season")
        if isinstance(season, dict):
            crowd = "、".join(season.get("crowdNotes", [])[:2])
            if crowd:
                parts.append(f"{self.season}季现场感受：{crowd}。")
        return " ".join(parts)

    def cite_entity(self, name: str) -> str:
        for ref in self.spec.entity_refs:
            if ref.endswith(f"/{name}"):
                return f"[/entity/{ref}](/entity/{ref})"
        return name

    def source_hint(self) -> str:
        if not self.source_snippets:
            return ""
        raw = self.source_snippets[0]
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            raw = parts[2] if len(parts) > 2 else raw
        snippet = raw.replace("#", "").replace("\n", " ")[:100].strip()
        if len(snippet) < 20:
            return ""
        return f"游记里还提到：{snippet}。"


def _entity_scenic_guide(heading: str, ctx: ComposeContext) -> str:
    facts = get_entity_facts(ctx.primary_entity)
    ent = ctx.cite_entity(ctx.primary_entity)
    if heading in ("交通方式", "行前概览"):
        return (
            f"到达方式：从成都方向去 {ent}，{facts.transport_from_chengdu}。"
            f"{ctx.source_hint()} {ctx.condition_blurb()}"
        )
    if heading in ("门票信息", "门票与门票"):
        return (
            f"{ctx.primary_entity} 门票价格：{facts.ticket}；开放时间：{facts.hours}。"
            f"旺季我会提前在官方渠道预约，避免现场限流。"
        )
    if heading in ("推荐路线", "推荐动线"):
        return (
            f"动线我会按 {facts.highlight} 来排，"
            f"把高强度段落放在上午，下午留缓冲应对天气变化。"
        )
    if heading in ("最佳季节", "高原与季节"):
        base = f"我更推荐 {facts.best_season} 前往 {ent}。"
        if facts.altitude_note:
            base += f" {facts.altitude_note}"
        return base + f" {ctx.condition_blurb()}"
    if heading == "注意事项":
        return (
            f"离开 {ctx.primary_entity} 前再核对观光车末班与返程路况；"
            f"垃圾随身带走，尊重当地生态与宗教习俗。"
        )
    return f"关于{heading}，{facts.highlight} {ctx.source_hint()}"


def _entity_experience(heading: str, ctx: ComposeContext) -> str:
    facts = get_entity_facts(ctx.primary_entity)
    ent = ctx.cite_entity(ctx.primary_entity)
    if heading == "初见印象":
        return (
            f"到达时间约上午 9:30，第一次到 {ent}，{ctx.creator_name} 印象最深的是尺度与色彩——"
            f"{facts.highlight.split('，')[0]}。"
        )
    if heading == "核心体验":
        return (
            f"体验路线我把徒步强度压在舒适区，停留时长约 3–4 小时；"
            f"{facts.transport_from_chengdu.split('；')[0]}。"
        )
    if heading == "意外收获":
        return (
            f"和民宿老板聊天补上了攻略里没有的闭馆时间与隐藏机位，"
            f"这类信息往往比榜单更实用。{ctx.source_hint()}"
        )
    if heading == "离开时的感受":
        return f"离开 {ent} 时我会留 1 小时弹性，{facts.altitude_note or '别把时间卡死在最后一班车上。'}"
    return f"{heading}：{facts.highlight}"


def _weekend_section(heading: str, ctx: ComposeContext) -> str:
    dest = ctx.spec.title.replace("成都出发", "").split("周末")[0].strip() or ctx.primary_entity
    dest = dest.replace("公共交通", "").replace("自驾", "").strip()
    facts = get_entity_facts(ctx.primary_entity or dest)
    if heading == "周末动线":
        return (
            f"出发地成都，这个周末我去 {dest}：Day1 走核心，Day2 上午补点后返程。"
            f"步行动线按 {facts.highlight.split('；')[0]} 排，别把时间耗在路上。"
        )
    if heading == "交通方式":
        transit_extra = (
            "公共交通衔接：地铁+快铁/景区直通车，预留换乘 30 分钟；"
            if ctx.transport == "公共交通"
            else "若临时改公共交通，衔接成都枢纽再转景区大巴/直通车；"
        )
        return (
            f"交通方式选 {ctx.transport}；单程耗时 {facts.transport_from_chengdu.split('约')[-1] if '约' in facts.transport_from_chengdu else '视班次 1–3 小时'}。"
            f"{transit_extra}{facts.transport_from_chengdu}"
        )
    if heading == "时间安排":
        return (
            "周六 7:30 前出城，11:00 前进入核心区域；返程时间建议周日 15:00 前启程，"
            "留 1 小时堵车缓冲。"
        )
    if heading == "费用区间":
        return f"人均预算 300–600 元（含门票或预约 {facts.ticket} 与餐饮交通）。"
    if heading == "避坑与备选":
        return (
            f"{ctx.season}季周末人流大，城市天气与限行以官方通报为准。"
            f"高温避暑策略：上午进馆/进沟，午后雷阵雨频繁，室内备选留 1 套；"
            f"防蚊与防晒按 {ctx.condition_blurb()} 准备。"
            f"预约失败就改近郊低强度备选。"
        )
    return f"{heading}：{ctx.source_hint()}"


def _loop_section(heading: str, ctx: ComposeContext) -> str:
    route = ctx.spec.ref.split("_")[0] if "_" in ctx.spec.ref else ctx.spec.title
    nodes = " → ".join(ctx.entities) if ctx.entities else route
    first = ctx.entities[0] if ctx.entities else route
    second = ctx.entities[1] if len(ctx.entities) > 1 else "下一节点"
    if heading == "产品类型":
        return (
            f"这条 {route} 我选 {ctx.transport} 产品，重点看是否含景区交通、"
            f"自由活动时间占比，以及集合城市是否在成都。"
        )
    if heading in ("路线逻辑", "行程概览"):
        if heading == "行程概览":
            return (
                f"行程概览：Day1–2 深度 {first}；Day3 转场 {second}；"
                f"最后一天上午收尾，下午返成都，不把驾驶/乘车堆在同一天。"
            )
        return (
            f"路线逻辑按 {nodes} 顺序推进，"
            f"{'自驾' if ctx.transport == '自驾' else ctx.transport} 模式下每天驾驶/乘车不超过 5 小时。"
        )
    if heading == "天数安排":
        return (
            f"整体 {route} 安排 4–5 天：前 2 天给 {first}，"
            f"中间 1 天转场 {second}，最后 1 天机动/返程。"
        )
    if heading == "每日节点":
        return (
            f"每日节点：Day1 成都→{first} 口；Day2 沟内深度；"
            f"Day3 上午 {second} 下午返成都方向；别把驾驶堆在最后一天。"
        )
    if heading == "分段路书":
        return (
            f"分段路书按 {nodes} 写进导航收藏夹，"
            f"每段预留 30 分钟休息与加油窗口。"
        )
    if heading in ("住宿选择", "补给与住宿"):
        return "住宿优先选下一日动线出口附近，高原区域选含氧或供暖条件更好的酒店，别为了省钱跨夜赶路过远。"
    if heading in ("适合与不适合", "强度与适合人群", "强度说明"):
        return (
            f"{'自驾' if ctx.transport == '自驾' else ctx.transport} 适合能自理票务、"
            f"接受海拔变化的旅人；老人幼儿需缩短步行并增加适应日。"
        )
    if heading in ("费用构成", "费用包含", "预算区间"):
        return "费用我会拆成：大交通、租车/跟团团费、门票观光车、油费过路费、应急储备 五块分别记账。"
    if heading in ("成团与退改", "退改规则"):
        return "跟团产品务必看清退改规则与自费项目清单，暑期取消政策常更严格，下单前截图条款。"
    if heading in ("避坑提醒", "避坑与备选"):
        return f"旺季预约、海拔适应、雨季落石是三大变量。{ctx.condition_blurb()} {ctx.source_hint()}"
    if ctx.transport == "跟团" and heading == "成团与退改":
        return "选团时看集合地点、是否含景区交通、自由活动时间占比，拒绝口头承诺。"
    return f"{heading}（{route}）：{nodes}。{ctx.source_hint()}"


def _deep_section(heading: str, ctx: ComposeContext) -> str:
    theme = ctx.spec.title
    if heading == "线路定位":
        return f"{theme} 属于深度线，不是打卡清单；我会先确认总天数与退出通道再订交通。"
    if heading == "体能与经验要求":
        return "需要连续多日徒步或高海拔适应经验；新手建议先走双桥沟/亚丁短线再考虑穿越。"
    if heading in ("分段行程", "分段路书"):
        return (
            f"按 {ctx.entities[0] if ctx.entities else '起点'} 分段推进，"
            f"每日爬升控制在合理范围，预留天气缓冲日。"
        )
    if heading in ("补给与露营", "补给与住宿"):
        return "露营需自带轻量化装备与冗余热量；若走商业线，确认补给点间距与饮用水来源。"
    if heading in ("风险与应急", "风险与替代方案"):
        facts = get_entity_facts(ctx.primary_entity)
        return f"高海拔与天气突变是主要风险。{facts.altitude_note} 遇暴雪/落石果断下撤。"
    if heading == "向导与许可":
        return "穿越类线路建议请当地向导，部分区域需登记或环保许可，勿擅自偏离成熟轨迹。"
    if heading == "替代方案":
        return "若体能或天气不允许，可降级为同一区域的沟内环线，保留安全窗口。"
    return f"{heading}：{ctx.source_hint()}"


def _inbound_section(heading: str, ctx: ComposeContext) -> str:
    hub = INBOUND_TRANSPORT.get(ctx.origin, INBOUND_TRANSPORT["北京"])
    nodes = "、".join(ctx.entities) if ctx.entities else "川西段"
    if heading == "大交通方案":
        return (
            f"从 {ctx.origin} 进川，我通常比较 {hub['flight']} 与 {hub['rail']}。"
            f"大交通方式、耗时与费用要在订川西段之前先锁定。"
        )
    if heading == "到达成都":
        return (
            f"落地后按 {hub['hub']} 进城，"
            f"成都到达站/机场到市区预留 1–1.5 小时，别当晚直接翻折多山。"
        )
    if heading == "休整与补给":
        taikoo = ctx.cite_entity("成都太古里") if "成都太古里" in ctx.entities else "春熙路附近"
        return (
            f"我会在 {taikoo} 一带半日 city walk，采购红景天、氧气、零食与雨具，"
            f"休整安排至少 0.5–1 晚，让睡眠先适应。"
        )
    if heading == "再出发衔接":
        return (
            f"休整后按 {ctx.transport} 进入 {nodes} 主线。"
            f"后续川西段衔接：成都→康定→新都桥方向，首日驾驶不超过 6 小时。"
        )
    if heading == "时间与费用":
        return (
            f"整体我会拆成：{ctx.origin}↔成都大交通 1–2 天 + 川西段 5–7 天；"
            f"人均预算 5000–9000 元（含机票/油费/门票，视 {ctx.transport} 而定）。"
        )
    if heading == "风险提醒":
        return (
            f"外地进川最怕 Day1 就上海拔。进 {nodes} 前先在成都睡好，"
            f"高原反应不是硬扛能扛过去。{ctx.condition_blurb()}"
        )
    return f"{heading}：{ctx.source_hint()}"


def _drive_section(heading: str, ctx: ComposeContext) -> str:
    if heading == "线路总览":
        return f"自驾走 {ctx.spec.title}，总里程视停点约 1500–2200 公里，{ctx.season}季路况以官方通报为准。"
    if heading == "行前判断":
        return "我会查折多山/巴朗山天气，确认防滑链、备胎、拖车绳是否在位；高反药与氧气按人数×1.5 备。"
    if heading == "分段路书":
        return _loop_section("分段路书", ctx)
    if heading == "补给与住宿":
        return _loop_section("补给与住宿", ctx)
    if heading == "风险与替代方案":
        return _deep_section("风险与应急", ctx)
    return _loop_section(heading, ctx)


def _museum_experience(heading: str, ctx: ComposeContext) -> str:
    ent = ctx.cite_entity(ctx.primary_entity)
    facts = get_entity_facts(ctx.primary_entity)
    if heading == "进馆第一印象":
        return f"从入口进 {ent}，我先在导览台拿展线册，{facts.transport_from_chengdu}。{ctx.condition_blurb()}"
    if heading == "最停留的展厅":
        return "青铜馆与联合遗址厅最耗时间，我各留了 45 分钟，数字导览能补背景。"
    if heading == "一个展品故事":
        return "青铜大面具前的说明牌值得细读——祭祀与合金工艺比照片更有冲击力。"
    if heading == "参观动线":
        return f"推荐动线：按「历史脉络 → 核心文物 → 特展」顺序走，{facts.hours} 前 30 分钟停止入馆。"
    if heading == "离开后的感受":
        return f"出馆后在 {facts.city} 简餐再返程，别在闭馆高峰挤公交。{ctx.source_hint()}"
    return f"{heading}：{facts.highlight}"


def _museum_popular_science(heading: str, ctx: ComposeContext) -> str:
    facts = get_entity_facts(ctx.primary_entity)
    ent = ctx.cite_entity(ctx.primary_entity)
    if heading == "馆舍概况":
        return f"{ent} 新馆展线完整，{facts.transport_from_chengdu}，建议预留 3–4 小时。"
    if heading == "镇馆之宝":
        return "青铜大面具、青铜神树与金杖是镇馆序列，建议先读说明牌再拍照。"
    if heading == "展陈动线":
        return "推荐从古代四川序厅进入，按时代递进，避免在单一展厅耗尽体力。"
    if heading == "关键展品":
        return "联合遗址出土器物的层位信息值得细看，可帮助理解考古上下文。"
    if heading == "参观建议":
        return f"门票 {facts.ticket}，{facts.hours}；旺季务必预约。{ctx.condition_blurb()}"
    return _museum_science(heading, ctx)


def _site_culture(heading: str, ctx: ComposeContext) -> str:
    facts = get_entity_facts(ctx.primary_entity)
    ent = ctx.cite_entity(ctx.primary_entity)
    if heading == "遗址概况":
        return f"{ent} 位置在{facts.city}，是古蜀文明的重要现场，{facts.highlight}"
    if heading == "历史脉络":
        return "历史脉络上可追溯到古蜀青铜时代，年代信息以考古简报与展牌为准。"
    if heading == "现场可见细节":
        return "代表遗存以祭祀坑、城墙与出土器物层位为主，请遵守不触摸、不闪光灯规定。"
    if heading == "参观动线":
        return f"推荐动线：入口 → 祭祀坑区 → 博物馆联动展线，{facts.hours} 前停止入馆。"
    if heading == "延伸阅读":
        return f"可与 {ctx.cite_entity('三星堆博物馆') if ctx.primary_entity != '三星堆博物馆' else ent} 联票安排一日深度游。"
    return f"{heading}：{facts.highlight} {ctx.source_hint()}"


def _museum_science(heading: str, ctx: ComposeContext) -> str:
    facts = get_entity_facts(ctx.primary_entity)
    ent = ctx.cite_entity(ctx.primary_entity)
    if heading in ("历史背景", "展线概览"):
        return f"{ent} 是理解古蜀文明的重要窗口，{facts.highlight}"
    if heading in ("参观要点", "镇馆重点"):
        return f"重点文物建议预留 40 分钟；门票 {facts.ticket}，{facts.hours}。"
    if heading in ("延伸阅读", "预约规则"):
        return f"{facts.transport_from_chengdu} 建议网上预约，旺季 {facts.ticket} 需提前锁定。"
    return f"{heading}：{facts.highlight} {ctx.source_hint()}"


def _checkin_guide(heading: str, ctx: ComposeContext) -> str:
    facts = get_entity_facts(ctx.primary_entity)
    ent = ctx.cite_entity(ctx.primary_entity)
    if heading == "最佳时段":
        return f"{ent} 工作日上午与蓝调时刻人流更少，拍照更从容。"
    if heading == "交通接驳":
        return facts.transport_from_chengdu
    if heading == "周边串联":
        return f"可与同片区商圈组合半日 city walk，{ctx.condition_blurb()}"
    if heading == "今日记录":
        return f"在 {ent} 慢走 30 分钟，比赶景点更贴近城市气质。{ctx.source_hint()}"
    if heading == "感官细节":
        return "街声、咖啡香与橱窗光影，比地标清单更能定义一次漫步。"
    return f"{heading}：{facts.highlight}"


def _town_guide(heading: str, ctx: ComposeContext) -> str:
    facts = get_entity_facts(ctx.primary_entity)
    ent = ctx.cite_entity(ctx.primary_entity)
    if heading == "到达方式":
        return (
            f"到达方式：{facts.transport_from_chengdu}。"
            f"自驾注意古城外围停车场与摆渡车时刻。{ctx.source_hint()}"
        )
    if heading == "游览动线":
        return (
            f"停留时长建议半天到 1 天；上午走核心街巷，下午留 1 小时喝茶或坐船。"
            f"{facts.highlight.split('。')[0]}。"
        )
    if heading == "值得停留的街巷":
        return (
            f"核心街巷我会优先走 {facts.highlight.split('核心街巷：')[-1] if '核心街巷' in facts.highlight else facts.highlight}，"
            f"避开主街高峰时段。"
        )
    if heading == "餐饮住宿":
        return f"餐饮选本地小吃与河鲜，住宿可住古城内客栈或城外酒店，旺季提前 2 周预订。{ctx.condition_blurb()}"
    if heading == "避坑提醒":
        return "节假日主街拥挤，预约联票；雨天石板路滑，别穿硬底高跟鞋。"
    return f"{heading}：{facts.highlight}"


def _town_narrative(heading: str, ctx: ComposeContext) -> str:
    facts = get_entity_facts(ctx.primary_entity)
    ent = ctx.cite_entity(ctx.primary_entity)
    if heading == "抵达时刻":
        return (
            f"抵达方式：{facts.transport_from_chengdu}。"
            f"我选在上午 9 点前进 {ent}，街巷节点从华光楼方向开始慢走。"
        )
    if heading == "街巷漫步":
        return (
            f"街巷节点以 {facts.highlight.split('核心街巷：')[-1].split('。')[0] if '核心街巷' in facts.highlight else '主街与支巷'} 为主，"
            f"不赶景点清单，只跟光线走。"
        )
    if heading == "一个生活细节":
        return f"老茶馆里听本地口音聊天，比打卡更记得住。{ctx.source_hint()}"
    if heading == "人文故事":
        return f"{ctx.primary_entity} 的历史层叠在砖缝里，走慢才能听见。体验时间我控制在 3–4 小时，留弹性给意外发现。"
    if heading == "实用补充":
        return f"门票 {facts.ticket}，{facts.hours}；{facts.altitude_note or '返程别卡末班公交。'}"
    return f"{heading}：{facts.highlight}"


def _image_gallery_section(heading: str, ctx: ComposeContext) -> str:
    facts = get_entity_facts(ctx.primary_entity)
    ent = ctx.cite_entity(ctx.primary_entity)
    if heading == "封面主图":
        return (
            f"封面主图选 {ent} 最具识别度的山形与云隙光，"
            f"拍摄地点在 {facts.city} 方向经典机位，季节以 {facts.best_season} 为主。"
        )
    if heading == "地理线索":
        return f"地理线索：{facts.transport_from_chengdu}；{facts.highlight}"
    if heading == "图集分组":
        return "图集分组按「远景山势 → 中景沟谷 → 细节纹理」三段排列，便于读者滑动阅读。"
    if heading == "拍摄提示":
        return (
            f"光线时段优先清晨与傍晚，强侧光更能拉出层次；"
            f"图片来源为作者现场拍摄，授权状态仅限个人分享非商用。"
        )
    if heading == "图注说明":
        return (
            f"每张图注写清拍摄地点、季节与焦段，避免过度滤镜；"
            f"{facts.altitude_note or '高海拔注意保暖与电池续航。'}"
        )
    return f"{heading}：{facts.highlight} {ctx.source_hint()}"


def render_section(template_id: str, heading: str, ctx: ComposeContext) -> str:
    if template_id == "线路_枢纽到达":
        return _inbound_section(heading, ctx)
    if template_id == "线路_周末短途":
        return _weekend_section(heading, ctx)
    if template_id == "线路_跟团攻略":
        return _loop_section(heading, ctx)
    if template_id == "线路_环线攻略":
        return _loop_section(heading, ctx)
    if template_id == "线路_深度探险":
        return _deep_section(heading, ctx)
    if template_id == "线路_自驾路书":
        return _drive_section(heading, ctx)
    if template_id == "博物馆_体验":
        return _museum_experience(heading, ctx)
    if template_id == "博物馆_科普":
        return _museum_popular_science(heading, ctx)
    if template_id == "遗址_文化":
        return _site_culture(heading, ctx)
    if template_id in ("打卡地_攻略", "打卡地_日记"):
        return _checkin_guide(heading, ctx)
    if template_id in ("景区_攻略", "景区_专业导览"):
        return _entity_scenic_guide(heading, ctx)
    if template_id == "景区_体验":
        return _entity_experience(heading, ctx)
    if template_id in ("打卡地_美图", "主题_图文画报"):
        return _image_gallery_section(heading, ctx)
    if template_id == "古镇_攻略":
        return _town_guide(heading, ctx)
    if template_id == "古镇_叙事":
        return _town_narrative(heading, ctx)
    return _entity_scenic_guide(heading, ctx)
