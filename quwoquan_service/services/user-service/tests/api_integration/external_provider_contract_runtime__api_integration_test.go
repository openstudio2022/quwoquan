package api_integration

import (
	"context"
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"quwoquan_service/services/user-service/internal/application"
	"quwoquan_service/services/user-service/internal/infrastructure/integration"
)

type externalProviderContractRuntime struct {
	server      *httptest.Server
	wechat      application.FederatedIdentityVerifier
	alipay      application.FederatedIdentityVerifier
	alipayIssue application.FederatedAuthorizationIssuer
	qq          application.FederatedIdentityVerifier
}

func startExternalProviderContractRuntime() (*externalProviderContractRuntime, error) {
	merchantPrivateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		return nil, fmt.Errorf("generate merchant private key: %w", err)
	}
	platformPrivateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		return nil, fmt.Errorf("generate platform private key: %w", err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/wechat/token", handleWechatToken)
	mux.HandleFunc("/wechat/user", handleWechatUser)
	mux.HandleFunc("/qq/user", handleQQUser)
	mux.HandleFunc("/alipay", func(writer http.ResponseWriter, request *http.Request) {
		handleAlipayGateway(writer, request, platformPrivateKey)
	})
	server := httptest.NewServer(mux)

	wechat, err := integration.NewWechatFederatedIdentityVerifier(
		integration.ProviderOAuthConfig{
			AppID:       "wechat-contract-app",
			AppSecret:   "wechat-contract-secret",
			TokenURL:    server.URL + "/wechat/token",
			UserInfoURL: server.URL + "/wechat/user",
		},
		server.Client(),
	)
	if err != nil {
		return nil, fmt.Errorf("build wechat verifier: %w", err)
	}
	alipay, alipayIssue, err := integration.NewAlipayFederatedIdentityVerifier(
		integration.ProviderOAuthConfig{
			AppID:                "alipay-contract-app",
			AppPrivateKeyPEM:     encodeRSAPrivateKey(merchantPrivateKey),
			PlatformPublicKeyPEM: encodeRSAPublicKey(&platformPrivateKey.PublicKey),
			MerchantPID:          "2088000000000000",
			TokenURL:             server.URL + "/alipay",
			UserInfoURL:          server.URL + "/alipay",
		},
		server.Client(),
	)
	if err != nil {
		return nil, fmt.Errorf("build alipay verifier: %w", err)
	}
	qq, err := integration.NewQqFederatedIdentityVerifier(
		integration.ProviderOAuthConfig{
			AppID:       "qq-contract-app",
			UserInfoURL: server.URL + "/qq/user",
		},
		server.Client(),
	)
	if err != nil {
		return nil, fmt.Errorf("build qq verifier: %w", err)
	}
	return &externalProviderContractRuntime{
		server:      server,
		wechat:      wechat,
		alipay:      alipay,
		alipayIssue: alipayIssue,
		qq:          qq,
	}, nil
}

func (runtime *externalProviderContractRuntime) Close() {
	if runtime != nil && runtime.server != nil {
		runtime.server.Close()
	}
}

func handleWechatToken(writer http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodGet ||
		request.URL.Query().Get("appid") != "wechat-contract-app" ||
		request.URL.Query().Get("secret") != "wechat-contract-secret" ||
		request.URL.Query().Get("grant_type") != "authorization_code" {
		http.Error(writer, "invalid wechat token request", http.StatusBadRequest)
		return
	}
	code := strings.TrimSpace(request.URL.Query().Get("code"))
	if code == "" {
		http.Error(writer, "wechat code required", http.StatusBadRequest)
		return
	}
	suffix := stableProviderSuffix(code)
	writeJSON(writer, map[string]any{
		"access_token": "wechat-access-" + suffix,
		"openid":       "wechat-open-" + suffix,
		"unionid":      "wechat-union-" + suffix,
		"scope":        "snsapi_userinfo",
	})
}

func handleWechatUser(writer http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodGet ||
		!strings.HasPrefix(request.URL.Query().Get("access_token"), "wechat-access-") ||
		!strings.HasPrefix(request.URL.Query().Get("openid"), "wechat-open-") {
		http.Error(writer, "invalid wechat user request", http.StatusBadRequest)
		return
	}
	openID := request.URL.Query().Get("openid")
	writeJSON(writer, map[string]any{
		"nickname":   "微信契约用户",
		"headimgurl": "https://cdn.quwoquan.test/provider/wechat/" + url.PathEscape(openID) + ".png",
	})
}

func handleQQUser(writer http.ResponseWriter, request *http.Request) {
	query := request.URL.Query()
	if request.Method != http.MethodGet ||
		query.Get("oauth_consumer_key") != "qq-contract-app" ||
		strings.TrimSpace(query.Get("access_token")) == "" ||
		strings.TrimSpace(query.Get("openid")) == "" ||
		query.Get("format") != "json" {
		http.Error(writer, "invalid qq user request", http.StatusBadRequest)
		return
	}
	writeJSON(writer, map[string]any{
		"ret":            0,
		"nickname":       "QQ契约用户",
		"figureurl_qq_2": "https://cdn.quwoquan.test/provider/qq/" + url.PathEscape(query.Get("openid")) + ".png",
	})
}

