// Package publicweb 提供 post 对象的公开 SEO HTML 读面（public-content-web-entry
// REQ-002/003/006 第一段）：正文 HTML 只由 articleMarkdown 派生，全部文本经
// html.EscapeString 转义，禁止透传原始 HTML。
package publicweb

import (
	"html"
	"regexp"
	"strings"
)

var (
	inlineMentionPattern   = regexp.MustCompile(`@\[(.+?)\]\((?:entity|tag):[A-Za-z0-9_:/-]+\)`)
	orderedItemPattern     = regexp.MustCompile(`^\d+\.\s+`)
	inlineStrongEmPattern  = regexp.MustCompile(`\*{1,3}([^*]+)\*{1,3}`)
	inlineUnderlinePattern = regexp.MustCompile(`\+\+([^+]+)\+\+`)
	inlineStrikePattern    = regexp.MustCompile(`~~([^~]+)~~`)
	inlineLinkPattern      = regexp.MustCompile(`\[([^\]]+)\]\((https?://[^)\s]+)\)`)
	// 站内相对链接（数据工程供稿 `/entity/...` 等）：实体落地页 SEO 未上线
	// 前渲染纯文本，fail-closed 不产生死链。
	inlineInternalLinkPattern = regexp.MustCompile(`\[([^\]]+)\]\(/[^)\s]*\)`)
	directiveNamePattern      = regexp.MustCompile(`^:::([A-Za-z][A-Za-z0-9_-]*)`)
	directiveCaptionPattern   = regexp.MustCompile(`caption="((?:[^"\\]|\\.)*)"`)
	directiveIDsPattern       = regexp.MustCompile(`ids="((?:[^"\\]|\\.)*)"`)
	horizontalRulePattern     = regexp.MustCompile(`^-{3,}$`)
)

// BodyAsset 是正文图片的公网渲染输入（articleAssetManifest 派生）。
type BodyAsset struct {
	URL     string
	Caption string
}

// RenderQwqMarkdownBodyHTML 将 qwq-rich-md 正文渲染为安全 SEO HTML 片段。
//
// 覆盖核心文本块：标题（H1 跳过，页面 H1 由 envelope 输出）、段落、有序/
// 无序列表、引用、代码块；`:::figure/gallery` 指令块内的 `asset://` 引用按
// [assets]（assetId → 公网 URL/caption）渲染为 `<figure><img>`，无公网 URL
// 的 asset 保持跳过（fail-closed 不猜测地址）。行内 mention 记号还原为纯
// 文本，链接记号（https/http）渲染为 `<a rel="noopener">`，样式记号还原为
// 对应语义标签。
func RenderQwqMarkdownBodyHTML(markdown string, assets map[string]BodyAsset) string {
	lines := strings.Split(strings.ReplaceAll(markdown, "\r\n", "\n"), "\n")
	index := 0
	// 跳过 frontmatter。
	if len(lines) > 0 && strings.TrimSpace(lines[0]) == "---" {
		for cursor := 1; cursor < len(lines); cursor++ {
			if strings.TrimSpace(lines[cursor]) == "---" {
				index = cursor + 1
				break
			}
		}
	}
	var b strings.Builder
	listKind := ""
	closeList := func() {
		switch listKind {
		case "ol":
			b.WriteString("</ol>")
		case "ul":
			b.WriteString("</ul>")
		}
		listKind = ""
	}
	inDirective := false
	directiveName := ""
	directiveCaption := ""
	inCode := false
	var codeLines []string
	for ; index < len(lines); index++ {
		line := strings.TrimSpace(lines[index])
		if inCode {
			if strings.HasPrefix(line, "```") {
				b.WriteString("<pre><code>" + html.EscapeString(strings.Join(codeLines, "\n")) + "</code></pre>")
				codeLines = nil
				inCode = false
				continue
			}
			codeLines = append(codeLines, lines[index])
			continue
		}
		if strings.HasPrefix(line, "```") {
			closeList()
			inCode = true
			continue
		}
		if strings.HasPrefix(line, ":::") {
			closeList()
			entering := line != ":::" && !inDirective
			if entering {
				inDirective = true
				directiveName = ""
				directiveCaption = ""
				if match := directiveNamePattern.FindStringSubmatch(line); match != nil {
					directiveName = match[1]
				}
				if match := directiveCaptionPattern.FindStringSubmatch(line); match != nil {
					directiveCaption = strings.ReplaceAll(match[1], `\"`, `"`)
				}
				if directiveName == "gallery" {
					if match := directiveIDsPattern.FindStringSubmatch(line); match != nil {
						for _, assetID := range strings.Split(match[1], ",") {
							renderBodyAsset(&b, strings.TrimSpace(assetID), directiveCaption, assets)
						}
					}
				} else if directiveName == "callout" {
					b.WriteString(`<aside class="qwq-callout">`)
				}
				continue
			}
			if inDirective && directiveName == "callout" {
				b.WriteString("</aside>")
			}
			inDirective = false
			directiveName = ""
			directiveCaption = ""
			continue
		}
		if line == "" {
			closeList()
			continue
		}
		if inDirective && strings.HasPrefix(line, "asset://") {
			renderBodyAsset(
				&b,
				strings.TrimSpace(strings.TrimPrefix(line, "asset://")),
				directiveCaption,
				assets,
			)
			continue
		}
		if inDirective && directiveName == "callout" {
			b.WriteString(`<p>` + renderInlineText(line) + `</p>`)
			continue
		}
		switch {
		case horizontalRulePattern.MatchString(line):
			closeList()
			b.WriteString("<hr>")
		case strings.HasPrefix(line, "# "):
			// 文档标题由 envelope 的 <h1> 承载，跳过避免重复 H1。
			closeList()
		case strings.HasPrefix(line, "## "):
			closeList()
			b.WriteString("<h2>" + renderInlineText(strings.TrimPrefix(line, "## ")) + "</h2>")
		case strings.HasPrefix(line, "### "):
			closeList()
			b.WriteString("<h3>" + renderInlineText(strings.TrimPrefix(line, "### ")) + "</h3>")
		case strings.HasPrefix(line, "> "):
			closeList()
			b.WriteString("<blockquote><p>" + renderInlineText(strings.TrimPrefix(line, "> ")) + "</p></blockquote>")
		case strings.HasPrefix(line, "- "):
			if listKind != "ul" {
				closeList()
				b.WriteString("<ul>")
				listKind = "ul"
			}
			b.WriteString("<li>" + renderInlineText(strings.TrimPrefix(line, "- ")) + "</li>")
		case orderedItemPattern.MatchString(line):
			if listKind != "ol" {
				closeList()
				b.WriteString("<ol>")
				listKind = "ol"
			}
			b.WriteString("<li>" + renderInlineText(orderedItemPattern.ReplaceAllString(line, "")) + "</li>")
		default:
			closeList()
			b.WriteString("<p>" + renderInlineText(line) + "</p>")
		}
	}
	closeList()
	if inCode && len(codeLines) > 0 {
		b.WriteString("<pre><code>" + html.EscapeString(strings.Join(codeLines, "\n")) + "</code></pre>")
	}
	if inDirective && directiveName == "callout" {
		b.WriteString("</aside>")
	}
	return b.String()
}

