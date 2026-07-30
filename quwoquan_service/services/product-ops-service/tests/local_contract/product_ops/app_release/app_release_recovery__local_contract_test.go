// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-001
package local_contract

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"

	httpadapter "quwoquan_service/services/product-ops-service/internal/product_ops/app_release/adapters/inbound/http"
	apprelease "quwoquan_service/services/product-ops-service/internal/product_ops/app_release/application"
)

const (
	testSHA256      = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
	testCertificate = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
)

func TestAppReleaseVersionResponseContainsOnlyRecoveryContractFields(t *testing.T) {
	service := newAppReleaseService(t)
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).Register(mux)

	request := httptest.NewRequest(
		http.MethodGet,
		"/ops/app-recovery/version?platform=android&appVersion=1.8.1&buildNumber=18100",
		nil,
	)
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("version status=%d body=%s", response.Code, response.Body.String())
	}
	var payload map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode version response: %v", err)
	}
	wantKeys := []string{"latestBuild", "latestVersion", "recoveryUrl", "updateUrl"}
	gotKeys := make([]string, 0, len(payload))
	for key := range payload {
		gotKeys = append(gotKeys, key)
	}
	sortStrings(gotKeys)
	if !reflect.DeepEqual(gotKeys, wantKeys) {
		t.Fatalf("version keys=%v want=%v", gotKeys, wantKeys)
	}
	if payload["updateUrl"] != "https://download.quwoquan.example/download/android" {
		t.Fatalf("android update url=%v", payload["updateUrl"])
	}
}

func TestOfficialDownloadRouteRecommendsPlatformWithoutAutomaticBinaryDownload(t *testing.T) {
	service := newAppReleaseService(t)
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).Register(mux)

	tests := []struct {
		name      string
		userAgent string
		contains  string
	}{
		{
			name:      "android recommends signed apk",
			userAgent: "Mozilla/5.0 (Linux; Android 15)",
			contains:  "趣我圈 Android 版",
		},
		{
			name:      "ios recommends pwa",
			userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X)",
			contains:  "趣我圈 iOS 网页版",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodGet, "/download/mobile", nil)
			request.Header.Set("User-Agent", test.userAgent)
			response := httptest.NewRecorder()
			mux.ServeHTTP(response, request)
			if response.Code != http.StatusOK {
				t.Fatalf("download status=%d body=%s", response.Code, response.Body.String())
			}
			if got := response.Body.String(); !strings.Contains(got, test.contains) {
				t.Fatalf("download body=%q missing=%q", got, test.contains)
			}
			if got := response.Header().Get("Location"); got != "" {
				t.Fatalf("download must wait for explicit click, location=%q", got)
			}
		})
	}
}

func TestAndroidExplicitDownloadAndLatestManifestUseVerifiedRelease(t *testing.T) {
	service := newAppReleaseService(t)
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).Register(mux)

	download := httptest.NewRecorder()
	mux.ServeHTTP(download, httptest.NewRequest(http.MethodGet, "/download/android", nil))
	if download.Code != http.StatusTemporaryRedirect {
		t.Fatalf("android download status=%d body=%s", download.Code, download.Body.String())
	}
	if got := download.Header().Get("Location"); got != "https://cdn.quwoquan.example/releases/quwoquan-18201.apk" {
		t.Fatalf("android location=%q", got)
	}

	manifest := httptest.NewRecorder()
	mux.ServeHTTP(manifest, httptest.NewRequest(http.MethodGet, "/download/android/latest.json", nil))
	var payload map[string]any
	if err := json.Unmarshal(manifest.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode android manifest: %v", err)
	}
	if payload["minAndroidVersion"] != "26" || payload["latestBuild"] != "18201" {
		t.Fatalf("android manifest=%v", payload)
	}
}

func TestAppReleaseRejectsUntrustedAndroidAPKAndIncompleteProof(t *testing.T) {
	catalog := appReleaseCatalog()
	catalog.Android.APKURL = "https://attacker.example/quwoquan.apk"
	if _, err := apprelease.NewService(catalog); err == nil {
		t.Fatal("untrusted apk host must be rejected")
	}

	catalog = appReleaseCatalog()
	catalog.Android.APKSHA256 = ""
	if _, err := apprelease.NewService(catalog); err == nil {
		t.Fatal("missing apk sha256 must be rejected")
	}

	catalog = appReleaseCatalog()
	catalog.Android.UpdateURL = "https://attacker.example/download/android"
	if _, err := apprelease.NewService(catalog); err == nil {
		t.Fatal("android update url outside the official web host must be rejected")
	}

	catalog = appReleaseCatalog()
	catalog.IOS.RecoveryURL = "https://attacker.example/recovery"
	if _, err := apprelease.NewService(catalog); err == nil {
		t.Fatal("recovery url outside the official web host must be rejected")
	}
}

func TestAndroidOfficialReleaseRemainsAvailableWithoutIOSRelease(t *testing.T) {
	catalog := appReleaseCatalog()
	catalog.IOS = apprelease.Release{}
	service, err := apprelease.NewService(catalog)
	if err != nil {
		t.Fatalf("android-only release service: %v", err)
	}
	if _, ok := service.Release(apprelease.PlatformAndroid); !ok {
		t.Fatal("android release must remain available")
	}
	if _, ok := service.Release(apprelease.PlatformIOS); ok {
		t.Fatal("unconfigured ios release must stay unavailable")
	}
}

func TestUnknownDeviceGetsChoicePageWithoutThirdPartyNavigation(t *testing.T) {
	service := newAppReleaseService(t)
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).Register(mux)
	request := httptest.NewRequest(http.MethodGet, "/download", nil)
	request.Header.Set("User-Agent", "Mozilla/5.0 (X11; Linux x86_64)")
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("landing status=%d body=%s", response.Code, response.Body.String())
	}
	if got := response.Header().Get("Content-Security-Policy"); got == "" {
		t.Fatal("landing page must set a content security policy")
	}
}

func newAppReleaseService(t *testing.T) *apprelease.Service {
	t.Helper()
	service, err := apprelease.NewService(appReleaseCatalog())
	if err != nil {
		t.Fatalf("build app release service: %v", err)
	}
	return service
}

func appReleaseCatalog() apprelease.Catalog {
	return apprelease.Catalog{
		PublicOrigin: "https://download.quwoquan.example",
		IOS: apprelease.Release{
			LatestVersion: "1.8.2",
			LatestBuild:   "18201",
			UpdateURL:     "",
			RecoveryURL:   "https://download.quwoquan.example/download/ios",
		},
		Android: apprelease.Release{
			LatestVersion:               "1.8.2",
			LatestBuild:                 "18201",
			UpdateURL:                   "https://download.quwoquan.example/download/android",
			RecoveryURL:                 "https://download.quwoquan.example/download",
			APKURL:                      "https://cdn.quwoquan.example/releases/quwoquan-18201.apk",
			APKHostAllowlist:            []string{"cdn.quwoquan.example"},
			APKPackageName:              "com.quwoquan.quwoquan_app",
			APKSHA256:                   testSHA256,
			APKSizeBytes:                42,
			APKSigningCertificateSHA256: testCertificate,
			MinAndroidVersion:           "26",
		},
	}
}

func sortStrings(values []string) {
	for i := 1; i < len(values); i++ {
		for j := i; j > 0 && values[j] < values[j-1]; j-- {
			values[j], values[j-1] = values[j-1], values[j]
		}
	}
}
