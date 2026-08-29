// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
//
// DEC-032：research 身份是服务端签发的 principal role。命中 research allowlist
// 的账号在登录签发的 access token roles 中携带 research；未命中账号与未配置
// allowlist 的部署不受影响。能力面收敛由 operation guard 按 role 执行，请求方
// 无法通过客户端行为脱离收敛。
package local_contract

import (
	"context"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

func newResearchIssuanceAuthService(
	t *testing.T,
	tokenConfig rtauth.TokenConfig,
	allowlist []string,
) *accountapp.AuthService {
	t.Helper()
	profile := &usermodel.UserProfile{
		UserID:                   "login-owner",
		AccountState:             "active",
		IdentityOrigin:           "phone",
		AnonymousRetentionPolicy: "preserve",
		Phone:                    "+8613800000401",
		LogicalShard:             1,
		OwnerDisplayName:         "Login Owner",
	}
	signer, err := rtauth.NewHS256Signer(tokenConfig)
	if err != nil {
		t.Fatalf("access signer: %v", err)
	}
	options := []accountapp.AuthServiceOption{
		accountapp.WithAccountSessionCommands(
			newAccountSessionCommandFacadeForTest(newFakeAccountSessionStore()),
		),
		accountapp.WithDeviceRegistration(&accountSessionLoginDeviceRegistrar{}),
		accountapp.WithConsentRecordStore(&accountSessionLoginConsentStore{}),
		accountapp.WithAuthenticationChallenges(&accountSessionLoginChallengeFacet{}),
		accountapp.WithAccountSecurityReader(accountSessionOperationSecurityReader{}),
		accountapp.WithAccessTokenSigner(signer),
	}
	if allowlist != nil {
		options = append(
			options,
			accountapp.WithResearchAccountAllowlist(allowlist),
		)
	}
	return accountapp.NewAuthService(
		&accountSessionOperationProfileStore{profile: profile},
		&accountSessionOperationPersonaStore{persona: &usermodel.Persona{
			UserID:      profile.UserID,
			PersonaID:   "login-persona",
			DisplayName: "Login Owner",
			IsActive:    true,
			Version:     1,
		}},
		newAccountSessionLoginCredentialStore(t),
		&accountSessionLoginAnonymousStore{},
		nil,
		options...,
	)
}

func researchIssuanceTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("research-role-issuance-local-32b"),
		Issuer:       "https://auth.quwoquan.local",
		Audience:     "quwoquan-api",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          30 * time.Minute,
	}
}

func loginAndVerifyClaims(
	t *testing.T,
	service *accountapp.AuthService,
	tokenConfig rtauth.TokenConfig,
) *rtauth.Claims {
	t.Helper()
	grant, err := service.LoginWithPhone(
		context.Background(),
		"+8613800000401",
		"246810",
		"138****0401",
		"research-role-device",
		"ios",
		"1.0.0",
		"agreement-v1",
		"privacy-v1",
	)
	if err != nil || grant == nil {
		t.Fatalf("LoginWithPhone grant=%+v err=%v", grant, err)
	}
	verifier, err := rtauth.NewHS256Verifier(tokenConfig)
	if err != nil {
		t.Fatalf("access verifier: %v", err)
	}
	claims, err := verifier.Verify(grant.AccessToken)
	if err != nil {
		t.Fatalf("verify access token: %v", err)
	}
	return claims
}

func claimsContainRole(claims *rtauth.Claims, role string) bool {
	for _, value := range claims.Roles {
		if value == role {
			return true
		}
	}
	return false
}

func TestAllowlistedAccountLoginIssuesResearchRole(t *testing.T) {
	tokenConfig := researchIssuanceTokenConfig()
	service := newResearchIssuanceAuthService(
		t,
		tokenConfig,
		[]string{"login-owner"},
	)

	claims := loginAndVerifyClaims(t, service, tokenConfig)
	if !claimsContainRole(claims, rtauth.RoleResearch) {
		t.Fatalf(
			"allowlisted account token roles=%v, want to contain %q",
			claims.Roles,
			rtauth.RoleResearch,
		)
	}
}

func TestNonAllowlistedAccountLoginHasNoResearchRole(t *testing.T) {
	tokenConfig := researchIssuanceTokenConfig()
	for _, testCase := range []struct {
		name      string
		allowlist []string
	}{
		{name: "allowlist absent", allowlist: nil},
		{name: "allowlist misses the account", allowlist: []string{"other-owner"}},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			service := newResearchIssuanceAuthService(
				t,
				tokenConfig,
				testCase.allowlist,
			)
			claims := loginAndVerifyClaims(t, service, tokenConfig)
			if claimsContainRole(claims, rtauth.RoleResearch) {
				t.Fatalf(
					"non-allowlisted account must not carry research role: %v",
					claims.Roles,
				)
			}
		})
	}
}
