package local_contract

import (
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	integrationgenerated "quwoquan_service/services/integration-service/generated/external_integration/external_interaction"
	. "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/providerbinding"
)

const (
	externalInteractionSMSCapabilityID  = "identity.sms.otp"
	externalInteractionPushCapabilityID = "integration.push.delivery"
)

// 环境隔离由多环境声明拥有：非生产三环境只声明本地捕获 SMS 与协议替身 Push，
// prod 只声明真实运营商 Provider。断言取相等而非不等，因此「prod 不得落到替身」
// 与「非生产不得落到真实 Provider」两个方向都被钉住。
func TestExternalInteractionBindingsSelectLocalCaptureOnlyInNonprod(t *testing.T) {
	for _, environment := range []string{"alpha", "beta", "gamma"} {
		sms := declaredExternalInteractionBinding(
			t,
			environment,
			externalInteractionSMSCapabilityID,
		)
		if sms.State != "enabled" || sms.AdapterID != SMSAdapterLocalCapture {
			t.Fatalf("%s SMS 声明必须是本地捕获替身: %+v", environment, sms)
		}
		if len(sms.EndpointEnvironmentKeys) != 1 || len(sms.SecretEnvironmentKeys) == 0 ||
			sms.TimeoutMilliseconds <= 0 {
			t.Fatalf("%s SMS 声明材料键不完整: %+v", environment, sms)
		}

		push := declaredExternalInteractionBinding(
			t,
			environment,
			externalInteractionPushCapabilityID,
		)
		if push.State != "enabled" || push.AdapterID != PushAdapterProtocolSubstitute {
			t.Fatalf("%s Push 声明必须是协议替身: %+v", environment, push)
		}
		if len(push.EndpointEnvironmentKeys) != 1 || len(push.SecretEnvironmentKeys) != 0 ||
			push.TimeoutMilliseconds <= 0 {
			t.Fatalf("%s Push 声明材料键不完整: %+v", environment, push)
		}
	}

	prodSMS := declaredExternalInteractionBinding(
		t,
		"prod",
		externalInteractionSMSCapabilityID,
	)
	if prodSMS.State != "enabled" || prodSMS.AdapterID != SMSAdapterAliyun {
		t.Fatalf("prod SMS 声明必须是真实运营商 Provider: %+v", prodSMS)
	}
	prodPush := declaredExternalInteractionBinding(
		t,
		"prod",
		externalInteractionPushCapabilityID,
	)
	if prodPush.State != "enabled" || prodPush.AdapterID != PushAdapterDispatch {
		t.Fatalf("prod Push 声明必须是真实分发 Provider: %+v", prodPush)
	}
}

// 未打包源码树不固化任何环境：多环境发射器只写出恒 false 的 CompiledBindingFor，
// 单环境实现由 stackctl package 的 provider binding overlay 在构建期覆盖写入。
// 因此每个 capability 在任何环境、任何材料组合下都必须 fail closed。
func TestExternalInteractionResolutionFailsClosedWithoutCompiledEnvironmentBinding(
	t *testing.T,
) {
	completeMaterials := runtimeconfig.MapRuntimeConfigProvider{
		Values: map[string]string{
			"INTEGRATION_SMS_ENDPOINT":                  "https://sms-provider-substitute:9443/v1/provider/sms/send",
			"INTEGRATION_SMS_TOKEN":                     "test-token",
			"OTP_CODE_REF_KEYS_JSON":                    "test-code-ref-key",
			"INTEGRATION_SERVICE_MTLS_CA_FILE":          "/test/ca.pem",
			"INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE": "/test/client.pem",
			"INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE":  "/test/client.key",
			"INTEGRATION_PUSH_SUBSTITUTE_ENDPOINT":      "https://provider-protocol-substitute:18089/push/send",
			"INTEGRATION_PUSH_USER_SERVICE_BASE_URL":    "https://user.example.test",
			"INTEGRATION_PUSH_APNS_ENVIRONMENT":         "sandbox",
			"INTEGRATION_PUSH_APNS_KEY_ID":              "test-key-id",
			"INTEGRATION_PUSH_APNS_TEAM_ID":             "test-team-id",
			"INTEGRATION_PUSH_APNS_TOPIC":               "com.example.app.voip",
			"INTEGRATION_PUSH_FCM_PROJECT_ID":           "test-project",
			"INTEGRATION_PUSH_APNS_KEY_FILE":            "/test/AuthKey.p8",
			"INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE": "/test/fcm.json",
		},
	}
	for _, capabilityID := range []string{
		externalInteractionSMSCapabilityID,
		externalInteractionPushCapabilityID,
	} {
		if _, found := integrationgenerated.CompiledBindingFor(capabilityID); found {
			t.Fatalf(
				"源码树编译进了环境绑定 capability=%s；环境只能由打包期 overlay 固化",
				capabilityID,
			)
		}
	}

	resolvers := []struct {
		capabilityID string
		resolve      func(
			string,
			runtimeconfig.RuntimeConfigProvider,
		) (ExternalInteractionBinding, error)
	}{
		{capabilityID: externalInteractionSMSCapabilityID, resolve: ResolveSMSBinding},
		{capabilityID: externalInteractionPushCapabilityID, resolve: ResolvePushBinding},
	}
	materials := []struct {
		name   string
		config runtimeconfig.MapRuntimeConfigProvider
	}{
		{
			name:   "no material",
			config: runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}},
		},
		{name: "complete material", config: completeMaterials},
	}
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		for _, resolver := range resolvers {
			for _, material := range materials {
				_, err := resolver.resolve(environment, material.config)
				if err == nil || !strings.Contains(err.Error(), "binding is missing") {
					t.Fatalf(
						"%s/%s（%s）未打包时必须 fail closed，got %v",
						environment,
						resolver.capabilityID,
						material.name,
						err,
					)
				}
			}
		}
	}
}

