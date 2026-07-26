package embedding_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/application/embedding"
	"testing"
)

type gatewayStub struct{}

func (gatewayStub) Embed(_ context.Context, _ string) (Vector, error) {
	return Vector{0.1, 0.2}, nil
}

func (gatewayStub) EmbedBatch(_ context.Context, texts []string) ([]Vector, error) {
	vectors := make([]Vector, 0, len(texts))
	for range texts {
		vectors = append(vectors, Vector{0.1, 0.2})
	}
	return vectors, nil
}

var _ EmbeddingGateway = gatewayStub{}

func TestEmbeddingGatewayUsesContentOwnedTypedVectors(t *testing.T) {
	var gateway EmbeddingGateway = gatewayStub{}

	vector, err := gateway.Embed(context.Background(), "内容语义输入")
	if err != nil {
		t.Fatalf("Embed() error = %v", err)
	}
	if len(vector) != 2 || vector[0] != 0.1 || vector[1] != 0.2 {
		t.Fatalf("Embed() vector = %#v", vector)
	}
}
