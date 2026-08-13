package publicweb

import (
	"context"
	"net/http"
	"strings"
	"time"

	rtweb "quwoquan_service/runtime/publicweb"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// PostDetailReader 是公开 HTML 读面消费的对象级查询端口（匿名 viewer）。
type PostDetailReader interface {
	GetPost(
		ctx context.Context,
		query postports.PostDetailQuery,
	) (postports.PostDetailSlice, error)
}

// SitemapPostLister 提供 sitemap 用的公开已发布 postId 列表。
type SitemapPostLister interface {
	ListPublicPostIDs(ctx context.Context, limit int) ([]string, error)
}

// Handler 是 post 对象的公开 SEO HTML 读面（public-content-web-entry 第一段）：
// `GET /public-web/post/{postId}`、`/public-web/robots.txt`、
// `/public-web/sitemap-posts.xml`。可见性复用 GetPost 公开读语义；非 public
// 或不可读的 post 一律 404 HTML（不泄露存在性），非 prod noindex 由部署层
// origin/robots 控制。
type Handler struct {
	origin        string
	cdnOrigin     string
	posts         PostDetailReader
	sitemapLister SitemapPostLister
	sitemapLimit  int
}

func NewHandler(
	origin string,
	cdnOrigin string,
	posts PostDetailReader,
	sitemapLister SitemapPostLister,
) *Handler {
	return &Handler{
		origin:        strings.TrimRight(strings.TrimSpace(origin), "/"),
		cdnOrigin:     strings.TrimRight(strings.TrimSpace(cdnOrigin), "/"),
		posts:         posts,
		sitemapLister: sitemapLister,
		sitemapLimit:  500,
	}
}

// RegisterRoutes 把公开 HTML 读面挂到宿主 mux。
func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("/public-web/post/{postId}", h.handlePostHTML)
	mux.HandleFunc("/public-web/robots.txt", h.handleRobots)
	mux.HandleFunc("/public-web/sitemap-posts.xml", h.handleSitemap)
	mux.HandleFunc("/public-web/open", h.handleTransfer)
	mux.HandleFunc("/public-web/s/{token}", h.handleTransferToken)
}

// Routes 返回自带路由的 http.Handler（组合根 outer mux 挂载用）。
func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	h.RegisterRoutes(mux)
	return mux
}

func (h *Handler) handlePostHTML(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	postID := strings.TrimSpace(r.PathValue("postId"))
	if postID == "" {
		h.writeNotFound(w)
		return
	}
	detail, err := h.posts.GetPost(
		r.Context(),
		postports.NewPostDetailQuery(
			postports.NewPostID(postID),
			postports.NewViewerContext(postports.NewPersonaID("")),
		),
	)
	if err != nil {
		h.writeNotFound(w)
		return
	}
	// fail-closed：只有公开且已发布的 Post 才有公开 HTML；其余 404，
	// 不泄露对象存在性。
	if strings.ToLower(strings.TrimSpace(string(detail.Visibility))) != "public" ||
		strings.ToLower(strings.TrimSpace(string(detail.Status))) != "published" {
		h.writeNotFound(w)
		return
	}
	page := rtweb.ObjectPage{
		ObjectType:  "post",
		ObjectID:    postID,
		Path:        "post/" + postID,
		Title:       firstNonEmpty(detail.Title, summaryLead(detail.Body), postID),
		Description: firstNonEmpty(detail.Summary, summaryLead(detail.Body)),
		CoverURL:    detail.CoverURL,
		Visibility:  string(detail.Visibility),
		AuthorName:  detail.AuthorDisplayName,
		BodyHTML:    h.renderBodyHTML(detail),
	}
	if !detail.PublishedAt.IsZero() {
		page.PublishedISO = detail.PublishedAt.UTC().Format(time.RFC3339)
	}
	document := rtweb.RenderObjectHTML(h.origin, page)
	w.Header().Set("Content-Type", document.ContentType)
	w.WriteHeader(document.StatusCode)
	_, _ = w.Write([]byte(document.HTML))
}

func (h *Handler) renderBodyHTML(detail postports.PostDetailSlice) string {
	markdown := strings.TrimSpace(detail.ArticleMarkdown)
	if markdown != "" {
		return RenderQwqMarkdownBodyHTML(markdown, h.bodyAssetsFor(detail))
	}
	body := strings.TrimSpace(detail.Body)
	if body == "" {
		return ""
	}
	var b strings.Builder
	for _, paragraph := range strings.Split(body, "\n") {
		if trimmed := strings.TrimSpace(paragraph); trimmed != "" {
			b.WriteString("<p>" + renderInlineText(trimmed) + "</p>")
		}
	}
	return b.String()
}

// bodyAssetsFor 从 articleAssetManifest 派生正文图片公网地址：优先 manifest
// 的 cdnUrl，其次 PublicSliceKey + 配置的 CDN origin；两者皆无则不进映射
// （渲染层跳过，fail-closed 不猜测地址）。
func (h *Handler) bodyAssetsFor(
	detail postports.PostDetailSlice,
) map[string]BodyAsset {
	manifest := detail.ArticleAssetManifest
	if manifest == nil || len(manifest.Assets) == 0 {
		return nil
	}
	assets := make(map[string]BodyAsset, len(manifest.Assets))
	for _, asset := range manifest.Assets {
		assetID := strings.TrimSpace(asset.AssetID)
		if assetID == "" {
			continue
		}
		url := strings.TrimSpace(asset.CDNURL)
		if url == "" {
			sliceKey := strings.Trim(strings.TrimSpace(asset.PublicSliceKey), "/")
			if sliceKey != "" && h.cdnOrigin != "" {
				url = h.cdnOrigin + "/" + sliceKey
			}
		}
		if url == "" {
			continue
		}
		assets[assetID] = BodyAsset{URL: url, Caption: strings.TrimSpace(asset.Caption)}
	}
	return assets
}

