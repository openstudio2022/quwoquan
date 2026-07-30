package integration

import (
	"bytes"
	"context"
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"

	sessiongenerated "quwoquan_service/services/user-service/generated/account/account_session"
	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

// ProviderOAuthConfig 是一个已绑定认证适配器的运行配置。
type ProviderOAuthConfig struct {
	AppID                string
	AppSecret            string
	AppPrivateKeyPEM     string
	PlatformPublicKeyPEM string
	MerchantPID          string
	TokenURL             string
	UserInfoURL          string
}

type providerKind string

const (
	providerWechat providerKind = "wechat"
	providerAlipay providerKind = "alipay"
	providerQq     providerKind = "qq"
)

// HTTPFederatedIdentityVerifier binds exactly one concrete protocol
// implementation. There is deliberately no runtime provider selector.
type HTTPFederatedIdentityVerifier struct {
	kind   providerKind
	config ProviderOAuthConfig
	client *http.Client
}

func NewWechatFederatedIdentityVerifier(
	config ProviderOAuthConfig,
	client *http.Client,
) (application.FederatedIdentityVerifier, error) {
	return newHTTPFederatedIdentityVerifier(providerWechat, config, client)
}

func NewAlipayFederatedIdentityVerifier(
	config ProviderOAuthConfig,
	client *http.Client,
) (application.FederatedIdentityVerifier, application.FederatedAuthorizationIssuer, error) {
	verifier, err := newHTTPFederatedIdentityVerifier(providerAlipay, config, client)
	if err != nil {
		return nil, nil, err
	}
	return verifier, verifier, nil
}

func NewQqFederatedIdentityVerifier(
	config ProviderOAuthConfig,
	client *http.Client,
) (application.FederatedIdentityVerifier, error) {
	return newHTTPFederatedIdentityVerifier(providerQq, config, client)
}

func newHTTPFederatedIdentityVerifier(
	kind providerKind,
	config ProviderOAuthConfig,
	client *http.Client,
) (*HTTPFederatedIdentityVerifier, error) {
	if !isConfigured(kind, config) {
		return nil, fmt.Errorf("federated identity adapter is not configured")
	}
	if client == nil {
		client = &http.Client{Timeout: 5 * time.Second}
	}
	return &HTTPFederatedIdentityVerifier{
		kind:   kind,
		config: config,
		client: client,
	}, nil
}

func isConfigured(kind providerKind, config ProviderOAuthConfig) bool {
	if strings.TrimSpace(config.AppID) == "" {
		return false
	}
	switch kind {
	case providerWechat:
		return strings.TrimSpace(config.AppSecret) != ""
	case providerAlipay:
		return strings.TrimSpace(config.AppPrivateKeyPEM) != "" &&
			strings.TrimSpace(config.PlatformPublicKeyPEM) != "" &&
			strings.TrimSpace(config.MerchantPID) != ""
	case providerQq:
		return true
	default:
		return false
	}
}

func (c *HTTPFederatedIdentityVerifier) IssueAuthorizationRequest(
	_ context.Context,
) (application.FederatedAuthorizationRequest, error) {
	if c == nil || c.kind != providerAlipay {
		return application.FederatedAuthorizationRequest{},
			sessiongenerated.AppErrorFromSocialProviderUnavailable("federated authorization unavailable")
	}
	privateKey, err := parseRSAPrivateKey(c.config.AppPrivateKeyPEM)
	if err != nil {
		return application.FederatedAuthorizationRequest{},
			sessiongenerated.AppErrorFromSocialProviderUnavailable("federated authorization unavailable")
	}
	nonce := make([]byte, 24)
	if _, err := rand.Read(nonce); err != nil {
		return application.FederatedAuthorizationRequest{},
			sessiongenerated.AppErrorFromSocialProviderUnavailable("federated authorization unavailable")
	}
	values := url.Values{
		"apiname":    {"com.alipay.account.auth"},
		"method":     {"alipay.open.auth.sdk.code.get"},
		"app_id":     {c.config.AppID},
		"app_name":   {"mc"},
		"biz_type":   {"openservice"},
		"pid":        {c.config.MerchantPID},
		"product_id": {"APP_FAST_LOGIN"},
		"scope":      {"kuaijie"},
		"target_id":  {base64.RawURLEncoding.EncodeToString(nonce)},
		"auth_type":  {"AUTHACCOUNT"},
		"sign_type":  {"RSA2"},
	}
	signature, err := signAlipayValues(values, privateKey)
	if err != nil {
		return application.FederatedAuthorizationRequest{},
			sessiongenerated.AppErrorFromSocialProviderUnavailable("federated authorization unavailable")
	}
	values.Set("sign", signature)
	return application.FederatedAuthorizationRequest{
		Payload:   values.Encode(),
		ExpiresAt: time.Now().UTC().Add(5 * time.Minute),
	}, nil
}

func (c *HTTPFederatedIdentityVerifier) Verify(
	ctx context.Context,
	authorizationCode string,
) (application.VerifiedFederatedIdentity, error) {
	if c == nil {
		return application.VerifiedFederatedIdentity{},
			sessiongenerated.AppErrorFromSocialProviderUnavailable("federated identity adapter unavailable")
	}
	var (
		identity providerIdentity
		err      error
	)
	switch c.kind {
	case providerWechat:
		identity, err = c.exchangeWechat(ctx, c.config, strings.TrimSpace(authorizationCode))
	case providerAlipay:
		identity, err = c.exchangeAlipay(ctx, c.config, strings.TrimSpace(authorizationCode))
	case providerQq:
		identity, err = c.exchangeQq(ctx, c.config, strings.TrimSpace(authorizationCode))
	default:
		return application.VerifiedFederatedIdentity{},
			sessiongenerated.AppErrorFromSocialProviderUnavailable("federated identity adapter unavailable")
	}
	if err != nil {
		return application.VerifiedFederatedIdentity{}, c.mapVerificationFailure(err)
	}
	return c.normalizeIdentity(identity)
}

type providerIdentity struct {
	OpenID      string
	UnionID     string
	AppID       string
	DisplayName string
	AvatarURL   string
}

func (c *HTTPFederatedIdentityVerifier) normalizeIdentity(
	identity providerIdentity,
) (application.VerifiedFederatedIdentity, error) {
	stableID := firstNonEmpty(identity.UnionID, identity.OpenID)
	if stableID == "" {
		return application.VerifiedFederatedIdentity{},
			c.mapVerificationFailure(errors.New("provider response identity missing"))
	}
	var credentialType credentialmodel.CredentialType
	switch c.kind {
	case providerWechat:
		credentialType = credentialmodel.CredentialTypeFederatedSlotA
	case providerAlipay:
		credentialType = credentialmodel.CredentialTypeFederatedSlotB
	case providerQq:
		credentialType = credentialmodel.CredentialTypeFederatedSlotC
	default:
		return application.VerifiedFederatedIdentity{},
			sessiongenerated.AppErrorFromSocialProviderUnavailable("federated identity adapter unavailable")
	}
	return application.VerifiedFederatedIdentity{
		CredentialType: credentialType,
		CredentialKey:  string(c.kind) + ":" + stableID,
		DisplayName:    identity.DisplayName,
		AvatarURL:      identity.AvatarURL,
	}, nil
}

func (c *HTTPFederatedIdentityVerifier) mapVerificationFailure(err error) error {
	if errors.Is(err, context.Canceled) || strings.Contains(strings.ToLower(err.Error()), "cancel") {
		return sessiongenerated.AppErrorFromSocialProviderCancelled("federated authorization cancelled")
	}
	if errors.Is(err, context.DeadlineExceeded) ||
		strings.Contains(strings.ToLower(err.Error()), "timeout") ||
		strings.Contains(strings.ToLower(err.Error()), "unavailable") {
		return sessiongenerated.AppErrorFromSocialProviderUnavailable("federated identity adapter unavailable")
	}
	switch c.kind {
	case providerWechat:
		return sessiongenerated.AppErrorFromWechatAuthFailed("federated authorization verification failed")
	case providerAlipay:
		return sessiongenerated.AppErrorFromAlipayAuthFailed("federated authorization verification failed")
	case providerQq:
		return sessiongenerated.AppErrorFromQqAuthFailed("federated authorization verification failed")
	default:
		return sessiongenerated.AppErrorFromSocialProviderUnavailable("federated identity adapter unavailable")
	}
}

// exchangeWechat 实现微信开放平台 code 换 openid/unionid 的标准流程。
func (c *HTTPFederatedIdentityVerifier) exchangeWechat(ctx context.Context, cfg ProviderOAuthConfig, code string) (providerIdentity, error) {
	tokenURL := strings.TrimSpace(cfg.TokenURL)
	if tokenURL == "" {
		tokenURL = "https://api.weixin.qq.com/sns/oauth2/access_token"
	}
	q := url.Values{}
	q.Set("appid", cfg.AppID)
	q.Set("secret", cfg.AppSecret)
	q.Set("code", code)
	q.Set("grant_type", "authorization_code")
	var tokenResp struct {
		AccessToken string `json:"access_token"`
		OpenID      string `json:"openid"`
		UnionID     string `json:"unionid"`
		Scope       string `json:"scope"`
		ErrCode     int    `json:"errcode"`
		ErrMsg      string `json:"errmsg"`
	}
	if err := c.getJSON(ctx, tokenURL+"?"+q.Encode(), &tokenResp); err != nil {
		return providerIdentity{}, fmt.Errorf("wechat token exchange failed: %w", err)
	}
	if tokenResp.ErrCode != 0 {
		return providerIdentity{}, fmt.Errorf(
			"wechat token exchange rejected with provider code %d",
			tokenResp.ErrCode,
		)
	}
	identity := providerIdentity{
		OpenID:  tokenResp.OpenID,
		UnionID: tokenResp.UnionID,
		AppID:   cfg.AppID,
	}
	userInfoURL := strings.TrimSpace(cfg.UserInfoURL)
	if userInfoURL == "" {
		userInfoURL = "https://api.weixin.qq.com/sns/userinfo"
	}
	uq := url.Values{}
	uq.Set("access_token", tokenResp.AccessToken)
	uq.Set("openid", tokenResp.OpenID)
	var userResp struct {
		Nickname   string `json:"nickname"`
		HeadImgURL string `json:"headimgurl"`
		UnionID    string `json:"unionid"`
		ErrCode    int    `json:"errcode"`
	}
	if err := c.getJSON(ctx, userInfoURL+"?"+uq.Encode(), &userResp); err == nil && userResp.ErrCode == 0 {
		identity.DisplayName = userResp.Nickname
		identity.AvatarURL = userResp.HeadImgURL
		if strings.TrimSpace(identity.UnionID) == "" {
			identity.UnionID = userResp.UnionID
		}
	}
	return identity, nil
}

// exchangeAlipay 使用支付宝 OpenAPI RSA2 网关完成 authCode 置换，并校验响应签名。
func (c *HTTPFederatedIdentityVerifier) exchangeAlipay(
	ctx context.Context,
	cfg ProviderOAuthConfig,
	authCode string,
) (providerIdentity, error) {
	if authCode == "" {
		return providerIdentity{}, errors.New("alipay authorization code required")
	}
	gatewayURL := strings.TrimSpace(cfg.TokenURL)
	if gatewayURL == "" {
		gatewayURL = "https://openapi.alipay.com/gateway.do"
	}
	tokenPayload, err := c.postAlipayGateway(
		ctx,
		cfg,
		gatewayURL,
		"alipay.system.oauth.token",
		url.Values{
			"grant_type": {"authorization_code"},
			"code":       {authCode},
		},
	)
	if err != nil {
		return providerIdentity{}, err
	}
	var token struct {
		AccessToken string `json:"access_token"`
		UserID      string `json:"user_id"`
		OpenID      string `json:"open_id"`
	}
	if err := json.Unmarshal(tokenPayload, &token); err != nil ||
		strings.TrimSpace(token.AccessToken) == "" ||
		(strings.TrimSpace(token.UserID) == "" && strings.TrimSpace(token.OpenID) == "") {
		return providerIdentity{}, errors.New("alipay provider response invalid")
	}

	identity := providerIdentity{
		UnionID: strings.TrimSpace(token.UserID),
		OpenID:  firstNonEmpty(strings.TrimSpace(token.OpenID), strings.TrimSpace(token.UserID)),
		AppID:   cfg.AppID,
	}
	userInfoURL := strings.TrimSpace(cfg.UserInfoURL)
	if userInfoURL == "" {
		userInfoURL = gatewayURL
	}
	profilePayload, profileErr := c.postAlipayGateway(
		ctx,
		cfg,
		userInfoURL,
		"alipay.user.info.share",
		url.Values{"auth_token": {token.AccessToken}},
	)
	if profileErr == nil {
		var profile struct {
			NickName string `json:"nick_name"`
			Avatar   string `json:"avatar"`
		}
		if json.Unmarshal(profilePayload, &profile) == nil {
			identity.DisplayName = strings.TrimSpace(profile.NickName)
			identity.AvatarURL = strings.TrimSpace(profile.Avatar)
		}
	}
	return identity, nil
}

// exchangeQq 校验移动 SDK 返回的 accessToken+openId 票据。QQ OpenAPI 的
// get_user_info 同时消费两者，ret=0 才证明该 token 可访问该 openId。
func (c *HTTPFederatedIdentityVerifier) exchangeQq(
	ctx context.Context,
	cfg ProviderOAuthConfig,
	authCode string,
) (providerIdentity, error) {
	token, openID, err := parseQqMobileTicket(authCode)
	if err != nil {
		return providerIdentity{}, err
	}
	userInfoURL := strings.TrimSpace(cfg.UserInfoURL)
	if userInfoURL == "" {
		userInfoURL = "https://graph.qq.com/user/get_user_info"
	}
	q := url.Values{
		"access_token":       {token},
		"oauth_consumer_key": {cfg.AppID},
		"openid":             {openID},
		"format":             {"json"},
	}
	var profile struct {
		Ret       int    `json:"ret"`
		Nickname  string `json:"nickname"`
		FigureURL string `json:"figureurl_qq_2"`
	}
	if err := c.getJSON(ctx, userInfoURL+"?"+q.Encode(), &profile); err != nil {
		return providerIdentity{}, err
	}
	if profile.Ret != 0 {
		return providerIdentity{}, errors.New("qq provider authorization rejected")
	}
	return providerIdentity{
		OpenID:      openID,
		AppID:       cfg.AppID,
		DisplayName: strings.TrimSpace(profile.Nickname),
		AvatarURL:   strings.TrimSpace(profile.FigureURL),
	}, nil
}

func parseQqMobileTicket(ticket string) (accessToken string, openID string, err error) {
	ticket = strings.TrimSpace(ticket)
	// Frozen first-party/provider boundary prefix. `_v1` is the sole canonical
	// byte sequence and is not a multi-version negotiation envelope.
	const prefix = "qq_mobile_v1."
	if !strings.HasPrefix(ticket, prefix) {
		return "", "", errors.New("qq authorization ticket invalid")
	}
	raw, decodeErr := base64.RawURLEncoding.DecodeString(strings.TrimPrefix(ticket, prefix))
	if decodeErr != nil {
		return "", "", errors.New("qq authorization ticket invalid")
	}
	var payload struct {
		AccessToken string `json:"accessToken"`
		OpenID      string `json:"openId"`
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&payload) != nil {
		return "", "", errors.New("qq authorization ticket invalid")
	}
	if decodeErr = decoder.Decode(&struct{}{}); decodeErr != io.EOF {
		return "", "", errors.New("qq authorization ticket invalid")
	}
	accessToken = strings.TrimSpace(payload.AccessToken)
	openID = strings.TrimSpace(payload.OpenID)
	if accessToken == "" || openID == "" {
		return "", "", errors.New("qq authorization ticket invalid")
	}
	return accessToken, openID, nil
}

func (c *HTTPFederatedIdentityVerifier) postAlipayGateway(
	ctx context.Context,
	cfg ProviderOAuthConfig,
	endpoint string,
	method string,
	extra url.Values,
) (json.RawMessage, error) {
	privateKey, err := parseRSAPrivateKey(cfg.AppPrivateKeyPEM)
	if err != nil {
		return nil, errors.New("alipay provider unavailable")
	}
	values := url.Values{
		"app_id":    {cfg.AppID},
		"method":    {method},
		"format":    {"JSON"},
		"charset":   {"utf-8"},
		"sign_type": {"RSA2"},
		"timestamp": {time.Now().In(time.FixedZone("CST", 8*60*60)).Format("2006-01-02 15:04:05")},
		"version":   {"1.0"},
	}
	for key, entries := range extra {
		for _, entry := range entries {
			values.Add(key, entry)
		}
	}
	signature, err := signAlipayValues(values, privateKey)
	if err != nil {
		return nil, errors.New("alipay provider unavailable")
	}
	values.Set("sign", signature)

	var response map[string]json.RawMessage
	if err := c.postFormJSON(ctx, endpoint, values, &response); err != nil {
		return nil, err
	}
	responseKey := strings.ReplaceAll(method, ".", "_") + "_response"
	payload := response[responseKey]
	if len(payload) == 0 {
		return nil, errors.New("alipay provider response invalid")
	}
	var providerSignature string
	_ = json.Unmarshal(response["sign"], &providerSignature)
	publicKey, err := parseRSAPublicKey(cfg.PlatformPublicKeyPEM)
	if err != nil || !verifyAlipayPayload(payload, providerSignature, publicKey) {
		return nil, errors.New("alipay provider response signature invalid")
	}
	var status struct {
		Code string `json:"code"`
	}
	if json.Unmarshal(payload, &status) != nil {
		return nil, errors.New("alipay provider response invalid")
	}
	if status.Code != "" && status.Code != "10000" {
		return nil, errors.New("alipay provider authorization rejected")
	}
	return payload, nil
}

func signAlipayValues(values url.Values, key *rsa.PrivateKey) (string, error) {
	keys := make([]string, 0, len(values))
	for key, entries := range values {
		if key == "sign" || len(entries) == 0 || strings.TrimSpace(entries[0]) == "" {
			continue
		}
		keys = append(keys, key)
	}
	sort.Strings(keys)
	parts := make([]string, 0, len(keys))
	for _, key := range keys {
		parts = append(parts, key+"="+values.Get(key))
	}
	digest := sha256.Sum256([]byte(strings.Join(parts, "&")))
	signature, err := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, digest[:])
	if err != nil {
		return "", err
	}
	return base64.StdEncoding.EncodeToString(signature), nil
}

