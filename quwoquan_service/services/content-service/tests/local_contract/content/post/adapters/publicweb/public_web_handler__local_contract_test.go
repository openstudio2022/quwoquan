// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#req-002
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#req-003
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#req-004
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#req-006
package publicweb_test

import (
	"context"
	"errors"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	publicweb "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/publicweb"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type fixedPostReader struct {
	details map[string]postports.PostDetailSlice
}

func (r fixedPostReader) GetPost(
	_ context.Context,
	query postports.PostDetailQuery,
) (postports.PostDetailSlice, error) {
	detail, ok := r.details[string(query.PostID())]
	if !ok {
		return postports.PostDetailSlice{}, errors.New("not found")
	}
	return detail, nil
}

type fixedSitemapLister struct {
	ids []string
	err error
}

func (l fixedSitemapLister) ListPublicPostIDs(
	_ context.Context,
	_ int,
) ([]string, error) {
	return l.ids, l.err
}

func publicArticleDetail() postports.PostDetailSlice {
	return postports.PostDetailSlice{
		PostID:            postports.NewPostID("post-web-1"),
		Title:             "黄龙秋色两日路线",
		Summary:           "从五彩池到雪宝顶的徒步摄影路线。",
		CoverURL:          "https://cdn.example.test/cover.webp",
		AuthorDisplayName: "山野摄影师",
		ArticleMarkdown: "---\n" +
			"title: 黄龙秋色两日路线\n" +
			"markdownDialect: qwq-rich-md\n" +
			"---\n\n" +
			"# 黄龙秋色两日路线\n\n" +
			"清晨从**五彩池**出发，沿栈道向上。\n\n" +
			"## 行程安排\n\n" +
			"1. 第一天：五彩池\n" +
			"2. 第二天：雪宝顶\n\n" +
			"> 高原徒步注意保暖。\n\n" +
			":::figure id=\"asset-1\" layout=\"fullWidth\" caption=\"五彩池\"\n" +
			"asset://asset-1\n" +
			":::\n",
		Status:      postports.PostStatus("published"),
		Visibility:  postports.PostVisibility("public"),
		PublishedAt: time.Date(2026, 8, 10, 8, 0, 0, 0, time.UTC),
	}
}

func newHandler(t *testing.T, details map[string]postports.PostDetailSlice, lister publicweb.SitemapPostLister) *publicweb.Handler {
	t.Helper()
	return publicweb.NewHandler(
		"https://web.example.test",
		"https://cdn.example.test",
		fixedPostReader{details: details},
		lister,
	)
}

func TestPublicPostHTMLRendersEnvelopeAndArticleBody(t *testing.T) {
	handler := newHandler(t, map[string]postports.PostDetailSlice{
		"post-web-1": publicArticleDetail(),
	}, fixedSitemapLister{})

	recorder := httptest.NewRecorder()
	request := httptest.NewRequest("GET", "/public-web/post/post-web-1", nil)
	handler.Routes().ServeHTTP(recorder, request)

	if recorder.Code != 200 {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	if contentType := recorder.Header().Get("Content-Type"); !strings.Contains(contentType, "text/html") {
		t.Fatalf("content type=%q", contentType)
	}
	html := recorder.Body.String()
	assertContains(t, html, `<link rel="canonical" href="https://web.example.test/post/post-web-1">`)
	assertContains(t, html, `<meta name="robots" content="index,follow">`)
	assertContains(t, html, `og:title`)
	assertContains(t, html, `application/ld+json`)
	assertContains(t, html, "<h1>黄龙秋色两日路线</h1>")
	// 正文由 articleMarkdown 派生：行内样式、列表、引用均为语义标签。
	assertContains(t, html, "<strong>五彩池</strong>")
	assertContains(t, html, "<h2>行程安排</h2>")
	assertContains(t, html, "<ol><li>第一天：五彩池</li><li>第二天：雪宝顶</li></ol>")
	assertContains(t, html, "<blockquote><p>高原徒步注意保暖。</p></blockquote>")
	// asset:// 引用不得泄漏到 HTML。
	if strings.Contains(html, "asset://") {
		t.Fatalf("asset reference leaked: %s", html)
	}
}

func TestPublicPostHTMLFailsClosedForPrivateOrMissing(t *testing.T) {
	private := publicArticleDetail()
	private.Visibility = postports.PostVisibility("private")
	pending := publicArticleDetail()
	pending.Status = postports.PostStatus("pending_review")
	handler := newHandler(t, map[string]postports.PostDetailSlice{
		"post-private": private,
		"post-pending": pending,
	}, fixedSitemapLister{})

	for _, path := range []string{
		"/public-web/post/post-private",
		"/public-web/post/post-pending",
		"/public-web/post/post-missing",
	} {
		recorder := httptest.NewRecorder()
		handler.Routes().ServeHTTP(recorder, httptest.NewRequest("GET", path, nil))
		if recorder.Code != 404 {
			t.Fatalf("path=%s status=%d（非公开对象必须 404 不泄露存在性）", path, recorder.Code)
		}
		assertContains(t, recorder.Body.String(), "noindex")
	}
}

func TestPublicPostHTMLEscapesUntrustedText(t *testing.T) {
	hostile := publicArticleDetail()
	hostile.ArticleMarkdown = ""
	hostile.Title = `<script>alert(1)</script>`
	hostile.Body = "第一段 <img src=x onerror=alert(1)>\n第二段"
	handler := newHandler(t, map[string]postports.PostDetailSlice{
		"post-web-1": hostile,
	}, fixedSitemapLister{})

	recorder := httptest.NewRecorder()
	handler.Routes().ServeHTTP(recorder, httptest.NewRequest("GET", "/public-web/post/post-web-1", nil))

	html := recorder.Body.String()
	if strings.Contains(html, "<script>alert(1)</script>") {
		t.Fatalf("XSS leaked: %s", html)
	}
	if strings.Contains(html, "<img src=x") {
		t.Fatalf("raw html leaked: %s", html)
	}
	assertContains(t, html, "&lt;script&gt;")
	assertContains(t, html, "<p>第一段 &lt;img src=x onerror=alert(1)&gt;</p>")
}

func TestRobotsAndSitemapExposePublicPostURLs(t *testing.T) {
	handler := newHandler(t, map[string]postports.PostDetailSlice{},
		fixedSitemapLister{ids: []string{"post-a", "post-b"}})

	robots := httptest.NewRecorder()
	handler.Routes().ServeHTTP(robots, httptest.NewRequest("GET", "/public-web/robots.txt", nil))
	if robots.Code != 200 {
		t.Fatalf("robots status=%d", robots.Code)
	}
	assertContains(t, robots.Body.String(), "Sitemap: https://web.example.test/sitemap-posts.xml")

	sitemap := httptest.NewRecorder()
	handler.Routes().ServeHTTP(sitemap, httptest.NewRequest("GET", "/public-web/sitemap-posts.xml", nil))
	if sitemap.Code != 200 {
		t.Fatalf("sitemap status=%d", sitemap.Code)
	}
	assertContains(t, sitemap.Body.String(), "<loc>https://web.example.test/post/post-a</loc>")
	assertContains(t, sitemap.Body.String(), "<loc>https://web.example.test/post/post-b</loc>")
}

func TestSitemapFailsClosedWhenListerUnavailable(t *testing.T) {
	handler := newHandler(t, map[string]postports.PostDetailSlice{},
		fixedSitemapLister{err: errors.New("mongo down")})

	recorder := httptest.NewRecorder()
	handler.Routes().ServeHTTP(recorder, httptest.NewRequest("GET", "/public-web/sitemap-posts.xml", nil))
	if recorder.Code != 503 {
		t.Fatalf("status=%d（读失败必须 503，不得输出空 sitemap 伪成功）", recorder.Code)
	}
}

func TestPublicPostHTMLRendersBodyImagesFromAssetManifest(t *testing.T) {
	detail := publicArticleDetail()
	detail.ArticleMarkdown = "---\ntitle: t\n---\n\n" +
		"正文开头。\n\n" +
		":::figure id=\"asset-cdn\" layout=\"fullWidth\" caption=\"五彩池全景\"\n" +
		"asset://asset-cdn\n" +
		":::\n\n" +
		":::figure id=\"asset-slice\" layout=\"fullWidth\" caption=\"雪宝顶\"\n" +
		"asset://asset-slice\n" +
		":::\n\n" +
		":::figure id=\"asset-missing\" layout=\"fullWidth\" caption=\"无公网图\"\n" +
		"asset://asset-missing\n" +
		":::\n"
	detail.ArticleAssetManifest = &postports.PostArticleAssetManifestSlice{
		Assets: []postports.PostArticleAssetSlice{
			{
				AssetID: "asset-cdn",
				CDNURL:  "https://cdn.example.test/p/full.webp",
				Caption: "五彩池全景",
			},
			{
				AssetID:        "asset-slice",
				PublicSliceKey: "public/post-web-1/slice-2.webp",
			},
			{AssetID: "asset-missing"},
		},
	}
	handler := newHandler(t, map[string]postports.PostDetailSlice{
		"post-web-1": detail,
	}, fixedSitemapLister{})

	recorder := httptest.NewRecorder()
	handler.Routes().ServeHTTP(recorder, httptest.NewRequest("GET", "/public-web/post/post-web-1", nil))
	html := recorder.Body.String()

	// manifest cdnUrl 直出。
	assertContains(t, html, `<figure><img src="https://cdn.example.test/p/full.webp" alt="五彩池全景" loading="lazy" data-asset-id="asset-cdn">`)
	assertContains(t, html, "<figcaption>五彩池全景</figcaption>")
	// PublicSliceKey + CDN origin 派生；caption 从指令行属性回退。
	assertContains(t, html, `<img src="https://cdn.example.test/public/post-web-1/slice-2.webp" alt="雪宝顶" loading="lazy" data-asset-id="asset-slice">`)
	// 无公网 URL 的 asset 跳过，不泄漏 asset://。
	if strings.Contains(html, "asset-missing") || strings.Contains(html, "asset://") {
		t.Fatalf("missing-url asset leaked: %s", html)
	}
}

func TestPublicPostHTMLRendersInlineLinksWithSchemeAllowlist(t *testing.T) {
	detail := publicArticleDetail()
	detail.ArticleMarkdown = "---\ntitle: t\n---\n\n" +
		"详见 [官网攻略](https://example.com/guide?a=1&b=2) 与 [中奖](javascript:alert(1)) 两处。\n"
	handler := newHandler(t, map[string]postports.PostDetailSlice{
		"post-web-1": detail,
	}, fixedSitemapLister{})

	recorder := httptest.NewRecorder()
	handler.Routes().ServeHTTP(recorder, httptest.NewRequest("GET", "/public-web/post/post-web-1", nil))
	html := recorder.Body.String()

	assertContains(t, html, `<a href="https://example.com/guide?a=1&amp;b=2" rel="noopener">官网攻略</a>`)
	if strings.Contains(html, `href="javascript:`) {
		t.Fatalf("javascript scheme leaked into href: %s", html)
	}
	assertContains(t, html, "[中奖](javascript:alert(1))")
}

func TestPublicPostHTMLStripsInternalEntityLinks(t *testing.T) {
	// 数据工程真实供稿形态：正文含站内实体相对链接；实体落地页 SEO 未
	// 上线前渲染纯文本，不产生死链、不裸露记号。
	detail := publicArticleDetail()
	detail.ArticleMarkdown = "---\ntitle: t\n---\n\n" +
		"真正牵动期待的却是[杭州西湖](/entity/地点/景区/杭州西湖)——湖面与堤桥叠在一起。\n"
	handler := newHandler(t, map[string]postports.PostDetailSlice{
		"post-web-1": detail,
	}, fixedSitemapLister{})

	recorder := httptest.NewRecorder()
	handler.Routes().ServeHTTP(recorder, httptest.NewRequest("GET", "/public-web/post/post-web-1", nil))
	html := recorder.Body.String()

	assertContains(t, html, "<p>真正牵动期待的却是杭州西湖——湖面与堤桥叠在一起。</p>")
	if strings.Contains(html, "/entity/") || strings.Contains(html, "[杭州西湖]") {
		t.Fatalf("internal link markup leaked: %s", html)
	}
}

func TestPublicPostHTMLRendersHorizontalRuleAndAlignedParagraph(t *testing.T) {
	detail := publicArticleDetail()
	detail.ArticleMarkdown = "---\ntitle: t\n---\n\n" +
		"上一段。\n\n" +
		"---\n\n" +
		":::align value=\"center\"\n" +
		"居中的段落文本\n" +
		":::\n"
	handler := newHandler(t, map[string]postports.PostDetailSlice{
		"post-web-1": detail,
	}, fixedSitemapLister{})

	recorder := httptest.NewRecorder()
	handler.Routes().ServeHTTP(recorder, httptest.NewRequest("GET", "/public-web/post/post-web-1", nil))
	html := recorder.Body.String()

	assertContains(t, html, "<hr>")
	// align 指令块内文本按段落降级渲染（SEO 端不承载版式）。
	assertContains(t, html, "<p>居中的段落文本</p>")
	if strings.Contains(html, ":::") {
		t.Fatalf("directive markup leaked: %s", html)
	}
}

func TestTransferRedirectsCrawlerAndUnknownUAToObjectPage(t *testing.T) {
	handler := newHandler(t, map[string]postports.PostDetailSlice{}, fixedSitemapLister{})

	// 爬虫/未知 UA（web_preview）→ 302 对象 SEO 页。
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest("GET", "/public-web/open?target=post&id=post-web-1", nil)
	request.Header.Set("User-Agent", "Googlebot/2.1 (+http://www.google.com/bot.html)")
	handler.Routes().ServeHTTP(recorder, request)
	if recorder.Code != 302 {
		t.Fatalf("crawler status=%d", recorder.Code)
	}
	if location := recorder.Header().Get("Location"); location != "https://web.example.test/post/post-web-1" {
		t.Fatalf("crawler location=%q", location)
	}

	// 无目标（token 未解析）→ 302 首页，不伪造对象跳转。
	tokenRecorder := httptest.NewRecorder()
	tokenRequest := httptest.NewRequest("GET", "/public-web/s/abc123", nil)
	tokenRequest.Header.Set("User-Agent", "Googlebot/2.1")
	handler.Routes().ServeHTTP(tokenRecorder, tokenRequest)
	if tokenRecorder.Code != 302 {
		t.Fatalf("token status=%d", tokenRecorder.Code)
	}
	if location := tokenRecorder.Header().Get("Location"); location != "https://web.example.test/" {
		t.Fatalf("token location=%q", location)
	}
}

func TestTransferRendersMobileLaunchPageByUAMatrix(t *testing.T) {
	handler := newHandler(t, map[string]postports.PostDetailSlice{}, fixedSitemapLister{})
	cases := []struct {
		name         string
		userAgent    string
		expectMode   string
		expectMethod string
	}{
		{
			name:         "iphone",
			userAgent:    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
			expectMode:   "ios_universal_link",
			expectMethod: "universal_link",
		},
		{
			name:         "wechat_android",
			userAgent:    "Mozilla/5.0 (Linux; Android 14) MicroMessenger/8.0",
			expectMode:   "wechat_android_launch",
			expectMethod: "wx-open-launch-app",
		},
		{
			name:         "pc",
			userAgent:    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
			expectMode:   "pc_preview",
			expectMethod: "qr_install",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			recorder := httptest.NewRecorder()
			request := httptest.NewRequest("GET", "/public-web/open?target=post&id=post-web-1", nil)
			request.Header.Set("User-Agent", tc.userAgent)
			handler.Routes().ServeHTTP(recorder, request)
			if recorder.Code != 200 {
				t.Fatalf("status=%d", recorder.Code)
			}
			if robots := recorder.Header().Get("X-Robots-Tag"); robots != "noindex" {
				t.Fatalf("X-Robots-Tag=%q（中转页不得被索引）", robots)
			}
			html := recorder.Body.String()
			assertContains(t, html, `data-transfer-mode="`+tc.expectMode+`"`)
			assertContains(t, html, `data-launch-method="`+tc.expectMethod+`"`)
			assertContains(t, html, `href="https://web.example.test/post/post-web-1"`)
		})
	}
}

func assertContains(t *testing.T, haystack string, needle string) {
	t.Helper()
	if !strings.Contains(haystack, needle) {
		t.Fatalf("expected %q in output:\n%s", needle, haystack)
	}
}
