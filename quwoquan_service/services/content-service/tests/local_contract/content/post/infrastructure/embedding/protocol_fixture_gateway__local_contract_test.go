package embedding_test

import (
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/embedding"
)

func TestEveryEnvironmentEmbeddingFailsClosedWithoutProviderMaterial(t *testing.T) {
	t.Setenv("CONTENT_EMBEDDING_ENDPOINT", "")
	t.Setenv(EmbeddingAPIKeyEnv, "")
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		t.Run(environment, func(t *testing.T) {
			binding, found := contentgenerated.ExternalProviderBindingFor(
				environment,
				"content.embedding.generation",
			)
			if !found || binding.AdapterID != OpenAICompatibleAdapterID {
				t.Fatalf("embedding binding is not canonical: %#v", binding)
			}
			_, err := LoadEmbeddingGateway(
				environment,
				runtimeconfig.EnvRuntimeConfigProvider{},
			)
			if err == nil {
				t.Fatal("LoadEmbeddingGateway() accepted missing provider material")
			}
			assertRequiredDependencyError(t, err)
		})
	}
}