func verifyAlipayPayload(payload []byte, signatureText string, key *rsa.PublicKey) bool {
	signature, err := base64.StdEncoding.DecodeString(strings.TrimSpace(signatureText))
	if err != nil || key == nil {
		return false
	}
	digest := sha256.Sum256(payload)
	return rsa.VerifyPKCS1v15(key, crypto.SHA256, digest[:], signature) == nil
}

func parseRSAPrivateKey(value string) (*rsa.PrivateKey, error) {
	block, _ := pem.Decode([]byte(normalizePEM(value, "PRIVATE KEY")))
	if block == nil {
		return nil, errors.New("invalid private key")
	}
	if key, err := x509.ParsePKCS8PrivateKey(block.Bytes); err == nil {
		if rsaKey, ok := key.(*rsa.PrivateKey); ok {
			return rsaKey, nil
		}
	}
	return x509.ParsePKCS1PrivateKey(block.Bytes)
}

func parseRSAPublicKey(value string) (*rsa.PublicKey, error) {
	block, _ := pem.Decode([]byte(normalizePEM(value, "PUBLIC KEY")))
	if block == nil {
		return nil, errors.New("invalid public key")
	}
	if key, err := x509.ParsePKIXPublicKey(block.Bytes); err == nil {
		if rsaKey, ok := key.(*rsa.PublicKey); ok {
			return rsaKey, nil
		}
	}
	return x509.ParsePKCS1PublicKey(block.Bytes)
}

