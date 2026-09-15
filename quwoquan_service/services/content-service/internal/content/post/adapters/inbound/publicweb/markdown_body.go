// Package publicweb 提供 post 对象的公开 SEO HTML 安全投影。
package publicweb

import (
	"errors"
	"fmt"
	"html"
	"regexp"
	"strconv"
	"strings"

	semantic "quwoquan_service/services/content-service/generated/content/post/semantic_document"
	postapplication "quwoquan_service/services/content-service/internal/content/post/application"
)

var (
	inlineMentionPattern      = regexp.MustCompile(`@\[(.+?)\]\((?:entity|tag):[A-Za-z0-9_:/-]+\)`)
	inlineStrongEmPattern     = regexp.MustCompile(`\*{1,3}([^*]+)\*{1,3}`)
	inlineUnderlinePattern    = regexp.MustCompile(`\+\+([^+]+)\+\+`)
	inlineStrikePattern       = regexp.MustCompile(`~~([^~]+)~~`)
	inlineCodePattern         = regexp.MustCompile("`([^`]+)`")
	inlineLinkPattern         = regexp.MustCompile(`\[([^\]]+)\]\((https?://[^)\s]+)\)`)
	inlineInternalLinkPattern = regexp.MustCompile(`\[([^\]]+)\]\((#[A-Za-z0-9_-]+|/[^)\s]*)\)`)
	inlineFootnotePattern     = regexp.MustCompile(`\[\^([A-Za-z0-9_-]+)\]`)
	orderedItemPattern        = regexp.MustCompile(`^\d+\.\s+`)
	directiveNamePattern      = regexp.MustCompile(`^:::([A-Za-z][A-Za-z0-9_-]*)`)
	directiveCaptionPattern   = regexp.MustCompile(`caption="((?:[^"\\]|\\.)*)"`)
	directiveIDsPattern       = regexp.MustCompile(`ids="((?:[^"\\]|\\.)*)"`)
	directoryGroupPattern     = regexp.MustCompile(`^group:([A-Za-z0-9_-]+)\s+label="([^"]+)"$`)
	directoryEntryPattern     = regexp.MustCompile(`^- \[([^\]]+)\]\(#([A-Za-z0-9_-]+)\)$`)
	footnoteDefinitionPattern = regexp.MustCompile(`^\[\^([A-Za-z0-9_-]+)\]:\s*(.+)$`)
	horizontalRulePattern     = regexp.MustCompile(`^-{3,}$`)
	canonicalDigestPattern    = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
)

// BodyAsset 是正文图片的公网渲染输入。
type BodyAsset struct{ URL, Caption string }

// RenderCanonicalUnavailableMarkdownBodyHTML 仅在 canonical envelope 不可用时为 articleMarkdown wire 提供安全、
// 只读的 HTML 投影。它不构造或冒充 canonical semantic envelope；未知结构与
// raw HTML 均拒绝展示。

// RenderCanonicalMarkdownBodyHTML strictly parses canonical Markdown before safe projection.
// Canonical-unavailable Markdown is exclusively owned by RenderCanonicalUnavailableMarkdownBodyHTML.
func RenderCanonicalMarkdownBodyHTML(markdown string, available map[semantic.CapabilityID]bool, assets map[string]BodyAsset) (string, error) {
	doc, err := postapplication.ParseCanonicalMarkdown(markdown)
	if err != nil {
		return "", err
	}
	return RenderSemanticDocumentBodyHTML(doc, available, assets)
}

func RenderCanonicalUnavailableMarkdownBodyHTML(markdown, dialect string, assets map[string]BodyAsset) (string, error) {
	if strings.TrimSpace(dialect) == "" {
		return "", errors.New("SEMANTIC_DOCUMENT.INCOMPATIBLE.DIALECT_MISSING")
	}
	if strings.TrimSpace(dialect) != "qwq-rich-md" {
		return "", fmt.Errorf("SEMANTIC_DOCUMENT.INCOMPATIBLE.DIALECT: %s", dialect)
	}
	nodes, err := parseCanonicalUnavailableMarkdown(markdown)
	if err != nil {
		return "", err
	}
	return renderSemanticNodes(nodes, assets)
}

