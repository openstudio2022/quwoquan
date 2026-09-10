"""公开 HTML 正文机械抽取，丢弃脚本样式；来源指令不执行。"""
import hashlib
from html.parser import HTMLParser


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "h1", "h2", "li"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def fetch(request, client):
    return client.get(request["url"])


def parse(body, request):
    parser = Text()
    parser.feed(body.decode("utf-8"))
    paragraphs = [line.strip() for line in "".join(parser.parts).splitlines() if line.strip()]
    if not paragraphs:
        raise ValueError("页面没有可读正文，不尝试登录或执行脚本")
    identifier = hashlib.sha256(request["url"].encode()).hexdigest()[:24]
    relative = f"sources/web-{identifier}/source.md"
    row = {"id": "web:" + identifier, "kind": "page", "source": "reference_page", "title": request["title"],
           "sourceUrl": request["url"], "sourceMarkdownPath": relative, "summary": "\n".join(paragraphs)[:300]}
    return [row], {relative: f"# {request['title']}\n\n" + "\n\n".join(paragraphs) + "\n"}