func (h *Handler) handleRobots(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	_, _ = w.Write([]byte(rtweb.RenderRobots(h.origin + "/sitemap-posts.xml")))
}

func (h *Handler) handleSitemap(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if h.sitemapLister == nil {
		http.Error(w, "sitemap unavailable", http.StatusServiceUnavailable)
		return
	}
	ids, err := h.sitemapLister.ListPublicPostIDs(r.Context(), h.sitemapLimit)
	if err != nil {
		http.Error(w, "sitemap unavailable", http.StatusServiceUnavailable)
		return
	}
	urls := make([]string, 0, len(ids))
	for _, id := range ids {
		if trimmed := strings.TrimSpace(id); trimmed != "" {
			urls = append(urls, h.origin+"/post/"+trimmed)
		}
	}
	w.Header().Set("Content-Type", "application/xml; charset=utf-8")
	_, _ = w.Write([]byte(rtweb.RenderSitemap(urls)))
}

// handleTransfer 是 UA 分流中转页（public-content-web-entry REQ-004 第一段）：
// `GET /public-web/open?target=post&id=...`。爬虫/未知 UA（web_preview）302
// 到对象 SEO 页保证抓取质量；移动端 UA 渲染 deeplink 引导页。
func (h *Handler) handleTransfer(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	h.writeTransfer(w, r, rtweb.TransferRequest{
		UserAgent:    r.UserAgent(),
		TargetEntity: strings.TrimSpace(r.URL.Query().Get("target")),
		TargetID:     strings.TrimSpace(r.URL.Query().Get("id")),
	})
}

// handleTransferToken：`GET /public-web/s/{token}`。token → 对象解析属短链
// 后续段（public-content-web-entry OPEN 承接），当前按无目标 fallback_home
// 分流，不伪造对象跳转。
func (h *Handler) handleTransferToken(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	h.writeTransfer(w, r, rtweb.TransferRequest{
		UserAgent: r.UserAgent(),
		Token:     strings.TrimSpace(r.PathValue("token")),
	})
}

func (h *Handler) writeTransfer(
	w http.ResponseWriter,
	r *http.Request,
	req rtweb.TransferRequest,
) {
	decision := rtweb.ResolveTransfer(req)
	// 爬虫/未知 UA：302 到对象 SEO 页（post 目标）保证抓取；无目标回首页。
	if decision.Mode == "web_preview" || decision.Mode == "fallback_home" {
		target := h.origin + "/"
		if decision.Mode == "web_preview" &&
			decision.TargetEntity == "post" &&
			decision.TargetID != "" {
			target = h.origin + "/post/" + decision.TargetID
		}
		http.Redirect(w, r, target, http.StatusFound)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("X-Robots-Tag", "noindex")
	_, _ = w.Write([]byte(renderTransferHTML(h.origin, decision)))
}

// renderTransferHTML 渲染移动端 deeplink 引导页：主按钮按分流决策的
// LaunchMethod 语义打开 App，副链接回退到对象 SEO 页或下载页。
func renderTransferHTML(origin string, decision rtweb.TransferDecision) string {
	objectURL := origin + "/"
	if decision.TargetEntity == "post" && decision.TargetID != "" {
		objectURL = origin + "/post/" + decision.TargetID
	}
	fallback := decision.FallbackURL
	if fallback == "" {
		fallback = "/download"
	}
	var b strings.Builder
	b.WriteString(`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">`)
	b.WriteString(`<meta name="viewport" content="width=device-width, initial-scale=1">`)
	b.WriteString(`<meta name="robots" content="noindex,nofollow">`)
	b.WriteString(`<title>打开趣窝圈</title></head><body><main>`)
	b.WriteString(`<h1>在趣窝圈 App 中查看</h1>`)
	b.WriteString(`<p data-transfer-mode="` + htmlEscape(decision.Mode) +
		`" data-launch-method="` + htmlEscape(decision.LaunchMethod) + `">`)
	b.WriteString(`<a href="` + htmlEscape(objectURL) + `">继续浏览网页版</a></p>`)
	b.WriteString(`<p><a href="` + htmlEscape(fallback) + `">下载趣窝圈 App</a></p>`)
	b.WriteString(`</main></body></html>`)
	return b.String()
}

func htmlEscape(value string) string {
	replacer := strings.NewReplacer(
		"&", "&amp;",
		"<", "&lt;",
		">", "&gt;",
		`"`, "&quot;",
	)
	return replacer.Replace(value)
}

func (h *Handler) writeNotFound(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusNotFound)
	_, _ = w.Write([]byte(
		`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">` +
			`<meta name="robots" content="noindex,nofollow"><title>内容不存在</title>` +
			`</head><body><main><h1>内容不存在或不可见</h1></main></body></html>`,
	))
}

func summaryLead(body string) string {
	trimmed := strings.TrimSpace(body)
	if trimmed == "" {
		return ""
	}
	runes := []rune(trimmed)
	if len(runes) > 120 {
		return string(runes[:120])
	}
	return trimmed
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}
