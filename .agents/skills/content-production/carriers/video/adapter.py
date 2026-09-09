"""视频选择保持一作品一视频；poster 由 Data acquire 派生。"""
import json


def check(chosen, candidates):
    sources = chosen["sources"]
    if len(sources) != 1 or candidates[sources[0]["candidateId"]]["kind"] != "video":
        raise ValueError("一个 video target 选择一个来源视频")
    if len(sources[0].get("assets", [])) != 1:
        raise ValueError("视频必须显式选择唯一视频资产")


def lint(path):
    document = json.loads(path.read_text())
    return [] if document.get("scriptLines") else ["脚本须基于来源描述与真实画面，不把 poster 当作完整视频证据"]
