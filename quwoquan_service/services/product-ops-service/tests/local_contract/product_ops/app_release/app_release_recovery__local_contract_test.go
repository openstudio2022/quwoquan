// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-001
package local_contract

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
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

func TestOfficialDownloadRouteDetectsPlatformAndUsesTrustedTargets(t *testing.T) {
	service := newAppReleaseService(t)
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).Register(mux)

	tests := []struct {
		name      string
		userAgent string
		location  string
	}{
		{
			name:      "android downloads signed apk",
			userAgent: "Mozilla/5.0 (Linux; Android 15)",
			location:  "https://cdn.quwoquan.example/releases/quwoquan-18201.apk",
		},
		{
			name:      "ios opens app store",
			userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X)",
			location:  "https://apps.apple.com/cn/app/quwoquan/id1234567890",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodGet, "/download/mobile", nil)
			request.Header.Set("User-Agent", test.userAgent)
			response := httptest.NewRecorder()
			mux.ServeHTTP(response, request)
			if response.Code != http.StatusTemporaryRedirect {
				t.Fatalf("download status=%d body=%s", response.Code, response.Body.String())
			}
			if got := response.Header().Get("Location"); got != test.location {
				t.Fatalf("download location=%q want=%q", got, test.location)
			}
		})
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
			UpdateURL:     "https://apps.apple.com/cn/app/quwoquan/id1234567890",
			RecoveryURL:   "https://download.quwoquan.example/download",
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
