package local_contract

import (
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/providerbinding"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

// 仓内源码树不固化任何环境：external_provider_governance.py 的多环境发射器只写出
// 恒 false 的 CompiledBindingFor，单环境实现由 stackctl package 的 provider binding
// overlay 在构建期覆盖写入。因此未打包树里 Resolve 对任何 capability 都必须 fail
// closed —— 这正是「环境在构建期固化、运行时不做动态适配」的可执行证据。
func TestResolveFailsClosedWithoutCompiledEnvironmentBinding(t *testing.T) {
	config := runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}}

	if _, err := Resolve("unknown", "assistant.model.generation", config); err == nil {
		t.Fatal("unknown binding must fail closed")
	}

	for _, capabilityID := range []string{
		"assistant.model.generation",
		"assistant.public.search",
	} {
		if _, found := assistantgenerated.CompiledBindingFor(capabilityID); found {
			t.Fatalf(
				"源码树编译进了环境绑定 capability=%s；环境只能由打包期 overlay 固化",
				capabilityID,
			)
		}
		_, err := Resolve("prod", capabilityID, config)
		if err == nil || !strings.Contains(err.Error(), "binding is missing") {
			t.Fatalf("uncompiled binding error = %v", err)
		}
	}
}

// 多环境声明仍是治理与打包输入，overlay 从中挑出目标环境；它不再是运行时解析源。
func TestMultiEnvironmentDeclarationsRemainPackagingInputOnly(t *testing.T) {
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		binding, found := assistantgenerated.ExternalProviderBindingFor(
			environment,
			"assistant.model.generation",
		)
		if !found {
			t.Fatalf("环境 %s 缺少 assistant.model.generation 声明，打包期无可固化输入", environment)
		}
		if strings.TrimSpace(binding.AdapterID) == "" || binding.TimeoutMilliseconds <= 0 {
			t.Fatalf("环境 %s 的声明不完整: %+v", environment, binding)
		}
	}
}

func TestResolveRequiresRuntimeConfigProvider(t *testing.T) {
	if _, err := Resolve("prod", "assistant.model.generation", nil); err == nil ||
		!strings.Contains(err.Error(), "no runtime config provider") {
		t.Fatalf("missing config provider must fail closed, got %v", err)
	}
}
