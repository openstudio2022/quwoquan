"""图片作品边界；作品选择和顺序来自宿主显式输入。"""
import json


def check(chosen, candidates):
    sources = chosen["sources"]
    if len(sources) != 1 or candidates[sources[0]["candidateId"]]["kind"] != "image":
        raise ValueError("一个 image target 必须选择一个原生图片作品")
    selected = [asset["id"] for asset in sources[0].get("assets", [])]
    known = {asset["id"] for asset in candidates[sources[0]["candidateId"]]["assets"]}
    if not selected or len(selected) != len(set(selected)) or not set(selected) <= known:
        raise ValueError("作品资产必须是非空、不重复的显式子集")


def lint(path):
    doc = json.loads(path.read_text())
    return [] if str(doc.get("caption", "")).strip() else ["缺少作品说明；请按真实像素和来源填写"]
