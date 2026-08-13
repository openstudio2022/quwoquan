package httpadapter

import (
	"encoding/json"
	"errors"
	"html/template"
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	releasegenerated "quwoquan_service/services/product-ops-service/generated/product_ops/app_release"
	apprelease "quwoquan_service/services/product-ops-service/internal/product_ops/app_release/application"
)

type Handler struct {
	service *apprelease.Service
}

type downloadPageModel struct {
	Platform string
}

func NewHandler(service *apprelease.Service) *Handler { return &Handler{service: service} }

func (h *Handler) Register(mux *http.ServeMux) {
	mux.HandleFunc("/ops/app-recovery/version", h.version)
	mux.HandleFunc("/download/android/latest.json", h.androidLatest)
	mux.HandleFunc("/download", h.downloadLanding)
	mux.HandleFunc("/download/", h.download)
}

func (h *Handler) version(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		h.notFound(w, r)
		return
	}
	if h.service == nil {
		h.unavailable(w, r)
		return
	}
	result, err := h.service.Version(apprelease.VersionQuery{
		Platform: r.URL.Query().Get("platform"), AppVersion: r.URL.Query().Get("appVersion"), BuildNumber: r.URL.Query().Get("buildNumber"),
	})
	if errors.Is(err, apprelease.ErrInvalidVersionQuery) {
		rterr.WriteHTTPError(
			w,
			releasegenerated.AppErrorFromAppReleaseQueryInvalid(
				"app release version query rejected",
			),
			rterr.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	if err != nil {
		h.unavailable(w, r)
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	h.writeJSON(w, http.StatusOK, result)
}

func (h *Handler) downloadLanding(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		h.notFound(w, r)
		return
	}
	h.renderLanding(w, h.detectPlatform(r))
}

func (h *Handler) download(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		h.notFound(w, r)
		return
	}
	switch strings.TrimSuffix(r.URL.Path, "/") {
	case "/download/mobile":
		h.renderLanding(w, h.detectPlatform(r))
	case "/download/desktop":
		h.renderLanding(w, "")
	case "/download/ios":
		h.renderIOSInstall(w)
	case "/download/android":
		h.redirectAndroid(w, r)
	default:
		h.notFound(w, r)
	}
}

func (h *Handler) detectPlatform(r *http.Request) string {
	if explicit := apprelease.NormalizePlatform(r.URL.Query().Get("platform")); explicit != "" {
		return explicit
	}
	if clientHint := apprelease.NormalizePlatform(
		strings.Trim(r.Header.Get("Sec-CH-UA-Platform"), `"`),
	); clientHint != "" {
		return clientHint
	}
	return apprelease.DetectPlatform(r.UserAgent())
}

func (h *Handler) redirectAndroid(w http.ResponseWriter, r *http.Request) {
	if h.service == nil {
		h.unavailable(w, r)
		return
	}
	release, ok := h.service.Release(apprelease.PlatformAndroid)
	if !ok {
		h.unavailable(w, r)
		return
	}
	w.Header().Set("X-App-Package-SHA256", strings.ToLower(release.APKSHA256))
	w.Header().Set("X-App-Build-Number", release.LatestBuild)
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Referrer-Policy", "no-referrer")
	http.Redirect(w, r, release.APKURL, http.StatusTemporaryRedirect)
}

func (h *Handler) androidLatest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet || h.service == nil {
		h.notFound(w, r)
		return
	}
	release, ok := h.service.Release(apprelease.PlatformAndroid)
	if !ok {
		h.unavailable(w, r)
		return
	}
	h.writeJSON(w, http.StatusOK, map[string]any{
		"latestVersion":               release.LatestVersion,
		"latestBuild":                 release.LatestBuild,
		"apkUrl":                      release.APKURL,
		"apkSizeBytes":                release.APKSizeBytes,
		"apkSHA256":                   strings.ToLower(release.APKSHA256),
		"apkSigningCertificateSHA256": strings.ToLower(release.APKSigningCertificateSHA256),
		"minAndroidVersion":           release.MinAndroidVersion,
		"packageName":                 release.APKPackageName,
	})
}

