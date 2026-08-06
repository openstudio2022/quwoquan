package main

import (
	"fmt"
	"strings"

	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	userauthbinding "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/authbinding"
	userintegration "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
)

// ErrAuthRuntimeCapabilityBlocked 表示 metadata 明确禁用认证外部能力。
// ErrAuthRuntimeCapabilityUnavailable 表示可选能力缺少受保护的运行材料。
// 两者都会在 composition root 保留 nil adapter，让应用层返回生成的 structured
// unavailable error；未知 binding、错误 adapter 与非法 binding 元数据仍须 fail-fast。
var ErrAuthRuntimeCapabilityBlocked = userauthbinding.ErrAuthRuntimeCapabilityBlocked

var ErrAuthRuntimeCapabilityUnavailable = userauthbinding.ErrAuthRuntimeCapabilityUnavailable

const nonPromotablePrevalidationEnv = userauthbinding.NonPromotablePrevalidationEnv

func contentSliceExternalAuthDisabled() bool {
	return userauthbinding.ContentSliceExternalAuthDisabled()
}

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
	if binding.adapterID == userauthbinding.FederatedIdentityProtocolFixtureAdapterID {
		endpoint := binding.endpoint("endpoint")
		wechatVerifier, verifierErr :=
			userintegration.NewProtocolSubstituteFederatedIdentityVerifier(
				credentialmodel.CredentialTypeFederatedSlotA,
				"wechat",
				endpoint,
				nil,
			)
		if verifierErr != nil {
			return federatedLoginBindings{}, verifierErr
		}
		alipayVerifier, verifierErr :=
			userintegration.NewProtocolSubstituteFederatedIdentityVerifier(
				credentialmodel.CredentialTypeFederatedSlotB,
				"alipay",
				endpoint,
				nil,
			)
		if verifierErr != nil {
			return federatedLoginBindings{}, verifierErr
		}
		qqVerifier, verifierErr :=
			userintegration.NewProtocolSubstituteFederatedIdentityVerifier(
				credentialmodel.CredentialTypeFederatedSlotC,
				"qq",
				endpoint,
				nil,
			)
		if verifierErr != nil {
			return federatedLoginBindings{}, verifierErr
		}
		return federatedLoginBindings{
			wechat: application.NewFederatedLoginFacade(
				auth,
				wechatVerifier,
				wechatVerifier,
			),
			alipay: application.NewFederatedLoginFacade(
				auth,
				alipayVerifier,
				alipayVerifier,
			),
			qq: application.NewFederatedLoginFacade(
				auth,
				qqVerifier,
				qqVerifier,
			),
		}, nil
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
	if binding.adapterID == userauthbinding.CarrierOneTapProtocolFixtureAdapterID {
		return userintegration.NewProtocolSubstituteCarrierPhoneResolver(
			binding.endpoint("endpoint"),
			nil,
		)
	}
	return userintegration.NewAliyunOneTapPhoneResolver(
		binding.secret("ALIYUN_DYPNS_ACCESS_KEY_ID"),
		binding.secret("ALIYUN_DYPNS_ACCESS_KEY_SECRET"),
		binding.endpoint("endpoint"),
	)
}

type authRuntimeBinding struct {
	adapterID string
	runtime   userauthbinding.RuntimeBinding
}

func resolveCarrierOneTapBinding() (authRuntimeBinding, error) {
	binding, err := userauthbinding.ResolveCarrierOneTapBinding()
	return authRuntimeBindingFrom(binding), err
}

func resolveFederatedIdentityBinding() (authRuntimeBinding, error) {
	binding, err := userauthbinding.ResolveFederatedIdentityBinding()
	return authRuntimeBindingFrom(binding), err
}

func authRuntimeBindingFrom(binding userauthbinding.RuntimeBinding) authRuntimeBinding {
	return authRuntimeBinding{
		adapterID: binding.AdapterID(),
		runtime:   binding,
	}
}

func (binding authRuntimeBinding) endpoint(role string) string {
	return binding.runtime.Endpoint(role)
}

func (binding authRuntimeBinding) secret(environmentKey string) string {
	return binding.runtime.Secret(environmentKey)
}
