package main

import (
	"errors"
	"testing"
)

func TestContentSliceDisablesUnrelatedExternalAuth(t *testing.T) {
	for _, workload := range []string{"content-release", "content-commercial", "CONTENT-COMMERCIAL"} {
		t.Run(workload, func(t *testing.T) {
			t.Setenv("QWQ_WORKLOAD", workload)
			if !contentSliceExternalAuthDisabled() {
				t.Fatalf("workload %q must not require unrelated external auth Providers", workload)
			}
		})
	}
	t.Setenv("QWQ_WORKLOAD", "full")
	if contentSliceExternalAuthDisabled() {
		t.Fatal("full workload must keep external auth enabled")
	}
}

func TestOptionalAuthBindingsReportUnavailableWhenProtectedMaterialIsMissing(t *testing.T) {
	t.Setenv("APP_ENV", "prod")
	t.Setenv("QWQ_WORKLOAD", "")
	t.Setenv(nonPromotablePrevalidationEnv, "")
	t.Setenv("ALIYUN_DYPNS_ENDPOINT", "")
	t.Setenv("ALIYUN_DYPNS_ACCESS_KEY_ID", "")
	t.Setenv("ALIYUN_DYPNS_ACCESS_KEY_SECRET", "")
	t.Setenv("WECHAT_OAUTH_TOKEN_URL", "")
	t.Setenv("WECHAT_OAUTH_USER_INFO_URL", "")
	t.Setenv("ALIPAY_OAUTH_TOKEN_URL", "")
	t.Setenv("ALIPAY_OAUTH_USER_INFO_URL", "")
	t.Setenv("QQ_OAUTH_USER_INFO_URL", "")
	t.Setenv("WECHAT_OAUTH_APP_ID", "")
	t.Setenv("WECHAT_OAUTH_APP_SECRET", "")
	t.Setenv("ALIPAY_OAUTH_APP_ID", "")
	t.Setenv("ALIPAY_OAUTH_APP_PRIVATE_KEY_PEM", "")
	t.Setenv("ALIPAY_OAUTH_PLATFORM_PUBLIC_KEY_PEM", "")
	t.Setenv("ALIPAY_OAUTH_MERCHANT_PID", "")
	t.Setenv("QQ_OAUTH_APP_ID", "")

	if _, err := resolveCarrierOneTapBinding(); !errors.Is(
		err,
		ErrAuthRuntimeCapabilityUnavailable,
	) {
		t.Fatalf("carrier binding error = %v, want unavailable sentinel", err)
	}
	if _, err := resolveFederatedIdentityBinding(); !errors.Is(
		err,
		ErrAuthRuntimeCapabilityUnavailable,
	) {
		t.Fatalf("federated binding error = %v, want unavailable sentinel", err)
	}
}

func TestUnknownAuthBindingConfigurationRemainsStartupError(t *testing.T) {
	t.Setenv("APP_ENV", "unknown")
	t.Setenv("QWQ_WORKLOAD", "")
	t.Setenv(nonPromotablePrevalidationEnv, "")

	if _, err := resolveCarrierOneTapBinding(); err == nil || errors.Is(
		err,
		ErrAuthRuntimeCapabilityUnavailable,
	) {
		t.Fatalf("unknown binding configuration must not be classified as unavailable: %v", err)
	}
}
