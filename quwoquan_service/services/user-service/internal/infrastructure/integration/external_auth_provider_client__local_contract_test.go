package integration

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/user-service/internal/application"
)

type externalAuthRoundTripFunc func(*http.Request) (*http.Response, error)

func (f externalAuthRoundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return f(request)
}

func TestHTTPExternalAuthProviderUnavailableWhenUnconfigured(t *testing.T) {
	client := NewHTTPExternalAuthProviderClient(map[string]ProviderOAuthConfig{}, nil)
	if client.Supports("wechat") {
		t.Fatal("unconfigured provider must not report supported")
	}
	if _, err := client.Exchange(context.Background(), "alipay", "code", "ios", "1.0.0"); err == nil {
		t.Fatal("unconfigured provider must return structured unavailable, not fake success")
	}
}

func TestHTTPExternalAuthProviderCreatesServerSignedAlipayAuthorization(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	privateDER, err := x509.MarshalPKCS8PrivateKey(privateKey)
	if err != nil {
		t.Fatalf("marshal private key: %v", err)
	}
	privatePEM := string(pem.EncodeToMemory(&pem.Block{
		Type:  "PRIVATE KEY",
		Bytes: privateDER,
	}))
	publicDER, err := x509.MarshalPKIXPublicKey(&privateKey.PublicKey)
	if err != nil {
		t.Fatalf("marshal public key: %v", err)
	}
	publicPEM := string(pem.EncodeToMemory(&pem.Block{
		Type:  "PUBLIC KEY",
		Bytes: publicDER,
	}))
	client := NewHTTPExternalAuthProviderClient(
		map[string]ProviderOAuthConfig{
			application.SocialProviderAlipay: {
				AppID:                "alipay-app-id",
				AppPrivateKeyPEM:     privatePEM,
				PlatformPublicKeyPEM: publicPEM,
				MerchantPID:          "2088000000000000",
			},
		},
		nil,
	)

	payload, expiresAt, err := client.CreateAuthorizationRequest(
		context.Background(),
		application.SocialProviderAlipay,
	)
	if err != nil {
		t.Fatalf("create alipay authorization: %v", err)
	}
	values, err := url.ParseQuery(payload)
	if err != nil {
		t.Fatalf("parse authorization payload: %v", err)
	}
	if values.Get("sign") == "" || values.Get("target_id") == "" {
		t.Fatalf("signed authorization payload missing sign/target_id: %v", values)
	}
	if values.Get("app_id") != "alipay-app-id" ||
		values.Get("pid") != "2088000000000000" ||
		values.Get("product_id") != "APP_FAST_LOGIN" {
		t.Fatalf("unexpected authorization contract: %v", values)
	}
	if !expiresAt.After(time.Now().UTC()) {
		t.Fatalf("authorization must have a future expiry: %v", expiresAt)
	}
	if strings.Contains(payload, "PRIVATE KEY") {
		t.Fatal("authorization payload leaked private key")
	}
}

func TestHTTPExternalAuthProviderVerifiesQqMobileTicket(t *testing.T) {
	const (
		accessToken = "qq-access-token-security-contract"
		openID      = "qq-open-id-contract"
	)
	httpClient := &http.Client{
		Transport: externalAuthRoundTripFunc(func(request *http.Request) (*http.Response, error) {
			query := request.URL.Query()
			if query.Get("access_token") != accessToken || query.Get("openid") != openID {
				t.Fatalf("QQ identity verification did not receive SDK token/openId")
			}
			return &http.Response{
				StatusCode: http.StatusOK,
				Header:     make(http.Header),
				Body: io.NopCloser(strings.NewReader(
					`{"ret":0,"nickname":"QQ用户","figureurl_qq_2":"https://qlogo.example.test/avatar"}`,
				)),
			}, nil
		}),
	}
	client := NewHTTPExternalAuthProviderClient(
		map[string]ProviderOAuthConfig{
			application.SocialProviderQq: {
				AppID:       "qq-app-id",
				UserInfoURL: "https://provider.example.test/qq/user",
			},
		},
		httpClient,
	)

	identity, err := client.Exchange(
		context.Background(),
		application.SocialProviderQq,
		`{"accessToken":"`+accessToken+`","openId":"`+openID+`"}`,
		"android",
		"1.0.0",
	)
	if err != nil {
		t.Fatalf("QQ exchange: %v", err)
	}
	if identity.OpenID != openID || identity.DisplayName != "QQ用户" {
		t.Fatalf("unexpected QQ identity: %#v", identity)
	}
}

func TestHTTPExternalAuthProviderErrorsNeverExposeOAuthCredentials(t *testing.T) {
	const (
		appID     = "wechat-app-id-security-contract"
		appSecret = "wechat-secret-security-contract"
		authCode  = "wechat-auth-code-security-contract"
	)
	httpClient := &http.Client{
		Transport: externalAuthRoundTripFunc(func(request *http.Request) (*http.Response, error) {
			return nil, errors.New("dial failed for " + request.URL.String())
		}),
	}
	client := NewHTTPExternalAuthProviderClient(
		map[string]ProviderOAuthConfig{
			application.SocialProviderWechat: {
				AppID:     appID,
				AppSecret: appSecret,
				TokenURL:  "https://provider.example.test/oauth/token",
			},
		},
		httpClient,
	)

	_, err := client.Exchange(context.Background(), "wechat", authCode, "ios", "1.0.0")
	if err == nil {
		t.Fatal("provider transport failure must be returned")
	}
	for _, sensitiveValue := range []string{appID, appSecret, authCode, "provider.example.test"} {
		if strings.Contains(err.Error(), sensitiveValue) {
			t.Fatalf("provider error leaked sensitive value %q: %v", sensitiveValue, err)
		}
	}
}

func TestHTTPExternalAuthProviderRejectMessageIsRedacted(t *testing.T) {
	const echoedAuthorizationCode = "echoed-auth-code-security-contract"
	httpClient := &http.Client{
		Transport: externalAuthRoundTripFunc(func(_ *http.Request) (*http.Response, error) {
			return &http.Response{
				StatusCode: http.StatusOK,
				Header:     make(http.Header),
				Body: io.NopCloser(strings.NewReader(
					`{"errcode":40029,"errmsg":"invalid code ` + echoedAuthorizationCode + `"}`,
				)),
			}, nil
		}),
	}
	client := NewHTTPExternalAuthProviderClient(
		map[string]ProviderOAuthConfig{
			application.SocialProviderWechat: {
				AppID:     "app-id",
				AppSecret: "app-secret",
				TokenURL:  "https://provider.example.test/oauth/token",
			},
		},
		httpClient,
	)

	_, err := client.Exchange(context.Background(), "wechat", "request-code", "ios", "1.0.0")
	if err == nil {
		t.Fatal("provider rejection must be returned")
	}
	if strings.Contains(err.Error(), echoedAuthorizationCode) {
		t.Fatalf("provider rejection leaked upstream message: %v", err)
	}
	if !strings.Contains(err.Error(), "provider code 40029") {
		t.Fatalf("provider rejection must retain safe diagnostic code: %v", err)
	}
}