// 材料读取器把「键不存在」与「键存在但只有空白」当成同一件事：空白 endpoint
// 或空白 token 一旦被当成在场，composition root 就会带着无效凭据启动。
func TestExternalInteractionBindingTreatsBlankMaterialAsAbsent(t *testing.T) {
	binding := ExternalInteractionBinding{
		Endpoints: map[string]string{
			"endpoint":              "https://sms-provider-substitute:9443/v1/provider/sms/send",
			"user_service_base_url": "   ",
		},
		Secrets: map[string]string{
			"INTEGRATION_SMS_TOKEN":          "target-scoped-provider-token",
			"INTEGRATION_PUSH_APNS_KEY_FILE": "\t\n",
		},
	}

	if value, ok := binding.Endpoint("endpoint"); !ok ||
		value != "https://sms-provider-substitute:9443/v1/provider/sms/send" {
		t.Fatalf("present endpoint material must be readable: value=%q ok=%v", value, ok)
	}
	if _, ok := binding.Endpoint("user_service_base_url"); ok {
		t.Fatal("blank endpoint material must be reported as absent")
	}
	if _, ok := binding.Endpoint("apns_topic"); ok {
		t.Fatal("undeclared endpoint role must be reported as absent")
	}
	if value, ok := binding.Secret("INTEGRATION_SMS_TOKEN"); !ok ||
		value != "target-scoped-provider-token" {
		t.Fatalf("present secret material must be readable: ok=%v", ok)
	}
	if _, ok := binding.Secret("INTEGRATION_PUSH_APNS_KEY_FILE"); ok {
		t.Fatal("blank secret material must be reported as absent")
	}
	if _, ok := binding.Secret("INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE"); ok {
		t.Fatal("undeclared secret key must be reported as absent")
	}
}

// 纯守卫子句不依赖编译期绑定，未打包树里同样必须 fail closed。
func TestExternalInteractionResolutionRequiresRuntimeConfigProvider(t *testing.T) {
	if _, err := ResolveSMSBinding("prod", nil); err == nil ||
		!strings.Contains(err.Error(), "no runtime config provider") {
		t.Fatalf("SMS missing config provider must fail closed, got %v", err)
	}
	if _, err := ResolvePushBinding("prod", nil); err == nil ||
		!strings.Contains(err.Error(), "no runtime config provider") {
		t.Fatalf("Push missing config provider must fail closed, got %v", err)
	}
}

func declaredExternalInteractionBinding(
	t *testing.T,
	environment string,
	capabilityID string,
) integrationgenerated.ExternalProviderBinding {
	t.Helper()
	binding, found := integrationgenerated.ExternalProviderBindingFor(
		environment,
		capabilityID,
	)
	if !found {
		t.Fatalf("环境 %s 缺少 %s 声明，打包期无可固化输入", environment, capabilityID)
	}
	return binding
}
