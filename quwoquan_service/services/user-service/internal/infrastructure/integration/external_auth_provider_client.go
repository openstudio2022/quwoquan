package integration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
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

// MockExternalAuthProviderClient 为 alpha/beta 提供离线确定性社交身份。
// 它是发布代码（非 *_test.go），通过 main.go 按环境注入；同一 authCode 稳定映射同一账号，
// 便于重复登录与端云联调测试。
type MockExternalAuthProviderClient struct{}

func NewMockExternalAuthProviderClient() *MockExternalAuthProviderClient {
	return &MockExternalAuthProviderClient{}
}

func (c *MockExternalAuthProviderClient) Supports(provider string) bool {
	_, ok := application.NormalizeSocialProvider(provider)
	return ok
}

func (c *MockExternalAuthProviderClient) Exchange(_ context.Context, provider, authCode, _ , _ string) (application.ExternalIdentity, error) {
	normalized, ok := application.NormalizeSocialProvider(provider)
	if !ok {
		return application.ExternalIdentity{}, fmt.Errorf("unsupported provider %q", provider)
	}
	authCode = strings.TrimSpace(authCode)
	if authCode == "" {
		return application.ExternalIdentity{}, fmt.Errorf("authCode required")
	}
	if strings.Contains(strings.ToLower(authCode), "cancel") {
		return application.ExternalIdentity{}, fmt.Errorf("user cancelled authorization")
	}
	return deterministicIdentity(normalized, authCode), nil
}

// SandboxExternalAuthProviderClient 为 gamma 提供受控放通：命中 token allowlist 的测试授权码返回
// 确定性沙箱身份；其余授权码委托真实实现走严格校验。
type SandboxExternalAuthProviderClient struct {
	allow    application.SandboxAllowlist
	fallback application.ExternalAuthProviderClient
	now      func() time.Time
}

func NewSandboxExternalAuthProviderClient(
	allow application.SandboxAllowlist,
	fallback application.ExternalAuthProviderClient,
) *SandboxExternalAuthProviderClient {
	return &SandboxExternalAuthProviderClient{
		allow:    allow,
		fallback: fallback,
		now:      func() time.Time { return time.Now().UTC() },
	}
}

func (c *SandboxExternalAuthProviderClient) Supports(provider string) bool {
	if _, ok := application.NormalizeSocialProvider(provider); !ok {
		return false
	}
	return true
}

func (c *SandboxExternalAuthProviderClient) Exchange(ctx context.Context, provider, authCode, platform, appVersion string) (application.ExternalIdentity, error) {
	normalized, ok := application.NormalizeSocialProvider(provider)
	if !ok {
		return application.ExternalIdentity{}, fmt.Errorf("unsupported provider %q", provider)
	}
	if c.allow.AllowsToken(strings.TrimSpace(authCode), c.now()) {
		return deterministicIdentity(normalized, strings.TrimSpace(authCode)), nil
	}
	if c.fallback == nil {
		return application.ExternalIdentity{}, fmt.Errorf("%s provider unavailable for non-sandbox account", normalized)
	}
	return c.fallback.Exchange(ctx, normalized, authCode, platform, appVersion)
}

// ProviderOAuthConfig 是单个社交提供方的真实 OAuth 应用配置（prod 注入）。
type ProviderOAuthConfig struct {
	AppID       string
	AppSecret   string
	TokenURL    string
	UserInfoURL string
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
	return ok && strings.TrimSpace(cfg.AppID) != "" && strings.TrimSpace(cfg.AppSecret) != ""
}

func (c *HTTPExternalAuthProviderClient) Exchange(ctx context.Context, provider, authCode, _, _ string) (application.ExternalIdentity, error) {
	key, ok := application.NormalizeSocialProvider(provider)
	if !ok {
		return application.ExternalIdentity{}, fmt.Errorf("unsupported provider %q", provider)
	}
	cfg, ok := c.configs[key]
	if !ok || strings.TrimSpace(cfg.AppID) == "" || strings.TrimSpace(cfg.AppSecret) == "" {
		return application.ExternalIdentity{}, fmt.Errorf("%s provider unavailable: oauth app not configured", key)
	}
	switch key {
	case application.SocialProviderWechat:
		return c.exchangeWechat(ctx, cfg, strings.TrimSpace(authCode))
	default:
		// 支付宝/QQ 真实置换需各自 SDK/签名流程；未实现完整置换前返回结构化 unavailable。
		return application.ExternalIdentity{}, fmt.Errorf("%s provider unavailable: production exchange not yet provisioned", key)
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
		return application.ExternalIdentity{}, fmt.Errorf("wechat token exchange: %w", err)
	}
	if tokenResp.ErrCode != 0 {
		return application.ExternalIdentity{}, fmt.Errorf("wechat token exchange failed: %d %s", tokenResp.ErrCode, tokenResp.ErrMsg)
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

func (c *HTTPExternalAuthProviderClient) getJSON(ctx context.Context, fullURL string, out any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, fullURL, nil)
	if err != nil {
		return err
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("provider http status %d", resp.StatusCode)
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

// deterministicIdentity 基于 authCode 生成稳定身份，供 mock/sandbox 使用。
func deterministicIdentity(provider, authCode string) application.ExternalIdentity {
	sum := sha256.Sum256([]byte(provider + ":" + authCode))
	digest := hex.EncodeToString(sum[:])
	short := digest[:12]
	label := map[string]string{
		application.SocialProviderWechat: "微信用户",
		application.SocialProviderAlipay: "支付宝用户",
		application.SocialProviderQq:     "QQ用户",
	}[provider]
	return application.ExternalIdentity{
		Provider:    provider,
		UnionID:     provider + "_union_" + short,
		OpenID:      provider + "_open_" + short,
		AppID:       provider + "_sandbox_app",
		DisplayName: label + short[:6],
		AvatarURL:   "https://cdn.quwoquan.local/sandbox/avatar/" + provider + "/" + short[:8] + ".png",
		Scope:       "snsapi_userinfo",
	}
}
