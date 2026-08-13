package publicweb

import (
	"encoding/json"
	"html"
	"strings"
)

type ObjectPage struct {
	ObjectType   string
	ObjectID     string
	Path         string
	Title        string
	Description  string
	CoverURL     string
	SchemaType   string
	Visibility   string
	PublishedISO string
	AuthorName   string
	// BodyHTML 是调用方已完成转义/白名单过滤的安全正文 HTML 片段
	//（如 qwq-rich-md 派生的文章正文），原样注入 <article> 内。
	BodyHTML string
}

type HTMLDocument struct {
	StatusCode   int
	ContentType  string
	HTML         string
	CanonicalURL string
	Indexable    bool
}

func RenderObjectHTML(origin string, page ObjectPage) HTMLDocument {
	origin = strings.TrimRight(strings.TrimSpace(origin), "/")
	path := strings.TrimLeft(strings.TrimSpace(page.Path), "/")
	canonical := origin + "/" + path
	if !isIndexable(page.Visibility) {
		return HTMLDocument{
			StatusCode:   200,
			ContentType:  "text/html; charset=utf-8",
			CanonicalURL: canonical,
			Indexable:    false,
			HTML:         baseHTML(page, canonical, false, nil),
		}
	}
	jsonLD := map[string]any{
		"@context": "https://schema.org",
		"@type":    firstNonEmpty(page.SchemaType, schemaTypeForObject(page.ObjectType)),
		"name":     page.Title,
		"url":      canonical,
	}
	if strings.TrimSpace(page.Description) != "" {
		jsonLD["description"] = page.Description
	}
	if strings.TrimSpace(page.CoverURL) != "" {
		jsonLD["image"] = page.CoverURL
	}
	if strings.TrimSpace(page.AuthorName) != "" {
		jsonLD["author"] = map[string]any{"@type": "Person", "name": page.AuthorName}
	}
	if strings.TrimSpace(page.PublishedISO) != "" {
		jsonLD["datePublished"] = page.PublishedISO
	}
	return HTMLDocument{
		StatusCode:   200,
		ContentType:  "text/html; charset=utf-8",
		HTML:         baseHTML(page, canonical, true, jsonLD),
		CanonicalURL: canonical,
		Indexable:    true,
	}
}

func RenderRobots(sitemapURL string) string {
	return "User-agent: *\nAllow: /\nSitemap: " + strings.TrimSpace(sitemapURL) + "\n"
}

func RenderSitemap(urls []string) string {
	var b strings.Builder
	b.WriteString(`<?xml version="1.0" encoding="UTF-8"?>` + "\n")
	b.WriteString(`<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">` + "\n")
	for _, raw := range urls {
		raw = strings.TrimSpace(raw)
		if raw == "" {
			continue
		}
		b.WriteString("  <url><loc>")
		b.WriteString(html.EscapeString(raw))
		b.WriteString("</loc></url>\n")
	}
	b.WriteString("</urlset>\n")
	return b.String()
}

func baseHTML(page ObjectPage, canonical string, indexable bool, jsonLD map[string]any) string {
	title := firstNonEmpty(page.Title, page.ObjectID, "趣我圈")
	description := strings.TrimSpace(page.Description)
	robots := "index,follow"
	if !indexable {
		robots = "noindex,nofollow"
	}
	var b strings.Builder
	b.WriteString("<!doctype html><html lang=\"zh-CN\"><head>")
	b.WriteString("<meta charset=\"utf-8\">")
	b.WriteString("<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">")
	b.WriteString("<meta name=\"robots\" content=\"" + robots + "\">")
	b.WriteString("<title>" + html.EscapeString(title) + "</title>")
	if description != "" {
		b.WriteString("<meta name=\"description\" content=\"" + html.EscapeString(description) + "\">")
	}
	b.WriteString("<link rel=\"canonical\" href=\"" + html.EscapeString(canonical) + "\">")
	b.WriteString(metaProperty("og:type", ogTypeForObject(page.ObjectType)))
	b.WriteString(metaProperty("og:title", title))
	if description != "" {
		b.WriteString(metaProperty("og:description", description))
	}
	b.WriteString(metaProperty("og:url", canonical))
	if strings.TrimSpace(page.CoverURL) != "" {
		b.WriteString(metaProperty("og:image", page.CoverURL))
		b.WriteString("<meta name=\"twitter:card\" content=\"summary_large_image\">")
	} else {
		b.WriteString("<meta name=\"twitter:card\" content=\"summary\">")
	}
	if jsonLD != nil {
		raw, _ := json.Marshal(jsonLD)
		b.WriteString("<script type=\"application/ld+json\">" + html.EscapeString(string(raw)) + "</script>")
	}
	b.WriteString("</head><body>")
	b.WriteString("<main><article>")
	b.WriteString("<h1>" + html.EscapeString(title) + "</h1>")
	if description != "" {
		b.WriteString("<p>" + html.EscapeString(description) + "</p>")
	}
	if strings.TrimSpace(page.BodyHTML) != "" {
		b.WriteString(page.BodyHTML)
	}
	b.WriteString("<a href=\"/open?target_entity=" + html.EscapeString(page.ObjectType) + "&target_id=" + html.EscapeString(page.ObjectID) + "\">打开趣我圈 App</a>")
	b.WriteString("</article></main></body></html>")
	return b.String()
}

func metaProperty(key string, value string) string {
	return "<meta property=\"" + html.EscapeString(key) + "\" content=\"" + html.EscapeString(value) + "\">"
}

func isIndexable(visibility string) bool {
	return strings.TrimSpace(strings.ToLower(visibility)) == "public"
}

func schemaTypeForObject(objectType string) string {
	switch strings.TrimSpace(objectType) {
	case "post", "content.post":
		return "Article"
	case "circle", "circle.circle":
		return "Organization"
	case "user", "user.profile":
		return "ProfilePage"
	case "entity_homepage", "entity.homepage":
		return "Place"
	default:
		return "WebPage"
	}
}

func ogTypeForObject(objectType string) string {
	if schemaTypeForObject(objectType) == "Article" {
		return "article"
	}
	return "website"
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}
