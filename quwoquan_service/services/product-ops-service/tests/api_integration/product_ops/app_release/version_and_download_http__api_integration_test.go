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
			MinimumSupportedVersion:     "1.8.0",
			MinimumSupportedBuild:       "18000",
			UpdateURL:                   "https://download.quwoquan.example/download/android",
			RecoveryURL:                 "https://download.quwoquan.example/download",
			APKURL:                      "https://cdn.quwoquan.example/releases/quwoquan-18201.apk",
			APKHostAllowlist:            []string{"cdn.quwoquan.example"},
			APKPackageName:              "com.leadwise.quwoquan",
			APKSHA256:                   "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
			APKSizeBytes:                42,
			APKSigningCertificateSHA256: "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
			MinAndroidVersion:           "26",
		},
		IOS: apprelease.Release{
			LatestVersion:           "1.8.2",
			LatestBuild:             "18201",
			MinimumSupportedVersion: "1.8.0",
			MinimumSupportedBuild:   "18000",
			UpdateURL:               "https://apps.apple.com/app/id1234567890",
			RecoveryURL:             "https://download.quwoquan.example/download/ios",
		},
		Web: apprelease.Release{
			LatestVersion:           "1.8.2",
			LatestBuild:             "18201",
			MinimumSupportedVersion: "1.8.0",
			MinimumSupportedBuild:   "18000",
			UpdateURL:               "https://download.quwoquan.example/",
			RecoveryURL:             "https://download.quwoquan.example/download",
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
	if payload["latestBuild"] != "18201" || payload["minimumSupportedBuild"] != "18000" ||
		payload["updateState"] != "available" || payload["platform"] != "android" ||
		payload["updateUrl"] != "https://download.quwoquan.example/download/android" {
		t.Fatalf("version payload=%v", payload)
	}

	iosVersion := httptest.NewRecorder()
	mux.ServeHTTP(iosVersion, httptest.NewRequest(
		http.MethodGet,
		"/ops/app-recovery/version?platform=ios&appVersion=1.8.1&buildNumber=18100",
		nil,
	))
	if iosVersion.Code != http.StatusOK {
		t.Fatalf("ios version status=%d body=%s", iosVersion.Code, iosVersion.Body.String())
	}
	payload = nil
	if err := json.Unmarshal(iosVersion.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if payload["platform"] != "ios" || payload["updateState"] != "available" ||
		payload["updateUrl"] != nil ||
		payload["recoveryUrl"] != "https://download.quwoquan.example/download/ios" {
		t.Fatalf("ios version payload=%v", payload)
	}

	webVersion := httptest.NewRecorder()
	mux.ServeHTTP(webVersion, httptest.NewRequest(
		http.MethodGet,
		"/ops/app-recovery/version?platform=web&appVersion=1.0.0&buildNumber=1",
		nil,
	))
	if webVersion.Code != http.StatusOK {
		t.Fatalf("web version status=%d body=%s", webVersion.Code, webVersion.Body.String())
	}
	payload = nil
	if err := json.Unmarshal(webVersion.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if payload["platform"] != "web" || payload["updateState"] != "required" ||
		payload["updateUrl"] != "https://download.quwoquan.example/" {
		t.Fatalf("web version payload=%v", payload)
	}

	download := httptest.NewRecorder()
	mux.ServeHTTP(download, httptest.NewRequest(http.MethodGet, "/download/android", nil))
	if download.Code != http.StatusTemporaryRedirect || download.Header().Get("Location") != "https://cdn.quwoquan.example/releases/quwoquan-18201.apk" {
		t.Fatalf("download status=%d headers=%v", download.Code, download.Header())
	}
	if download.Header().Get("X-App-Package-SHA256") != "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" {
		t.Fatalf("download digest=%q", download.Header().Get("X-App-Package-SHA256"))
	}
	if download.Header().Get("X-App-Build-Number") != "18201" {
		t.Fatalf("download build=%q", download.Header().Get("X-App-Build-Number"))
	}
	if download.Header().Get("X-Quwoquan-APK-SHA256") != "" || download.Header().Get("X-Quwoquan-APK-Build") != "" {
		t.Fatalf("legacy branded headers must be absent: %v", download.Header())
	}
}
