// spec_ref: specs/feature-tree/runtime/runtime-external-integration/spec.md#sit-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-003
package local_contract

import (
	"errors"
	"testing"

	authbinding "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/authbinding"
)

func TestContentSliceDisablesUnrelatedExternalAuth(t *testing.T) {
	for _, workload := range []string{"content-release", "content-commercial", "CONTENT-COMMERCIAL"} {
		t.Run(workload, func(t *testing.T) {
			t.Setenv("QWQ_WORKLOAD", workload)
			if !authbinding.ContentSliceExternalAuthDisabled() {
				t.Fatalf("workload %q must not require unrelated external auth Providers", workload)
			}
		})
	}
	t.Setenv("QWQ_WORKLOAD", "full")
	if authbinding.ContentSliceExternalAuthDisabled() {
		t.Fatal("full workload must keep external auth enabled")
	}
}

func TestOptionalAuthBindingsReportUnavailableWhenProtectedMaterialIsMissing(t *testing.T) {
	t.Setenv("APP_ENV", "prod")
	t.Setenv("QWQ_WORKLOAD", "")
	t.Setenv(authbinding.NonPromotablePrevalidationEnv, "")
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

	if _, err := authbinding.ResolveCarrierOneTapBinding(); !errors.Is(
		err,
		authbinding.ErrAuthRuntimeCapabilityUnavailable,
	) {
		t.Fatalf("carrier binding error = %v, want unavailable sentinel", err)
	}
	if _, err := authbinding.ResolveFederatedIdentityBinding(); !errors.Is(
		err,
		authbinding.ErrAuthRuntimeCapabilityUnavailable,
	) {
		t.Fatalf("federated binding error = %v, want unavailable sentinel", err)
	}
}

func TestUnknownAuthBindingConfigurationRemainsStartupError(t *testing.T) {
	t.Setenv("APP_ENV", "unknown")
	t.Setenv("QWQ_WORKLOAD", "")
	t.Setenv(authbinding.NonPromotablePrevalidationEnv, "")

	if _, err := authbinding.ResolveCarrierOneTapBinding(); err == nil || errors.Is(
		err,
		authbinding.ErrAuthRuntimeCapabilityUnavailable,
	) {
		t.Fatalf("unknown binding configuration must not be classified as unavailable: %v", err)
	}
}