func normalizePEM(value, kind string) string {
	value = strings.TrimSpace(strings.ReplaceAll(value, `\n`, "\n"))
	if strings.Contains(value, "-----BEGIN") {
		return value
	}
	return "-----BEGIN " + kind + "-----\n" + value + "\n-----END " + kind + "-----"
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func (c *HTTPFederatedIdentityVerifier) postFormJSON(
	ctx context.Context,
	endpoint string,
	values url.Values,
	out any,
) error {
	req, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		endpoint,
		strings.NewReader(values.Encode()),
	)
	if err != nil {
		return errors.New("provider request configuration invalid")
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := c.client.Do(req)
	if err != nil {
		return sanitizedProviderRequestError(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("provider http status %d", resp.StatusCode)
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

func (c *HTTPFederatedIdentityVerifier) getJSON(ctx context.Context, fullURL string, out any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, fullURL, nil)
	if err != nil {
		return errors.New("provider request configuration invalid")
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return sanitizedProviderRequestError(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("provider http status %d", resp.StatusCode)
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

func sanitizedProviderRequestError(err error) error {
	switch {
	case errors.Is(err, context.Canceled):
		return context.Canceled
	case errors.Is(err, context.DeadlineExceeded):
		return context.DeadlineExceeded
	}
	var networkError net.Error
	if errors.As(err, &networkError) && networkError.Timeout() {
		return errors.New("provider request timed out")
	}
	return errors.New("provider request failed")
}
