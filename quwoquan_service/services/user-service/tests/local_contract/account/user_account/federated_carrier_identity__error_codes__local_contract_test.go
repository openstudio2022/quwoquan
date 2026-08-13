package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	runtimeerrors "quwoquan_service/runtime/errors"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
)

func assertFederatedErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	var appErr *runtimeerrors.AppError
	if !errors.As(err, &appErr) || appErr.Code.String() != wantCode {
		t.Fatalf("expected %s, got %T: %v", wantCode, err, err)
	}
}

func newWechatRejectingProviderServer(t *testing.T) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, _ *http.Request) {
			// 微信 code 置换被 provider 拒绝(错误码 40029: invalid code)。
			_ = json.NewEncoder(w).Encode(map[string]any{
				"errcode": 40029,
				"errmsg":  "invalid code",
			})
		},
	))
	t.Cleanup(server.Close)
	return server
}

func TestWechatVerifySurfacesWechatAuthFailedOnProviderRejection(t *testing.T) {
	t.Parallel()
	server := newWechatRejectingProviderServer(t)
	verifier, err := integration.NewWechatFederatedIdentityVerifier(
		integration.ProviderOAuthConfig{
			AppID:     "wx-test-app",
			AppSecret: "wx-test-secret",
			TokenURL:  server.URL,
		},
		server.Client(),
	)
	if err != nil {
		t.Fatalf("construct wechat verifier: %v", err)
	}

	_, err = verifier.Verify(context.Background(), "rejected-authorization-code")
	assertFederatedErrorCode(t, err, "USER.AUTH.wechat_auth_failed")
}

func TestAlipayVerifySurfacesAlipayAuthFailedOnMissingAuthorizationCode(
	t *testing.T,
) {
	t.Parallel()
	verifier, _, err := integration.NewAlipayFederatedIdentityVerifier(
		integration.ProviderOAuthConfig{
			AppID:                "alipay-test-app",
			AppPrivateKeyPEM:     "not-a-real-key",
			PlatformPublicKeyPEM: "not-a-real-key",
			MerchantPID:          "2088000000000000",
		},
		nil,
	)
	if err != nil {
		t.Fatalf("construct alipay verifier: %v", err)
	}

	_, err = verifier.Verify(context.Background(), "   ")
	assertFederatedErrorCode(t, err, "USER.AUTH.alipay_auth_failed")
}

func TestQqVerifySurfacesQqAuthFailedOnInvalidMobileTicket(t *testing.T) {
	t.Parallel()
	verifier, err := integration.NewQqFederatedIdentityVerifier(
		integration.ProviderOAuthConfig{AppID: "qq-test-app"},
		nil,
	)
	if err != nil {
		t.Fatalf("construct qq verifier: %v", err)
	}

	_, err = verifier.Verify(context.Background(), "not-a-qq-mobile-ticket")
	assertFederatedErrorCode(t, err, "USER.AUTH.qq_auth_failed")
}

func TestWechatVerifySurfacesSocialProviderCancelledOnCallerCancel(
	t *testing.T,
) {
	t.Parallel()
	server := newWechatRejectingProviderServer(t)
	verifier, err := integration.NewWechatFederatedIdentityVerifier(
		integration.ProviderOAuthConfig{
			AppID:     "wx-test-app",
			AppSecret: "wx-test-secret",
			TokenURL:  server.URL,
		},
		server.Client(),
	)
	if err != nil {
		t.Fatalf("construct wechat verifier: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = verifier.Verify(ctx, "cancelled-authorization-code")
	assertFederatedErrorCode(t, err, "USER.AUTH.social_provider_cancelled")
}

func TestAlipayAuthorizationRequestSurfacesSocialProviderUnavailable(
	t *testing.T,
) {
	t.Parallel()
	// 私钥材料无法解析时,授权发起必须以 unavailable 收敛,而不是崩溃或泄露细节。
	_, issuer, err := integration.NewAlipayFederatedIdentityVerifier(
		integration.ProviderOAuthConfig{
			AppID:                "alipay-test-app",
			AppPrivateKeyPEM:     "corrupted-private-key-material",
			PlatformPublicKeyPEM: "corrupted-public-key-material",
			MerchantPID:          "2088000000000000",
		},
		nil,
	)
	if err != nil {
		t.Fatalf("construct alipay verifier: %v", err)
	}

	_, err = issuer.IssueAuthorizationRequest(context.Background())
	assertFederatedErrorCode(t, err, "USER.AUTH.social_provider_unavailable")
}

func newCarrierPhoneResolver(t *testing.T) *integration.AliyunOneTapPhoneResolver {
	t.Helper()
	resolver, err := integration.NewAliyunOneTapPhoneResolver(
		"test-access-key",
		"test-access-secret",
		"localhost",
	)
	if err != nil {
		t.Fatalf("construct carrier resolver: %v", err)
	}
	return resolver
}

func TestCarrierResolveSurfacesCarrierTokenInvalidOnBlankToken(t *testing.T) {
	t.Parallel()
	resolver := newCarrierPhoneResolver(t)

	_, err := resolver.ResolvePhone(context.Background(), "   ")
	assertFederatedErrorCode(t, err, "USER.AUTH.carrier_token_invalid")
}

func TestCarrierResolveSurfacesCarrierUnavailableOnCancelledRequest(
	t *testing.T,
) {
	t.Parallel()
	resolver := newCarrierPhoneResolver(t)

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := resolver.ResolvePhone(ctx, "carrier-token")
	assertFederatedErrorCode(t, err, "USER.AUTH.carrier_unavailable")
}

func TestCarrierResolveSurfacesCarrierProviderTimeoutOnDeadlineExceeded(
	t *testing.T,
) {
	t.Parallel()
	resolver := newCarrierPhoneResolver(t)

	ctx, cancel := context.WithDeadline(
		context.Background(),
		time.Now().Add(-time.Second),
	)
	defer cancel()
	_, err := resolver.ResolvePhone(ctx, "carrier-token")
	assertFederatedErrorCode(t, err, "USER.AUTH.carrier_provider_timeout")
}