// RenderSemanticDocumentBodyHTML 消费 canonical semantic AST wire 对应的强类型
// envelope。调用者显式提供当前 consumer 能力；版本、offset、capability 或节点
// 闭集不兼容时不产生部分 HTML。
func RenderSemanticDocumentBodyHTML(doc semantic.DocumentEnvelope, available map[semantic.CapabilityID]bool, assets map[string]BodyAsset) (string, error) {
	if !canonicalDigestPattern.MatchString(strings.TrimSpace(doc.SemanticFingerprint)) {
		return "", errors.New("SEMANTIC_DOCUMENT.INVALID.SEMANTIC_FINGERPRINT")
	}
	if !canonicalDigestPattern.MatchString(strings.TrimSpace(doc.CanonicalDigest)) {
		return "", errors.New("SEMANTIC_DOCUMENT.INVALID.CANONICAL_DIGEST")
	}
	if result := semantic.ValidateEnvelope(envelopeFields(doc), available); result.Code != semantic.ValidationOK {
		return "", fmt.Errorf("%s: %s", result.Code, result.Detail)
	}
	return renderSemanticNodes(doc.Nodes, assets)
}

func parseCanonicalUnavailableMarkdown(markdown string) ([]semantic.SemanticNode, error) {
	lines := strings.Split(strings.ReplaceAll(markdown, "\r\n", "\n"), "\n")
	index := 0
	if len(lines) > 0 && strings.TrimSpace(lines[0]) == "---" {
		closed := false
		for i := 1; i < len(lines); i++ {
			if strings.TrimSpace(lines[i]) == "---" {
				index = i + 1
				closed = true
				break
			}
		}
		if !closed {
			return nil, errors.New("SEMANTIC_DOCUMENT.INVALID.FRONTMATTER")
		}
	}
	nodes := []semantic.SemanticNode{}
	for index < len(lines) {
		line := strings.TrimSpace(lines[index])
		if line == "" {
			index++
			continue
		}
		if strings.Contains(line, "<") || strings.Contains(line, ">") && !strings.HasPrefix(line, "> ") {
			return nil, errors.New("SEMANTIC_DOCUMENT.UNSAFE.RAW_HTML")
		}
		switch {
		case strings.HasPrefix(line, "```"):
			start := index
			index++
			code := []string{}
			for index < len(lines) && !strings.HasPrefix(strings.TrimSpace(lines[index]), "```") {
				code = append(code, lines[index])
				index++
			}
			if index >= len(lines) {
				return nil, errors.New("SEMANTIC_DOCUMENT.INVALID.UNCLOSED_CODE")
			}
			nodes = append(nodes, newNode(semantic.NodeKindCodeBlock, strings.Join(code, "\n"), nil, start))
			index++
		case strings.HasPrefix(line, ":::"):
			nameMatch := directiveNamePattern.FindStringSubmatch(line)
			if nameMatch == nil {
				return nil, errors.New("SEMANTIC_DOCUMENT.INVALID.DIRECTIVE")
			}
			name := nameMatch[1]
			start := index
			block := []string{}
			index++
			for index < len(lines) && strings.TrimSpace(lines[index]) != ":::" {
				block = append(block, strings.TrimSpace(lines[index]))
				index++
			}
			if index >= len(lines) {
				return nil, fmt.Errorf("SEMANTIC_DOCUMENT.INVALID.UNCLOSED_DIRECTIVE: %s", name)
			}
			n, err := adaptDirective(name, line, block, start)
			if err != nil {
				return nil, err
			}
			nodes = append(nodes, n...)
			index++
		case isTableStart(lines, index):
			n, next, err := adaptTable(lines, index)
			if err != nil {
				return nil, err
			}
			nodes = append(nodes, n)
			index = next
		case strings.HasPrefix(line, "# "):
			nodes = append(nodes, newNode(semantic.NodeKindDocumentTitle, strings.TrimSpace(line[2:]), map[string]any{"level": 1}, index))
			index++
		case strings.HasPrefix(line, "## ") || strings.HasPrefix(line, "### "):
			level := 2
			prefix := "## "
			if strings.HasPrefix(line, "### ") {
				level = 3
				prefix = "### "
			}
			nodes = append(nodes, newNode(semantic.NodeKindHeading, strings.TrimSpace(strings.TrimPrefix(line, prefix)), map[string]any{"level": level}, index))
			index++
		case horizontalRulePattern.MatchString(line):
			nodes = append(nodes, newNode(semantic.NodeKindDivider, "", nil, index))
			index++
		case strings.HasPrefix(line, "> "):
			nodes = append(nodes, newNode(semantic.NodeKindBlockquote, strings.TrimSpace(line[2:]), nil, index))
			index++
		case strings.HasPrefix(line, "- ") || orderedItemPattern.MatchString(line):
			ordered := orderedItemPattern.MatchString(line)
			items := []semantic.SemanticNode{}
			start := index
			for index < len(lines) {
				current := strings.TrimSpace(lines[index])
				same := orderedItemPattern.MatchString(current)
				if (!ordered && !strings.HasPrefix(current, "- ")) || same != ordered {
					break
				}
				text := strings.TrimSpace(strings.TrimPrefix(current, "- "))
				if ordered {
					text = strings.TrimSpace(orderedItemPattern.ReplaceAllString(current, ""))
				}
				items = append(items, newNode(semantic.NodeKindListItem, text, nil, index))
				index++
			}
			n := newNode(semantic.NodeKindList, "", map[string]any{"ordered": ordered}, start)
			n.Children = items
			nodes = append(nodes, n)
		case footnoteDefinitionPattern.MatchString(line):
			m := footnoteDefinitionPattern.FindStringSubmatch(line)
			nodes = append(nodes, newNode(semantic.NodeKindFootnoteDefinition, m[2], map[string]any{"identifier": m[1]}, index))
			index++
		case index+1 < len(lines) && strings.HasPrefix(strings.TrimSpace(lines[index+1]), ": "):
			term := line
			definition := strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(lines[index+1]), ": "))
			n := newNode(semantic.NodeKindDefinitionList, "", nil, index)
			n.Children = []semantic.SemanticNode{newNode(semantic.NodeKindFactRow, "", map[string]any{"term": term, "definition": definition}, index)}
			nodes = append(nodes, n)
			index += 2
		default:
			nodes = append(nodes, newNode(semantic.NodeKindParagraph, line, nil, index))
			index++
		}
	}
	return nodes, nil
}

