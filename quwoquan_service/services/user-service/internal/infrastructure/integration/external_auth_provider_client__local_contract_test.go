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
)

type externalAuthRoundTripFunc func(*http.Request) (*http.Response, error)

func (f externalAuthRoundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return f(request)
}

func TestFederatedIdentityVerifierFailsClosedWhenUnconfigured(t *testing.T) {
	if _, err := NewWechatFederatedIdentityVerifier(ProviderOAuthConfig{}, nil); err == nil {
		t.Fatal("unconfigured verifier must fail composition")
	}
}

func TestFederatedIdentityVerifierCreatesServerSignedAlipayAuthorization(t *testing.T) {
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
	_, issuer, err := NewAlipayFederatedIdentityVerifier(
		ProviderOAuthConfig{
			AppID:                "alipay-app-id",
			AppPrivateKeyPEM:     privatePEM,
			PlatformPublicKeyPEM: publicPEM,
			MerchantPID:          "2088000000000000",
		},
		nil,
	)
	if err != nil {
		t.Fatalf("build alipay verifier: %v", err)
	}
	request, err := issuer.IssueAuthorizationRequest(context.Background())
	if err != nil {
		t.Fatalf("create alipay authorization: %v", err)
	}
	values, err := url.ParseQuery(request.Payload)
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
	if !request.ExpiresAt.After(time.Now().UTC()) {
		t.Fatalf("authorization must have a future expiry: %v", request.ExpiresAt)
	}
	if strings.Contains(request.Payload, "PRIVATE KEY") {
		t.Fatal("authorization payload leaked private key")
	}
}

func TestFederatedIdentityVerifierVerifiesQqMobileTicket(t *testing.T) {
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
	verifier, err := NewQqFederatedIdentityVerifier(
		ProviderOAuthConfig{
			AppID:       "qq-app-id",
			UserInfoURL: "https://provider.example.test/qq/user",
		},
		httpClient,
	)
	if err != nil {
		t.Fatalf("build QQ verifier: %v", err)
	}
	identity, err := verifier.Verify(
		context.Background(),
		`{"accessToken":"`+accessToken+`","openId":"`+openID+`"}`,
	)
	if err != nil {
		t.Fatalf("QQ exchange: %v", err)
	}
	if identity.CredentialKey != "qq:"+openID ||
		identity.DisplayName != "QQ用户" {
		t.Fatalf("unexpected normalized identity: %#v", identity)
	}
}

func TestFederatedIdentityVerifierErrorsNeverExposeOAuthCredentials(t *testing.T) {
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
	verifier, err := NewWechatFederatedIdentityVerifier(
		ProviderOAuthConfig{
			AppID:     appID,
			AppSecret: appSecret,
			TokenURL:  "https://provider.example.test/oauth/token",
		},
		httpClient,
	)
	if err != nil {
		t.Fatalf("build verifier: %v", err)
	}
	_, err = verifier.Verify(context.Background(), authCode)
	if err == nil {
		t.Fatal("provider transport failure must be returned")
	}
	for _, sensitiveValue := range []string{appID, appSecret, authCode, "provider.example.test"} {
		if strings.Contains(err.Error(), sensitiveValue) {
			t.Fatalf("provider error leaked sensitive value %q: %v", sensitiveValue, err)
		}
	}
}

func TestFederatedIdentityVerifierRejectMessageIsRedacted(t *testing.T) {
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
	verifier, err := NewWechatFederatedIdentityVerifier(
		ProviderOAuthConfig{
			AppID:     "app-id",
			AppSecret: "app-secret",
			TokenURL:  "https://provider.example.test/oauth/token",
		},
		httpClient,
	)
	if err != nil {
		t.Fatalf("build verifier: %v", err)
	}
	_, err = verifier.Verify(context.Background(), "request-code")
	if err == nil {
		t.Fatal("provider rejection must be returned")
	}
	if strings.Contains(err.Error(), echoedAuthorizationCode) {
		t.Fatalf("provider rejection leaked upstream message: %v", err)
	}
}