func handleAlipayGateway(writer http.ResponseWriter, request *http.Request, platformPrivateKey *rsa.PrivateKey) {
	if request.Method != http.MethodPost {
		http.Error(writer, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if err := request.ParseForm(); err != nil {
		http.Error(writer, "invalid form", http.StatusBadRequest)
		return
	}
	if request.PostForm.Get("app_id") != "alipay-contract-app" ||
		request.PostForm.Get("sign_type") != "RSA2" ||
		strings.TrimSpace(request.PostForm.Get("sign")) == "" {
		http.Error(writer, "invalid alipay request", http.StatusBadRequest)
		return
	}

	var responseKey string
	var payload []byte
	var err error
	switch request.PostForm.Get("method") {
	case "alipay.system.oauth.token":
		code := strings.TrimSpace(request.PostForm.Get("code"))
		if code == "" || request.PostForm.Get("grant_type") != "authorization_code" {
			http.Error(writer, "invalid alipay token request", http.StatusBadRequest)
			return
		}
		suffix := stableProviderSuffix(code)
		responseKey = "alipay_system_oauth_token_response"
		payload, err = json.Marshal(map[string]string{
			"code":         "10000",
			"access_token": "alipay-access-" + suffix,
			"user_id":      "alipay-user-" + suffix,
			"open_id":      "alipay-open-" + suffix,
		})
	case "alipay.user.info.share":
		if !strings.HasPrefix(request.PostForm.Get("auth_token"), "alipay-access-") {
			http.Error(writer, "invalid alipay profile request", http.StatusBadRequest)
			return
		}
		responseKey = "alipay_user_info_share_response"
		payload, err = json.Marshal(map[string]string{
			"code":      "10000",
			"nick_name": "支付宝契约用户",
			"avatar":    "https://cdn.quwoquan.test/provider/alipay/avatar.png",
		})
	default:
		http.Error(writer, "unsupported alipay method", http.StatusBadRequest)
		return
	}
	if err != nil {
		http.Error(writer, "marshal alipay response", http.StatusInternalServerError)
		return
	}

	signature, err := signProviderPayload(payload, platformPrivateKey)
	if err != nil {
		http.Error(writer, "sign alipay response", http.StatusInternalServerError)
		return
	}
	encodedSignature, _ := json.Marshal(signature)
	writer.Header().Set("Content-Type", "application/json")
	_, _ = writer.Write([]byte(`{"` + responseKey + `":`))
	_, _ = writer.Write(payload)
	_, _ = writer.Write([]byte(`,"sign":`))
	_, _ = writer.Write(encodedSignature)
	_, _ = writer.Write([]byte(`}`))
}

func signProviderPayload(payload []byte, key *rsa.PrivateKey) (string, error) {
	digest := sha256.Sum256(payload)
	signature, err := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, digest[:])
	if err != nil {
		return "", err
	}
	return base64.StdEncoding.EncodeToString(signature), nil
}

func encodeRSAPrivateKey(key *rsa.PrivateKey) string {
	encoded, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		panic(err)
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: encoded}))
}

func encodeRSAPublicKey(key *rsa.PublicKey) string {
	encoded, err := x509.MarshalPKIXPublicKey(key)
	if err != nil {
		panic(err)
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: encoded}))
}

func stableProviderSuffix(value string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(digest[:6])
}

func qqAuthorizationTicket(accessToken, openID string) string {
	payload, err := json.Marshal(map[string]string{
		"accessToken": accessToken,
		"openId":      openID,
	})
	if err != nil {
		panic(err)
	}
	return string(payload)
}

func writeJSON(writer http.ResponseWriter, value any) {
	writer.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(writer).Encode(value)
}

func TestExternalProviderContractRuntime_ProductionClientExchangesAllProviders(t *testing.T) {
	if externalProviderRuntime == nil {
		t.Fatal("external provider contract runtime is not initialized")
	}
	cases := []struct {
		name     string
		verifier application.FederatedIdentityVerifier
		code     string
	}{
		{name: "wechat", verifier: externalProviderRuntime.wechat, code: "wechat-contract-direct"},
		{name: "alipay", verifier: externalProviderRuntime.alipay, code: "alipay-contract-direct"},
		{name: "qq", verifier: externalProviderRuntime.qq, code: qqAuthorizationTicket("qq-access-direct", "qq-open-direct")},
	}
	for _, item := range cases {
		identity, err := item.verifier.Verify(context.Background(), item.code)
		if err != nil {
			t.Fatalf("exchange %s: %v", item.name, err)
		}
		if identity.CredentialKey == "" || identity.AvatarURL == "" {
			t.Fatalf("unexpected %s identity: %#v", item.name, identity)
		}
	}
}
