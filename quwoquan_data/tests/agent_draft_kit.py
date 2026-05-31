"""测试用：模拟会话模型创作的 agent 正文（替代脚本拼接）。

这些 builder 刻意写成不同措辞、含出发动机/喜欢/不喜欢/取舍、注意事项就地融入、
不含数字单位（保证 factTraceability 数值可回溯），用于驱动 review/materialize/verify 全绿。
不是脚本拼正文的回归：它们只在测试里产出固定 fixture 草稿，并以 generator=agent 落盘。
"""
from __future__ import annotations

from typing import Sequence

# 每个节点一段独特措辞，避免 narrativeContinuity 的相似度门（jaccard>0.72）。
_NODE_PARAS = [
    "{t}抵达{name}时，让我真正放松下来的是清晨那层薄雾里安静的湖面，舍不得快走。如果你也想慢看，我会建议把这一段排在体力最好的上午。",
    "{t}到了{name}，山色和草甸的层次让人心动，可午后人潮和长时间坐车确实有点累。宁可少看一个点，也别把自己逼到疲惫。",
    "{t}在{name}，我更愿意把时间留给傍晚的光线，那种治愈感很难用照片复刻；不过补给和路况要提前想清楚，别等扎堆了才后悔。",
    "{t}走到{name}已是收束，回望整条线我反而最踏实。如果你怕高反，就把这里当作放慢呼吸的出口，而不是再冲一个打卡点。",
]

_TRANS = ["先", "再", "随后", "最后", "一路"]


def route_article(title: str, byline: str, nodes: Sequence[str], must_facts: Sequence[str]) -> str:
    paras: list[str] = [f"# {title}", f"> {byline} · 真实走过之后想说的"]
    paras.append(
        "出发前我犹豫了很久，既期待这条线能让人松弛下来，又怕一路赶路把状态拖垮。"
        "如果你也在纠结要不要走，我想先把我真实的喜欢和担心讲清楚，再决定值不值得。"
    )
    for i, name in enumerate(nodes):
        paras.append(f"## 走到{name}")
        paras.append(_NODE_PARAS[i % len(_NODE_PARAS)].format(t=_TRANS[i % len(_TRANS)], name=name))
    if must_facts:
        paras.append("## 临行前我会反复确认的")
        paras.append(
            "出发前我会把这些都问清楚再上路：" + "、".join(must_facts) + "。"
            "我更愿意多问一句，也不想到现场才被动应付，因为它们直接决定这趟走得舒不舒服。"
        )
        paras.append("这些不是为了凑清单，而是每一条都和当天的节奏、体力和退路绑在一起。")
    paras.append("## 这条线适合谁")
    paras.append(
        "如果你愿意为节奏让路、能接受偶尔的疲惫，这条线值得慢慢走；"
        "但如果时间很紧又怕累，我会建议宁可砍掉一两个点，也别硬撑着赶完。"
    )
    return "\n\n".join(paras) + "\n"


def entity_article(title: str, byline: str, name: str, must_facts: Sequence[str]) -> str:
    paras: list[str] = [f"# {title}", f"> {byline} · 去过{name}之后想说的"]
    paras.append(
        f"出发前我其实有点犹豫，怕{name}只是被过度宣传的打卡点，又期待它能让人安静下来。"
        "如果你也在纠结值不值得专门跑一趟，我想先把真实的体验讲给你听。"
    )
    paras.append(f"## 初见{name}")
    paras.append(
        f"第一眼的{name}并没有急着用名气压人，反而是现场的节奏感先打动了我。"
        "我没急着赶下一处，而是先在入口附近站了一会儿，让自己从赶路的状态里慢下来；"
        "越是这样慢慢看，越觉得它和我出发前担心的样子很不一样，那种被过度包装的浮躁感并没有出现。"
    )
    paras.append("## 最打动我的")
    paras.append(
        "最让我愿意停下来的，是那种安静看展的松弛感，光线好的时候尤其治愈，连呼吸都会跟着放慢。"
        "我喜欢的是它没有逼着你打卡，而是允许你为真正感兴趣的细节多停一会儿；"
        "如果你也喜欢这种慢看的方式，我会建议把最想细看的部分排在人少的时段，体验会完全不一样。"
    )
    paras.append("## 也得说说不足")
    paras.append(
        "让我有点累的是午后排队和讲解扎堆，连着看下来确实会疲惫，注意力也容易散。"
        "我不会假装它完美：高峰期的人流会稀释掉那份安静，怕吵的人需要提前有心理准备；"
        "与其硬撑着把时间耗在排队上，不如错峰来，把状态留给真正想细看的部分。"
    )
    if must_facts:
        paras.append("## 去之前我会确认的")
        paras.append(
            "动身前我会把这些先想清楚，免得到现场被动：" + "、".join(must_facts) + "。"
            "把它们提前排进当天计划，比盲目想着要把每个角落都走遍更省心，也更能保住体验的节奏；"
            "我宁可前一晚多花十分钟规划，也不愿意在现场手忙脚乱地临时决定。"
        )
    paras.append(f"## {name}适合谁")
    paras.append(
        f"如果你愿意为一两处真正打动你的细节多留些时间，{name}值得专门来一趟，慢看比赶场值得；"
        "但如果你只想快速打卡、对安静看展并不在意，那我会建议把宝贵的时间留给更想看的地方，别勉强。"
    )
    return "\n\n".join(paras) + "\n"


# 画报载体：以图为主、配简短小字（<=captionMax）。每张图一个 :::figure 块。
_GALLERY_CAPTIONS = ["晨雾里的安静", "风口的光影", "草甸的层次", "傍晚的治愈", "云隙的山脊", "湖面的倒影"]


def gallery_article(
    title: str,
    byline: str,
    assets: Sequence[dict],
) -> str:
    """模拟会话模型创作的画报：标题 + 多个 figure 块，配简短小字。"""
    lines: list[str] = [f"# {title}｜光影图集", f"> {byline} · 用图说话"]
    for i, asset in enumerate(assets):
        aid = asset.get("assetId") or asset.get("ref") or f"img_{i}"
        cap = _GALLERY_CAPTIONS[i % len(_GALLERY_CAPTIONS)]
        lines.append(f":::figure\n![{cap}](asset://{aid})\n{cap}\n:::")
    return "\n\n".join(lines) + "\n"