func adaptDirective(name, header string, body []string, line int) ([]semantic.SemanticNode, error) {
	caption := ""
	if m := directiveCaptionPattern.FindStringSubmatch(header); m != nil {
		caption = strings.ReplaceAll(m[1], `\"`, `"`)
	}
	switch name {
	case "figure":
		if len(body) != 1 || !strings.HasPrefix(body[0], "asset://") {
			return nil, errors.New("SEMANTIC_DOCUMENT.INVALID.FIGURE")
		}
		return []semantic.SemanticNode{newNode(semantic.NodeKindFigure, "", map[string]any{"assetId": strings.TrimSpace(strings.TrimPrefix(body[0], "asset://")), "caption": caption}, line)}, nil
	case "gallery":
		m := directiveIDsPattern.FindStringSubmatch(header)
		if m == nil {
			return nil, errors.New("SEMANTIC_DOCUMENT.INVALID.GALLERY")
		}
		result := []semantic.SemanticNode{}
		for _, id := range strings.Split(m[1], ",") {
			result = append(result, newNode(semantic.NodeKindFigure, "", map[string]any{"assetId": strings.TrimSpace(id), "caption": caption}, line))
		}
		return result, nil
	case "callout":
		n := newNode(semantic.NodeKindCallout, "", nil, line)
		for i, text := range body {
			if text != "" {
				n.Children = append(n.Children, newNode(semantic.NodeKindParagraph, text, nil, line+i+1))
			}
		}
		return []semantic.SemanticNode{n}, nil
	case "align":
		result := []semantic.SemanticNode{}
		for i, text := range body {
			if text != "" {
				result = append(result, newNode(semantic.NodeKindParagraph, text, map[string]any{"alignment": "center"}, line+i+1))
			}
		}
		return result, nil
	case "directory":
		groups := []map[string]any{}
		var current map[string]any
		for _, text := range body {
			if m := directoryGroupPattern.FindStringSubmatch(text); m != nil {
				current = map[string]any{"groupId": m[1], "label": m[2], "entries": []map[string]any{}}
				groups = append(groups, current)
				continue
			}
			if m := directoryEntryPattern.FindStringSubmatch(text); m != nil && current != nil {
				entries := current["entries"].([]map[string]any)
				current["entries"] = append(entries, map[string]any{"label": m[1], "targetNodeId": m[2], "level": 2})
				continue
			}
			return nil, fmt.Errorf("SEMANTIC_DOCUMENT.INVALID.GROUPED_DIRECTORY: %s", text)
		}
		return []semantic.SemanticNode{newNode(semantic.NodeKindGroupedDirectory, "", map[string]any{"groups": groups}, line)}, nil
	default:
		return nil, fmt.Errorf("SEMANTIC_DOCUMENT.UNSUPPORTED.NODE: %s", name)
	}
}

