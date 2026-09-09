"""从页内 JSON 提取头条百科原文，不以标题词频判实体是否正确。"""
import hashlib
import json
from urllib.parse import quote


def fetch(request, client):
    return client.get("https://www.baike.com/wiki/" + quote(request["title"], safe=""))


def node_text(node):
    if isinstance(node, list):
        return "".join(node_text(item) for item in node)
    if not isinstance(node, dict):
        return ""
    return str(node.get("text") or "") + node_text(node.get("children", []))


def parse(body, request):
    text = body.decode("utf-8")
    marker = text.find("__prefetch_doc_data__")
    start = text.find("{", marker) if marker >= 0 else -1
    if start < 0:
        raise ValueError("来源无公开结构化正文；不尝试绕过挑战页")
    data, _ = json.JSONDecoder().raw_decode(text[start:])
    content = data.get("VersionContent") or {}
    title = content.get("Title") or (data.get("DocMeta") or {}).get("Title") or request["title"]
    nodes = content.get("Content") or []
    boxes = content.get("Infobox") or []
    nodes = json.loads(nodes) if isinstance(nodes, str) else nodes
    boxes = json.loads(boxes) if isinstance(boxes, str) else boxes
    paragraphs = []
    for node in nodes:
        value = node_text(node).strip()
        if not value:
            continue
        if str(node.get("type", "")).startswith("heading"):
            value = "## " + value
        paragraphs.append(value)
    if not paragraphs:
        raise ValueError("来源正文为空")
    url = "https://www.baike.com/wiki/" + quote(request["title"], safe="")
    identifier = hashlib.sha256(url.encode()).hexdigest()[:24]
    relative = f"sources/toutiao-{identifier}/source.md"
    markdown = f"# {title}\n\n" + "\n\n".join(paragraphs) + "\n"
    if boxes:
        markdown += "\n## 信息区（原文）\n\n" + "\n".join(node_text(node) for node in boxes) + "\n"
    references = [ref.get("URL") for ref in content.get("ReferenceList", []) if ref.get("URL")]
    if references:
        markdown += "\n## 来源列出的参考\n\n" + "\n".join(references) + "\n"
    row = {"id": "toutiao:" + identifier, "kind": "page", "source": "toutiao_baike", "sourceUrl": url,
           "title": title, "sourceMarkdownPath": relative, "summary": paragraphs[0][:300]}
    if data.get("VersionNumber") is not None:
        row["revision"] = data["VersionNumber"]
    return [row], {relative: markdown}
