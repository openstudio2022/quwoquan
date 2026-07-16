package integration

import (
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
	"net"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"

	"quwoquan_service/services/user-service/internal/application"
)

// allKnownProviders 是当前迭代支持的社交提供方（不含 Apple/Passkey）。
var allKnownProviders = []string{
	application.SocialProviderWechat,
	application.SocialProviderAlipay,
	application.SocialProviderQq,
}

// ProviderOAuthConfig 是单个社交提供方的真实 OAuth 应用配置（prod 注入）。
type ProviderOAuthConfig struct {
	AppID                string
	AppSecret            string
	AppPrivateKeyPEM     string
	PlatformPublicKeyPEM string
	MerchantPID          string
	TokenURL             string
	UserInfoURL          string
}

// HTTPExternalAuthProviderClient 为 prod 提供真实票据置换。
// 微信走标准 code->access_token(openid/unionid)->userinfo 流程；支付宝/QQ 需各自签名/令牌流程，
// 未注入完整配置时返回结构化 unavailable，绝不伪造成功（honest，不打桩）。
type HTTPExternalAuthProviderClient struct {
	configs map[string]ProviderOAuthConfig
	client  *http.Client
}

func NewHTTPExternalAuthProviderClient(configs map[string]ProviderOAuthConfig, client *http.Client) *HTTPExternalAuthProviderClient {
	if client == nil {
		client = &http.Client{Timeout: 5 * time.Second}
	}
	normalized := make(map[string]ProviderOAuthConfig, len(configs))
	for k, v := range configs {
		if key, ok := application.NormalizeSocialProvider(k); ok {
			normalized[key] = v
		}
	}
	return &HTTPExternalAuthProviderClient{configs: normalized, client: client}
}

func (c *HTTPExternalAuthProviderClient) Supports(provider string) bool {
	key, ok := application.NormalizeSocialProvider(provider)
	if !ok {
		return false
	}
	cfg, ok := c.configs[key]
	if !ok || strings.TrimSpace(cfg.AppID) == "" {
		return false
	}
	switch key {
	case application.SocialProviderWechat:
		return strings.TrimSpace(cfg.AppSecret) != ""
	case application.SocialProviderAlipay:
		return strings.TrimSpace(cfg.AppPrivateKeyPEM) != "" &&
			strings.TrimSpace(cfg.PlatformPublicKeyPEM) != "" &&
			strings.TrimSpace(cfg.MerchantPID) != ""
	case application.SocialProviderQq:
		return true
	default:
		return false
	}
}

// CreateAuthorizationRequest 生成支付宝 authV2 所需签名串；App 只能拿到短期
// authorizationPayload，拿不到商户私钥。
func (c *HTTPExternalAuthProviderClient) CreateAuthorizationRequest(
	_ context.Context,
	provider string,
) (string, time.Time, error) {
	key, ok := application.NormalizeSocialProvider(provider)
	if !ok || key != application.SocialProviderAlipay || !c.Supports(key) {
		return "", time.Time{}, errors.New("social provider authorization unavailable")
	}
	cfg := c.configs[key]
	privateKey, err := parseRSAPrivateKey(cfg.AppPrivateKeyPEM)
	if err != nil {
		return "", time.Time{}, errors.New("social provider authorization unavailable")
	}
	nonce := make([]byte, 24)
	if _, err := rand.Read(nonce); err != nil {
		return "", time.Time{}, errors.New("social provider authorization unavailable")
	}
	values := url.Values{
		"apiname":    {"com.alipay.account.auth"},
		"method":     {"alipay.open.auth.sdk.code.get"},
		"app_id":     {cfg.AppID},
		"app_name":   {"mc"},
		"biz_type":   {"openservice"},
		"pid":        {cfg.MerchantPID},
		"product_id": {"APP_FAST_LOGIN"},
		"scope":      {"kuaijie"},
		"target_id":  {base64.RawURLEncoding.EncodeToString(nonce)},
		"auth_type":  {"AUTHACCOUNT"},
		"sign_type":  {"RSA2"},
	}
	signature, err := signAlipayValues(values, privateKey)
	if err != nil {
		return "", time.Time{}, errors.New("social provider authorization unavailable")
	}
	values.Set("sign", signature)
	return values.Encode(), time.Now().UTC().Add(5 * time.Minute), nil
}