func (h *Handler) renderLanding(w http.ResponseWriter, platform string) {
	h.writeHTMLHeaders(w)
	_ = downloadPage.Execute(w, downloadPageModel{Platform: platform})
}

func (h *Handler) renderIOSInstall(w http.ResponseWriter) {
	h.writeHTMLHeaders(w)
	_ = iosInstallPage.Execute(w, nil)
}

func (h *Handler) writeHTMLHeaders(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
	w.Header().Set("Referrer-Policy", "no-referrer")
	w.Header().Set("X-Content-Type-Options", "nosniff")
}

func (h *Handler) unavailable(w http.ResponseWriter, r *http.Request) {
	rterr.WriteHTTPError(
		w,
		releasegenerated.AppErrorFromAppReleaseUnavailable(
			"app release catalog unavailable",
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}

func (h *Handler) notFound(w http.ResponseWriter, r *http.Request) {
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "route_not_found"),
			"接口不存在或已下线",
			"app release route not found",
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}

func (h *Handler) writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

var downloadPage = template.Must(template.New("download").Parse(`<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>获取趣我圈</title><style>
:root{color-scheme:light;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans CJK SC","Noto Sans SC",sans-serif;background:#f6f8fc;color:#111318}
body{margin:0;min-height:100vh;display:grid;place-items:center}.wrap{width:min(320px,calc(100vw - 48px));text-align:center}
h1{font-size:28px;line-height:1.3;margin:0 0 16px;font-weight:600}p{font-size:17px;line-height:1.5;color:#6b707c;margin:0 0 28px}
a{display:flex;height:50px;align-items:center;justify-content:center;border-radius:25px;text-decoration:none;font-size:17px;font-weight:500;margin-top:12px}
.primary{background:#087bff;color:#fff}.secondary{border:1px solid #087bff;color:#087bff;background:transparent}
</style></head><body><main class="wrap">
{{if eq .Platform "android"}}<h1>趣我圈 Android 版</h1><p>下载趣我圈官方签名版本</p>
<a class="primary" href="/download/android">下载</a><a class="secondary" href="/">使用网页版</a>
{{else if eq .Platform "ios"}}<h1>趣我圈 iOS 网页版</h1><p>添加到主屏幕，快速打开</p>
<a class="primary" href="/download/ios">安装</a><a class="secondary" href="/">使用网页版</a>
{{else}}<h1>获取趣我圈</h1><p>请选择与你设备对应的官方方式</p>
<a class="primary" href="/download/android">Android 下载</a><a class="secondary" href="/download/ios">iOS 网页版</a>
<a class="secondary" href="/">使用网页版</a>{{end}}
</main></body></html>`))

var iosInstallPage = template.Must(template.New("ios-install").Parse(`<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>安装趣我圈 iOS 网页版</title><style>
:root{color-scheme:light;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans CJK SC","Noto Sans SC",sans-serif;background:#f6f8fc;color:#111318}
body{margin:0;min-height:100vh;display:grid;place-items:center}.wrap{width:min(320px,calc(100vw - 48px))}
h1{text-align:center;font-size:28px;line-height:1.3;margin:0 0 16px;font-weight:600}p,ol{font-size:17px;line-height:1.7;color:#6b707c}ol{padding-left:24px;margin:0 0 28px}
a{display:flex;height:50px;align-items:center;justify-content:center;border-radius:25px;text-decoration:none;font-size:17px;font-weight:500;background:#087bff;color:#fff}
</style></head><body><main class="wrap"><h1>安装趣我圈 iOS 网页版</h1>
<p>请在 Safari 中完成以下操作：</p><ol><li>点击浏览器的“分享”按钮</li><li>选择“添加到主屏幕”</li><li>确认后从主屏幕打开趣我圈</li></ol>
<a href="/">立即使用网页版</a></main></body></html>`))
