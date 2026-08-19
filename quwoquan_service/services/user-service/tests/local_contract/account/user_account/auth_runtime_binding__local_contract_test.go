// spec_ref: specs/feature-tree/runtime/runtime-external-integration/spec.md#sit-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-003
package local_contract

import (
	"errors"
	"slices"
	"strings"
	"testing"

	usergenerated "quwoquan_service/services/user-service/generated/account/user_account"
	authbinding "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/authbinding"
)

const (
	authRuntimeCarrierCapabilityID   = "identity.carrier.one_tap"
	authRuntimeFederatedCapabilityID = "identity.social.login"
)

func TestContentSliceDisablesUnrelatedExternalAuth(t *testing.T) {
	for _, workload := range []string{"content-release", "content-commercial", "CONTENT-COMMERCIAL"} {
		t.Run(workload, func(t *testing.T) {
			t.Setenv("QWQ_WORKLOAD", workload)
			if !authbinding.ContentSliceExternalAuthDisabled() {
				t.Fatalf("workload %q must not require unrelated external auth Providers", workload)
			}
		})
	}
	t.Setenv("QWQ_WORKLOAD", "full")
	if authbinding.ContentSliceExternalAuthDisabled() {
		t.Fatal("full workload must keep external auth enabled")
	}
}

// 仓内源码树不固化任何环境：external_provider_governance.py 的多环境发射器只写出
// 恒 false 的 CompiledBindingFor，单环境实现由 stackctl package 的 provider binding
// overlay 在构建期覆盖写入。因此未打包树里两项可选认证能力都必须 fail closed，
// 材料齐备也救不回来；而且该失败不得被归类为 blocked/unavailable —— cmd/api 只容忍
// 这两个 sentinel，一旦被误分类，未打包树就会静默降级成一个「外部认证已关闭」的
// 可启动组合。这里断言的正是「不可被静默降级」。
func TestOptionalAuthBindingsFailClosedWithoutCompiledEnvironmentBinding(t *testing.T) {
	for _, capabilityID := range []string{
		authRuntimeCarrierCapabilityID,
		authRuntimeFederatedCapabilityID,
	} {
		if _, found := usergenerated.CompiledBindingFor(capabilityID); found {
			t.Fatalf(
				"源码树编译进了环境绑定 capability=%s；环境只能由打包期 overlay 固化",
				capabilityID,
			)
		}
	}

	resolvers := []struct {
		capabilityID string
		resolve      func() (authbinding.RuntimeBinding, error)
	}{
		{
			capabilityID: authRuntimeCarrierCapabilityID,
			resolve:      authbinding.ResolveCarrierOneTapBinding,
		},
		{
			capabilityID: authRuntimeFederatedCapabilityID,
			resolve:      authbinding.ResolveFederatedIdentityBinding,
		},
	}
	for _, material := range []struct {
		name    string
		present bool
	}{
		{name: "protected material missing", present: false},
		{name: "protected material present", present: true},
	} {
		t.Run(material.name, func(t *testing.T) {
			t.Setenv("APP_ENV", "prod")
			t.Setenv("QWQ_WORKLOAD", "")
			t.Setenv(authbinding.NonPromotablePrevalidationEnv, "")
			setDeclaredAuthRuntimeMaterial(t, material.present)

			for _, resolver := range resolvers {
				_, err := resolver.resolve()
				if err == nil ||
					!strings.Contains(err.Error(), "binding is missing") {
					t.Fatalf(
						"%s 未打包时必须 fail closed，got %v",
						resolver.capabilityID,
						err,
					)
				}
				if errors.Is(err, authbinding.ErrAuthRuntimeCapabilityUnavailable) ||
					errors.Is(err, authbinding.ErrAuthRuntimeCapabilityBlocked) {
					t.Fatalf(
						"%s 未固化环境不得归类为可容忍的 blocked/unavailable：%v",
						resolver.capabilityID,
						err,
					)
				}
			}
		})
	}
}