func (c *HTTPExternalAuthProviderClient) Exchange(ctx context.Context, provider, authCode, _, _ string) (application.ExternalIdentity, error) {
	key, ok := application.NormalizeSocialProvider(provider)
	if !ok {
		return application.ExternalIdentity{}, fmt.Errorf("unsupported provider %q", provider)
	}
	cfg, ok := c.configs[key]
	if !ok || !c.Supports(key) {
		return application.ExternalIdentity{}, fmt.Errorf("%s provider unavailable: oauth app not configured", key)
	}
	switch key {
	case application.SocialProviderWechat:
		return c.exchangeWechat(ctx, cfg, strings.TrimSpace(authCode))
	case application.SocialProviderAlipay:
		return c.exchangeAlipay(ctx, cfg, strings.TrimSpace(authCode))
	case application.SocialProviderQq:
		return c.exchangeQq(ctx, cfg, strings.TrimSpace(authCode))
	default:
		return application.ExternalIdentity{}, fmt.Errorf("unsupported provider %q", key)
	}
}

// exchangeWechat 实现微信开放平台 code 换 openid/unionid 的标准流程。
func (c *HTTPExternalAuthProviderClient) exchangeWechat(ctx context.Context, cfg ProviderOAuthConfig, code string) (application.ExternalIdentity, error) {
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
		return application.ExternalIdentity{}, fmt.Errorf("wechat token exchange failed: %w", err)
	}
	if tokenResp.ErrCode != 0 {
		return application.ExternalIdentity{}, fmt.Errorf(
			"wechat token exchange rejected with provider code %d",
			tokenResp.ErrCode,
		)
	}
	identity := application.ExternalIdentity{
		Provider: application.SocialProviderWechat,
		OpenID:   tokenResp.OpenID,
		UnionID:  tokenResp.UnionID,
		AppID:    cfg.AppID,
		Scope:    tokenResp.Scope,
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
func (c *HTTPExternalAuthProviderClient) exchangeAlipay(
	ctx context.Context,
	cfg ProviderOAuthConfig,
	authCode string,
) (application.ExternalIdentity, error) {
	if authCode == "" {
		return application.ExternalIdentity{}, errors.New("alipay authorization code required")
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
		return application.ExternalIdentity{}, err
	}
	var token struct {
		AccessToken string `json:"access_token"`
		UserID      string `json:"user_id"`
		OpenID      string `json:"open_id"`
	}
	if err := json.Unmarshal(tokenPayload, &token); err != nil ||
		strings.TrimSpace(token.AccessToken) == "" ||
		(strings.TrimSpace(token.UserID) == "" && strings.TrimSpace(token.OpenID) == "") {
		return application.ExternalIdentity{}, errors.New("alipay provider response invalid")
	}

	identity := application.ExternalIdentity{
		Provider: application.SocialProviderAlipay,
		UnionID:  strings.TrimSpace(token.UserID),
		OpenID:   firstNonEmpty(strings.TrimSpace(token.OpenID), strings.TrimSpace(token.UserID)),
		AppID:    cfg.AppID,
		Scope:    "auth_user",
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
func (c *HTTPExternalAuthProviderClient) exchangeQq(
	ctx context.Context,
	cfg ProviderOAuthConfig,
	authCode string,
) (application.ExternalIdentity, error) {
	token, openID, err := parseQqMobileTicket(authCode)
	if err != nil {
		return application.ExternalIdentity{}, err
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
		return application.ExternalIdentity{}, err
	}
	if profile.Ret != 0 {
		return application.ExternalIdentity{}, errors.New("qq provider authorization rejected")
	}
	return application.ExternalIdentity{
		Provider:    application.SocialProviderQq,
		OpenID:      openID,
		AppID:       cfg.AppID,
		DisplayName: strings.TrimSpace(profile.Nickname),
		AvatarURL:   strings.TrimSpace(profile.FigureURL),
		Scope:       "get_user_info",
	}, nil
}

func parseQqMobileTicket(ticket string) (accessToken string, openID string, err error) {
	ticket = strings.TrimSpace(ticket)
	const prefix = "qq_mobile_v1."
	if strings.HasPrefix(ticket, prefix) {
		raw, decodeErr := base64.RawURLEncoding.DecodeString(strings.TrimPrefix(ticket, prefix))
		if decodeErr != nil {
			return "", "", errors.New("qq authorization ticket invalid")
		}
		ticket = string(raw)
	}
	var payload struct {
		AccessToken string `json:"accessToken"`
		OpenID      string `json:"openId"`
	}
	if json.Unmarshal([]byte(ticket), &payload) != nil {
		return "", "", errors.New("qq authorization ticket invalid")
	}
	accessToken = strings.TrimSpace(payload.AccessToken)
	openID = strings.TrimSpace(payload.OpenID)
	if accessToken == "" || openID == "" {
		return "", "", errors.New("qq authorization ticket invalid")
	}
	return accessToken, openID, nil
}

func (c *HTTPExternalAuthProviderClient) postAlipayGateway(
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

func (c *HTTPExternalAuthProviderClient) postFormJSON(
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

func (c *HTTPExternalAuthProviderClient) getJSON(ctx context.Context, fullURL string, out any) error {
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
