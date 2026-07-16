package application

import (
	"context"
	"strings"
	"time"
)

// 社交登录提供方标识（与 metadata CredentialType 对齐的子集）。
const (
	SocialProviderWechat = "wechat"
	SocialProviderAlipay = "alipay"
	SocialProviderQq     = "qq"
)

// ExternalIdentity 是各社交提供方票据置换后归一化的稳定身份。
// 服务端基于它生成 credentialKey，App 不得上传可持久化的厂商账号 ID。
type ExternalIdentity struct {
	Provider    string
	UnionID     string
	OpenID      string
	AppID       string
	DisplayName string
	AvatarURL   string
	Scope       string
}

// StableKey 返回服务端规范化后的 credentialKey：
//   - 优先 unionId（可跨同主体多应用打通）；
//   - 否则使用 appId+openId 形成 app-scoped key（标明不可跨 app 自动合并）。
func (i ExternalIdentity) StableKey() string {
	provider := strings.TrimSpace(i.Provider)
	if union := strings.TrimSpace(i.UnionID); union != "" {
		return provider + ":unionid:" + union
	}
	open := strings.TrimSpace(i.OpenID)
	app := strings.TrimSpace(i.AppID)
	if app != "" {
		return provider + ":appopenid:" + app + ":" + open
	}
	return provider + ":openid:" + open
}

func (i ExternalIdentity) hasIdentity() bool {
	return strings.TrimSpace(i.UnionID) != "" || strings.TrimSpace(i.OpenID) != ""
}

// ExternalAuthProviderClient 抽象社交登录票据置换。App 只上传短期授权码，
// 服务端用它换取稳定身份与公开资料。运行时只装配真实 HTTP provider；
// provider 凭据不完整时必须返回结构化 unavailable，不能生成测试身份。
type ExternalAuthProviderClient interface {
	// Exchange 用短期授权码换取稳定外部身份。
	Exchange(ctx context.Context, provider, authCode, platform, appVersion string) (ExternalIdentity, error)
	// Supports 报告该实现是否支持指定提供方（用于能力探测与降级）。
	Supports(provider string) bool
}

// ExternalAuthAuthorizationIssuer 为需要服务端签名的原生授权 SDK 生成短期请求。
// 当前仅支付宝 authV2 需要该能力；私钥永远不进入客户端。
type ExternalAuthAuthorizationIssuer interface {
	CreateAuthorizationRequest(
		ctx context.Context,
		provider string,
	) (authorizationPayload string, expiresAt time.Time, err error)
}

// NormalizeSocialProvider 归一化提供方标识，返回是否受支持。
func NormalizeSocialProvider(provider string) (string, bool) {
	switch strings.ToLower(strings.TrimSpace(provider)) {
	case SocialProviderWechat:
		return SocialProviderWechat, true
	case SocialProviderAlipay:
		return SocialProviderAlipay, true
	case SocialProviderQq:
		return SocialProviderQq, true
	default:
		return "", false
	}
}
