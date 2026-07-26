package embedding

import "context"

// Vector 表示单个内容输入生成的向量。
type Vector []float64

// EmbeddingGateway 是 content 生成语义向量的强类型边界。
// 供应商 endpoint、凭据、HTTP client 与 wire DTO 仅属于 infrastructure adapter。
type EmbeddingGateway interface {
	Embed(ctx context.Context, text string) (Vector, error)
	EmbedBatch(ctx context.Context, texts []string) ([]Vector, error)
}