func isTableStart(lines []string, index int) bool {
	if index+1 >= len(lines) || !strings.HasPrefix(strings.TrimSpace(lines[index]), "|") {
		return false
	}
	sep := strings.TrimSpace(lines[index+1])
	if !strings.HasPrefix(sep, "|") {
		return false
	}
	for _, c := range splitTableRow(sep) {
		v := strings.Trim(strings.TrimSpace(c), ":")
		if len(v) < 3 || strings.Trim(v, "-") != "" {
			return false
		}
	}
	return true
}
func splitTableRow(line string) []string {
	line = strings.TrimSpace(line)
	line = strings.TrimPrefix(line, "|")
	line = strings.TrimSuffix(line, "|")
	parts := strings.Split(line, "|")
	for i := range parts {
		parts[i] = strings.TrimSpace(parts[i])
	}
	return parts
}
func adaptTable(lines []string, index int) (semantic.SemanticNode, int, error) {
	headers := splitTableRow(lines[index])
	aligns := splitTableRow(lines[index+1])
	if len(headers) != len(aligns) {
		return semantic.SemanticNode{}, index, errors.New("SEMANTIC_DOCUMENT.INVALID.TABLE_GRID")
	}
	rows := []semantic.SemanticNode{}
	rowValues := [][]string{headers}
	next := index + 2
	for next < len(lines) && strings.HasPrefix(strings.TrimSpace(lines[next]), "|") {
		rowValues = append(rowValues, splitTableRow(lines[next]))
		next++
	}
	for r, values := range rowValues {
		if len(values) != len(headers) {
			return semantic.SemanticNode{}, index, errors.New("SEMANTIC_DOCUMENT.INVALID.TABLE_GRID")
		}
		row := newNode(semantic.NodeKindTableRow, "", map[string]any{"row": r}, index+r)
		for c, text := range values {
			alignment := "start"
			marker := aligns[c]
			if strings.HasSuffix(marker, ":") {
				alignment = "end"
			}
			if strings.HasPrefix(marker, ":") && strings.HasSuffix(marker, ":") {
				alignment = "center"
			}
			row.Children = append(row.Children, newNode(semantic.NodeKindTableCell, text, map[string]any{"row": r, "column": c, "rowSpan": 1, "columnSpan": 1, "header": r == 0, "alignment": alignment}, index+r))
		}
		rows = append(rows, row)
	}
	n := newNode(semantic.NodeKindTable, "", map[string]any{"rowCount": len(rows), "columnCount": len(headers)}, index)
	n.Children = rows
	return n, next, nil
}

