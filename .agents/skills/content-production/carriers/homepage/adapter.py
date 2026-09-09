"""主页的来源结构与移动版式提示，不判断实体语义。"""
import re

HEADINGS = ("概览", "看点", "到达", "门票与开放", "季节与贴士", "历史", "参见")


def check(chosen, candidates):
    primary = [source for source in chosen["sources"] if source.get("role") == "primary"]
    if len(primary) != 1:
        raise ValueError("主页选择须点名一个主源；不是用顺序猜测")
    candidate = candidates[primary[0]["candidateId"]]
    if candidate["kind"] != "page" or candidate["source"] not in {"wikipedia", "toutiao_baike"}:
        raise ValueError("主页主源必须是百科候选")


def lint(path):
    text = path.read_text(encoding="utf-8")
    headings = re.findall(r"^## (.+)$", text, flags=re.M)
    issues = [f"未使用模板段名：{heading}" for heading in headings if heading not in HEADINGS]
    if len(text) > 800:
        issues.append("正文超过移动端 800 字目标；建议删去次要细节")
    if "概览" not in headings:
        issues.append("缺少概览；没有来源事实的其他槽位可以省略")
    for heading, body in re.findall(r"^## ([^\n]+)\n(.*?)(?=^## |\Z)", text, flags=re.M | re.S):
        if not body.strip():
            issues.append(f"空章节应省略而不是编造：{heading}")
    return issues
