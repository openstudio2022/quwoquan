package post

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"sort"
	"strings"

	semantic "quwoquan_service/services/content-service/generated/content/post/semantic_document"
)

var canonicalRawHTML = regexp.MustCompile(`<\s*/?\s*[A-Za-z][^>]*>`)
var canonicalHeaderKeys = []string{"assets", "canonicalDigest", "canonicalizationVersion", "dialectVersion", "losses", "offsetEncoding", "policyVersion", "requiredCapabilities", "schemaVersion", "semanticFingerprint", "sourceMap"}
var canonicalNodeKeys = []string{"attributes", "children", "diagnostics", "disposition", "inlines", "losses", "nodeId", "policyVersion", "rawSlice", "rawSliceFingerprint", "requiredCapabilities", "semanticFingerprint", "sourceAnchor"}

func canonicalJSON(value any) ([]byte, error) {
	var b bytes.Buffer
	enc := json.NewEncoder(&b)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "")
	if err := enc.Encode(value); err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(b.Bytes(), []byte("\n")), nil
}
func canonicalDigestOf(v map[string]any, excluded ...string) (string, error) {
	copy := map[string]any{}
	skip := map[string]bool{}
	for _, k := range excluded {
		skip[k] = true
	}
	for k, x := range v {
		if !skip[k] {
			copy[k] = x
		}
	}
	raw, e := canonicalJSON(copy)
	if e != nil {
		return "", e
	}
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:]), nil
}
func digestMatches(v any, actual string) bool {
	s, ok := v.(string)
	return ok && (s == actual || s == "sha256:"+actual)
}
func validateCanonicalIdentity(v map[string]any) error {
	semanticDigest, e := canonicalDigestOf(v, "semanticFingerprint", "canonicalDigest")
	if e != nil {
		return e
	}
	if !digestMatches(v["semanticFingerprint"], semanticDigest) {
		return errors.New("SEMANTIC_DOCUMENT.INVALID.SEMANTIC_FINGERPRINT")
	}
	canonical, e := canonicalDigestOf(v, "canonicalDigest")
	if e != nil {
		return e
	}
	if !digestMatches(v["canonicalDigest"], canonical) {
		return errors.New("SEMANTIC_DOCUMENT.INVALID.CANONICAL_DIGEST")
	}
	return nil
}
func semanticEnvelopeMap(envelope semantic.DocumentEnvelope) (map[string]any, error) {
	raw, e := json.Marshal(envelope)
	if e != nil {
		return nil, e
	}
	var v map[string]any
	if e = json.Unmarshal(raw, &v); e != nil {
		return nil, e
	}
	return v, nil
}
func validateCanonicalEnvelope(v map[string]any) error {
	available := map[semantic.CapabilityID]bool{}
	for id := range semantic.CapabilityRegistry {
		available[id] = true
	}
	if result := semantic.ValidateEnvelope(v, available); result.Code != semantic.ValidationOK {
		return fmt.Errorf("%s:%s", result.Code, result.Detail)
	}
	nodes, _ := v["nodes"].([]any)
	for _, raw := range nodes {
		if n, ok := raw.(map[string]any); ok && n["kind"] == "unsupportedOpaque" {
			return errors.New("SEMANTIC_DOCUMENT.UNSUPPORTED_OPAQUE.PUBLISH_FORBIDDEN")
		}
	}
	return validateCanonicalIdentity(v)
}
func exactKeys(v map[string]any, want []string) bool {
	if len(v) != len(want) {
		return false
	}
	keys := make([]string, 0, len(v))
	for k := range v {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return strings.Join(keys, "\x00") == strings.Join(want, "\x00")
}
func nodeText(n map[string]any) string {
	attrs, _ := n["attributes"].(map[string]any)
	for _, k := range []string{"plainText", "text", "caption"} {
		if s, ok := attrs[k].(string); ok && s != "" {
			return strings.ReplaceAll(strings.ReplaceAll(s, "\r\n", "\n"), "\r", "\n")
		}
	}
	return ""
}

func nodeReviewBody(n map[string]any) string {
	text := nodeText(n)
	attrs, _ := n["attributes"].(map[string]any)
	switch n["kind"] {
	case "documentTitle":
		return "# " + text
	case "heading":
		level := 2
		if raw, ok := attrs["level"].(float64); ok {
			level = int(raw)
		}
		if level < 2 {
			level = 2
		}
		if level > 6 {
			level = 6
		}
		return strings.Repeat("#", level) + " " + text
	case "paragraph":
		return text
	case "blockquote":
		return "> " + strings.ReplaceAll(text, "\n", "\n> ")
	case "codeBlock":
		return "```" + fmt.Sprint(attrs["language"]) + "\n" + text + "\n```"
	case "preformatted":
		return "    " + strings.ReplaceAll(text, "\n", "\n    ")
	case "divider":
		return "---"
	case "listItem":
		prefix := "- "
		if attrs["listKind"] == "ordered" {
			prefix = "1. "
		}
		return prefix + text
	default:
		return text
	}
}
func renderableUnsafe(text string) bool {
	lower := strings.ToLower(text)
	return regexp.MustCompile(`<\s*(script|style|iframe|object|embed|form|input|button|meta|link)(?:\s|>|/)`).MatchString(lower) || regexp.MustCompile(`\bon[a-z]+\s*=|\bsrcdoc\s*=|(?:javascript|data)\s*:`).MatchString(lower)
}
func SerializeEnvelope(envelope semantic.DocumentEnvelope) (string, error) {
	v, e := semanticEnvelopeMap(envelope)
	if e != nil {
		return "", e
	}
	return SerializeEnvelopeMap(v)
}
func SerializeEnvelopeMap(v map[string]any) (string, error) {
	var e error
	if e = validateCanonicalEnvelope(v); e != nil {
		return "", e
	}
	header := map[string]any{}
	for _, k := range canonicalHeaderKeys {
		header[k] = v[k]
	}
	h, _ := canonicalJSON(header)
	var b strings.Builder
	b.WriteString("---\n")
	b.Write(h)
	b.WriteString("\n---\n\n")
	nodesWritten := []bool{}
	for _, raw := range v["nodes"].([]any) {
		n := raw.(map[string]any)
		meta := map[string]any{}
		for _, k := range canonicalNodeKeys {
			meta[k] = n[k]
		}
		m, _ := canonicalJSON(meta)
		body := nodeReviewBody(n)
		if renderableUnsafe(body) {
			return "", errors.New("SEMANTIC_DOCUMENT.UNSAFE.RAW_HTML")
		}
		if len(nodesWritten) > 0 {
			b.WriteString("\n\n")
		}
		fmt.Fprintf(&b, ":::qwq-meta %s %s\n\n%s", n["kind"], m, body)
		nodesWritten = append(nodesWritten, true)
	}
	b.WriteString("\n")
	return b.String(), nil
}
func ParseCanonicalMarkdown(markdown string) (semantic.DocumentEnvelope, error) {
	var zero semantic.DocumentEnvelope
	if strings.Contains(markdown, "\r") || !strings.HasSuffix(markdown, "\n") {
		return zero, errors.New("SEMANTIC_DOCUMENT.INVALID.CANONICAL_LINE_ENDING")
	}
	lines := strings.Split(strings.TrimSuffix(markdown, "\n"), "\n")
	if len(lines) < 4 || lines[0] != "---" || lines[2] != "---" || lines[3] != "" {
		return zero, errors.New("SEMANTIC_DOCUMENT.INVALID.FRONTMATTER")
	}
	if len(lines) == 5 && lines[4] == "" {
		lines = lines[:4]
	}
	var header map[string]any
	if json.Unmarshal([]byte(lines[1]), &header) != nil || !exactKeys(header, canonicalHeaderKeys) {
		return zero, errors.New("SEMANTIC_DOCUMENT.INVALID.CANONICAL_FRONTMATTER")
	}
	canon, _ := canonicalJSON(header)
	if string(canon) != lines[1] {
		return zero, errors.New("SEMANTIC_DOCUMENT.INVALID.CANONICAL_FRONTMATTER")
	}
	nodes := []any{}
	for i := 4; i < len(lines); {
		if !strings.HasPrefix(lines[i], ":::qwq-meta ") {
			return zero, errors.New("SEMANTIC_DOCUMENT.INVALID.METADATA_BINDING")
		}
		rest := strings.TrimPrefix(lines[i], ":::qwq-meta ")
		at := strings.IndexByte(rest, ' ')
		if at < 1 {
			return zero, errors.New("SEMANTIC_DOCUMENT.INVALID.DIRECTIVE")
		}
		kind, payload := rest[:at], rest[at+1:]
		var meta map[string]any
		if json.Unmarshal([]byte(payload), &meta) != nil || !exactKeys(meta, canonicalNodeKeys) || i+1 >= len(lines) || lines[i+1] != "" {
			return zero, errors.New("SEMANTIC_DOCUMENT.INVALID.DIRECTIVE_ATTRIBUTE")
		}
		c, _ := canonicalJSON(meta)
		if string(c) != payload {
			return zero, errors.New("SEMANTIC_DOCUMENT.INVALID.DIRECTIVE_ATTRIBUTE")
		}
		node := map[string]any{"kind": kind}
		for k, v := range meta {
			node[k] = v
		}
		i += 2
		body := []string{}
		for i < len(lines) && !strings.HasPrefix(lines[i], ":::qwq-meta ") {
			body = append(body, lines[i])
			i++
		}
		if i < len(lines) && len(body) > 0 && body[len(body)-1] == "" {
			body = body[:len(body)-1]
		}
		text := strings.Join(body, "\n")
		if text != nodeReviewBody(node) || renderableUnsafe(text) {
			return zero, errors.New("SEMANTIC_DOCUMENT.INVALID.METADATA_BINDING")
		}
		nodes = append(nodes, node)
	}
	header["nodes"] = nodes
	if e := validateCanonicalEnvelope(header); e != nil {
		return zero, e
	}
	raw, _ := json.Marshal(header)
	if e := json.Unmarshal(raw, &zero); e != nil {
		return zero, e
	}
	out, e := SerializeEnvelope(zero)
	if e != nil || out != markdown {
		return zero, errors.New("SEMANTIC_DOCUMENT.INVALID.NON_CANONICAL_MARKDOWN")
	}
	return zero, nil
}
func SafeProjectionMap(envelope map[string]any) (string, error) {
	tags := map[string]string{"documentTitle": "h1", "heading": "heading_level", "paragraph": "p", "blockquote": "blockquote", "preformatted": "pre", "codeBlock": "code", "divider": "hr", "list": "list", "listItem": "li", "definitionList": "dl", "callout": "aside", "factBox": "aside", "factRow": "div", "table": "table", "tableCaption": "caption", "tableRow": "tr", "tableCell": "td_or_th", "groupedDirectory": "nav", "footnoteReference": "sup", "footnoteDefinition": "li", "footnoteList": "ol", "hatnote": "aside", "externalLinks": "section", "seeAlso": "section", "relatedResources": "section", "figure": "figure", "gallery": "gallery"}
	events := []any{}
	var visit func(map[string]any, int)
	visit = func(n map[string]any, depth int) {
		a, _ := n["attributes"].(map[string]any)
		links := []string{}
		assets := []string{}
		cells := []any{}
		edges := []string{}
		var scan func(any)
		scan = func(v any) {
			switch x := v.(type) {
			case map[string]any:
				if h, ok := x["href"].(string); ok && h != "" {
					links = append(links, h)
				}
				for _, k := range []string{"assetId", "figureId"} {
					if id, ok := x[k].(string); ok && id != "" {
						assets = append(assets, id)
					}
				}
				if _, ok := x["row"]; ok {
					x2 := map[string]any{}
					for _, k := range []string{"row", "column", "rowSpan", "rowspan", "columnSpan", "colspan", "scope", "sortKey"} {
						x2[k] = x[k]
					}
					cells = append(cells, x2)
				}
				for _, z := range x {
					scan(z)
				}
			case []any:
				for _, z := range x {
					scan(z)
				}
			}
		}
		scan(a)
		if n["kind"] == "footnoteReference" {
			if r, ok := a["refId"].(string); ok {
				edges = append(edges, r)
			}
		}
		sort.Strings(links)
		sort.Strings(assets)
		tag := tags[fmt.Sprint(n["kind"])]
		if tag == "" {
			tag = "section"
		}
		events = append(events, map[string]any{"order": len(events), "depth": depth, "nodeId": n["nodeId"], "kind": n["kind"], "safeTag": tag, "text": nodeText(n), "links": links, "assetIds": assets, "tableCells": cells, "footnoteEdges": edges})
		if children, ok := n["children"].([]any); ok {
			for _, c := range children {
				visit(c.(map[string]any), depth+1)
			}
		}
	}
	for _, n := range envelope["nodes"].([]any) {
		visit(n.(map[string]any), 0)
	}
	raw, e := canonicalJSON(events)
	return string(raw) + "\n", e
}
