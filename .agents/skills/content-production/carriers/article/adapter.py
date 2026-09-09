"""文章接受独立事实来源与任意张配图，不向 image 载体取状态。"""
import re


def check(chosen, candidates):
    if not any(candidates[source["candidateId"]]["kind"] == "page" for source in chosen["sources"]):
        raise ValueError("文章选择须包含事实底稿")


def lint(path):
    text = path.read_text(encoding="utf-8")
    issues = []
    if not text.startswith("---\n"):
        issues.append("建议在 frontmatter 声明标题、标签与创作者")
    if any(not ref.startswith("assets/") for ref in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)):
        issues.append("正文图片只能引用已取得的本对象 assets")
    return issues
