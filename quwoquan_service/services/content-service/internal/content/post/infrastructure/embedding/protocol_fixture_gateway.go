package embedding

import (
	runtimeconfig "quwoquan_service/runtime/config"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	embeddingapp "quwoquan_service/services/content-service/internal/content/post/application/embedding"
)

// LoadEmbeddingGateway materializes the compiler-selected embedding adapter.
func LoadEmbeddingGateway(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
) (embeddingapp.EmbeddingGateway, error) {
	if configProvider == nil {
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"embedding binding has no runtime config provider",
		)
	}
	descriptor, found := contentgenerated.ExternalProviderBindingFor(
		appEnv,
		embeddingCapabilityID,
	)
	if !found || descriptor.State != "enabled" {
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"embedding binding is unavailable for the current environment",
		)
	}
	switch descriptor.AdapterID {
	case OpenAICompatibleAdapterID:
		binding, err := LoadOpenAICompatibleBinding(appEnv, configProvider)
		if err != nil {
			return nil, err
		}
		return NewOpenAICompatibleGateway(binding)
	default:
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"embedding binding selects an unsupported adapter",
		)
	}
}
