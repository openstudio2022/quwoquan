package embedding

import (
	"context"
	"crypto/sha256"
	"encoding/binary"

	embeddingapp "quwoquan_service/services/content-service/internal/content/post/application/embedding"
	runtimeconfig "quwoquan_service/runtime/config"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
)

const protocolFixtureDimensions = 8

// ProtocolFixtureGateway is the non-prod Port-equivalent embedding substitute.
// It returns deterministic vectors without contacting a vendor.
type ProtocolFixtureGateway struct{}

func NewProtocolFixtureGateway() embeddingapp.EmbeddingGateway {
	return ProtocolFixtureGateway{}
}

func (ProtocolFixtureGateway) Embed(ctx context.Context, text string) (embeddingapp.Vector, error) {
	vectors, err := ProtocolFixtureGateway{}.EmbedBatch(ctx, []string{text})
	if err != nil {
		return nil, err
	}
	return vectors[0], nil
}

func (ProtocolFixtureGateway) EmbedBatch(
	_ context.Context,
	texts []string,
) ([]embeddingapp.Vector, error) {
	out := make([]embeddingapp.Vector, len(texts))
	for index, text := range texts {
		out[index] = deterministicVector(text)
	}
	return out, nil
}

func deterministicVector(text string) embeddingapp.Vector {
	digest := sha256.Sum256([]byte(text))
	vector := make(embeddingapp.Vector, protocolFixtureDimensions)
	for i := 0; i < protocolFixtureDimensions; i++ {
		raw := binary.BigEndian.Uint32(digest[(i*4)%len(digest) : (i*4)%len(digest)+4])
		vector[i] = float64(raw%1000) / 1000.0
	}
	return vector
}

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
	case ProtocolFixtureAdapterID:
		return NewProtocolFixtureGateway(), nil
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