func renderBodyAsset(
	b *strings.Builder,
	assetID string,
	directiveCaption string,
	assets map[string]BodyAsset,
) {
	// 正文图片只渲染 manifest 给出公网 URL 的 asset；其余跳过。
	asset, ok := assets[assetID]
	if !ok || strings.TrimSpace(asset.URL) == "" {
		return
	}
	caption := firstNonEmpty(asset.Caption, directiveCaption)
	b.WriteString(`<figure><img src="` + html.EscapeString(asset.URL) +
		`" alt="` + html.EscapeString(caption) + `" loading="lazy" data-asset-id="` +
		html.EscapeString(assetID) + `">`)
	if caption != "" {
		b.WriteString("<figcaption>" + html.EscapeString(caption) + "</figcaption>")
	}
	b.WriteString("</figure>")
}

// renderInlineText 先转义全部文本，再把 qwq 行内记号还原为语义标签。
// 记号匹配在转义后的文本上进行（记号字符不受 HTML 转义影响）。链接只匹配
// https/http scheme（与 App 端解析白名单一致），恶意 scheme 保持字面量。
func renderInlineText(text string) string {
	escaped := html.EscapeString(inlineMentionPattern.ReplaceAllString(text, "$1"))
	escaped = inlineInternalLinkPattern.ReplaceAllString(escaped, "$1")
	escaped = inlineLinkPattern.ReplaceAllString(
		escaped,
		`<a href="$2" rel="noopener">$1</a>`,
	)
	escaped = inlineStrikePattern.ReplaceAllString(escaped, "<s>$1</s>")
	escaped = inlineUnderlinePattern.ReplaceAllString(escaped, "<u>$1</u>")
	escaped = inlineStrongEmPattern.ReplaceAllStringFunc(escaped, func(match string) string {
		inner := strings.Trim(match, "*")
		switch {
		case strings.HasPrefix(match, "***"):
			return "<strong><em>" + inner + "</em></strong>"
		case strings.HasPrefix(match, "**"):
			return "<strong>" + inner + "</strong>"
		default:
			return "<em>" + inner + "</em>"
		}
	})
	return escaped
}