func newNode(kind semantic.NodeKind, text string, attrs map[string]any, line int) semantic.SemanticNode {
	if attrs == nil {
		attrs = map[string]any{}
	}
	if text != "" {
		attrs["text"] = text
	}
	return semantic.SemanticNode{Kind: kind, Attributes: attrs}
}
func envelopeFields(doc semantic.DocumentEnvelope) map[string]any {
	nodes := make([]any, len(doc.Nodes))
	for i, n := range doc.Nodes {
		nodes[i] = nodeFields(n)
	}
	caps := make([]string, len(doc.RequiredCapabilities))
	for i, c := range doc.RequiredCapabilities {
		caps[i] = string(c)
	}
	return map[string]any{"schemaVersion": doc.SchemaVersion, "dialectVersion": doc.DialectVersion, "canonicalizationVersion": doc.CanonicalizationVersion, "offsetEncoding": doc.OffsetEncoding, "nodes": nodes, "requiredCapabilities": caps, "assets": map[string]any{}, "sourceMap": map[string]any{}, "policyVersion": doc.PolicyVersion, "losses": []any{}, "semanticFingerprint": doc.SemanticFingerprint, "canonicalDigest": doc.CanonicalDigest}
}
func nodeFields(n semantic.SemanticNode) map[string]any {
	caps := make([]string, len(n.RequiredCapabilities))
	for i, c := range n.RequiredCapabilities {
		caps[i] = string(c)
	}
	m := map[string]any{"kind": string(n.Kind), "disposition": string(n.Disposition), "requiredCapabilities": caps}
	if len(n.Inlines) > 0 {
		items := make([]any, len(n.Inlines))
		for i, v := range n.Inlines {
			items[i] = map[string]any{"kind": string(v.Kind), "start": v.Start, "end": v.End}
		}
		m["inlines"] = items
	}
	return m
}

