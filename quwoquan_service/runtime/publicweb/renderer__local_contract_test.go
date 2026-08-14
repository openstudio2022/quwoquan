// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#gwt-002
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#gwt-002.t2
package publicweb

import (
	"strings"
	"testing"
)

func TestRenderObjectHTMLIncludesSeoMetadata(t *testing.T) {
	doc := RenderObjectHTML("https://quwoquan.app", ObjectPage{
		ObjectType:   "content.post",
		ObjectID:     "post_1",
		Path:         "post/post_1",
		Title:        "四川露营攻略",
		Description:  "川西营地和路线建议",
		CoverURL:     "https://cdn.example/cover.jpg",
		Visibility:   "public",
		PublishedISO: "2026-06-08T12:00:00Z",
		AuthorName:   "小趣用户",
	})
	if !doc.Indexable {
		t.Fatal("public object should be indexable")
	}
	for _, want := range []string{
		`<link rel="canonical" href="https://quwoquan.app/post/post_1">`,
		`property="og:title" content="四川露营攻略"`,
		`application/ld+json`,
		`Article`,
		`打开趣我圈 App`,
	} {
		if !strings.Contains(doc.HTML, want) {
			t.Fatalf("html missing %q: %s", want, doc.HTML)
		}
	}
}

func TestRenderObjectHTMLEscapesInjectedMarkup(t *testing.T) {
	doc := RenderObjectHTML("https://quwoquan.app", ObjectPage{
		ObjectType:   "content.post",
		ObjectID:     `post_1"><script>alert(2)</script>`,
		Path:         "post/post_1",
		Title:        `<script>alert(1)</script>攻略`,
		Description:  `"><img src=x onerror=alert(3)>`,
		CoverURL:     `https://cdn.example/cover.jpg" onload="alert(4)`,
		Visibility:   "public",
		PublishedISO: "2026-06-08T12:00:00Z",
		AuthorName:   `</script><script>alert(5)</script>`,
	})
	for _, forbidden := range []string{
		"<script>alert(1)</script>",
		"<script>alert(2)</script>",
		"<img src=x onerror=alert(3)>",
		`" onload="alert(4)`,
		"<script>alert(5)</script>",
	} {
		if strings.Contains(doc.HTML, forbidden) {
			t.Fatalf("html leaked unescaped injection %q: %s", forbidden, doc.HTML)
		}
	}
	if !strings.Contains(doc.HTML, "&lt;script&gt;alert(1)&lt;/script&gt;攻略") {
		t.Fatalf("title should be escaped instead of dropped: %s", doc.HTML)
	}
}

func TestRenderObjectHTMLNoindexesPrivateObject(t *testing.T) {
	doc := RenderObjectHTML("https://quwoquan.app", ObjectPage{
		ObjectType:  "content.post",
		ObjectID:    "post_private",
		Path:        "post/post_private",
		Title:       "私密内容",
		Visibility:  "private",
		Description: "不应被索引",
	})
	if doc.Indexable {
		t.Fatal("private object must not be indexable")
	}
	if !strings.Contains(doc.HTML, `content="noindex,nofollow"`) {
		t.Fatalf("private html should include noindex: %s", doc.HTML)
	}
}

func TestRobotsAndSitemap(t *testing.T) {
	robots := RenderRobots("https://quwoquan.app/sitemap.xml")
	if !strings.Contains(robots, "Sitemap: https://quwoquan.app/sitemap.xml") {
		t.Fatalf("robots=%s", robots)
	}
	sitemap := RenderSitemap([]string{"https://quwoquan.app/post/post_1"})
	if !strings.Contains(sitemap, "<loc>https://quwoquan.app/post/post_1</loc>") {
		t.Fatalf("sitemap=%s", sitemap)
	}
}
