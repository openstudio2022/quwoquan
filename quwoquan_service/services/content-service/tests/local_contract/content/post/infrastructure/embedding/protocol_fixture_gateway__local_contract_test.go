package embedding_test

import (
	"context"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/embedding"
)

func TestGammaProtocolFixtureGatewayNeedsNoProviderMaterial(t *testing.T) {
	binding, found := contentgenerated.ExternalProviderBindingFor(
		"gamma",
		"content.embedding.generation",
	)
	if !found {
		t.Fatal("gamma embedding binding is missing")
	}
	if got := binding.AdapterID; got != ProtocolFixtureAdapterID {
		t.Fatalf("gamma embedding adapter = %q, want %q", got, ProtocolFixtureAdapterID)
	}
	if binding.EndpointRef != "" ||
		len(binding.EndpointEnvironmentKeys) != 0 ||
		len(binding.SecretEnvironmentKeys) != 0 {
		t.Fatalf("gamma fixture binding unexpectedly needs provider material: %#v", binding)
	}

	gateway, err := LoadEmbeddingGateway(
		"gamma",
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		t.Fatalf("LoadEmbeddingGateway() error = %v", err)
	}
	first, err := gateway.Embed(context.Background(), "本地 Gamma 向量输入")
	if err != nil {
		t.Fatalf("Embed() first error = %v", err)
	}
	second, err := gateway.Embed(context.Background(), "本地 Gamma 向量输入")
	if err != nil {
		t.Fatalf("Embed() second error = %v", err)
	}
	if len(first) == 0 || len(first) != len(second) {
		t.Fatalf("unexpected deterministic fixture vector lengths: %#v %#v", first, second)
	}
	for index := range first {
		if first[index] != second[index] {
			t.Fatalf("fixture vector differs at index %d: %#v %#v", index, first, second)
		}
	}
}

func TestProdOpenAIEmbeddingFailsClosedWithoutProviderMaterial(t *testing.T) {
	t.Setenv("CONTENT_EMBEDDING_ENDPOINT", "")
	t.Setenv(EmbeddingAPIKeyEnv, "")

	_, err := LoadEmbeddingGateway(
		"prod",
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err == nil {
		t.Fatal("LoadEmbeddingGateway() accepted missing prod provider material")
	}
	assertRequiredDependencyError(t, err)
}
