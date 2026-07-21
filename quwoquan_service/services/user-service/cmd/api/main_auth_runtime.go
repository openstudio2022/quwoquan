package main

import (
	"errors"
	"fmt"
	"os"
	"strings"

	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/services/user-service/internal/application"
	usergenerated "quwoquan_service/services/user-service/internal/generated"
	userintegration "quwoquan_service/services/user-service/internal/infrastructure/integration"
)

// ErrAuthRuntimeCapabilityBlocked 表示 metadata 明确禁用认证外部能力。
// composition root 可保留 nil adapter，让应用层返回生成的 structured unavailable
// error；未知 binding、错误 adapter 或缺失材料仍必须 fail-fast。
var ErrAuthRuntimeCapabilityBlocked = errors.New(
	"user authentication external capability is blocked",
)

// federatedLoginBindings is the explicit production composition for every
// published federated authorization route. Each field is bound once at
// startup; requests never select an adapter from client-controlled data.
type federatedLoginBindings struct {
	wechat *application.FederatedLoginFacade
	alipay *application.FederatedLoginFacade
	qq     *application.FederatedLoginFacade
}

func newFederatedLoginBindings(
	auth *application.AuthService,
) (federatedLoginBindings, error) {
	binding, err := resolveFederatedIdentityBinding()
	if err != nil {
		return federatedLoginBindings{}, err
	}
	wechatVerifier, err := userintegration.NewWechatFederatedIdentityVerifier(
		oauthConfig(
			binding.secret("WECHAT_OAUTH_APP_ID"),
			binding.secret("WECHAT_OAUTH_APP_SECRET"),
			"", "", "",
			binding.endpoint("wechat_token"),
			binding.endpoint("wechat_user_info"),
		),
		nil,
	)
	if err != nil {
		return federatedLoginBindings{}, fmt.Errorf("wechat identity adapter: %w", err)
	}
	alipayVerifier, alipayIssuer, err :=
		userintegration.NewAlipayFederatedIdentityVerifier(
			oauthConfig(
				binding.secret("ALIPAY_OAUTH_APP_ID"),
				"",
				binding.secret("ALIPAY_OAUTH_APP_PRIVATE_KEY_PEM"),
				binding.secret("ALIPAY_OAUTH_PLATFORM_PUBLIC_KEY_PEM"),
				binding.secret("ALIPAY_OAUTH_MERCHANT_PID"),
				binding.endpoint("alipay_token"),
				binding.endpoint("alipay_user_info"),
			),
			nil,
		)
	if err != nil {
		return federatedLoginBindings{}, fmt.Errorf("alipay identity adapter: %w", err)
	}
	qqVerifier, err := userintegration.NewQqFederatedIdentityVerifier(
		oauthConfig(
			binding.secret("QQ_OAUTH_APP_ID"),
			"", "", "", "",
			"",
			binding.endpoint("qq_user_info"),
		),
		nil,
	)
	if err != nil {
		return federatedLoginBindings{}, fmt.Errorf("qq identity adapter: %w", err)
	}
	return federatedLoginBindings{
		wechat: application.NewFederatedLoginFacade(auth, wechatVerifier, nil),
		alipay: application.NewFederatedLoginFacade(auth, alipayVerifier, alipayIssuer),
		qq:     application.NewFederatedLoginFacade(auth, qqVerifier, nil),
	}, nil
}

func oauthConfig(
	appID string,
	appSecret string,
	appPrivateKeyPEM string,
	platformPublicKeyPEM string,
	merchantPID string,
	tokenURL string,
	userInfoURL string,
) userintegration.ProviderOAuthConfig {
	return userintegration.ProviderOAuthConfig{
		AppID:                strings.TrimSpace(appID),
		AppSecret:            strings.TrimSpace(appSecret),
		AppPrivateKeyPEM:     strings.TrimSpace(appPrivateKeyPEM),
		PlatformPublicKeyPEM: strings.TrimSpace(platformPublicKeyPEM),
		MerchantPID:          strings.TrimSpace(merchantPID),
		TokenURL:             strings.TrimSpace(tokenURL),
		UserInfoURL:          strings.TrimSpace(userInfoURL),
	}
}

func newCarrierPhoneResolver() (application.CarrierPhoneResolver, error) {
	binding, err := resolveCarrierOneTapBinding()
	if err != nil {
		return nil, err
	}
	return userintegration.NewAliyunOneTapPhoneResolver(
		binding.secret("ALIYUN_DYPNS_ACCESS_KEY_ID"),
		binding.secret("ALIYUN_DYPNS_ACCESS_KEY_SECRET"),
		binding.endpoint("endpoint"),
	)
}

type authRuntimeBinding struct {
	endpoints map[string]string
	secrets   map[string]string
}

func resolveCarrierOneTapBinding() (authRuntimeBinding, error) {
	return resolveAuthRuntimeBinding(
		"identity.carrier.one_tap",
		"ext.auth.carrier_one_tap",
	)
}

func resolveFederatedIdentityBinding() (authRuntimeBinding, error) {
	return resolveAuthRuntimeBinding(
		"identity.social.login",
		"ext.auth.federated_identity",
	)
}

func resolveAuthRuntimeBinding(
	capabilityID string,
	expectedAdapterID string,
) (authRuntimeBinding, error) {
	appEnv := strings.TrimSpace(os.Getenv("APP_ENV"))
	if appEnv == "" {
		appEnv = "alpha"
	}
	descriptor, found := usergenerated.ExternalProviderBindingFor(appEnv, capabilityID)
	if !found {
		return authRuntimeBinding{}, fmt.Errorf(
			"%s binding is missing for environment=%s",
			capabilityID,
			appEnv,
		)
	}
	if descriptor.State != "enabled" {
		return authRuntimeBinding{}, fmt.Errorf(
			"%w: %s for environment=%s",
			ErrAuthRuntimeCapabilityBlocked,
			capabilityID,
			appEnv,
		)
	}
	if descriptor.AdapterID != expectedAdapterID {
		return authRuntimeBinding{}, fmt.Errorf(
			"%s binding selects an unexpected adapter for environment=%s",
			capabilityID,
			appEnv,
		)
	}
	configProvider := runtimeconfig.EnvRuntimeConfigProvider{}
	binding := authRuntimeBinding{
		endpoints: make(map[string]string, len(descriptor.EndpointEnvironmentKeys)),
		secrets:   make(map[string]string, len(descriptor.SecretEnvironmentKeys)),
	}
	for role, environmentKey := range descriptor.EndpointEnvironmentKeys {
		value, ok := configProvider.GetString(environmentKey)
		if !ok {
			return authRuntimeBinding{}, fmt.Errorf(
				"%s endpoint material is unavailable for role=%s",
				capabilityID,
				role,
			)
		}
		binding.endpoints[role] = value
	}
	for _, environmentKey := range descriptor.SecretEnvironmentKeys {
		value, ok := configProvider.GetString(environmentKey)
		if !ok {
			return authRuntimeBinding{}, fmt.Errorf(
				"%s secret material is unavailable",
				capabilityID,
			)
		}
		binding.secrets[environmentKey] = value
	}
	if descriptor.TimeoutMilliseconds <= 0 {
		return authRuntimeBinding{}, fmt.Errorf("%s binding timeout is invalid", capabilityID)
	}
	return binding, nil
}

func (binding authRuntimeBinding) endpoint(role string) string {
	return strings.TrimSpace(binding.endpoints[role])
}

func (binding authRuntimeBinding) secret(environmentKey string) string {
	return strings.TrimSpace(binding.secrets[environmentKey])
}
