package httpadapter

import (
	"encoding/json"
	"errors"
	"html/template"
	"net/http"
	"strings"

	apprelease "quwoquan_service/services/product-ops-service/internal/product_ops/app_release/application"
)

type Handler struct {
	service *apprelease.Service
}

func NewHandler(service *apprelease.Service) *Handler { return &Handler{service: service} }

func (h *Handler) Register(mux *http.ServeMux) {
	mux.HandleFunc("/ops/app-recovery/version", h.version)
	mux.HandleFunc("/download", h.downloadLanding)
	mux.HandleFunc("/download/", h.download)
}

func (h *Handler) version(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		h.notFound(w)
		return
	}
	if h.service == nil {
		h.unavailable(w)
		return
	}
	result, err := h.service.Version(apprelease.VersionQuery{
		Platform: r.URL.Query().Get("platform"), AppVersion: r.URL.Query().Get("appVersion"), BuildNumber: r.URL.Query().Get("buildNumber"),
	})
	if errors.Is(err, apprelease.ErrInvalidVersionQuery) {
		h.writeJSON(w, http.StatusBadRequest, map[string]string{"code": "OPS.USER.app_release_query_invalid"})
		return
	}
	if err != nil {
		h.unavailable(w)
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	h.writeJSON(w, http.StatusOK, result)
}

func (h *Handler) downloadLanding(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		h.notFound(w)
		return
	}
	h.routeDetectedPlatform(w, r, false)
}

func (h *Handler) download(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		h.notFound(w)
		return
	}
	switch strings.TrimSuffix(r.URL.Path, "/") {
	case "/download/mobile":
		h.routeDetectedPlatform(w, r, true)
	case "/download/ios":
		h.redirectPlatform(w, r, apprelease.PlatformIOS)
	case "/download/android":
		h.redirectPlatform(w, r, apprelease.PlatformAndroid)
	default:
		h.notFound(w)
	}
}

func (h *Handler) routeDetectedPlatform(w http.ResponseWriter, r *http.Request, requireMobile bool) {
	if h.service == nil {
		h.unavailable(w)
		return
	}
	if platform := apprelease.DetectPlatform(r.UserAgent()); platform != "" {
		h.redirectPlatform(w, r, platform)
		return
	}
	if requireMobile {
		h.renderLanding(w)
		return
	}
	h.renderLanding(w)
}

func (h *Handler) redirectPlatform(w http.ResponseWriter, r *http.Request, platform string) {
	if h.service == nil {
		h.unavailable(w)
		return
	}
	release, ok := h.service.Release(platform)
	if !ok {
		h.unavailable(w)
		return
	}
	target := release.UpdateURL
	if platform == apprelease.PlatformAndroid {
		target = release.APKURL
		w.Header().Set("X-Quwoquan-APK-SHA256", strings.ToLower(release.APKSHA256))
		w.Header().Set("X-Quwoquan-APK-Build", release.LatestBuild)
	}
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Referrer-Policy", "no-referrer")
	http.Redirect(w, r, target, http.StatusTemporaryRedirect)
}

func (h *Handler) renderLanding(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
	w.Header().Set("Referrer-Policy", "no-referrer")
	_ = downloadPage.Execute(w, nil)
}

func (h *Handler) unavailable(w http.ResponseWriter) {
	h.writeJSON(w, http.StatusServiceUnavailable, map[string]string{"code": "OPS.SYSTEM.app_release_unavailable"})
}

func (h *Handler) notFound(w http.ResponseWriter) {
	h.writeJSON(w, http.StatusNotFound, map[string]string{"code": "RUNTIME.USER.route_not_found"})
}

func (h *Handler) writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

var downloadPage = template.Must(template.New("download").Parse(`<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>下载趣我圈</title><style>
:root{color-scheme:light;font-family:-apple-system,BlinkMacSystemFont,"Noto Sans SC",sans-serif;background:#f7f7fc;color:#111827}
body{margin:0;min-height:100vh;display:grid;place-items:center}.wrap{width:min(280px,calc(100vw - 48px));text-align:center}
h1{font-size:28px;line-height:1.3;margin:0 0 16px;font-weight:600}p{font-size:17px;line-height:1.5;color:#6b7280;margin:0 0 28px}
a{display:flex;height:48px;align-items:center;justify-content:center;border-radius:24px;text-decoration:none;font-size:17px;font-weight:500;margin-top:12px}
.primary{background:#0a84ff;color:#fff}.secondary{border:1px solid #0a84ff;color:#0a84ff;background:transparent}
</style></head><body><main class="wrap"><h1>获取趣我圈</h1><p>请选择与你设备对应的官方版本</p>
<a class="primary" href="/download/ios">iPhone / iPad</a><a class="secondary" href="/download/android">Android / 鸿蒙</a>
</main></body></html>`))