// 多环境声明仍是治理与打包输入：非生产三环境只声明协议替身认证 Provider，prod 只
// 声明真实运营商/社交 Provider。断言取相等而非不等，因此「prod 不得落到协议替身」
// 与「非生产不得落到真实 Provider」两个方向都被钉住。prod 的 endpoint/secret 材料
// 键闭包同时被钉住，因为它就是打包期固化后运行时要求的受保护材料集合。
func TestAuthRuntimeDeclarationsIsolateNonprodFixtureFromProdProvider(t *testing.T) {
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		expectedCarrier := authbinding.CarrierOneTapProtocolFixtureAdapterID
		expectedFederated := authbinding.FederatedIdentityProtocolFixtureAdapterID
		if environment == "prod" {
			expectedCarrier = authbinding.CarrierOneTapAdapterID
			expectedFederated = authbinding.FederatedIdentityAdapterID
		}
		carrier := declaredAuthRuntimeBinding(t, environment, authRuntimeCarrierCapabilityID)
		if carrier.State != "enabled" || carrier.AdapterID != expectedCarrier ||
			carrier.TimeoutMilliseconds <= 0 {
			t.Fatalf("环境 %s 的一键登录声明漂移: %+v", environment, carrier)
		}
		federated := declaredAuthRuntimeBinding(
			t,
			environment,
			authRuntimeFederatedCapabilityID,
		)
		if federated.State != "enabled" || federated.AdapterID != expectedFederated ||
			federated.TimeoutMilliseconds <= 0 {
			t.Fatalf("环境 %s 的社交登录声明漂移: %+v", environment, federated)
		}
	}

	prodCarrier := declaredAuthRuntimeBinding(t, "prod", authRuntimeCarrierCapabilityID)
	if prodCarrier.EndpointEnvironmentKeys["endpoint"] != "ALIYUN_DYPNS_ENDPOINT" {
		t.Fatalf("prod 一键登录 endpoint 材料键漂移: %+v", prodCarrier.EndpointEnvironmentKeys)
	}
	for _, environmentKey := range []string{
		"ALIYUN_DYPNS_ACCESS_KEY_ID",
		"ALIYUN_DYPNS_ACCESS_KEY_SECRET",
	} {
		if !slices.Contains(prodCarrier.SecretEnvironmentKeys, environmentKey) {
			t.Fatalf("prod 一键登录缺少受保护材料键 %s", environmentKey)
		}
	}

	prodFederated := declaredAuthRuntimeBinding(t, "prod", authRuntimeFederatedCapabilityID)
	for role, environmentKey := range map[string]string{
		"wechat_token":     "WECHAT_OAUTH_TOKEN_URL",
		"wechat_user_info": "WECHAT_OAUTH_USER_INFO_URL",
		"alipay_token":     "ALIPAY_OAUTH_TOKEN_URL",
		"alipay_user_info": "ALIPAY_OAUTH_USER_INFO_URL",
		"qq_user_info":     "QQ_OAUTH_USER_INFO_URL",
	} {
		if prodFederated.EndpointEnvironmentKeys[role] != environmentKey {
			t.Fatalf(
				"prod 社交登录角色 %s 的材料键漂移: got %q, want %q",
				role,
				prodFederated.EndpointEnvironmentKeys[role],
				environmentKey,
			)
		}
	}
	for _, environmentKey := range []string{
		"WECHAT_OAUTH_APP_ID",
		"WECHAT_OAUTH_APP_SECRET",
		"ALIPAY_OAUTH_APP_ID",
		"ALIPAY_OAUTH_APP_PRIVATE_KEY_PEM",
		"ALIPAY_OAUTH_PLATFORM_PUBLIC_KEY_PEM",
		"ALIPAY_OAUTH_MERCHANT_PID",
		"QQ_OAUTH_APP_ID",
	} {
		if !slices.Contains(prodFederated.SecretEnvironmentKeys, environmentKey) {
			t.Fatalf("prod 社交登录缺少受保护材料键 %s", environmentKey)
		}
	}
}

// 非可提升的第一方预验证是编译期绑定之前的守卫子句，未打包树里依然可达：
// 它必须返回 blocked sentinel，让 cmd/api 在不装配外部认证的情况下继续启动。
func TestNonPromotablePrevalidationBlocksOptionalAuthBeforeBindingLookup(t *testing.T) {
	t.Setenv("APP_ENV", "prod")
	t.Setenv("QWQ_WORKLOAD", "")
	t.Setenv(authbinding.NonPromotablePrevalidationEnv, "first-party")

	if _, err := authbinding.ResolveCarrierOneTapBinding(); !errors.Is(
		err,
		authbinding.ErrAuthRuntimeCapabilityBlocked,
	) {
		t.Fatalf("carrier binding error = %v, want blocked sentinel", err)
	}
	if _, err := authbinding.ResolveFederatedIdentityBinding(); !errors.Is(
		err,
		authbinding.ErrAuthRuntimeCapabilityBlocked,
	) {
		t.Fatalf("federated binding error = %v, want blocked sentinel", err)
	}
}

func TestUnknownAuthBindingConfigurationRemainsStartupError(t *testing.T) {
	t.Setenv("APP_ENV", "unknown")
	t.Setenv("QWQ_WORKLOAD", "")
	t.Setenv(authbinding.NonPromotablePrevalidationEnv, "")

	if _, err := authbinding.ResolveCarrierOneTapBinding(); err == nil || errors.Is(
		err,
		authbinding.ErrAuthRuntimeCapabilityUnavailable,
	) {
		t.Fatalf("unknown binding configuration must not be classified as unavailable: %v", err)
	}
}

// 受保护材料集合从声明层推导，避免在测试里维护第二份材料键清单；键名本身由
// TestAuthRuntimeDeclarationsIsolateNonprodFixtureFromProdProvider 钉住。
func setDeclaredAuthRuntimeMaterial(t *testing.T, present bool) {
	t.Helper()
	value := ""
	if present {
		value = "contract-material"
	}
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		for _, capabilityID := range []string{
			authRuntimeCarrierCapabilityID,
			authRuntimeFederatedCapabilityID,
		} {
			binding := declaredAuthRuntimeBinding(t, environment, capabilityID)
			for _, environmentKey := range binding.EndpointEnvironmentKeys {
				t.Setenv(environmentKey, value)
			}
			for _, environmentKey := range binding.SecretEnvironmentKeys {
				t.Setenv(environmentKey, value)
			}
		}
	}
}

func declaredAuthRuntimeBinding(
	t *testing.T,
	environment string,
	capabilityID string,
) usergenerated.ExternalProviderBinding {
	t.Helper()
	binding, found := usergenerated.ExternalProviderBindingFor(environment, capabilityID)
	if !found {
		t.Fatalf("环境 %s 缺少 %s 声明，打包期无可固化输入", environment, capabilityID)
	}
	return binding
}
