package main

import (
	"fmt"
	"os"
	"strings"

	"quwoquan_service/services/user-service/internal/application"
	userintegration "quwoquan_service/services/user-service/internal/infrastructure/integration"
)

type externalAuthProviderMode string

const (
	externalAuthProviderModeRequired      externalAuthProviderMode = "required"
	externalAuthProviderModeAnonymousOnly externalAuthProviderMode = "anonymous_only"
)

func configuredExternalAuthProviderMode() (externalAuthProviderMode, error) {
	value := strings.ToLower(strings.TrimSpace(os.Getenv("USER_AUTH_EXTERNAL_PROVIDER_MODE")))
	if value == "" {
		return externalAuthProviderModeRequired, nil
	}
	mode := externalAuthProviderMode(value)
	switch mode {
	case externalAuthProviderModeRequired, externalAuthProviderModeAnonymousOnly:
		return mode, nil
	default:
		return "", fmt.Errorf("USER_AUTH_EXTERNAL_PROVIDER_MODE must be required or anonymous_only")
	}
}

// socialAuthProviderClient 只装配真实 OAuth provider。默认和所有已部署环境必须
// 注入完整凭据；只有 local-gamma 明确声明 anonymous_only 时，才保留匿名设备
// 登录并让第三方登录以结构化 unavailable 返回，绝不伪造外部身份。
func socialAuthProviderClient(cfg config) (application.ExternalAuthProviderClient, error) {
	mode, err := configuredExternalAuthProviderMode()
	if err != nil {
		return nil, err
	}
	providerConfigs := make(map[string]userintegration.ProviderOAuthConfig, len(cfg.Integration.Social.Providers))
	for name, p := range cfg.Integration.Social.Providers {
		providerConfigs[name] = userintegration.ProviderOAuthConfig{
			AppID:                strings.TrimSpace(p.AppID),
			AppSecret:            strings.TrimSpace(p.AppSecret),
			AppPrivateKeyPEM:     strings.TrimSpace(p.AppPrivateKeyPEM),
			PlatformPublicKeyPEM: strings.TrimSpace(p.PlatformPublicKeyPEM),
			MerchantPID:          strings.TrimSpace(p.MerchantPID),
			TokenURL:             strings.TrimSpace(p.TokenURL),
			UserInfoURL:          strings.TrimSpace(p.UserInfoURL),
		}
	}
	// 商用凭据只从部署密钥系统注入；YAML 仅允许承载非敏感 endpoint。
	injectSocialOAuthEnv := func(provider string, envPrefix string) {
		current := providerConfigs[provider]
		if value := strings.TrimSpace(os.Getenv(envPrefix + "_APP_ID")); value != "" {
			current.AppID = value
		}
		if value := strings.TrimSpace(os.Getenv(envPrefix + "_APP_SECRET")); value != "" {
			current.AppSecret = value
		}
		if value := strings.TrimSpace(os.Getenv(envPrefix + "_APP_PRIVATE_KEY_PEM")); value != "" {
			current.AppPrivateKeyPEM = value
		}
		if value := strings.TrimSpace(os.Getenv(envPrefix + "_PLATFORM_PUBLIC_KEY_PEM")); value != "" {
			current.PlatformPublicKeyPEM = value
		}
		if value := strings.TrimSpace(os.Getenv(envPrefix + "_MERCHANT_PID")); value != "" {
			current.MerchantPID = value
		}
		providerConfigs[provider] = current
	}
	if mode == externalAuthProviderModeRequired {
		injectSocialOAuthEnv(application.SocialProviderWechat, "WECHAT_OAUTH")
		injectSocialOAuthEnv(application.SocialProviderAlipay, "ALIPAY_OAUTH")
		injectSocialOAuthEnv(application.SocialProviderQq, "QQ_OAUTH")
	}
	httpClient := userintegration.NewHTTPExternalAuthProviderClient(providerConfigs, nil)
	if mode == externalAuthProviderModeAnonymousOnly {
		return httpClient, nil
	}
	for _, provider := range []string{
		application.SocialProviderWechat,
		application.SocialProviderAlipay,
		application.SocialProviderQq,
	} {
		if !httpClient.Supports(provider) {
			return nil, fmt.Errorf("social OAuth provider %s is not configured", provider)
		}
	}
	return httpClient, nil
}

// oneTapResolver 默认只装配真实阿里云号码认证。local-gamma 的匿名 UAT
// 显式关闭外部号码认证，调用时仍返回结构化 carrier unavailable。
func oneTapResolver(cfg config) (application.OneTapPhoneResolver, error) {
	mode, err := configuredExternalAuthProviderMode()
	if err != nil {
		return nil, err
	}
	if mode == externalAuthProviderModeAnonymousOnly {
		return application.UnavailableOneTapPhoneResolver{}, nil
	}
	if !strings.EqualFold(strings.TrimSpace(cfg.Integration.OneTap.Resolver), "aliyun") {
		return nil, fmt.Errorf("one-tap resolver must be aliyun")
	}
	accessKeyID := strings.TrimSpace(os.Getenv("ALIYUN_DYPNS_ACCESS_KEY_ID"))
	accessKeySecret := strings.TrimSpace(os.Getenv("ALIYUN_DYPNS_ACCESS_KEY_SECRET"))
	if accessKeyID == "" || accessKeySecret == "" {
		return nil, fmt.Errorf("ALIYUN_DYPNS_ACCESS_KEY_ID and ALIYUN_DYPNS_ACCESS_KEY_SECRET are required")
	}
	return userintegration.NewAliyunOneTapPhoneResolver(
		accessKeyID,
		accessKeySecret,
		strings.TrimSpace(os.Getenv("ALIYUN_DYPNS_ENDPOINT")),
	)
}
