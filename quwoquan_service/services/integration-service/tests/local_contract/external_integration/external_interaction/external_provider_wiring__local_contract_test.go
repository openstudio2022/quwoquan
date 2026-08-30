package local_contract

import (
	"slices"
	"strings"
	"testing"

	platformconfig "quwoquan_service/runtime/config"
	integrationconfig "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/runtimeconfig"
)

// 未打包源码树不固化任何环境，MaterializeReleaseExternalInteractionBindings 因此
// 在四环境、任何材料组合下都必须 fail closed：材料齐备也不能替代打包期 overlay 写入
// 的单环境绑定。「材料齐备则启用真实 Provider」的正向物化断言已迁移到打包期
// overlay 契约层（compiled-external-provider-bindings.single-environment）。
func TestMaterializeReleaseBindingsFailClosedWithoutCompiledEnvironmentBinding(
	t *testing.T,
) {
	completeProdMaterials := platformconfig.MapRuntimeConfigProvider{Values: map[string]string{
		"INTEGRATION_SMS_ENDPOINT":                  "https://sms.example.com",
		"INTEGRATION_SMS_TOKEN":                     "token",
		"OTP_CODE_REF_KEYS_JSON":                    `{"active":"test-key"}`,
		"INTEGRATION_SERVICE_MTLS_CA_FILE":          "/run/secrets/sms-ca.pem",
		"INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE": "/run/secrets/sms-client.pem",
		"INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE":  "/run/secrets/sms-client-key.pem",
		"INTEGRATION_PUSH_USER_SERVICE_BASE_URL":    "http://user-service:18081",
		"INTEGRATION_PUSH_APNS_ENVIRONMENT":         "production",
		"INTEGRATION_PUSH_APNS_KEY_ID":              "APNSKEY01",
		"INTEGRATION_PUSH_APNS_TEAM_ID":             "TEAM000001",
		"INTEGRATION_PUSH_APNS_TOPIC":               "com.quwoquan.app.voip",
		"INTEGRATION_PUSH_FCM_PROJECT_ID":           "quwoquan-gamma",
		"INTEGRATION_PUSH_APNS_KEY_FILE":            "/run/secrets/apns-key.p8",
		"INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE": "/run/secrets/fcm.json",
	}}
	completeSubstituteMaterials := platformconfig.MapRuntimeConfigProvider{
		Values: map[string]string{
			"INTEGRATION_SMS_ENDPOINT":             "https://sms-provider-substitute:9443/v1/provider/sms/send",
			"INTEGRATION_SMS_TOKEN":                "target-token",
			"INTEGRATION_SMS_SUBSTITUTE_CA_FILE":   "/run/secrets/sms-provider-substitute/ca.crt",
			"INTEGRATION_PUSH_SUBSTITUTE_ENDPOINT": "https://provider-protocol-substitute:18089/push/send",
		},
	}
	materials := []struct {
		name   string
		config platformconfig.MapRuntimeConfigProvider
	}{
		{
			name:   "no material",
			config: platformconfig.MapRuntimeConfigProvider{Values: map[string]string{}},
		},
		{name: "complete real provider material", config: completeProdMaterials},
		{name: "complete substitute material", config: completeSubstituteMaterials},
	}
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		// 预置为已启用，用来证明 fail closed 返回零值配置，而不是把入参原样透传。
		cfg := integrationconfig.Config{}
		cfg.Environment = environment
		cfg.Integration.ExternalInteraction.SMS.Enabled = true
		cfg.Integration.ExternalInteraction.Push.Enabled = true
		for _, material := range materials {
			resolved, err := integrationconfig.MaterializeReleaseExternalInteractionBindings(
				cfg,
				material.config,
			)
			if err == nil || !strings.Contains(err.Error(), "binding is missing") {
				t.Fatalf(
					"环境 %s（%s）未打包时必须 fail closed，got %v",
					environment,
					material.name,
					err,
				)
			}
			if resolved.Integration.ExternalInteraction.SMS.Enabled ||
				resolved.Integration.ExternalInteraction.Push.Enabled {
				t.Fatalf(
					"环境 %s（%s）fail closed 时不得返回已启用的 Provider 配置: %#v",
					environment,
					material.name,
					resolved.Integration.ExternalInteraction,
				)
			}
		}
	}
}

// 纯守卫子句不依赖编译期绑定：缺 runtime config provider 必须 fail closed。
func TestMaterializeReleaseBindingsRequiresRuntimeConfigProvider(t *testing.T) {
	prodConfig := integrationconfig.Config{}
	prodConfig.Environment = "prod"
	if _, err := integrationconfig.MaterializeReleaseExternalInteractionBindings(
		prodConfig,
		nil,
	); err == nil || !strings.Contains(err.Error(), "no runtime config provider") {
		t.Fatalf("missing config provider must fail closed, got %v", err)
	}
}

