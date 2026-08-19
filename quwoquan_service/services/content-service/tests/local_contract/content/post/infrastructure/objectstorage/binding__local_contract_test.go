package objectstorage_test

import (
	"slices"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/objectstorage"
)

const objectStorageCapabilityID = "runtime.object.storage"

// 仓内源码树不固化任何环境：external_provider_governance.py 的多环境发射器只写出
// 恒 false 的 CompiledBindingFor，单环境实现由 stackctl package 的 provider binding
// overlay 在构建期覆盖写入。因此未打包树里 LoadBinding 在任何环境、任何材料组合下
// 都必须 fail closed——齐备材料同样救不回来，这是「环境在构建期固化」的可执行证据。
func TestLoadBindingFailsClosedWithoutCompiledEnvironmentBinding(t *testing.T) {
	if _, found := contentgenerated.CompiledBindingFor(objectStorageCapabilityID); found {
		t.Fatalf(
			"源码树编译进了环境绑定 capability=%s；环境只能由打包期 overlay 固化",
			objectStorageCapabilityID,
		)
	}
	materials := []struct {
		name   string
		config runtimeconfig.MapRuntimeConfigProvider
	}{
		{
			name:   "no material",
			config: runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}},
		},
		{
			name: "complete material",
			config: runtimeconfig.MapRuntimeConfigProvider{
				Values: map[string]string{
					"CONTENT_OSS_ENDPOINT":          "https://upload.gamma.quwoquan.com:19130",
					"CONTENT_OSS_ACCESS_KEY_ID":     "fixture-access",
					"CONTENT_OSS_ACCESS_KEY_SECRET": "fixture-secret",
					"CONTENT_CDN_SIGN_KEY":          "fixture-cdn-sign-key",
				},
			},
		},
	}
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		for _, material := range materials {
			_, err := LoadBinding(environment, material.config)
			if err == nil || !strings.Contains(err.Error(), "binding is unavailable") {
				t.Fatalf(
					"环境 %s（%s）未打包时必须 fail closed，got %v",
					environment,
					material.name,
					err,
				)
			}
		}
	}
}

// 多环境声明仍是治理与打包输入，overlay 从中挑出目标环境；它不再是运行时解析源。
// 非生产三环境固定绑定 MinIO 本地替身，prod 只绑定真实 S3 兼容对象存储——
// 断言取的是相等而非不等，因此「prod 不得落到本地替身」比原断言更强。
func TestObjectStorageDeclarationsIsolateNonprodSubstituteFromProdProvider(t *testing.T) {
	requiredSecretKeys := []string{
		"CONTENT_OSS_ACCESS_KEY_ID",
		"CONTENT_OSS_ACCESS_KEY_SECRET",
		"CONTENT_CDN_SIGN_KEY",
	}
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		expectedAdapter := MinIOAdapterID
		if environment == "prod" {
			expectedAdapter = S3CompatibleAdapterID
		}
		binding, found := contentgenerated.ExternalProviderBindingFor(
			environment,
			objectStorageCapabilityID,
		)
		if !found {
			t.Fatalf(
				"环境 %s 缺少 %s 声明，打包期无可固化输入",
				environment,
				objectStorageCapabilityID,
			)
		}
		if binding.State != "enabled" || binding.AdapterID != expectedAdapter ||
			binding.TimeoutMilliseconds <= 0 {
			t.Fatalf("环境 %s 的 object storage 声明漂移: %+v", environment, binding)
		}
		if binding.EndpointEnvironmentKeys["endpoint"] != "CONTENT_OSS_ENDPOINT" {
			t.Fatalf(
				"环境 %s 的 endpoint 材料键漂移: %+v",
				environment,
				binding.EndpointEnvironmentKeys,
			)
		}
		for _, environmentKey := range requiredSecretKeys {
			if !slices.Contains(binding.SecretEnvironmentKeys, environmentKey) {
				t.Fatalf("环境 %s 缺少 secret 材料键 %s", environment, environmentKey)
			}
		}
	}
}

// 纯守卫子句不依赖编译期绑定，未打包树里同样必须 fail closed。
func TestLoadBindingRequiresRuntimeConfigProvider(t *testing.T) {
	if _, err := LoadBinding("gamma", nil); err == nil ||
		!strings.Contains(err.Error(), "no runtime config provider") {
		t.Fatalf("missing config provider must fail closed, got %v", err)
	}
}
