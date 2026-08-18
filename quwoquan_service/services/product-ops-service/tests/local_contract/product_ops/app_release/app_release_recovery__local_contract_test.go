// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-001
// readiness_case: get-app-recovery-version-local
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
	wantKeys := []string{
		"latestBuild",
		"latestVersion",
		"minimumSupportedBuild",
		"minimumSupportedVersion",
		"platform",
		"recoveryUrl",
		"updateState",
		"updateUrl",
	}
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
	if payload["platform"] != "android" || payload["minimumSupportedBuild"] != "18000" || payload["updateState"] != "available" {
		t.Fatalf("android version policy=%v", payload)
	}
}

func TestAppReleaseDerivesUpdateStateFromBuildOnly(t *testing.T) {
	service := newAppReleaseService(t)
	for _, test := range []struct {
		build string
		want  string
	}{
		{build: "17999", want: apprelease.UpdateStateRequired},
		{build: "18000", want: apprelease.UpdateStateAvailable},
		{build: "18201", want: apprelease.UpdateStateNone},
		{build: "19000", want: apprelease.UpdateStateNone},
	} {
		result, err := service.Version(apprelease.VersionQuery{
			Platform: "android", AppVersion: "ignored-for-state", BuildNumber: test.build,
		})
		if err != nil {
			t.Fatalf("version build=%s: %v", test.build, err)
		}
		if result.UpdateState != test.want {
			t.Fatalf("build=%s state=%s want=%s", test.build, result.UpdateState, test.want)
		}
	}
}

func TestAppReleaseSupportsWebAsAnIndependentPlatform(t *testing.T) {
	service := newAppReleaseService(t)
	result, err := service.Version(apprelease.VersionQuery{
		Platform: "web", AppVersion: "1.8.0", BuildNumber: "18000",
	})
	if err != nil {
		t.Fatalf("web version: %v", err)
	}
	if result.Platform != "web" || result.UpdateState != apprelease.UpdateStateAvailable ||
		result.UpdateURL != "https://download.quwoquan.example/" {
		t.Fatalf("web version=%+v", result)
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
	if got := download.Header().Get("X-App-Package-SHA256"); got != testSHA256 {
		t.Fatalf("android package digest header=%q", got)
	}
	if got := download.Header().Get("X-App-Build-Number"); got != "18201" {
		t.Fatalf("android build header=%q", got)
	}
	if got := download.Header().Get("X-Quwoquan-APK-SHA256"); got != "" {
		t.Fatalf("legacy branded package header must be absent, got=%q", got)
	}
	if got := download.Header().Get("X-Quwoquan-APK-Build"); got != "" {
		t.Fatalf("legacy branded build header must be absent, got=%q", got)
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

	catalog = appReleaseCatalog()
	catalog.IOS.UpdateURL = "https://attacker.example/app"
	if _, err := apprelease.NewService(catalog); err == nil {
		t.Fatal("ios update url outside the app store must be rejected")
	}

	catalog = appReleaseCatalog()
	catalog.Web.MinimumSupportedBuild = "19000"
	if _, err := apprelease.NewService(catalog); err == nil {
		t.Fatal("minimum supported build above latest must be rejected")
	}
}

func TestIOSInstallPageOffersAppStoreAndPWAWithoutSideload(t *testing.T) {
	service := newAppReleaseService(t)
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).Register(mux)
	request := httptest.NewRequest(http.MethodGet, "/download/ios", nil)
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("ios install status=%d body=%s", response.Code, response.Body.String())
	}
	body := response.Body.String()
	// 已登记 iOS release 时必须同时提供 App Store 跳转与 PWA 添加主屏指引。
	if !strings.Contains(body, "https://apps.apple.com/app/id1234567890") {
		t.Fatalf("ios install page must link the registered App Store release, body=%q", body)
	}
	if !strings.Contains(body, "添加到主屏幕") {
		t.Fatalf("ios install page must keep the PWA guidance, body=%q", body)
	}
	// iOS 网页版不提供二进制下载：不得出现 IPA 侧载或 APK 链接。
	for _, forbidden := range []string{".ipa", ".apk", "itms-services"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("ios install page must not offer sideload %q, body=%q", forbidden, body)
		}
	}
}

