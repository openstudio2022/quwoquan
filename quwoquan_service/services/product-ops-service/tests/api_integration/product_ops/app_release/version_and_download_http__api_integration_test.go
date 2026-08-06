// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-001
// readiness_case: get-app-recovery-version-api
package api_integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	httpadapter "quwoquan_service/services/product-ops-service/internal/product_ops/app_release/adapters/inbound/http"
	apprelease "quwoquan_service/services/product-ops-service/internal/product_ops/app_release/application"
)

func TestAppReleaseHTTPUsesOneValidatedReleaseCatalog(t *testing.T) {
	service, err := apprelease.NewService(apprelease.Catalog{
		PublicOrigin: "https://download.quwoquan.example",
		Android: apprelease.Release{
			LatestVersion: "1.8.2", LatestBuild: "18201",
			UpdateURL:                   "https://download.quwoquan.example/download/android",
			RecoveryURL:                 "https://download.quwoquan.example/download",
			APKURL:                      "https://cdn.quwoquan.example/releases/quwoquan-18201.apk",
			APKHostAllowlist:            []string{"cdn.quwoquan.example"},
			APKPackageName:              "com.quwoquan.quwoquan_app",
			APKSHA256:                   "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
			APKSizeBytes:                42,
			APKSigningCertificateSHA256: "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
			MinAndroidVersion:           "26",
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).Register(mux)

	version := httptest.NewRecorder()
	mux.ServeHTTP(version, httptest.NewRequest(
		http.MethodGet,
		"/ops/app-recovery/version?platform=android&appVersion=1.8.1&buildNumber=18100",
		nil,
	))
	if version.Code != http.StatusOK {
		t.Fatalf("version status=%d body=%s", version.Code, version.Body.String())
	}
	var payload map[string]any
	if err := json.Unmarshal(version.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if payload["latestBuild"] != "18201" || payload["updateUrl"] != "https://download.quwoquan.example/download/android" {
		t.Fatalf("version payload=%v", payload)
	}

	download := httptest.NewRecorder()
	mux.ServeHTTP(download, httptest.NewRequest(http.MethodGet, "/download/android", nil))
	if download.Code != http.StatusTemporaryRedirect || download.Header().Get("Location") != "https://cdn.quwoquan.example/releases/quwoquan-18201.apk" {
		t.Fatalf("download status=%d headers=%v", download.Code, download.Header())
	}
	if download.Header().Get("X-Quwoquan-APK-SHA256") != "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" {
		t.Fatalf("download digest=%q", download.Header().Get("X-Quwoquan-APK-SHA256"))
	}
}