// 声明层拥有「哪个环境选哪个 adapter」：非生产三环境的 SMS 声明必须是本地捕获替身
// （它就是 Config.Provider 的取值来源），Push 声明必须是协议替身（它决定
// Config.Push.Mode 走 protocol_substitute 分支）。prod 反向只声明真实 Provider。
func TestLocalCaptureSMSBindingIsSelectedByEachNonprodEnvironment(t *testing.T) {
	for _, environment := range []string{"alpha", "beta", "gamma"} {
		sms := declaredExternalInteractionBinding(
			t,
			environment,
			externalInteractionSMSCapabilityID,
		)
		if sms.State != "enabled" || sms.AdapterID != "ext.sms.local_capture" {
			t.Fatalf("%s Config.Provider 的声明来源必须是本地捕获替身: %+v", environment, sms)
		}
		push := declaredExternalInteractionBinding(
			t,
			environment,
			externalInteractionPushCapabilityID,
		)
		if push.State != "enabled" ||
			push.AdapterID != "ext.push.protocol_substitute" {
			t.Fatalf("%s Push 声明必须选中协议替身模式: %+v", environment, push)
		}
		if push.EndpointEnvironmentKeys["endpoint"] !=
			"INTEGRATION_PUSH_SUBSTITUTE_ENDPOINT" {
			t.Fatalf("%s Push 替身 endpoint 材料键漂移: %+v", environment, push)
		}
	}

	prodSMS := declaredExternalInteractionBinding(
		t,
		"prod",
		externalInteractionSMSCapabilityID,
	)
	if prodSMS.AdapterID == "ext.sms.local_capture" {
		t.Fatalf("prod 不得声明本地捕获 SMS 替身: %+v", prodSMS)
	}
	prodPush := declaredExternalInteractionBinding(
		t,
		"prod",
		externalInteractionPushCapabilityID,
	)
	if prodPush.AdapterID == "ext.push.protocol_substitute" {
		t.Fatalf("prod 不得声明协议替身 Push: %+v", prodPush)
	}
}

// 物化真实 Provider 所需的材料键闭包由 prod 声明拥有：这些角色/密钥名一旦漂移，
// 打包期固化出来的单环境绑定就无法喂满 Config，因此在声明层直接钉住。
func TestProdReleaseBindingDeclarationsCarryRealProviderMaterialClosure(t *testing.T) {
	sms := declaredExternalInteractionBinding(
		t,
		"prod",
		externalInteractionSMSCapabilityID,
	)
	if sms.EndpointEnvironmentKeys["endpoint"] != "INTEGRATION_SMS_ENDPOINT" {
		t.Fatalf("prod SMS endpoint 材料键漂移: %+v", sms.EndpointEnvironmentKeys)
	}
	if !slices.Contains(sms.SecretEnvironmentKeys, "INTEGRATION_SMS_TOKEN") {
		t.Fatalf("prod SMS 缺少 bearer token 材料键: %+v", sms.SecretEnvironmentKeys)
	}

	push := declaredExternalInteractionBinding(
		t,
		"prod",
		externalInteractionPushCapabilityID,
	)
	for role, environmentKey := range map[string]string{
		"user_service_base_url": "INTEGRATION_PUSH_USER_SERVICE_BASE_URL",
		"apns_environment":      "INTEGRATION_PUSH_APNS_ENVIRONMENT",
		"apns_key_id":           "INTEGRATION_PUSH_APNS_KEY_ID",
		"apns_team_id":          "INTEGRATION_PUSH_APNS_TEAM_ID",
		"apns_topic":            "INTEGRATION_PUSH_APNS_TOPIC",
		"fcm_project_id":        "INTEGRATION_PUSH_FCM_PROJECT_ID",
	} {
		if push.EndpointEnvironmentKeys[role] != environmentKey {
			t.Fatalf(
				"prod Push 角色 %s 的材料键漂移: got %q, want %q",
				role,
				push.EndpointEnvironmentKeys[role],
				environmentKey,
			)
		}
	}
	for _, environmentKey := range []string{
		"INTEGRATION_PUSH_APNS_KEY_FILE",
		"INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE",
	} {
		if !slices.Contains(push.SecretEnvironmentKeys, environmentKey) {
			t.Fatalf("prod Push 缺少凭据材料键 %s", environmentKey)
		}
	}
}