func TestIOSInstallPageWithoutRegisteredReleaseKeepsPWAOnly(t *testing.T) {
	catalog := appReleaseCatalog()
	catalog.IOS = apprelease.Release{}
	service, err := apprelease.NewService(catalog)
	if err != nil {
		t.Fatalf("android-only release service: %v", err)
	}
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).Register(mux)
	request := httptest.NewRequest(http.MethodGet, "/download/ios", nil)
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("ios install status=%d body=%s", response.Code, response.Body.String())
	}
	body := response.Body.String()
	if strings.Contains(body, "apps.apple.com") {
		t.Fatalf("without a registered ios release the page must not fabricate an App Store link, body=%q", body)
	}
	if !strings.Contains(body, "添加到主屏幕") {
		t.Fatalf("ios install page must keep the PWA guidance, body=%q", body)
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

// spec_ref: specs/feature-tree/runtime/runtime-errors/error-code-and-response-envelope/spec.md#gwt-003
func TestAppReleaseErrorPathsUseRuntimeErrorEnvelope(t *testing.T) {
	service := newAppReleaseService(t)
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).Register(mux)

	cases := []struct {
		name       string
		target     string
		wantStatus int
		wantCode   string
	}{
		{
			name:       "invalid version query",
			target:     "/ops/app-recovery/version?platform=unknown",
			wantStatus: http.StatusBadRequest,
			wantCode:   "OPS.USER.app_release_query_invalid",
		},
		{
			name:       "unknown download route",
			target:     "/download/windows",
			wantStatus: http.StatusNotFound,
			wantCode:   "GATEWAY.USER.route_not_found",
		},
	}

	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodGet, testCase.target, nil)
			request.Header.Set("X-Request-Id", "req-envelope-1")
			response := httptest.NewRecorder()
			mux.ServeHTTP(response, request)

			if response.Code != testCase.wantStatus {
				t.Fatalf(
					"status=%d want=%d body=%s",
					response.Code,
					testCase.wantStatus,
					response.Body.String(),
				)
			}
			var envelope map[string]any
			if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
				t.Fatalf("decode error envelope: %v", err)
			}
			if envelope["code"] != testCase.wantCode {
				t.Fatalf("code=%v want=%s", envelope["code"], testCase.wantCode)
			}
			// 完整 RuntimeErrorResponse 信封：不允许退化为裸 {"code": ...}。
			userMessage, _ := envelope["userMessage"].(string)
			if strings.TrimSpace(userMessage) == "" {
				t.Fatalf("userMessage missing in envelope: %s", response.Body.String())
			}
			if envelope["requestId"] != "req-envelope-1" {
				t.Fatalf("requestId=%v want=req-envelope-1", envelope["requestId"])
			}
			for _, field := range []string{"kind", "origin", "nature"} {
				value, _ := envelope[field].(string)
				if strings.TrimSpace(value) == "" {
					t.Fatalf("%s missing in envelope: %s", field, response.Body.String())
				}
			}
		})
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-errors/error-code-and-response-envelope/spec.md#gwt-003
func TestAppReleaseVersionUnavailablePlatformEmitsCanonicalUnavailableCode(t *testing.T) {
	catalog := appReleaseCatalog()
	catalog.IOS = apprelease.Release{}
	service, err := apprelease.NewService(catalog)
	if err != nil {
		t.Fatalf("android/web-only release service: %v", err)
	}
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).Register(mux)

	request := httptest.NewRequest(
		http.MethodGet,
		"/ops/app-recovery/version?platform=ios&appVersion=1.8.0&buildNumber=18000",
		nil,
	)
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	var envelope map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode error envelope: %v", err)
	}
	if envelope["code"] != "OPS.SYSTEM.app_release_unavailable" {
		t.Fatalf("code=%v want=OPS.SYSTEM.app_release_unavailable", envelope["code"])
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
			LatestVersion:           "1.8.2",
			LatestBuild:             "18201",
			MinimumSupportedVersion: "1.8.0",
			MinimumSupportedBuild:   "18000",
			UpdateURL:               "https://apps.apple.com/app/id1234567890",
			RecoveryURL:             "https://download.quwoquan.example/download/ios",
		},
		Android: apprelease.Release{
			LatestVersion:               "1.8.2",
			LatestBuild:                 "18201",
			MinimumSupportedVersion:     "1.8.0",
			MinimumSupportedBuild:       "18000",
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
		Web: apprelease.Release{
			LatestVersion:           "1.8.2",
			LatestBuild:             "18201",
			MinimumSupportedVersion: "1.8.0",
			MinimumSupportedBuild:   "18000",
			UpdateURL:               "https://download.quwoquan.example/",
			RecoveryURL:             "https://download.quwoquan.example/download",
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