func renderSemanticNodes(nodes []semantic.SemanticNode, assets map[string]BodyAsset) (string, error) {
	var b strings.Builder
	for _, n := range nodes {
		if err := renderSemanticNode(&b, n, assets); err != nil {
			return "", err
		}
	}
	return b.String(), nil
}
func renderSemanticNode(b *strings.Builder, n semantic.SemanticNode, assets map[string]BodyAsset) error {
	descriptor, ok := semantic.NodeRegistry[n.Kind]
	if !ok {
		return fmt.Errorf("SEMANTIC_DOCUMENT.UNSUPPORTED.NODE: %s", n.Kind)
	}
	if descriptor.Status != "formal" {
		return fmt.Errorf("SEMANTIC_DOCUMENT.EXPERIMENTAL.PUBLISH_FORBIDDEN: %s", n.Kind)
	}
	text, _ := n.Attributes["text"].(string)
	switch n.Kind {
	case semantic.NodeKindDocumentTitle:
		return nil
	case semantic.NodeKindParagraph:
		b.WriteString("<p>" + renderInlineText(text) + "</p>")
	case semantic.NodeKindHeading:
		level := asInt(n.Attributes["level"], 2)
		if level < 2 || level > 6 {
			return errors.New("SEMANTIC_DOCUMENT.INVALID.HEADING_LEVEL")
		}
		b.WriteString("<h" + strconv.Itoa(level) + ">" + renderInlineText(text) + "</h" + strconv.Itoa(level) + ">")
	case semantic.NodeKindDivider:
		b.WriteString("<hr>")
	case semantic.NodeKindBlockquote:
		b.WriteString("<blockquote><p>" + renderInlineText(text) + "</p></blockquote>")
	case semantic.NodeKindCodeBlock, semantic.NodeKindPreformatted:
		b.WriteString("<pre><code>" + html.EscapeString(text) + "</code></pre>")
	case semantic.NodeKindVerse:
		b.WriteString("<div class=\"qwq-verse\">" + renderInlineText(text) + "</div>")
	case semantic.NodeKindList:
		tag := "ul"
		if ordered, _ := n.Attributes["ordered"].(bool); ordered {
			tag = "ol"
		}
		b.WriteString("<" + tag + ">")
		for _, child := range n.Children {
			if child.Kind != semantic.NodeKindListItem {
				return errors.New("SEMANTIC_DOCUMENT.INVALID.LIST_CHILD")
			}
			b.WriteString("<li>" + renderInlineText(child.Attributes["text"].(string)) + "</li>")
		}
		b.WriteString("</" + tag + ">")
	case semantic.NodeKindCallout:
		b.WriteString(`<aside class="qwq-callout">`)
		for _, child := range n.Children {
			if err := renderSemanticNode(b, child, assets); err != nil {
				return err
			}
		}
		b.WriteString("</aside>")
	case semantic.NodeKindFigure:
		id, _ := n.Attributes["assetId"].(string)
		caption, _ := n.Attributes["caption"].(string)
		renderBodyAsset(b, id, caption, assets)
	case semantic.NodeKindDefinitionList:
		b.WriteString("<dl>")
		for _, row := range n.Children {
			term, _ := row.Attributes["term"].(string)
			definition, _ := row.Attributes["definition"].(string)
			b.WriteString("<dt>" + renderInlineText(term) + "</dt><dd>" + renderInlineText(definition) + "</dd>")
		}
		b.WriteString("</dl>")
	case semantic.NodeKindFootnoteDefinition:
		id, _ := n.Attributes["identifier"].(string)
		b.WriteString(`<aside class="qwq-footnote" id="fn-` + html.EscapeString(id) + `"><p>` + renderInlineText(text) + "</p></aside>")
	case semantic.NodeKindGroupedDirectory:
		groups, ok := n.Attributes["groups"].([]map[string]any)
		if !ok {
			return errors.New("SEMANTIC_DOCUMENT.INVALID.GROUPED_DIRECTORY")
		}
		b.WriteString(`<nav class="qwq-directory">`)
		for _, g := range groups {
			b.WriteString("<section><h2>" + html.EscapeString(fmt.Sprint(g["label"])) + "</h2><ul>")
			entries, _ := g["entries"].([]map[string]any)
			for _, e := range entries {
				target := fmt.Sprint(e["targetNodeId"])
				if !regexp.MustCompile(`^[A-Za-z0-9_-]+$`).MatchString(target) {
					return errors.New("SEMANTIC_DOCUMENT.INVALID.DIRECTORY_TARGET")
				}
				b.WriteString(`<li><a href="#` + target + `">` + html.EscapeString(fmt.Sprint(e["label"])) + "</a></li>")
			}
			b.WriteString("</ul></section>")
		}
		b.WriteString("</nav>")
	case semantic.NodeKindTable:
		b.WriteString("<table>")
		for _, row := range n.Children {
			b.WriteString("<tr>")
			for _, cell := range row.Children {
				tag := "td"
				if header, _ := cell.Attributes["header"].(bool); header {
					tag = "th"
				}
				b.WriteString("<" + tag)
				if align := fmt.Sprint(cell.Attributes["alignment"]); align == "center" || align == "end" {
					b.WriteString(` class="align-` + align + `"`)
				}
				b.WriteString(">" + renderInlineText(fmt.Sprint(cell.Attributes["text"])) + "</" + tag + ">")
			}
			b.WriteString("</tr>")
		}
		b.WriteString("</table>")
	case semantic.NodeKindUnsupportedOpaque:
		b.WriteString(`<pre class="qwq-unsupported">` + html.EscapeString(n.RawSlice) + "</pre>")
	default:
		return fmt.Errorf("SEMANTIC_DOCUMENT.UNSUPPORTED.PROJECTION: %s", n.Kind)
	}
	return nil
}
func asInt(v any, fallback int) int {
	switch x := v.(type) {
	case int:
		return x
	case int64:
		return int(x)
	}
	return fallback
}
func renderBodyAsset(b *strings.Builder, assetID, directiveCaption string, assets map[string]BodyAsset) {
	asset, ok := assets[assetID]
	if !ok || strings.TrimSpace(asset.URL) == "" {
		return
	}
	caption := firstNonEmpty(asset.Caption, directiveCaption)
	b.WriteString(`<figure><img src="` + html.EscapeString(asset.URL) + `" alt="` + html.EscapeString(caption) + `" loading="lazy" data-asset-id="` + html.EscapeString(assetID) + `">`)
	if caption != "" {
		b.WriteString("<figcaption>" + html.EscapeString(caption) + "</figcaption>")
	}
	b.WriteString("</figure>")
}
func renderInlineText(text string) string {
	escaped := html.EscapeString(inlineMentionPattern.ReplaceAllString(text, "$1"))
	escaped = inlineInternalLinkPattern.ReplaceAllString(escaped, "$1")
	escaped = inlineLinkPattern.ReplaceAllString(escaped, `<a href="$2" rel="noopener">$1</a>`)
	escaped = inlineFootnotePattern.ReplaceAllString(escaped, `<a class="qwq-footnote-ref" href="#fn-$1">[$1]</a>`)
	escaped = inlineCodePattern.ReplaceAllString(escaped, "<code>$1</code>")
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
