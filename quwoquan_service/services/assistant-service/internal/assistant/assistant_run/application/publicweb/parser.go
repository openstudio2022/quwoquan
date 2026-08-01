package publicweb

import (
	"bytes"
	"errors"
	"mime"
	"net/url"
	"strings"
	"unicode"

	"golang.org/x/net/html"
)

var ErrUnsupportedDocument = errors.New("unsupported public web document")

type ParsedLink struct {
	Title string
	URL   string
}

type ParsedDocument struct {
	Title string
	Text  string
	Links []ParsedLink
}

type DocumentParser struct {
	MaxLinks          int
	MaxExtractedRunes int
}

func DefaultDocumentParser() DocumentParser {
	return DocumentParser{MaxLinks: 128, MaxExtractedRunes: 200_000}
}

func (p DocumentParser) Parse(
	baseURL string,
	contentType string,
	body []byte,
) (ParsedDocument, error) {
	mediaType, _, err := mime.ParseMediaType(contentType)
	if err != nil {
		return ParsedDocument{}, ErrUnsupportedDocument
	}
	switch strings.ToLower(mediaType) {
	case "text/plain":
		return ParsedDocument{Text: limitRunes(normalizeText(string(body)), p.MaxExtractedRunes)}, nil
	case "text/html", "application/xhtml+xml":
		return p.parseHTML(baseURL, body)
	default:
		return ParsedDocument{}, ErrUnsupportedDocument
	}
}

func (p DocumentParser) parseHTML(baseURL string, body []byte) (ParsedDocument, error) {
	base, err := url.Parse(baseURL)
	if err != nil {
		return ParsedDocument{}, ErrUnsupportedDocument
	}
	root, err := html.Parse(bytes.NewReader(body))
	if err != nil {
		return ParsedDocument{}, ErrUnsupportedDocument
	}
	var textParts []string
	var titleParts []string
	links := make([]ParsedLink, 0, p.MaxLinks)
	var walk func(*html.Node, bool, bool)
	walk = func(node *html.Node, hidden bool, inTitle bool) {
		if node.Type == html.ElementNode {
			tag := strings.ToLower(node.Data)
			hidden = hidden || tag == "script" || tag == "style" || tag == "noscript" || tag == "template"
			inTitle = inTitle || tag == "title"
			if !hidden && tag == "a" && len(links) < p.MaxLinks {
				if link, ok := parseAnchor(base, node); ok {
					links = append(links, link)
				}
			}
		}
		if node.Type == html.TextNode && !hidden {
			value := normalizeText(node.Data)
			if value != "" {
				textParts = append(textParts, value)
				if inTitle {
					titleParts = append(titleParts, value)
				}
			}
		}
		for child := node.FirstChild; child != nil; child = child.NextSibling {
			walk(child, hidden, inTitle)
		}
	}
	walk(root, false, false)
	return ParsedDocument{
		Title: limitRunes(strings.Join(titleParts, " "), 512),
		Text:  limitRunes(strings.Join(textParts, "\n"), p.MaxExtractedRunes),
		Links: deduplicateLinks(links),
	}, nil
}

func parseAnchor(base *url.URL, node *html.Node) (ParsedLink, bool) {
	var raw string
	for _, attribute := range node.Attr {
		if strings.EqualFold(attribute.Key, "href") {
			raw = strings.TrimSpace(attribute.Val)
			break
		}
	}
	if raw == "" {
		return ParsedLink{}, false
	}
	reference, err := url.Parse(raw)
	if err != nil {
		return ParsedLink{}, false
	}
	resolved := base.ResolveReference(reference)
	if !strings.EqualFold(resolved.Scheme, "https") || resolved.Hostname() == "" || resolved.User != nil {
		return ParsedLink{}, false
	}
	resolved.Fragment = ""
	return ParsedLink{Title: anchorText(node), URL: resolved.String()}, true
}

func anchorText(node *html.Node) string {
	var parts []string
	var walk func(*html.Node)
	walk = func(current *html.Node) {
		if current.Type == html.TextNode {
			if value := normalizeText(current.Data); value != "" {
				parts = append(parts, value)
			}
		}
		for child := current.FirstChild; child != nil; child = child.NextSibling {
			walk(child)
		}
	}
	walk(node)
	return limitRunes(strings.Join(parts, " "), 512)
}

func normalizeText(value string) string {
	return strings.Join(strings.FieldsFunc(value, unicode.IsSpace), " ")
}

func limitRunes(value string, limit int) string {
	if limit <= 0 {
		return ""
	}
	runes := []rune(value)
	if len(runes) <= limit {
		return value
	}
	return string(runes[:limit])
}

func deduplicateLinks(values []ParsedLink) []ParsedLink {
	seen := make(map[string]struct{}, len(values))
	result := make([]ParsedLink, 0, len(values))
	for _, value := range values {
		if _, ok := seen[value.URL]; ok {
			continue
		}
		seen[value.URL] = struct{}{}
		result = append(result, value)
	}
	return result
}
